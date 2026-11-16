"""Standard mode: The Analyst fixtures and predicted table, enriched with soccer-rating signals."""

import numpy as np
import pandas as pd

from src.analyzer.config import LEAGUE_TABLE_TEAMS, LINEUP_DIFF_SCALE, ROUND_FIXTURES, W_LINEUP
from src.analyzer.errors import AnalyzerInputError
from src.analyzer.names import norm_key
from src.analyzer.recommendations import (
    SIGNAL_REPORT_COLUMNS,
    format_recommendations,
    recommendation_rank,
    round_numeric,
)
from src.analyzer.soccer_rating import expert_score

LEAGUE_NAMES = {"cl": "CHAMPIONS LEAGUE", "el": "EUROPA LEAGUE"}

# Ranking column -> (home row source, away row source); a ranking has one row per team and match
PERSPECTIVE_COLUMNS = {
    "Team": ("HomeTeamName", "AwayTeamName"),
    "Opp": ("AwayTeamName", "HomeTeamName"),
    "TeamWinProb%": ("HomeWin%", "AwayWin%"),
    "TeamMot": ("Mot_H", "Mot_A"),
    "TeamRotRisk": ("Risk_H", "Risk_A"),
    "TeamStatus": ("Status_H", "Status_A"),
    "Val": ("Val_H", "Val_A"),
    "OppMot": ("Mot_A", "Mot_H"),
    "OppStatus": ("Status_A", "Status_H"),
    "SR_edge": ("edge_1", "edge_2"),
    "sr_quality": ("sr_quality", "sr_quality"),
    "srDropping": ("srDropping", "srDropping"),
    "strangeOdds": ("strangeOdds", "strangeOdds"),
    "do_drop": ("do_drop", "do_drop"),
    "Close": ("close_1", "close_2"),
    "Fair": ("fair_1", "fair_2"),
    "matchExpertScore": ("matchExpertScore", "matchExpertScore"),
    "matchPick12": ("matchPick12", "matchPick12"),
}

REPORT_COLUMNS = {
    "Team": "team",
    "Opp": "opp",
    "TeamWinProb%": "teamWinProb%",
    "TeamRotRisk": "teamRotRisk",
    "TeamMot": "teamMot",
    "OppMot": "oppMot",
    "TeamStatus": "teamStatus",
    "OppStatus": "oppStatus",
    "expertScore": "expertScore",
    "sr_quality": "srCompleteness",
    **SIGNAL_REPORT_COLUMNS,
}


def validated_inputs(fixtures: pd.DataFrame, table: pd.DataFrame, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fixtures with HomeKey/AwayKey and the table with TeamKey; raises AnalyzerInputError on a wrong format."""
    league_name = LEAGUE_NAMES[prefix]
    if len(table) != LEAGUE_TABLE_TEAMS:
        raise AnalyzerInputError(f"{league_name} table must have {LEAGUE_TABLE_TEAMS} teams.")
    if len(fixtures) != ROUND_FIXTURES:
        raise AnalyzerInputError(f"{league_name} fixtures must have {ROUND_FIXTURES} matches.")

    fixtures = fixtures.assign(HomeKey=fixtures["HomeTeam"].map(norm_key), AwayKey=fixtures["AwayTeam"].map(norm_key))
    table = table.assign(TeamKey=table["TEAM"].map(norm_key))

    used = set(fixtures["HomeKey"]).union(set(fixtures["AwayKey"]))
    if missing := sorted(used - set(table["TeamKey"])):
        raise AnalyzerInputError(f"Missing teams in {prefix}_table: {missing}")
    return fixtures, table


def match_frame(fixtures: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Fixtures with both teams' status, motivation and rotation risk and win probabilities normalised to sum 1."""
    t_clean = table[["TeamKey", "TEAM", "Status", "Motivation", "RotRisk"]].set_index("TeamKey")

    f = fixtures.merge(t_clean, left_on="HomeKey", right_index=True)
    f = f.rename(columns={"TEAM": "HomeTeamName", "Status": "Status_H", "Motivation": "Mot_H", "RotRisk": "Risk_H"})
    f = f.merge(t_clean, left_on="AwayKey", right_index=True)
    f = f.rename(columns={"TEAM": "AwayTeamName", "Status": "Status_A", "Motivation": "Mot_A", "RotRisk": "Risk_A"})

    p_sum = (f["HomeWin%"] + f["Draw%"] + f["AwayWin%"]).replace(0, 1)
    for c in ["HomeWin%", "Draw%", "AwayWin%"]:
        f[c] = (f[c] / p_sum).fillna(0.0)
    return f


def with_match_pick(f: pd.DataFrame) -> pd.DataFrame:
    """Adds the home-side expert score (with the lineup term) and the 1/2 pick it implies."""
    f = f.copy()
    s_lineup = (f["lineup_adv"] / LINEUP_DIFF_SCALE).fillna(0.0)
    f["matchExpertScore"] = expert_score(f) + W_LINEUP * s_lineup
    f["matchPick12"] = np.where(f["matchExpertScore"] > 0, "1", "2")
    # Without SR data there are no odds: 99 (no bet)
    for col in ["close_1", "close_2", "fair_1", "fair_2"]:
        if col not in f.columns:
            f[col] = 99.0
    return f


def team_ranking(f: pd.DataFrame) -> pd.DataFrame:
    """One row per team and match, seen from that team (away rows flip expertScore, srDropping and do_drop)."""
    names = list(PERSPECTIVE_COLUMNS)
    h = f[[home for home, _ in PERSPECTIVE_COLUMNS.values()]].set_axis(names, axis=1)
    a = f[[away for _, away in PERSPECTIVE_COLUMNS.values()]].set_axis(names, axis=1)
    h = h.assign(is_home=True, expertScore=h["matchExpertScore"])
    a = a.assign(is_home=False, expertScore=-a["matchExpertScore"], srDropping=-a["srDropping"], do_drop=-a["do_drop"])

    ranking = pd.concat([h, a], ignore_index=True)
    for c in ["SR_edge", "sr_quality", "srDropping", "strangeOdds"]:
        ranking[c] = ranking[c].fillna(0.0)
    ranking["ValFinal"] = ranking["Val"]
    return ranking


def league_report(f: pd.DataFrame, decimal: str) -> pd.DataFrame:
    """The report rows, best recommendation and highest value first (`decimal` separates numbers in reasons)."""
    ranking = format_recommendations(team_ranking(with_match_pick(f)), allow_draws=False, decimal=decimal)
    ranking = ranking.assign(_sort_rank=recommendation_rank(ranking["recommendation"]))
    ranking = ranking.sort_values(["_sort_rank", "ValFinal"], ascending=[True, False])
    return round_numeric(ranking.rename(columns=REPORT_COLUMNS)[list(REPORT_COLUMNS.values())])
