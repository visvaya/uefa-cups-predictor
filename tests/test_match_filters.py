import argparse
from dataclasses import replace

import pytest

from scraping.match_filters import (
    CUP_CODES,
    MatchFilter,
    apply_filters,
    domestic_cups,
    national_teams,
    only_leagues,
    other_continental_cups,
    uefa_cups,
    unclassified_cups,
)
from scraping.match_filters import cups as all_cups
from scraping.models import TodayMatch
from scraping.parsers import team_id_from_href
from scraping.soccer_rating_cli import league_list_arg

CODES = ["CLCUP", "ELCUP", "ECLCUP", "CLICUP", "AFCCUP", "CCCUP", "FACUP", "UKLCUP", "NEWCUP", "AR1", "EN"]
BASE = TodayMatch(
    match_id="",
    snapshot_date="2026-02-05",
    league_code="",
    league_name="",
    time_local="21:00",
    home_id=101,
    away_id=202,
    home_team="Home FC",
    away_team="Away FC",
    home_href="/Home-FC/101/",
    away_href="/Away-FC/202/",
    value_side=None,
    odds_rating_oo_today=None,
    odd_1_today=None,
    odd_x_today=None,
    odd_2_today=None,
    lineup_rating_home_today=None,
    lineup_rating_away_today=None,
    lineup_type_today=None,
)
MATCHES = [replace(BASE, match_id=code, league_code=code) for code in CODES]


def kept_codes(*filters: MatchFilter, matches: list[TodayMatch] = MATCHES) -> list[str]:
    return [m.league_code for m in apply_filters(matches, filters)]


def test_skip_cups_drops_every_cup() -> None:
    assert kept_codes(all_cups()) == ["AR1", "EN"]


def test_skip_domestic_cups_keeps_continental_cups_and_counts_unknown_cups_as_domestic() -> None:
    assert kept_codes(domestic_cups()) == ["CLCUP", "ELCUP", "ECLCUP", "CLICUP", "AFCCUP", "CCCUP", "AR1", "EN"]


def test_skip_uefa_cups() -> None:
    assert kept_codes(uefa_cups()) == ["CLICUP", "AFCCUP", "CCCUP", "FACUP", "UKLCUP", "NEWCUP", "AR1", "EN"]


def test_skip_other_continental_cups() -> None:
    assert kept_codes(other_continental_cups()) == [
        "CLCUP",
        "ELCUP",
        "ECLCUP",
        "FACUP",
        "UKLCUP",
        "NEWCUP",
        "AR1",
        "EN",
    ]


def test_daily_combination_keeps_uefa_cups_and_leagues() -> None:
    assert kept_codes(domestic_cups(), other_continental_cups()) == ["CLCUP", "ELCUP", "ECLCUP", "AR1", "EN"]


def test_cups_classified_from_club_pages() -> None:
    # Copa Sudamericana and AFC Champions League Two are continental; Copa Chile and the Rio state cup are domestic
    classified = [replace(BASE, match_id=code, league_code=code) for code in ("CPCUP", "AFCUP", "CLCCUP", "BRRCUP")]
    assert kept_codes(other_continental_cups(), matches=classified) == ["CLCCUP", "BRRCUP"]
    assert kept_codes(domestic_cups(), matches=classified) == ["CPCUP", "AFCUP"]


def test_womens_champions_league_is_a_uefa_cup() -> None:
    # WCLCUP is the UEFA Women's Champions League (Chelsea v Paris Saint-Germain on 2026-11-18), not a domestic cup
    womens = [replace(BASE, match_id="WCLCUP", league_code="WCLCUP")]
    assert kept_codes(domestic_cups(), other_continental_cups(), matches=womens) == ["WCLCUP"]
    assert kept_codes(uefa_cups(), matches=womens) == []


def test_skip_national_teams_drops_matches_with_a_national_team_id() -> None:
    world_club = replace(BASE, home_id=team_id_from_href("/Zob-Ahan/w250/"))
    national = [replace(BASE, home_id=-28, away_id=-21), replace(BASE, away_id=-21), BASE, world_club]
    assert apply_filters(national, [national_teams()]) == [BASE, world_club]


def test_leagues_keeps_only_listed_codes_and_combines_with_other_filters() -> None:
    assert kept_codes(only_leagues(frozenset({"CLCUP", "FACUP", "AR1"}))) == ["CLCUP", "FACUP", "AR1"]
    assert kept_codes(only_leagues(frozenset({"CLCUP", "FACUP", "AR1"})), domestic_cups()) == ["CLCUP", "AR1"]


def test_apply_filters_logs_what_each_filter_dropped(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO")
    apply_filters(MATCHES, [uefa_cups(), national_teams()])
    assert "Filtered out 3 UEFA cup matches. Skipped codes: ['CLCUP', 'ECLCUP', 'ELCUP']" in caplog.text
    assert "national-team" not in caplog.text  # nothing dropped, nothing logged


def test_league_list_arg() -> None:
    assert league_list_arg("CLCUP, elcup,,AR1") == frozenset({"CLCUP", "ELCUP", "AR1"})
    with pytest.raises(argparse.ArgumentTypeError):
        league_list_arg(" , ")


def test_cup_codes_classify_every_cup_the_filters_name() -> None:
    assert {code for code, (kind, _) in CUP_CODES.items() if kind == "uefa"} == {"CLCUP", "ELCUP", "ECLCUP", "WCLCUP"}
    assert CUP_CODES["ESCUP"] == ("domestic", "Copa del Rey")


def test_unclassified_cups_names_cup_codes_missing_from_the_table() -> None:
    unknown = replace(BASE, match_id="NEWCUP", league_code="NEWCUP", league_name="New Cup")
    known = [replace(BASE, league_code=code) for code in ("WCLCUP", "ESCUP", "AR1")]
    assert unclassified_cups([unknown, *known, unknown]) == {"NEWCUP": "New Cup"}
