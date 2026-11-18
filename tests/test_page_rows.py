from datetime import date

import numpy as np
import pandas as pd
import pytest

from analyzer.page.model import PickOdds
from analyzer.page.sr_rows import sr_match_rows
from analyzer.page.texts import kickoff_at
from analyzer.sr_only import sr_only_ranking
from tests.test_analyze import _fixture_sr_only

DAY = date(2026, 1, 28)


@pytest.fixture(scope="module")
def ranking() -> pd.DataFrame:
    return _fixture_sr_only(sr_only_ranking)


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


def test_sr_rows_map_missing_facts_to_zero(ranking: pd.DataFrame) -> None:
    row = next(row for row in sr_match_rows(ranking) if row.home == "ID_999")

    assert row.sr is not None
    assert (row.sr.steam, row.sr.ao, row.sr.quality) == (0.0, -40.0, 0.0)


def test_sr_rows_round_the_score_as_the_report_shows_it(ranking: pd.DataFrame) -> None:
    (row,) = sr_match_rows(ranking[ranking["HomeTeamName"] == "Alpha FC"].assign(expertScore=0.4567))

    assert row.score == 0.46
