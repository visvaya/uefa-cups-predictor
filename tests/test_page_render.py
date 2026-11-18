"""The results page renderer: a golden page from the test fixtures and the rules for escaping, missing values and order.

Regenerate the golden page only when a change of the page is intended, never to make a refactor pass:
`UPDATE_GOLDEN=1 uv run pytest tests/test_page_render.py`, then review the diff of `tests/golden/page/`.
"""

import os
import re
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jinja2 import UndefinedError
from markupsafe import escape

from analyzer.cli import league_frames
from analyzer.config import PAGE_TIMEZONE
from analyzer.league import league_ranking
from analyzer.page.cup_rows import cup_section, cup_section_without_data
from analyzer.page.environment import page_environment
from analyzer.page.model import CupFacts, CupSection, MatchRow, PageData, Pick, PickOdds, SrFacts, TeamFacts
from analyzer.page.render import render_page
from analyzer.page.render_sr import sr_view
from analyzer.page.sr_rows import sr_match_rows
from analyzer.page.texts import ANALYST_SLUGS, CUP_NAMES, EN_DASH, SR_NO_DATA, TAB_SR_EMPTY
from analyzer.sr_only import sr_only_ranking
from tests.inputs import REPO_DIR, el_base_dir, fixture_sr_only, text_of, view_of

GOLDEN_PAGE = REPO_DIR / "tests" / "golden" / "page" / "results.html"
ENV = page_environment()
PAGE_ZONE = ZoneInfo(PAGE_TIMEZONE)
DAY = date(2026, 3, 4)  # a Wednesday
SR_FACTS = SrFacts(edge=0.05, steam=0.1, ao=0.0, quality=1.0, home_href="/Home-FC/1/", away_href="/Away-FC/2/")
SR_ROW = MatchRow(
    home="Home FC",
    away="Away FC",
    pick="1",
    level="consider",
    reason="Positive Signal",
    day=DAY,
    kickoff=datetime(2026, 3, 4, 21, 0, tzinfo=PAGE_ZONE),
    group="XX1",
    group_name="League",
    odds=PickOdds(open=1.8, close=1.6, fair=1.5),
    score=0.7,
    sr=SR_FACTS,
    cup=None,
)
TEAM = TeamFacts(
    team="Home FC",
    win_pct=55.0,
    motivation=80.0,
    status="IN_PLAY",
    rotation=1.0,
    value=60.0,
    score=0.7,
    edge=0.05,
    level="consider",
    reason="Good Value",
    close=1.6,
)
CUP_FACTS = CupFacts(55.0, 25.0, 20.0, TEAM, replace(TEAM, team="Away FC", level="neutral", close=5.0))
CUP_ROW = replace(SR_ROW, reason="Good Value", group="el", group_name=CUP_NAMES["el"], sr=None, cup=CUP_FACTS)


def page_data(sr_rows: tuple[MatchRow, ...], cups: tuple[CupSection, ...]) -> PageData:
    return PageData(
        sr_rows=sr_rows,
        cups=cups,
        scraped_at=datetime(2026, 3, 4, 9, 0, tzinfo=UTC),
        generated_at=datetime(2026, 3, 4, 12, 0, tzinfo=PAGE_ZONE),
    )


def el_section(*rows: MatchRow) -> CupSection:
    return CupSection("el", CUP_NAMES["el"], rows)


def test_render_matches_golden(tmp_path: Path) -> None:
    f, _ = league_frames(el_base_dir(tmp_path), "el")
    data = PageData(
        sr_rows=sr_match_rows(fixture_sr_only(sr_only_ranking, ",")),
        cups=(
            cup_section_without_data("cl"),
            cup_section("el", f, league_ranking(f, ",")),
            cup_section_without_data("ecl"),
        ),
        scraped_at=datetime(2026, 1, 28, 9, 0, tzinfo=UTC),
        generated_at=datetime(2026, 1, 28, 12, 0, tzinfo=PAGE_ZONE),
    )

    page = render_page(data, ENV)

    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_PAGE.parent.mkdir(exist_ok=True)
        GOLDEN_PAGE.write_text(page, encoding="utf-8", newline="")
    assert GOLDEN_PAGE.exists(), f"Missing {GOLDEN_PAGE}; create it with UPDATE_GOLDEN=1"
    assert page == GOLDEN_PAGE.read_text(encoding="utf-8")
    assert chr(0x2014) not in page
    assert not [c for c in page if ord(c) >= 0x1F000 or 0x2600 <= ord(c) <= 0x27BF]
    for root in (tmp_path, REPO_DIR):
        assert str(root) not in page
        assert root.as_posix() not in page


def test_render_escapes_team_names() -> None:
    hostile = "<b>" + '"A&B' + "'" + 'C"'
    sr = replace(SR_ROW, home=hostile, group_name=hostile, reason=hostile)
    cup_facts = replace(TEAM, team=hostile, status=hostile, reason=hostile)
    cup = replace(CUP_ROW, away=hostile, pick="2", reason=hostile, cup=replace(CUP_FACTS, away=cup_facts))

    page = render_page(page_data((sr,), (el_section(cup),)), ENV)

    assert hostile not in page
    assert '"A&B' not in page
    assert escape(hostile) in page
    assert "A&amp;B&#39;C&#34;" in page


def test_render_fails_on_a_missing_template_variable() -> None:
    view = sr_view(page_data((SR_ROW,), ()))
    del view["key"]

    with pytest.raises(UndefinedError, match="'key' is undefined"):
        ENV.get_template("sr.html.j2").render(view)


def test_render_reads_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    env = page_environment()

    def no_open(*args: object) -> None:
        raise AssertionError(f"render_page opened a file: {args}")

    monkeypatch.setattr("builtins.open", no_open)

    assert "<!doctype html>" in render_page(page_data((SR_ROW,), (el_section(CUP_ROW),)), env)


def test_render_leaves_out_a_range_without_values() -> None:
    no_close = replace(TEAM, close=None)
    no_odds = replace(CUP_ROW, odds=PickOdds(None, None, None), cup=replace(CUP_FACTS, home=no_close, away=no_close))

    page = render_page(page_data((), (el_section(no_odds),)), ENV)

    assert 'data-range="odds"' not in page
    assert 'data-range="win"' in page
    assert " data-odds=" not in page
    assert " data-s-odds=" not in page


def test_render_sorts_picks_one_draw_two() -> None:
    rows = (
        replace(SR_ROW, home="Zulu", pick="1"),
        replace(SR_ROW, home="Yankee", away="Alpha", pick="X"),
        replace(SR_ROW, home="Bravo", away="Alpha", pick="2"),
    )

    page = render_page(page_data(rows, ()), ENV)

    values = re.findall('data-s-pick="([^"]*)"', page)
    assert values == ["0 zulu", "1 yankee", "2 alpha"]
    assert sorted(values) == values


def test_render_has_no_fixed_mockup_dates() -> None:
    page = render_page(page_data((SR_ROW,), (el_section(CUP_ROW),)), ENV)

    for fixed in ("16.11.2026", "28.01.2026", "17:57", "przykładowe"):
        assert fixed not in page
    assert 'Soccer-rating: typy na <span class="nw">4 marca 2026</span>' in text_of(page)
    assert "Dane pobrano 04.03.2026 o 10:00." in text_of(page)
    assert "Strona wygenerowana 04.03.2026 o 12:00." in text_of(page)
    assert '"sr": "Soccer-rating 4.03.2026' in page
    assert "Wszystkie mecze zaczynają się o 21:00 czasu polskiego." in text_of(page)
    assert "Strona wygenerowana 04.03.2026 o&nbsp;12:00." in page


def kicking_off(row: MatchRow, day: date, hour: int, minute: int) -> MatchRow:
    return replace(row, day=day, kickoff=datetime(day.year, day.month, day.day, hour, minute, tzinfo=PAGE_ZONE))


def test_render_cups_intro_says_which_kickoffs_are_known() -> None:
    tuesday = kicking_off(replace(CUP_ROW, group="cl"), date(2026, 3, 3), 21, 0)
    thursday = kicking_off(CUP_ROW, date(2026, 3, 5), 18, 45)
    cups = (CupSection("cl", CUP_NAMES["cl"], (tuesday,)), el_section(thursday, replace(thursday, kickoff=None)))

    text = text_of(render_page(page_data((), cups), ENV))

    assert "Kolejka fazy ligowej: 3 mecze." in text
    assert f"{CUP_NAMES['cl']} gra we wtorek 03.03.2026." in text
    assert f"{CUP_NAMES['el']} gra w czwartek 05.03.2026." in text
    assert "Znane godziny (czas polski): 18:45 i 21:00 (1 mecz bez godziny)." in text
    assert "zaczynają się" not in text
    # A cup with a match of unknown kickoff counts its shown matches instead of naming times
    assert f"{CUP_NAMES['cl']}, 3.03 <small>· 21:00</small>" in text
    assert f'{CUP_NAMES["el"]}, 5.03 <small class="day-count"></small>' in text


def test_render_cups_over_two_days() -> None:
    rows = (kicking_off(CUP_ROW, date(2026, 1, 20), 18, 45), kicking_off(CUP_ROW, date(2026, 1, 21), 21, 0))

    text = text_of(render_page(page_data((), (el_section(*rows),)), ENV))

    assert f"{CUP_NAMES['el']} gra we wtorek 20.01 i w środę 21.01.2026." in text
    assert "Mecze zaczynają się o 18:45 i 21:00 czasu polskiego." in text
    assert f"{CUP_NAMES['el']}, 20{EN_DASH}21.01 <small>· 18:45 i 21:00</small>" in text


def test_render_cups_intro_counts_matches_without_a_day() -> None:
    rows = (CUP_ROW, replace(CUP_ROW, home="Late FC"), replace(CUP_ROW, home="Open FC", day=None, kickoff=None))

    text = text_of(render_page(page_data((), (el_section(*rows),)), ENV))

    assert f"{CUP_NAMES['el']} gra w środę 04.03.2026 (1 mecz bez daty)." in text


def test_render_cups_without_kickoffs_but_with_odds() -> None:
    text = text_of(render_page(page_data((), (el_section(replace(CUP_ROW, kickoff=None)),)), ENV))

    assert "Godziny: brak danych (1 mecz bez godziny)." in text
    assert "Godziny i kursy" not in text
    assert "Znane godziny" not in text


def test_render_cups_without_kickoffs_or_odds() -> None:
    row = replace(CUP_ROW, kickoff=None, odds=PickOdds(None, None, None))

    text = text_of(render_page(page_data((), (el_section(row),)), ENV))

    assert "Godziny i kursy: brak danych soccer-rating dla tych meczów." in text


def test_render_without_rows_shows_the_no_data_notices() -> None:
    page = render_page(page_data((), tuple(cup_section_without_data(prefix) for prefix in CUP_NAMES)), ENV)

    assert SR_NO_DATA in text_of(page)
    for slug in ANALYST_SLUGS.values():
        assert f'href="https://theanalyst.com/competition/{slug}/predictions"' in page
    assert 'class="filters"' not in page
    assert 'class="m ' not in page
    assert f'"sr": "{TAB_SR_EMPTY}"' in page


@pytest.mark.parametrize("pick", ["1", "2"])
def test_render_bolds_the_picked_cup_team(pick: Pick) -> None:
    row = replace(CUP_ROW, pick=pick)

    page = render_page(page_data((), (el_section(row),)), ENV)

    picked, other = ("Home FC", "Away FC") if pick == "1" else ("Away FC", "Home FC")
    assert f"<b>{picked}</b>" in page
    assert f"<b>{other}</b>" not in page


def test_render_sr_intro_without_kickoffs_or_scrape_time() -> None:
    data = replace(page_data((replace(SR_ROW, kickoff=None),), ()), scraped_at=None)

    text = text_of(render_page(data, ENV))

    assert "<p>1 mecz z soccer-rating.com. 1 mecz bez godziny.</p>" in text
    assert 'class="t">' + EN_DASH + "</td>" in text
    assert 'data-start="2026' not in text


@pytest.mark.parametrize(
    ("sr_rows", "cups"), [((replace(SR_ROW, sr=None),), ()), ((), (el_section(replace(CUP_ROW, cup=None)),))]
)
def test_render_refuses_rows_without_their_facts(sr_rows: tuple[MatchRow, ...], cups: tuple[CupSection, ...]) -> None:
    with pytest.raises(ValueError, match="Home FC - Away FC"):
        render_page(page_data(sr_rows, cups), ENV)


def test_render_sr_intro_with_some_kickoffs_unknown() -> None:
    rows = (
        SR_ROW,
        kicking_off(replace(SR_ROW, home="Late FC"), DAY, 22, 30),
        replace(SR_ROW, home="Open FC", kickoff=None),
        replace(SR_ROW, home="Quiet FC", kickoff=None, odds=PickOdds(None, None, None)),
    )

    page = render_page(page_data(rows, ()), ENV)

    assert (
        "4 mecze z soccer-rating.com. Pierwszy zaczyna się: środa 4.03.2026, 21:00. Ostatni: środa 4.03.2026, 22:30. "
        "2 mecze bez godziny. Godziny są w czasie polskim."
    ) in text_of(page)
    # Missing values carry no sort attribute, so the page script sorts them last
    assert page.count(" data-s-time=") == 2
    assert page.count(" data-s-odds=") == 3


# Synthetic worst case (not real data): long names with diacritics, every signal in one reason, the extreme odds,
# a negative edge, a draw pick, all five levels and rows with every optional value missing.
EVERY_SIGNAL = (
    "Sure Bet Pattern; Strong Expert Signal; Positive Signal; Steam (+); Steam (-); Strange Odds (45); SR Edge; "
    "Market Confidence; (Risk: Rising Odds); (No Steam Confirmation); Out of contention; High rotation risk; "
    "Status LOCKED_DIRECT_RO16; High Value; Good Value; Close(34,50) > Fair(1,01)"
)
LONG_HOME = "Borussia Mönchengladbach II"
LONG_AWAY = "Śląsk Wrocław"
WORST_SR = (
    replace(SR_ROW, home=LONG_HOME, away=LONG_AWAY, level="strong", reason=EVERY_SIGNAL),
    replace(SR_ROW, home=LONG_AWAY, away=LONG_HOME, pick="X", level="consider", odds=PickOdds(1.01, 1.01, 1.01)),
    replace(
        SR_ROW, home="Real Sociedad B", away="Górnik Łęczna", pick="2", level="neutral", odds=PickOdds(34.5, 34.5, 30.0)
    ),
    replace(
        SR_ROW, home="Zagłębie Sosnowiec", level="caution", sr=SrFacts(-0.12, -0.3, -45.0, 0.5, "/Zaglebie/3/", None)
    ),
    replace(
        SR_ROW,
        home="Nieznany Klub",
        level="avoid",
        reason="-",
        kickoff=None,
        odds=PickOdds(None, None, None),
        sr=SrFacts(edge=None, steam=None, ao=0.0, quality=0.0, home_href=None, away_href=None),
    ),
)
WORST_CUP_TEAM = replace(TEAM, team=LONG_HOME, edge=-0.12, reason=EVERY_SIGNAL, close=34.5)
WORST_CUPS = (
    replace(
        CUP_ROW,
        home=LONG_HOME,
        away=LONG_AWAY,
        level="strong",
        reason=EVERY_SIGNAL,
        cup=replace(CUP_FACTS, home=replace(WORST_CUP_TEAM, level="strong")),
    ),
    replace(
        CUP_ROW,
        home=LONG_AWAY,
        level="caution",
        odds=PickOdds(1.01, 1.01, 1.01),
        cup=replace(CUP_FACTS, home=replace(TEAM, team=LONG_AWAY, level="caution", close=1.01)),
    ),
    replace(
        CUP_ROW,
        home="Lokomotiv Płowdiw",
        level="avoid",
        day=None,
        kickoff=None,
        odds=PickOdds(None, None, None),
        # A match without soccer-rating data: no odds, score or edge for either team
        cup=CupFacts(
            12.0,
            18.0,
            70.0,
            replace(TEAM, team="Lokomotiv Płowdiw", level="avoid", status="OUT", close=None, score=None, edge=None),
            replace(TEAM, team="Away FC", level="neutral", win_pct=70.0, close=None, score=None, edge=None),
        ),
    ),
)


def filter_counts(section: str, name: str) -> list[int]:
    return [int(n) for n in re.findall(rf'name="{name}" value="[^"]*" checked>.*?\((\d+)\)</span></label>', section)]


def test_render_worst_case() -> None:
    page = render_page(page_data(WORST_SR, (el_section(*WORST_CUPS),)), ENV)

    for key, rows, names in (
        ("sr", WORST_SR, ("level", "league", "pick")),
        ("full", WORST_CUPS, ("level", "league", "status")),
    ):
        section = view_of(page, key)
        assert section.count('<tr class="m ') == len(rows)
        for name in names:
            assert sum(filter_counts(section, name)) == len(rows), name
        for level in {row.level for row in rows}:
            assert section.count(f'<tr class="m {level}"') == sum(row.level == level for row in rows)
    assert escape(LONG_HOME) in page
    assert escape(LONG_AWAY) in page
    if snapshot_dir := os.environ.get("PAGE_SNAPSHOT_DIR"):
        Path(snapshot_dir).joinpath("page-worst.html").write_text(page, encoding="utf-8", newline="")


WORD_JOINER = chr(0x2060)
NBSP = chr(0xA0)


def test_render_joins_the_last_two_words_of_headings_only_when_short() -> None:
    monday = replace(SR_ROW, day=date(2026, 3, 2), kickoff=None)
    page = render_page(page_data((SR_ROW, monday), (el_section(CUP_ROW), cup_section_without_data("ecl"))), ENV)

    assert "<h1>Europejskie puchary: faza&nbsp;ligowa</h1>" in page
    # A heading with markup keeps its own no-break span
    assert 'typy na <span class="nw">' in page
    # A long last pair stays breakable, so it never overflows a narrow phone
    assert "Poniedziałek, 2.03 <small" in page
    assert "Środa,&nbsp;4.03 <small" in page
    assert "Liga Europy,&nbsp;4.03 <small" in page
    assert '<h2 class="nodata">Liga&nbsp;Konferencji</h2>' in page


def test_render_joins_hyphens_in_shown_names_only() -> None:
    row = replace(
        SR_ROW,
        home="Bosnia-Herzegovina",
        group_name="Premijer-Liga",
        sr=replace(SR_FACTS, home_href="/Bosnia-Herzegovina/1/"),
    )

    page = render_page(page_data((row,), ()), ENV)

    assert f"<b>Bosnia-{WORD_JOINER}Herzegovina</b>" in page
    assert f'translate="no">Bosnia-{WORD_JOINER}Herzegovina</a>' in page
    assert f"Premijer-{WORD_JOINER}Liga" in page
    assert f"z soccer-{WORD_JOINER}rating.com" in page.replace("&nbsp;", " ")
    assert 'data-teams="bosnia-herzegovina away fc"' in page
    assert 'href="https://www.soccer-rating.com/Bosnia-Herzegovina/1/"' in page
    # No joiner in any tag: attributes, data values and URLs stay as they are
    assert not [tag for tag in re.findall("<[^>]*>", page) if WORD_JOINER in tag]


def test_render_binds_short_words_in_the_explanations() -> None:
    page = render_page(page_data((SR_ROW,), ()), ENV)

    assert f"co najmniej 50 i{NBSP}jest" in page
    assert f"Zakładka „Soccer-{WORD_JOINER}rating”" in page


def test_render_shows_missing_soccer_rating_values_as_missing() -> None:
    # Home has soccer-rating data with a real zero score and edge; away has none
    facts = replace(CUP_FACTS, home=replace(TEAM, score=0.0, edge=0.0), away=replace(TEAM, score=None, edge=None))
    sr_row = replace(SR_ROW, sr=replace(SR_FACTS, steam=None))

    text = text_of(render_page(page_data((sr_row,), (el_section(replace(CUP_ROW, cup=facts)),)), ENV))

    assert '<span role="cell">0,00</span><span role="cell">brak danych</span>' in text
    assert '<span role="cell">+0 pp</span><span role="cell">brak danych</span>' in text
    assert "Ruch kursu</button></dt> <dd>brak danych</dd>" in text


def test_render_shows_a_match_without_soccer_rating_quality_as_missing() -> None:
    row = replace(SR_ROW, odds=PickOdds(3.3, 3.3, None), sr=replace(SR_FACTS, edge=None, quality=0.0))

    text = text_of(render_page(page_data((row,), ()), ENV))

    assert "Przewaga modelu</button></dt> <dd>brak danych</dd>" in text
    assert "Kurs uczciwy</button></dt> <dd>brak danych</dd>" in text


def test_render_filters_on_the_shown_values() -> None:
    team = replace(TEAM, win_pct=54.96, value=60.04)
    cup = replace(CUP_ROW, odds=PickOdds(1.8, 1.604, 1.5), cup=replace(CUP_FACTS, home=team))
    sr = replace(SR_ROW, score=0.704, odds=PickOdds(1.8, 1.604, 1.5))

    page = render_page(page_data((sr,), (el_section(cup),)), ENV)

    # 54,96 is shown as 55,0, so a minimum of 55 keeps the row
    assert 'data-win="55.0"' in page
    assert 'data-range="win" data-bound="min" data-min="55"' in page
    assert 'data-value="60.0"' in page
    assert page.count('data-odds="1.6"') == 2
    assert 'data-ocena="0.7"' in page
