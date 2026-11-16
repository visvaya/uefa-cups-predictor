import pandas as pd
import pytest

from src.analyzer import sr_only
from src.analyzer.soccer_rating import add_soccer_rating_features

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


def test_sr_only_away_row_carries_the_score_of_the_away_team() -> None:
    match = pd.DataFrame(
        {
            "HomeTeamName": ["Home FC"],
            "AwayTeamName": ["Away FC"],
            "close_1": [5.0],
            "close_2": [1.6],
            "fair_1": [6.5],
            "fair_2": [1.5],
            "edge_1": [-0.02],
            "edge_2": [0.04],
            "steam_diff": [-0.3],
            "do_drop": [-0.02],
            "expertScore": [-0.9],
        }
    )

    ranking = sr_only.team_ranking(match).set_index("Team")

    assert ranking.loc["Home FC", "expertScore"] == -0.9
    assert ranking.loc["Away FC", "expertScore"] == 0.9
