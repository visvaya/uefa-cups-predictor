import argparse
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from csv_safety import neutralize_formulas

from .fetcher import DEFAULT_USER_AGENT, SoccerRatingFetcher, resolve_url
from .models import ClubCup, ClubMeta, OddsDevelopment, PayloadSource, TodayMatch
from .parsers import (
    parse_clip_payloads,
    parse_club_page,
    parse_team_ratings,
    parse_today_prediction,
    payload_to_odds_development,
    payload_to_odds_row,
    pick_best_payload,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MINUTES_PER_DAY = 24 * 60
# A kickoff more than this many minutes in the past is treated as the next day's (after midnight)
PAST_KICKOFF_ROLLOVER_MINUTES = 12 * 60
RE_KICKOFF_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")
# Kept by --skip-cups: Champions League, Europa League and Conference League (codes as soccer-rating.com uses them)
UEFA_CLUB_CUPS = frozenset({"CLCUP", "ELCUP", "ECLCUP"})


def local_now() -> datetime:
    """Current time as an aware datetime in the machine's local timezone."""
    return datetime.now().astimezone()


def minutes_until_kickoff(time_local: str, now: datetime) -> float:
    """Returns minutes from `now` to an "HH:MM" kickoff in the same timezone as `now`.

    Kickoffs far in the past roll over to the next day (late-night fixtures).
    Raises ValueError when `time_local` is not a valid HH:MM time.
    """
    hm = RE_KICKOFF_TIME.match(time_local)
    if hm is None:
        raise ValueError(f"expected HH:MM, got {time_local!r}")
    kickoff = now.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0)
    diff_min = (kickoff - now).total_seconds() / 60.0
    if diff_min < -PAST_KICKOFF_ROLLOVER_MINUTES:
        diff_min += MINUTES_PER_DAY
    return diff_min


def validate_matches(matches: list[TodayMatch]) -> set[str]:
    """Logs duplicate match ids and missing league codes; returns the unique match ids."""
    match_ids = [m.match_id for m in matches]
    unique_ids = set(match_ids)
    if len(match_ids) != len(unique_ids):
        logger.error(f"Validation FAILED: Found {len(match_ids) - len(unique_ids)} duplicate match_ids!")
    else:
        logger.info(f"Validation OK: No duplicate match_ids ({len(unique_ids)} unique).")

    # Unknown leagues are expected in all leagues mode; only an empty code is suspicious
    invalid_leagues = [m.league_code for m in matches if not m.league_code]
    if invalid_leagues:
        logger.error(f"Validation FAILED: Found {len(invalid_leagues)} matches with missing league codes!")
    else:
        logger.info(f"Validation OK: League codes extracted for all {len(matches)} matches.")
    return unique_ids


def validate_results(matches: list[TodayMatch], all_odds_dev: list[OddsDevelopment]) -> None:
    logger.info("--- Validation Report ---")
    unique_ids = validate_matches(matches)

    matched_ids = {d.match_id for d in all_odds_dev}
    coverage = len(matched_ids) / len(unique_ids) if unique_ids else 0
    logger.info(f"Payload Coverage: {coverage:.1%} ({len(matched_ids)}/{len(unique_ids)})")
    if coverage < 1.0:
        missing = unique_ids - matched_ids
        logger.warning(f"Missing payloads for {len(missing)} matches: {list(missing)}")

    low_conf = [d for d in all_odds_dev if d.match_confidence == "LOW"]
    if low_conf:
        logger.warning(f"Quality Alert: Found {len(low_conf)} LOW confidence matches!")
    else:
        logger.info("Quality OK: No LOW confidence matches found.")

    logger.info("--------------------------")


TODAY_PAGE = "today-prediction.html"
# Columns written first, in this order; the rest follow in model order
ODDS_ID_COLUMNS = ("match_id", "snapshot_date", "home_id", "away_id", "league_code", "source_url")
CLUB_COLUMNS = ("team_id", "team_name", "rating_total", "rating_home", "rating_away")

# One side of a match: team id, team name and the link to its club page
Side = tuple[int, str, str]
# Reads the club page of a side; None (after logging why) when it is not available
ClubPageReader = Callable[[Side], str | None]


@dataclass(frozen=True)
class MatchFilters:
    all_leagues: bool
    min_start: int | None
    max_start: int | None
    skip_cups: bool


@dataclass(frozen=True)
class MatchScan:
    """What the club pages of one match gave: payload candidates, team ratings (H/A), club data and cups."""

    candidates: list[dict[str, Any]]
    team_ratings: tuple[float | None, float | None]
    clubs: dict[int, ClubMeta]
    cups: list[ClubCup]


@dataclass(frozen=True)
class ScrapeResult:
    odds_development: list[OddsDevelopment]
    clubs: dict[int, ClubMeta]
    cups: list[ClubCup]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soccer-Rating ETL Scraper CLI")
    parser.add_argument("--local", action="store_true", help="Use local files for testing")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of matches to process")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds")
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="User-Agent header (default: names this tool and its repository)",
    )
    parser.add_argument("--output-dir", type=str, default="data/soccer-rating", help="Output directory")
    parser.add_argument("--all-leagues", action="store_true", help="Capture matches from ALL leagues, not just CL/EL")
    parser.add_argument(
        "--separate-snapshots", action="store_true", help="Save match odds to separate daily snapshot files"
    )
    parser.add_argument(
        "--min-start", type=int, default=None, help="Process matches starting at least N minutes from now"
    )
    parser.add_argument(
        "--max-start", type=int, default=None, help="Process matches starting at most N minutes from now"
    )
    parser.add_argument(
        "--skip-cups",
        action="store_true",
        help="Skip cup matches (league code contains 'CUP', e.g. FACUP) except CLCUP, ELCUP and ECLCUP",
    )
    return parser.parse_args()


def read_today_page(local: bool, fetch: Callable[[str], str | None]) -> str | None:
    if local:
        logger.info("Running in LOCAL mode.")
        if not Path(TODAY_PAGE).exists():
            logger.error(f"{TODAY_PAGE} not found.")
            return None
        html: str | None = Path(TODAY_PAGE).read_text(encoding="utf-8")
    else:
        html = fetch("/today-prediction")
    if not html:
        logger.error("Failed to get today predictions.")
        return None
    return html


def in_time_window(
    matches: list[TodayMatch], now: datetime, min_start: int | None, max_start: int | None
) -> list[TodayMatch]:
    """Matches kicking off between `min_start` and `max_start` minutes after `now`; unreadable times are dropped."""
    kept = []
    for m in matches:
        # Assumes the site shows kickoff times in the machine's local timezone
        try:
            diff_min = minutes_until_kickoff(m.time_local, now)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse time {m.time_local} for {m.match_id}: {e}")
            continue
        if (min_start is None or diff_min >= min_start) and (max_start is None or diff_min <= max_start):
            kept.append(m)
    return kept


def is_skipped_cup(league_code: str) -> bool:
    """A cup code (it contains 'CUP') other than the UEFA club competitions this project analyses."""
    return "CUP" in league_code and league_code not in UEFA_CLUB_CUPS


def without_cups(matches: list[TodayMatch]) -> tuple[list[TodayMatch], set[str]]:
    """Drops cup matches except UEFA club competitions; returns the kept matches and the skipped codes."""
    kept = [m for m in matches if not is_skipped_cup(m.league_code or "")]
    return kept, {m.league_code for m in matches if is_skipped_cup(m.league_code or "")}


def select_matches(filters: MatchFilters, today_html: str, snapshot_date: str, now: datetime) -> list[TodayMatch]:
    matches = parse_today_prediction(today_html, snapshot_date, all_leagues=filters.all_leagues)
    logger.info(f"Loaded {len(matches)} total matches (all matching leagues).")

    if filters.min_start is not None or filters.max_start is not None:
        filtered = in_time_window(matches, now, filters.min_start, filters.max_start)
        logger.info(f"Filtered matches: {len(filtered)} (from {len(matches)}) based on time window.")
        matches = filtered

    if filters.skip_cups:
        kept, skipped_codes = without_cups(matches)
        if len(kept) < len(matches):
            logger.info(f"Filtered out {len(matches) - len(kept)} cup matches. Skipped codes: {sorted(skipped_codes)}")
        matches = kept
    return matches


def club_page_or_warning(club_html: str | None, side: Side) -> str | None:
    """The page, or None with a warning when it is missing or empty."""
    if not club_html:
        team_id, team_name, _ = side
        logger.warning(f"Could not fetch club page for {team_name} ({team_id}).")
        return None
    return club_html


def read_local_club_page(side: Side) -> str | None:
    """A club page from the current directory: `<Team-Name>.html` (a few slug variants) or the generic `club.html`."""
    team_name = side[1]
    slug_variants = [
        team_name.replace(" ", "-"),
        team_name.replace(" ", "-").lower(),
        team_name.replace(" ", "_"),
        team_name.lower().replace(" ", "-"),
    ]
    local_candidates = [Path(f"{s}.html") for s in slug_variants] + [Path("club.html")]
    html_path = next((p for p in local_candidates if p.exists()), None)
    if html_path is None:
        logger.warning(f"No local file for {team_name}, skipping.")
        return None
    logger.info(f"Using local file {html_path} for {team_name}")
    return club_page_or_warning(html_path.read_text(encoding="utf-8"), side)


def remote_club_page_reader(fetch: Callable[[str], str | None], delay_s: float) -> ClubPageReader:
    def read(side: Side) -> str | None:
        time.sleep(delay_s)
        return club_page_or_warning(fetch(side[2]), side)

    return read


def remote_source_url(href: str) -> str:
    """The absolute URL of a club page link (the link itself when it leaves the site)."""
    return resolve_url(href) or href


def local_source_url(href: str) -> str:
    return href


def club_page_candidates(club_html: str, href: str) -> list[dict[str, Any]]:
    """Odds payloads of a club page as rows for `pick_best_payload`, with the raw parts and the page link."""
    rows = [(payload_to_odds_row(parts), parts) for parts in parse_clip_payloads(club_html)]
    return [{**row, "_raw_parts": parts, "_source_href": href} for row, parts in rows if row]


def scan_club_pages(match: TodayMatch, read_page: ClubPageReader) -> MatchScan:
    """Reads the home, then the away club page; stops at the first page with payload candidates."""
    team_ratings: tuple[float | None, float | None] = (None, None)
    clubs: dict[int, ClubMeta] = {}
    cups: list[ClubCup] = []
    sides = [(match.home_id, match.home_team, match.home_href), (match.away_id, match.away_team, match.away_href)]
    for side in sides:
        club_html = read_page(side)
        if not club_html:
            continue
        team_id, _, href = side
        tr_h, tr_a = parse_team_ratings(club_html)
        if tr_h and tr_a:
            team_ratings = (tr_h, tr_a)
        meta, club_cups = parse_club_page(club_html, team_id)
        clubs[team_id] = meta
        cups.extend(club_cups)
        candidates = club_page_candidates(club_html, href)
        # The payload of a match is on both club pages; the opponent's page would only repeat it
        if candidates:
            return MatchScan(candidates, team_ratings, clubs, cups)
    return MatchScan([], team_ratings, clubs, cups)


def best_odds_development(
    match: TodayMatch, scan: MatchScan, source_url: Callable[[str], str]
) -> OddsDevelopment | None:
    best_row, debug = pick_best_payload(match.__dict__, scan.candidates)
    if not best_row:
        logger.warning(f"No matching odds payload discovered for {match.match_id}")
        return None
    source = PayloadSource(
        source_url=source_url(best_row["_source_href"]),
        team_rating_home=scan.team_ratings[0],
        team_rating_away=scan.team_ratings[1],
    )
    dev = payload_to_odds_development(best_row["_raw_parts"], match, source, debug)
    if dev:
        logger.info(
            f"Matched {match.match_id} (conf={debug['match_confidence']}, "
            f"stage={debug['matched_odds_stage']}, dist={debug['odds_distance']:.4f})"
        )
        if debug["match_confidence"] == "LOW":
            logger.warning(f"Low confidence match for {match.match_id}")
    return dev


def scrape_matches(
    matches: list[TodayMatch], limit: int | None, read_page: ClubPageReader, source_url: Callable[[str], str]
) -> ScrapeResult:
    odds_development = []
    clubs: dict[int, ClubMeta] = {}
    cups: list[ClubCup] = []
    for match in matches[: max(limit, 0)] if limit else matches:
        logger.info(f"Processing Match: {match.home_team} vs {match.away_team} ({match.match_id})")
        # Every team gets a row, even when its club page is not read
        for tid, tname in [(match.home_id, match.home_team), (match.away_id, match.away_team)]:
            clubs.setdefault(
                tid, ClubMeta(team_id=tid, team_name=tname, rating_total=None, rating_home=None, rating_away=None)
            )
        scan = scan_club_pages(match, read_page)
        clubs.update(scan.clubs)
        cups.extend(scan.cups)
        dev = best_odds_development(match, scan, source_url)
        if dev:
            odds_development.append(dev)
    return ScrapeResult(odds_development, clubs, cups)


def save_cumulative(path: Path, df_new: pd.DataFrame, id_cols: list[str], sort_col: str | None = None) -> int:
    """Merges `df_new` into the CSV at `path` (later rows win per `id_cols`); returns the number of rows written."""
    if path.exists():
        try:
            df = pd.concat([pd.read_csv(path), df_new], ignore_index=True)
        except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            logger.warning(f"Could not read existing {path.name}: {e}")
            df = df_new
    else:
        df = df_new

    if sort_col:
        df = df.sort_values(sort_col, ascending=True)

    df = df.drop_duplicates(subset=id_cols, keep="last")
    neutralize_formulas(df).to_csv(path, index=False)
    return len(df)


def keep_columns(path: Path, columns: list[str]) -> None:
    """Rewrites the CSV at `path` with only `columns`, dropping legacy columns that a merge carried over."""
    neutralize_formulas(pd.read_csv(path)[columns]).to_csv(path, index=False)


def save_odds_development(output_dir: Path, odds_development: list[OddsDevelopment], snapshot_file: str | None) -> None:
    """Writes the daily `snapshot_file` when given, otherwise the cumulative `match_odds_development.csv`."""
    df_dev = pd.DataFrame([d.__dict__ for d in odds_development])
    columns = [*ODDS_ID_COLUMNS, *(c for c in df_dev.columns if c not in ODDS_ID_COLUMNS)]
    df_dev = df_dev[columns]
    if snapshot_file:
        # One file per day, merged so that a second run on the same day does not duplicate matches
        total = save_cumulative(output_dir / snapshot_file, df_dev, ["match_id"], "snapshot_date")
        logger.info(f"Saved snapshot to {snapshot_file} (Total records in file: {total})")
    else:
        path = output_dir / "match_odds_development.csv"
        total = save_cumulative(path, df_dev, ["match_id"], "snapshot_date")
        keep_columns(path, columns)
        logger.info(f"Updated match_odds_development.csv (Total records: {total})")


def save_results(output_dir: Path, matches: list[TodayMatch], result: ScrapeResult, snapshot_file: str | None) -> None:
    neutralize_formulas(pd.DataFrame([m.__dict__ for m in matches])).to_csv(
        output_dir / "today_matches.csv", index=False
    )
    if result.odds_development:
        save_odds_development(output_dir, result.odds_development, snapshot_file)
    if result.clubs:
        clubs_path = output_dir / "club_meta.csv"
        df_clubs = pd.DataFrame([c.__dict__ for c in result.clubs.values()])[list(CLUB_COLUMNS)]
        total = save_cumulative(clubs_path, df_clubs, ["team_id"], "team_id")
        keep_columns(clubs_path, list(CLUB_COLUMNS))
        logger.info(f"Updated club_meta.csv (Total records: {total})")
    if result.cups:
        df_cups = pd.DataFrame([c.__dict__ for c in result.cups])
        total = save_cumulative(output_dir / "club_cups.csv", df_cups, ["team_id", "cup_code"])
        logger.info(f"Updated club_cups.csv (Total records: {total})")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_date = local_now().strftime("%Y-%m-%d")
    fetcher = SoccerRatingFetcher(args.user_agent)

    today_html = read_today_page(args.local, fetcher.fetch)
    if today_html is None:
        return
    filters = MatchFilters(args.all_leagues, args.min_start, args.max_start, args.skip_cups)
    matches = select_matches(filters, today_html, snapshot_date, local_now())
    if not matches:
        logger.warning("No matches match the criteria. Exiting.")
        return

    read_page = read_local_club_page if args.local else remote_club_page_reader(fetcher.fetch, args.delay)
    source_url = local_source_url if args.local else remote_source_url
    result = scrape_matches(matches, args.limit, read_page, source_url)
    snapshot_file = f"match_odds_development_{snapshot_date}.csv" if args.separate_snapshots else None
    save_results(output_dir, matches, result, snapshot_file)
    logger.info(f"ETL Complete. Outputs in {output_dir}")
    validate_results(matches, result.odds_development)


if __name__ == "__main__":
    main()
