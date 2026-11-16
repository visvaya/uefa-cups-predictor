"""Filters on parsed today-page matches (`--skip-*` and `--leagues`); each drops the matches its predicate selects."""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from .models import TodayMatch

logger = logging.getLogger(__name__)

CupKind = Literal["uefa", "other continental", "domestic"]

# Every cup code the filters know: what kind of competition it is, and its name. A code containing CUP that is
# missing here is logged as unclassified (see `unclassified_cups`) and counts as a domestic cup until it is added.
# Sources, checked 2026-11-16: the league headers of the day pages ("WCLCUP  Champions League Women" with Chelsea
# v Paris Saint-Germain, "ESCUP  Copa del Rey") and the "Cups:" field and match lists of club pages
# (data/soccer-rating/club_cups.csv). AFCCUP is the AFC Champions League Elite (Al Sadd played Al Hilal, Vissel
# Kobe and Kawasaki Frontale in it); CPCUP and AFCUP were classified from the clubs' opponents.
CUP_CODES: dict[str, tuple[CupKind, str]] = {
    "CLCUP": ("uefa", "Champions League"),
    "ELCUP": ("uefa", "Europa League"),
    "ECLCUP": ("uefa", "Conference League"),
    "WCLCUP": ("uefa", "Champions League Women"),
    "CLICUP": ("other continental", "Copa Libertadores"),
    "AFCCUP": ("other continental", "AFC Champions League Elite"),
    "CCCUP": ("other continental", "CONCACAF Champions Cup"),
    "CPCUP": ("other continental", "Copa Sudamericana"),
    "AFCUP": ("other continental", "AFC Champions League Two"),
    "ESCUP": ("domestic", "Copa del Rey"),
    "CLCCUP": ("domestic", "Copa Chile"),
    "BRRCUP": ("domestic", "Rio de Janeiro state cup"),
}
UEFA_CLUB_CUPS = frozenset(code for code, (kind, _) in CUP_CODES.items() if kind == "uefa")
OTHER_CONTINENTAL_CLUB_CUPS = frozenset(code for code, (kind, _) in CUP_CODES.items() if kind == "other continental")


@dataclass(frozen=True)
class MatchFilter:
    label: str  # names the dropped matches in the log, e.g. "cup"
    drops: Callable[[TodayMatch], bool]


def is_cup(league_code: str) -> bool:
    return "CUP" in league_code


def unclassified_cups(matches: Iterable[TodayMatch]) -> dict[str, str]:
    """Cup codes of `matches` missing from `CUP_CODES`, with the league name the page gives them."""
    return {m.league_code: m.league_name for m in matches if is_cup(m.league_code) and m.league_code not in CUP_CODES}


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
