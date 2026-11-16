import argparse
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from csv_safety import neutralize_formulas

from .fetcher import DEFAULT_USER_AGENT, SoccerRatingFetcher, resolve_url
from .markup_check import TODAY_PATH, check_markup
from .match_filters import (
    MatchFilter,
    apply_filters,
    cups,
    domestic_cups,
    national_teams,
    only_leagues,
    other_continental_cups,
    uefa_cups,
)
from .models import ClubCup, ClubMeta, OddsDevelopment, PayloadSource, TodayMatch
from .parsers import (
    name_match_score,
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

SITE_TIMEZONE = "Europe/Paris"
# The site has day pages for the six days after today (/today-prediction/<weekday>)
MAX_DAYS_AHEAD = 6
WEEKDAY_PAGES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
RE_KICKOFF_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def local_now() -> datetime:
    """Current time as an aware datetime in the machine's local timezone."""
    return datetime.now().astimezone()


def timezone_arg(name: str) -> ZoneInfo:
    """An IANA timezone name such as Europe/Paris, for argparse."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"unknown timezone {name!r}") from e


def league_list_arg(text: str) -> frozenset[str]:
    """Comma-separated league codes such as "CLCUP,AR1", for argparse."""
    codes = frozenset(code.strip().upper() for code in text.split(",") if code.strip())
    if not codes:
        raise argparse.ArgumentTypeError("expected league codes separated by commas")
    return codes


def days_arg(text: str) -> int:
    """A number of days after today with a day page on the site, for argparse."""
    try:
        days = int(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"expected a whole number, got {text!r}") from e
    if not 0 <= days <= MAX_DAYS_AHEAD:
        raise argparse.ArgumentTypeError(f"expected 0-{MAX_DAYS_AHEAD}, got {days}")
    return days


def site_clock(now: datetime, site_tz: ZoneInfo) -> datetime:
    """`now` on the clock the site shows kickoffs in."""
    return now.astimezone(site_tz)


def minutes_until_kickoff(time_local: str, now: datetime, days_ahead: int = 0) -> float:
    """Returns real minutes from `now` to an "HH:MM" kickoff on the clock of `now`'s timezone (DST-aware with zoneinfo).

    The kickoff is on the date of the page that lists it, `days_ahead` days after `now`'s date: a day page lists
    the early-morning kickoffs of its own date (checked 2026-11-16), so an 00:00 kickoff on today's page is past.
    Raises ValueError when `time_local` is not a valid HH:MM time.
    """
    hm = RE_KICKOFF_TIME.match(time_local)
    if hm is None:
        raise ValueError(f"expected HH:MM, got {time_local!r}")
    # Adding days keeps the wall-clock time, so the kickoff day's offset applies
    kickoff = now.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    # Differences between datetimes of the same tzinfo ignore DST, so both are compared in UTC
    return (kickoff.astimezone(UTC) - now.astimezone(UTC)).total_seconds() / 60.0


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
    drop: tuple[MatchFilter, ...]


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
    # The markup check always reads the live site, so it cannot run on local files
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", action="store_true", help="Use local files for testing")
    mode.add_argument(
        "--check-markup",
        action="store_true",
        help="Fetch the today page and one team page, report whether the parsers find what they expect, write nothing",
    )
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
        "--site-timezone",
        type=timezone_arg,
        # The site's own timezone selector defaults to "GMT +1 Paris" (checked 2026-11-16)
        default=SITE_TIMEZONE,
        help=f"IANA timezone the site shows kickoff times in (default: {SITE_TIMEZONE})",
    )
    parser.add_argument(
        "--days",
        type=days_arg,
        default=0,
        help=f"Also read the day pages of the next N days (0-{MAX_DAYS_AHEAD}); match ids carry the kickoff date",
    )
    filters = parser.add_argument_group("match filters (combinable; each drops what it names)")
    filters.add_argument("--skip-cups", action="store_true", help="Skip every cup (league code contains CUP)")
    filters.add_argument(
        "--skip-domestic-cups",
        action="store_true",
        help="Skip cups that are neither UEFA nor other continental club cups (unknown CUP codes count as domestic)",
    )
    filters.add_argument("--skip-uefa-cups", action="store_true", help="Skip CLCUP, ELCUP and ECLCUP")
    filters.add_argument(
        "--skip-other-continental-cups",
        action="store_true",
        help="Skip continental club cups outside UEFA (CLICUP, AFCCUP, CCCUP, CPCUP, AFCUP)",
    )
    filters.add_argument("--skip-national-teams", action="store_true", help="Skip matches of national teams")
    filters.add_argument(
        "--leagues",
        type=league_list_arg,
        default=None,
        metavar="CODE[,CODE...]",
        help="Keep only these league codes, e.g. CLCUP,ELCUP,AR1 (reads all leagues of the page)",
    )
    args = parser.parse_args()
    if args.local and args.days:
        parser.error("--days reads the live site; --local has only the today page")
    return args


def match_filters(args: argparse.Namespace) -> tuple[MatchFilter, ...]:
    """The filters the command line asks for, in a fixed order."""
    flags = [
        (args.skip_cups, cups),
        (args.skip_domestic_cups, domestic_cups),
        (args.skip_uefa_cups, uefa_cups),
        (args.skip_other_continental_cups, other_continental_cups),
        (args.skip_national_teams, national_teams),
    ]
    chosen = [make() for wanted, make in flags if wanted]
    return (*chosen, only_leagues(args.leagues)) if args.leagues is not None else tuple(chosen)


def read_today_page(local: bool, fetch: Callable[[str], str | None]) -> str | None:
    if local:
        logger.info("Running in LOCAL mode.")
        if not Path(TODAY_PAGE).exists():
            logger.error(f"{TODAY_PAGE} not found.")
            return None
        html: str | None = Path(TODAY_PAGE).read_text(encoding="utf-8")
    else:
        html = fetch(TODAY_PATH)
    if not html:
        logger.error("Failed to get today predictions.")
        return None
    return html


def day_page_path(today: date, days_ahead: int) -> str:
    """The site path of the page listing the kickoffs `days_ahead` days after `today` (0 is the today page)."""
    if days_ahead == 0:
        return TODAY_PATH
    return f"{TODAY_PATH}/{WEEKDAY_PAGES[(today + timedelta(days=days_ahead)).weekday()]}"


def read_day_pages(fetch: Callable[[str], str | None], today: date, days: int, delay_s: float) -> list[tuple[int, str]]:
    """The pages of the `days` days after today, as (days ahead, html); a missing page is logged and skipped.

    Each request waits `delay_s` first, like the club page requests after the today page.
    """
    pages = []
    for days_ahead in range(1, days + 1):
        path = day_page_path(today, days_ahead)
        time.sleep(delay_s)
        html = fetch(path)
        if html:
            pages.append((days_ahead, html))
        else:
            logger.error(f"Failed to get the day page {path}.")
    return pages


def in_time_window(
    matches: list[TodayMatch], filters: MatchFilters, now: datetime, days_ahead: int
) -> list[TodayMatch]:
    """Matches kicking off between `min_start` and `max_start` minutes after `now`; unreadable times are dropped.

    `now` must be on the clock the site shows kickoffs in (see `site_clock`); the matches come from the page
    `days_ahead` days after `now`'s date.
    """
    kept = []
    for m in matches:
        try:
            diff_min = minutes_until_kickoff(m.time_local, now, days_ahead)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse time {m.time_local} for {m.match_id}: {e}")
            continue
        if (filters.min_start is None or diff_min >= filters.min_start) and (
            filters.max_start is None or diff_min <= filters.max_start
        ):
            kept.append(m)
    return kept


def page_matches(filters: MatchFilters, html: str, now: datetime, days_ahead: int) -> list[TodayMatch]:
    """The matches of one day page within the time window; their ids carry the page's date."""
    page_date = (now.date() + timedelta(days=days_ahead)).isoformat()
    matches = parse_today_prediction(html, page_date, all_leagues=filters.all_leagues)
    logger.info(f"Loaded {len(matches)} total matches for {page_date} (all matching leagues).")

    if filters.min_start is not None or filters.max_start is not None:
        filtered = in_time_window(matches, filters, now, days_ahead)
        logger.info(f"Filtered matches: {len(filtered)} (from {len(matches)}) based on time window.")
        matches = filtered
    return matches


def select_matches(filters: MatchFilters, pages: list[tuple[int, str]], now: datetime) -> list[TodayMatch]:
    """The matches of the day pages, given as (days ahead, html), that pass the time window and the filters."""
    matches = [m for days_ahead, html in pages for m in page_matches(filters, html, now, days_ahead)]
    return apply_filters(matches, filters.drop)


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
    """Reads the home, then the away club page; stops at the first page with a payload naming both teams.

    A club page can list another fixture of the team (a day page's match is often not its next one), so the
    away page is read when the home page names none; the candidates of both pages are returned.
    """
    team_ratings: tuple[float | None, float | None] = (None, None)
    clubs: dict[int, ClubMeta] = {}
    cups: list[ClubCup] = []
    found: list[dict[str, Any]] = []
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
        found.extend(club_page_candidates(club_html, href))
        # The payload of a match is on both club pages; once one names the fixture, the other would repeat it
        if any(names_fixture(match, c) for c in found):
            break
    return MatchScan(found, team_ratings, clubs, cups)


def names_fixture(match: TodayMatch, candidate: dict[str, Any]) -> bool:
    """Whether a payload names both teams of the match (in either order)."""
    score = name_match_score(
        match.home_team, match.away_team, candidate["home_team_payload"], candidate["away_team_payload"]
    )
    return score > 0


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
    snapshot_date = local_now().strftime("%Y-%m-%d")
    fetcher = SoccerRatingFetcher(args.user_agent, args.delay)
    if args.check_markup:
        raise SystemExit(check_markup(fetcher.fetch, args.delay, snapshot_date))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    today_html = read_today_page(args.local, fetcher.fetch)
    if today_html is None:
        return
    now = site_clock(local_now(), args.site_timezone)
    pages = [(0, today_html), *read_day_pages(fetcher.fetch, now.date(), args.days, args.delay)]
    all_leagues = args.all_leagues or args.leagues is not None
    filters = MatchFilters(all_leagues, args.min_start, args.max_start, match_filters(args))
    matches = select_matches(filters, pages, now)
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
