"""Manual check that the parsers still find what they expect on the live site (`soccer-rating --check-markup`).

The parser tests use hand-written HTML, so a change of the site's markup would go unnoticed; this check fetches the
today page and one team page, runs the parsers on them and reports what they found. Nothing is stored.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from .parsers import (
    club_page_match_date,
    parse_clip_payloads,
    parse_club_page,
    parse_team_ratings,
    parse_today_prediction,
    payload_to_odds_row,
)

logger = logging.getLogger(__name__)

TODAY_PATH = "/today-prediction"


@dataclass(frozen=True)
class MarkupReport:
    matches: int
    matches_with_odds: int
    payloads: int
    team_ratings: bool
    club_ratings: bool
    match_date: bool = False


def today_report(today_html: str, snapshot_date: str) -> tuple[MarkupReport, str | None]:
    """What the today page gave (team page fields still empty), and the link of the first match's home team."""
    matches = parse_today_prediction(today_html, snapshot_date, all_leagues=True)
    with_odds = [m for m in matches if None not in (m.odd_1_today, m.odd_x_today, m.odd_2_today)]
    report = MarkupReport(len(matches), len(with_odds), 0, team_ratings=False, club_ratings=False)
    return report, (matches[0].home_href if matches else None)


def with_team_page(report: MarkupReport, team_html: str) -> MarkupReport:
    """`report` completed with the payloads and ratings found on a team page."""
    payloads = [parts for parts in parse_clip_payloads(team_html) if payload_to_odds_row(parts)]
    meta, _ = parse_club_page(team_html, 0)
    return replace(
        report,
        payloads=len(payloads),
        team_ratings=None not in parse_team_ratings(team_html),
        club_ratings=None not in (meta.rating_total, meta.rating_home, meta.rating_away),
        match_date=club_page_match_date(team_html) is not None,
    )


def markup_problems(report: MarkupReport) -> list[str]:
    """What the parsers missed; empty when every expected structure was found."""
    checks = [
        (report.matches > 0, "no matches on the today page"),
        (report.matches_with_odds == report.matches, "some matches lack 1/X/2 odds"),
        (report.payloads > 0, "no odds payloads on the team page"),
        (report.team_ratings, "no Team Ratings (H/A) on the team page"),
        (report.club_ratings, "no Rating Total/Home/Away on the team page"),
        # Without it the scraper cannot tell a later fixture from the club's next match
        (report.match_date, "no next-match startDate on the team page"),
    ]
    return [problem for found, problem in checks if not found]


def check_markup(fetch: Callable[[str], str | None], delay_s: float, snapshot_date: str) -> int:
    """Fetches the today page and the first match's home team page, logs the report; returns the exit code."""
    today_html = fetch(TODAY_PATH)
    if not today_html:
        logger.error("Markup check FAILED: could not fetch the today page")
        return 1
    report, team_href = today_report(today_html, snapshot_date)
    if team_href is not None:
        time.sleep(delay_s)
        team_html = fetch(team_href)
        report = with_team_page(report, team_html or "")
    logger.info(f"Markup check: {report}")
    problems = markup_problems(report)
    for problem in problems:
        logger.error(f"Markup check FAILED: {problem}")
    if not problems:
        logger.info("Markup check OK")
    return 1 if problems else 0
