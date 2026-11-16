import pandas as pd
import pytest

from analyzer import sr_only
from analyzer.recommendations import CONSIDER
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
