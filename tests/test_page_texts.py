import math
from datetime import UTC, date, datetime, timedelta

import pytest

from analyzer.page.texts import (
    TERMS,
    club_link,
    date_span,
    day_heading,
    fold,
    footer_sources,
    kickoff_at,
    level_of,
    matches_phrase,
    pl_number,
    stamp,
)
from analyzer.recommendations import AVOID, CAUTION, CONSIDER, NEUTRAL, STRONG_BUY

MINUS = chr(0x2212)
EN_DASH = chr(0x2013)


def test_level_of_reads_every_label() -> None:
    assert [level_of(label) for label in (STRONG_BUY, CONSIDER, NEUTRAL, CAUTION, AVOID)] == [
        "strong",
        "consider",
        "neutral",
        "caution",
        "avoid",
    ]


def test_level_of_refuses_an_unknown_label() -> None:
    with pytest.raises(ValueError, match="BUY NOW"):
        level_of("BUY NOW")


def test_pl_number_writes_a_decimal_comma_and_a_real_minus() -> None:
    assert pl_number(1.567) == "1,57"
    assert pl_number(-0.04 * 100, 0, sign=True) == MINUS + "4"
    assert pl_number(0.12, sign=True) == "+0,12"
    assert pl_number(61.25, 1) == "61,2"


@pytest.mark.parametrize(
    ("n", "phrase"),
    [(1, "1 mecz"), (2, "2 mecze"), (5, "5 meczów"), (12, "12 meczów"), (22, "22 mecze")],
)
def test_matches_phrase_follows_polish_plurals(n: int, phrase: str) -> None:
    assert matches_phrase(n) == phrase


def test_day_heading_names_the_weekday() -> None:
    assert day_heading(date(2026, 11, 18)) == "Środa, 18.11"


def test_date_span_joins_days_and_months() -> None:
    assert date_span(date(2026, 11, 16), date(2026, 11, 18)) == f"16{EN_DASH}18 listopada 2026"
    assert date_span(date(2026, 11, 30), date(2026, 12, 2)) == f"30 listopada {EN_DASH} 2 grudnia 2026"
    assert date_span(date(2026, 12, 30), date(2027, 1, 2)) == f"30 grudnia 2026 {EN_DASH} 2 stycznia 2027"
    assert date_span(date(2026, 11, 18), date(2026, 11, 18)) == "18 listopada 2026"


def test_stamp_writes_date_and_time() -> None:
    assert stamp(datetime(2026, 11, 16, 17, 57)) == "16.11.2026 o 17:57"


def test_stamp_shows_an_aware_moment_in_page_time() -> None:
    assert stamp(datetime(2026, 11, 16, 16, 57, tzinfo=UTC)) == "16.11.2026 o 17:57"


def test_kickoff_converts_site_time_to_page_time() -> None:
    kickoff = kickoff_at(date(2026, 11, 18), "9:05")

    assert kickoff is not None
    assert kickoff.isoformat() == "2026-11-18T09:05:00+01:00"
    assert str(kickoff.tzinfo) == "Europe/Warsaw"


def test_kickoff_follows_daylight_saving() -> None:
    summer = kickoff_at(date(2026, 3, 29), "21:00")
    winter = kickoff_at(date(2026, 1, 28), "21:00")

    assert summer is not None
    assert winter is not None
    assert summer.utcoffset() == timedelta(hours=2)
    assert winter.utcoffset() == timedelta(hours=1)


@pytest.mark.parametrize("time_local", ["", "  ", "soon", "25:00", math.nan])
def test_kickoff_is_none_without_a_readable_time(time_local: str | float) -> None:
    assert kickoff_at(date(2026, 11, 18), time_local) is None


def test_club_link_points_to_the_club_page() -> None:
    link = club_link("Bodø/Glimt", "/team/Bodo-Glimt/1234")

    assert 'href="https://www.soccer-rating.com/team/Bodo-Glimt/1234"' in link
    assert ">Bodø/Glimt</a>" in link


@pytest.mark.parametrize("href", ["javascript:alert(1)", "//evil.example/", "", None])
def test_club_link_refuses_other_hrefs(href: str | None) -> None:
    assert club_link('<b>"A&B"', href) == "&lt;b&gt;&quot;A&amp;B&quot;"


def test_fold_drops_diacritics_and_folds_special_letters() -> None:
    assert fold("Fenerbahçe") == "fenerbahce"
    assert fold("Bodø/Glimt") == "bodo/glimt"
    assert fold("Łódź") == "lodz"


def test_terms_leave_out_the_sample_odds_sentence() -> None:
    assert "przykładowe" not in TERMS["odds"][1]
    assert TERMS["odds"][0] == "Kurs"


def test_footer_sources_names_the_scrape_time_only_when_known() -> None:
    known = footer_sources(datetime(2026, 11, 16, 16, 57, tzinfo=UTC))

    assert ", pobrane 16.11.2026 o 17:57." in known
    assert "pobrane" not in footer_sources(None)
    assert "przykładowe" not in footer_sources(None)
