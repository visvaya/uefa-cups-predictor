"""Filters on parsed today-page matches (`--skip-*` and `--leagues`); each drops the matches its predicate selects."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .models import TodayMatch

logger = logging.getLogger(__name__)

# Champions League, Europa League and Conference League, as soccer-rating.com codes them
UEFA_CLUB_CUPS = frozenset({"CLCUP", "ELCUP", "ECLCUP"})
# Continental club cups outside UEFA seen so far in the "Cups:" field of the site's club pages
# (data/soccer-rating/club_cups.csv, 2026-11-16): Copa Libertadores, AFC Cup, CONCACAF Champions Cup.
# Other codes containing CUP count as domestic cups until they are added here.
OTHER_CONTINENTAL_CLUB_CUPS = frozenset({"CLICUP", "AFCCUP", "CCCUP"})


@dataclass(frozen=True)
class MatchFilter:
    label: str  # names the dropped matches in the log, e.g. "cup"
    drops: Callable[[TodayMatch], bool]


def is_cup(league_code: str) -> bool:
    return "CUP" in league_code


def cups() -> MatchFilter:
    return MatchFilter("cup", lambda m: is_cup(m.league_code))


def domestic_cups() -> MatchFilter:
    continental = UEFA_CLUB_CUPS | OTHER_CONTINENTAL_CLUB_CUPS
    return MatchFilter("domestic cup", lambda m: is_cup(m.league_code) and m.league_code not in continental)


def uefa_cups() -> MatchFilter:
    return MatchFilter("UEFA cup", lambda m: m.league_code in UEFA_CLUB_CUPS)


def other_continental_cups() -> MatchFilter:
    return MatchFilter("other continental cup", lambda m: m.league_code in OTHER_CONTINENTAL_CLUB_CUPS)


def national_teams() -> MatchFilter:
    """Matches with a national team on either side (negative ids, see `parsers.team_id_from_href`)."""
    return MatchFilter("national-team", lambda m: m.home_id < 0 or m.away_id < 0)


def only_leagues(league_codes: frozenset[str]) -> MatchFilter:
    return MatchFilter("unlisted league", lambda m: m.league_code not in league_codes)


def apply_filters(matches: list[TodayMatch], filters: Iterable[MatchFilter]) -> list[TodayMatch]:
    """`matches` without those any filter drops; logs what each filter dropped."""
    for match_filter in filters:
        dropped = [m for m in matches if match_filter.drops(m)]
        if dropped:
            codes = sorted({m.league_code for m in dropped})
            logger.info(f"Filtered out {len(dropped)} {match_filter.label} matches. Skipped codes: {codes}")
        matches = [m for m in matches if not match_filter.drops(m)]
    return matches
