from datetime import datetime

import pytest

from src.scraping.parsers import (
    _extract_two_numbers,
    _normalize_time,
    name_match_score,
    norm_team,
    parse_today_prediction,
    payload_to_odds_row,
    team_id_from_href,
)
from src.scraping.soccer_rating_cli import minutes_until_kickoff

EVENING = datetime(2026, 2, 5, 18, 0)


def test_minutes_until_kickoff_same_day() -> None:
    assert minutes_until_kickoff("21:00", EVENING) == 180


def test_minutes_until_kickoff_rolls_over_midnight() -> None:
    assert minutes_until_kickoff("01:00", EVENING) == 7 * 60


def test_minutes_until_kickoff_keeps_recent_past_negative() -> None:
    assert minutes_until_kickoff("17:30", EVENING) == -30


def test_minutes_until_kickoff_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        minutes_until_kickoff("tbd", EVENING)


def test_team_id_from_href() -> None:
    assert team_id_from_href("/Sturm-Graz/1294/") == 1294
    with pytest.raises(ValueError):
        team_id_from_href("/no-id-here/")


def test_normalize_time() -> None:
    assert _normalize_time("2100") == "21:00"
    assert _normalize_time(" 9:30 ") == "9:30"


def test_extract_two_numbers_reads_odds_and_lineup_rating() -> None:
    # Cell format observed on soccer-rating.com: "<odds><br/>∅&nbsp;<rating>"
    assert _extract_two_numbers("1.57 ∅\xa068") == (1.57, 68.0)


def test_extract_two_numbers_ignores_decimal_part_without_rating() -> None:
    assert _extract_two_numbers("1.12") == (1.12, None)
    assert _extract_two_numbers("16.00") == (16.0, None)


def test_name_match_score() -> None:
    assert norm_team("  Bodø/Glimt ") == "bodo glimt"
    assert norm_team("Kobenhavn") == norm_team("København")
    assert name_match_score("Home FC", "Away FC", "home fc", "away fc") == 2
    assert name_match_score("Home FC", "Away FC", "away fc", "home fc") == 1
    assert name_match_score("Home FC", "Away FC", "other", "team") == 0


def _today_row(home_href: str, away_href: str) -> str:
    return (
        "<tr><td>21:00</td><td>55.1</td><td></td>"
        f'<td><a href="{home_href}">Home FC</a> - <a href="{away_href}">Away FC</a></td>'
        '<td align="center"><b>1.57</b><br/>∅&nbsp;68</td><td>4.20</td>'
        '<td align="center">5.25<br/>∅&nbsp;52</td></tr>'
    )


def _today_page(*rows: str) -> str:
    return (
        '<table class="bigtable"><tr><td>Football Prediction Today</td></tr>'
        '<tr><td colspan="8">CLCUP Champions League</td></tr>' + "".join(rows) + "</table>"
    )


def test_parse_today_prediction_reads_club_match() -> None:
    matches = parse_today_prediction(_today_page(_today_row("/Home-FC/101/", "/Away-FC/202/")), "2026-02-05")
    assert len(matches) == 1
    match = matches[0]
    assert match.match_id == "2026-02-05_CLCUP_101_202"
    assert (match.odd_1_today, match.lineup_rating_home_today) == (1.57, 68.0)
    assert (match.odd_x_today, match.lineup_rating_away_today) == (4.2, 52.0)


def test_parse_today_prediction_skips_national_team_links() -> None:
    page = _today_page(
        _today_row("/Antigua-Barbuda/n206/", "/Other/n300/"), _today_row("/Home-FC/101/", "/Away-FC/202/")
    )
    matches = parse_today_prediction(page, "2026-02-05")
    assert [m.home_id for m in matches] == [101]


def test_payload_to_odds_row_requires_full_payload() -> None:
    assert payload_to_odds_row(["a"] * 5) == {}
    parts = ["Home", "Away", "0", "CLCUP"] + [str(v) for v in range(1, 16)]
    row = payload_to_odds_row(parts)
    assert row["league_code_payload"] == "CLCUP"
    assert row["oo"] == 1.0
    assert row["fair_2"] == 15.0
