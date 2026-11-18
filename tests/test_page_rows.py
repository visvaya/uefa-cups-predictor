from datetime import date

import numpy as np
import pandas as pd
import pytest

from analyzer.cli import league_frames
from analyzer.league import league_ranking
from analyzer.page.cup_rows import cup_section, cup_section_without_data
from analyzer.page.model import CupSection, PickOdds, TeamFacts
from analyzer.page.sr_rows import odds_or_none, sr_match_rows
from analyzer.page.texts import CUP_NAMES, LEVEL_NAMES, kickoff_at
from analyzer.sr_only import sr_only_ranking
from tests.inputs import el_base_dir, fixture_sr_only

DAY = date(2026, 1, 28)


@pytest.fixture(scope="module")
def ranking() -> pd.DataFrame:
    return fixture_sr_only(sr_only_ranking)


def test_sr_rows_take_the_today_row_and_order_by_day_kickoff_and_home(ranking: pd.DataFrame) -> None:
    rows = sr_match_rows(ranking)

    # Kickoffs first (equal ones by home name), then the matches without a time, by folded home name
    assert [row.home for row in rows] == [
        "Alpha FC",
        "Epsilon Club",
        "Bodø/Glimt",
        "Eta Athletic",
        "Gamma SC",
        "ID_999",
        "Kappa Sport",
        "Nu Albion",
        "Omicron FC",
    ]
    alpha = rows[0]
    assert (alpha.away, alpha.pick, alpha.level, alpha.day) == ("Beta United", "1", "strong", DAY)
    assert alpha.reason == "Sure Bet Pattern; Positive Signal; Steam (+)"
    assert alpha.kickoff == kickoff_at(DAY, "20:00")
    assert (alpha.group, alpha.group_name) == ("XX1", "Synthetic League")
    assert alpha.odds == PickOdds(open=1.8, close=1.6, fair=1.5)
    assert alpha.score == pytest.approx(1.0)
    assert alpha.sr is not None
    assert alpha.sr.edge == pytest.approx(0.04)
    assert alpha.sr.steam == pytest.approx(0.12)
    assert (alpha.sr.ao, alpha.sr.quality) == (0.0, 1.0)
    assert (alpha.sr.home_href, alpha.sr.away_href) == ("/Alpha-FC/201/", "/Beta-United/202/")
    assert alpha.cup is None


def test_sr_rows_take_the_picked_outcome_odds(ranking: pd.DataFrame) -> None:
    rows = {row.home: row for row in sr_match_rows(ranking)}

    assert rows["Epsilon Club"].pick == "X"
    assert rows["Epsilon Club"].odds == PickOdds(open=3.4, close=3.2, fair=3.1)
    assert rows["Gamma SC"].pick == "2"
    assert rows["Gamma SC"].odds == PickOdds(open=1.8, close=1.6, fair=1.5)


def test_sr_rows_without_today_row(ranking: pd.DataFrame) -> None:
    gamma = next(row for row in sr_match_rows(ranking) if row.home == "Gamma SC")

    assert gamma.kickoff is None
    assert (gamma.group, gamma.group_name) == ("XX1", "XX1")
    assert gamma.sr is not None
    assert (gamma.sr.home_href, gamma.sr.away_href) == (None, None)


def test_sr_rows_map_missing_odds_to_none(ranking: pd.DataFrame) -> None:
    alpha = ranking[ranking["HomeTeamName"] == "Alpha FC"].assign(open_1=np.nan, close_1=99.0)

    (row,) = sr_match_rows(alpha)

    assert row.odds == PickOdds(open=None, close=None, fair=1.5)


def test_sr_rows_map_an_empty_href_to_none(ranking: pd.DataFrame) -> None:
    (row,) = sr_match_rows(ranking[ranking["HomeTeamName"] == "Alpha FC"].assign(home_href=""))

    assert row.sr is not None
    assert (row.sr.home_href, row.sr.away_href) == (None, "/Beta-United/202/")


def test_sr_rows_leave_a_missing_steam_empty(ranking: pd.DataFrame) -> None:
    rows = {row.home: row for row in sr_match_rows(ranking)}

    # ID_999 has no odds movement (NaN): no value, not a zero
    assert rows["ID_999"].sr is not None
    assert (rows["ID_999"].sr.steam, rows["ID_999"].sr.ao, rows["ID_999"].sr.quality) == (None, -40.0, 0.0)
    assert rows["Alpha FC"].sr is not None
    assert rows["Alpha FC"].sr.steam == pytest.approx(0.12)


def test_sr_rows_round_the_score_as_the_report_shows_it(ranking: pd.DataFrame) -> None:
    (row,) = sr_match_rows(ranking[ranking["HomeTeamName"] == "Alpha FC"].assign(expertScore=0.4567))

    assert row.score == 0.46


@pytest.fixture(scope="module")
def el_frames(tmp_path_factory: pytest.TempPathFactory) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The EL example's match frame and its team rows, as the page builds them."""
    f, _ = league_frames(el_base_dir(tmp_path_factory.mktemp("el")), "el")
    return f, league_ranking(f, ",")


def _team_row(match_index: int, is_home: bool, **values: object) -> dict[str, object]:
    """One hand-built team row of `league_ranking`, neutral and IN_PLAY unless `values` say otherwise."""
    row: dict[str, object] = {
        "match_index": match_index,
        "is_home": is_home,
        "TeamWinProb%": 40.0,
        "TeamMot": 70.0,
        "TeamStatus": "IN_PLAY",
        "TeamRotRisk": 1.0,
        "ValFinal": 30.0,
        "expertScore": 0.0,
        "SR_edge": 0.0,
        "sr_quality": 0.0,
        "Close": np.nan,
        "recommendation": "NEUTRAL",
        "reason": "-",
    }
    return {**row, **values}


# One match without soccer-rating data: the fixtures' names differ from the table's
NO_SR_MATCH = pd.DataFrame(
    {
        "HomeTeam": ["Home FC"],
        "AwayTeam": ["Away FC"],
        "HomeTeamName": ["Home Table"],
        "AwayTeamName": ["Away Table"],
        "HomeWin%": [0.4],
        "Draw%": [0.25],
        "AwayWin%": [0.35],
    }
)


def test_cup_pick_is_the_better_rated_side(el_frames: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    f, ranking = el_frames
    section = cup_section("el", f, ranking)
    rows = {row.home: row for row in section.rows}

    assert (rows["Team O"].pick, rows["Team O"].level) == ("1", "consider")
    # Both sides neutral: Team R (away) has the higher value
    assert (rows["Team Q"].pick, rows["Team Q"].level) == ("2", "neutral")
    assert rows["Team Q"].reason == ranking.loc[ranking["Team"] == "Team R", "reason"].item()
    # A better level wins over a higher value
    worse = ranking.assign(recommendation=ranking["recommendation"].where(ranking["Team"] != "Team R", "AVOID"))
    team_q = next(row for row in cup_section("el", f, worse).rows if row.home == "Team Q")
    assert team_q.pick == "1"


def test_cup_rows_order_by_level_then_value(el_frames: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    rows = cup_section("el", *el_frames).rows

    assert [row.home for row in rows[:4]] == ["Team W", "Team O", "Team A", "Team Q"]
    keys = []
    for row in rows:
        assert row.cup is not None
        picked = row.cup.home if row.pick == "1" else row.cup.away
        keys.append((list(LEVEL_NAMES).index(row.level), -picked.value))
    assert keys == sorted(keys)


def test_cup_rows_carry_both_teams(el_frames: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    f, ranking = el_frames
    section = cup_section("el", f, ranking)
    team_o = next(row for row in section.rows if row.home == "Team O")
    day = date(2026, 1, 28)

    assert (section.prefix, section.name, len(section.rows)) == ("el", CUP_NAMES["el"], len(f))
    assert (team_o.away, team_o.group, team_o.group_name, team_o.sr) == ("Team P", "el", CUP_NAMES["el"], None)
    assert (team_o.day, team_o.kickoff) == (day, kickoff_at(day, "18:45"))
    assert team_o.odds == PickOdds(open=1.8, close=1.65, fair=1.55)
    assert team_o.score == pytest.approx(0.9)
    assert team_o.cup is not None
    assert (team_o.cup.home_win_pct, team_o.cup.draw_pct, team_o.cup.away_win_pct) == (60.0, 20.0, 20.0)
    reason_o = ranking.loc[ranking["Team"] == "Team O", "reason"].item()
    assert team_o.reason == reason_o
    assert team_o.cup.home == TeamFacts(
        team="Team O",
        win_pct=60.0,
        motivation=100.0,
        status="IN_PLAY",
        rotation=1.0,
        value=60.0,
        score=0.9,
        edge=0.04,
        level="consider",
        reason=reason_o,
        close=1.65,
    )
    assert (team_o.cup.away.team, team_o.cup.away.level, team_o.cup.away.close) == ("Team P", "neutral", 5.2)


def test_cup_rows_of_matches_without_odds_or_kickoff(el_frames: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    rows = {row.home: row for row in cup_section("el", *el_frames).rows}

    # Team A - Team B has odds but no row in today's file; Team C - Team D has no soccer-rating match
    assert (rows["Team A"].day, rows["Team A"].kickoff) == (date(2026, 1, 28), None)
    team_c = rows["Team C"]
    assert (team_c.day, team_c.kickoff) == (None, None)
    assert team_c.odds == PickOdds(open=None, close=None, fair=None)
    assert team_c.cup is not None
    assert team_c.cup.home.close is None


def test_cup_pick_tie_goes_home() -> None:
    ranking = pd.DataFrame([_team_row(0, True), _team_row(0, False)])

    (row,) = cup_section("cl", NO_SR_MATCH, ranking).rows

    assert row.pick == "1"
    # Equal levels: the higher value wins even away
    (row,) = cup_section("cl", NO_SR_MATCH, ranking.assign(ValFinal=[30.0, 30.1])).rows
    assert row.pick == "2"


def test_cup_rows_without_soccer_rating_have_no_odds() -> None:
    ranking = pd.DataFrame([_team_row(0, True, recommendation="CONSIDER", reason="Good Value"), _team_row(0, False)])

    section = cup_section("ecl", NO_SR_MATCH, ranking)

    (row,) = section.rows
    assert section.name == CUP_NAMES["ecl"]
    assert (row.home, row.away, row.pick, row.level, row.reason) == (
        "Home FC",
        "Away FC",
        "1",
        "consider",
        "Good Value",
    )
    assert row.odds == PickOdds(open=None, close=None, fair=None)
    assert (row.day, row.kickoff) == (None, None)
    assert row.cup is not None
    assert (row.cup.home_win_pct, row.cup.draw_pct, row.cup.away_win_pct) == (40.0, 25.0, 35.0)
    assert (row.cup.away.team, row.cup.away.close) == ("Away FC", None)
    # Without soccer-rating data a team has no score or edge, not a zero
    assert (row.cup.home.score, row.cup.home.edge, row.score) == (None, None, None)


def test_cup_section_without_data_is_empty() -> None:
    assert cup_section_without_data("cl") == CupSection(prefix="cl", name=CUP_NAMES["cl"], rows=())


def test_sr_rows_without_quality_have_no_edge_or_fair_odds(ranking: pd.DataFrame) -> None:
    rows = {row.home: row for row in sr_match_rows(ranking)}

    # ID_999 has srCompleteness 0 and fair odds 0: no soccer-rating view of the match
    assert rows["ID_999"].sr is not None
    assert (rows["ID_999"].sr.edge, rows["ID_999"].odds.fair) == (None, None)
    assert rows["Alpha FC"].sr is not None
    assert rows["Alpha FC"].sr.edge == pytest.approx(0.04)


@pytest.mark.parametrize(
    ("value", "odds"), [(0.0, None), (0.99, None), (99.0, None), (float("nan"), None), (1.01, 1.01)]
)
def test_odds_below_one_are_missing(value: float, odds: float | None) -> None:
    assert odds_or_none(value) == odds


def test_sr_rows_take_the_draw_odds_movement_for_an_x_pick(ranking: pd.DataFrame) -> None:
    rows = {row.home: row for row in sr_match_rows(ranking)}
    epsilon = ranking.loc[ranking["HomeTeamName"] == "Epsilon Club"].iloc[0]

    assert rows["Epsilon Club"].pick == "X"
    assert epsilon["steam_x"] != epsilon["steam_1"]
    assert rows["Epsilon Club"].sr is not None
    assert rows["Epsilon Club"].sr.steam == pytest.approx(epsilon["steam_x"])
