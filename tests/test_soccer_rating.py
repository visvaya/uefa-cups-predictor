import pandas as pd
import pytest

from analyzer import sr_only
from analyzer.recommendations import CONSIDER, NEUTRAL, STRONG_BUY
from analyzer.soccer_rating import add_soccer_rating_features

FIXTURES = pd.DataFrame({"HomeKey": ["home"], "AwayKey": ["away"]})
SR_MATCH = {
    "HomeKey": "home",
    "AwayKey": "away",
    "oo": 2.0,
    "do": 12.0,
    "ao": -36.0,
    "open_1": 1.7,
    "open_x": 4.0,
    "open_2": 5.5,
    "close_1": 1.5,
    "close_x": 4.2,
    "close_2": 6.5,
    "fair_1": 1.4,
    "fair_x": 4.8,
    "fair_2": 8.0,
    "odds_distance": 0.0,
    "match_confidence": "HIGH",
    "team_rating_home": 1900.0,
    "team_rating_away": 1750.0,
    "lineup_rating_home_today": 40.0,
    "lineup_rating_away_today": 30.0,
    "lineup_type_today": "expected",
}


def test_add_soccer_rating_features_reads_value_ratings_of_the_merged_odds() -> None:
    features = add_soccer_rating_features(FIXTURES, pd.DataFrame([SR_MATCH]))

    assert features.loc[0, "do_drop"] == pytest.approx(0.10)
    assert features.loc[0, "strangeOdds"] == -36.0


def test_sr_only_recommends_an_away_favourite_without_the_sure_bet_pattern() -> None:
    # Odds unchanged since opening (no steam, so no sure bet); the market and the ratings favour the away team
    snapshot = pd.DataFrame(
        [
            {
                "match_id": "m1",
                "home_id": 1,
                "away_id": 2,
                "open_1": 4.5,
                "open_x": 3.8,
                "open_2": 1.8,
                "close_1": 4.5,
                "close_x": 3.8,
                "close_2": 1.8,
                "fair_1": 4.5,
                "fair_x": 3.8,
                "fair_2": 1.8,
                "odds_distance": 0.0,
                "match_confidence": "HIGH",
                "team_rating_home": 1700.0,
                "team_rating_away": 1850.0,
            }
        ]
    )

    report = sr_only.sr_only_report(snapshot, {1: "Home FC", 2: "Away FC"}, {}, ".")

    row = report.iloc[0]
    assert (row["pick"], row["recommendation"]) == ("2", CONSIDER)
    assert row["expertScore"] > 0.5


def _sr_match(match_id: str, **odds: float) -> dict[str, object]:
    """One snapshot row with even ratings, unchanged value ratings and the given odds."""
    return {
        "match_id": match_id,
        "home_id": 1,
        "away_id": 2,
        "oo": 0.0,
        "do": 0.0,
        "ao": 0.0,
        "odds_distance": 0.0,
        "match_confidence": "HIGH",
        "team_rating_home": 1500.0,
        "team_rating_away": 1500.0,
        **odds,
    }


def _sr_report(*matches: dict[str, object]) -> pd.DataFrame:
    names = {1: "Home FC", 2: "Away FC", 3: "No Odds FC", 4: "Other FC"}
    return sr_only.sr_only_report(pd.DataFrame(list(matches)), names, {}, ".")


EVEN_FALLING_HOME = {
    "open_1": 2.00,
    "open_x": 3.40,
    "open_2": 2.00,
    "close_1": 1.95,
    "close_x": 3.40,
    "close_2": 2.05,
    "fair_1": 2.00,
    "fair_x": 3.40,
    "fair_2": 2.00,
}


def test_sr_only_draw_pick_is_not_strong_buy_through_one_side_sure_bet() -> None:
    row = _sr_report(_sr_match("m1", **EVEN_FALLING_HOME)).iloc[0]

    assert row["pick"] == "X"
    assert row["recommendation"] != STRONG_BUY


def test_sr_only_missing_team_rating_keeps_the_market_pick() -> None:
    odds = {"open_1": 1.50, "open_x": 4.2, "open_2": 6.0, "close_1": 1.45, "close_x": 4.2, "close_2": 6.5}
    match = _sr_match("m1", **odds, fair_1=1.40, fair_x=4.5, fair_2=7.0, team_rating_away=float("nan"))

    row = _sr_report(match).iloc[0]

    assert row["pick"] == "1"
    assert row["expertScore"] > 0


def test_sr_only_match_without_valid_odds_stays_neutral() -> None:
    nan = float("nan")
    no_odds = {k: nan for k in EVEN_FALLING_HOME}

    report = _sr_report(_sr_match("m1", **EVEN_FALLING_HOME), _sr_match("m2", **no_odds, home_id=3, away_id=4))

    assert report.loc[report["homeTeam"] == "No Odds FC", "recommendation"].tolist() == [NEUTRAL]


def test_sr_only_draw_label_does_not_depend_on_which_side_is_at_home() -> None:
    odds = {"open_1": 2.60, "open_x": 3.20, "open_2": 2.70, "close_1": 2.60, "close_x": 3.20, "close_2": 2.70}
    match = _sr_match("m1", **odds, fair_1=2.90, fair_x=3.20, fair_2=2.45)
    swapped = {"open_1": 2.70, "open_x": 3.20, "open_2": 2.60, "close_1": 2.70, "close_x": 3.20, "close_2": 2.60}
    mirror = _sr_match("m2", **swapped, fair_1=2.45, fair_x=3.20, fair_2=2.90, home_id=3, away_id=4)

    report = _sr_report(match, mirror)

    assert report["pick"].tolist() == ["X", "X"]
    assert report["recommendation"].nunique() == 1
    assert report["srEdge"].nunique() == 1


def test_sr_only_steam_follows_the_picked_teams_own_odds() -> None:
    # The favourite's odds rose (1.60 to 1.65) while the outsider's rose more: no steam on the pick
    odds = {"open_1": 1.60, "open_x": 4.0, "open_2": 5.0, "close_1": 1.65, "close_x": 4.0, "close_2": 6.5}
    row = _sr_report(_sr_match("m1", **odds, fair_1=1.70, fair_x=4.0, fair_2=5.0)).iloc[0]

    assert row["pick"] == "1"
    assert row["srDropping"] < 0
    assert "Steam (+)" not in row["reason"]
    assert "Sure Bet Pattern" not in row["reason"]
