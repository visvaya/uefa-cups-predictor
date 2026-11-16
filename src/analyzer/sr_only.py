"""SR-only mode: recommendations from a soccer-rating snapshot alone (the snapshot is the fixture list)."""

import numpy as np
import pandas as pd

from src.analyzer.config import DRAW_ZONE_MAX_SCORE
from src.analyzer.data import ODDS_NUMERIC_COLUMNS, cast_numeric
from src.analyzer.recommendations import format_recommendations, recommendation_rank, round_numeric
from src.analyzer.soccer_rating import expert_score, sr_quality, with_market_signals, with_value_rating_signals

REPORT_COLUMNS = {
    "HomeTeamName": "homeTeam",
    "AwayTeamName": "awayTeam",
    "expertScore": "expertScore",
    "pick12": "pick",
    "srCompleteness": "srCompleteness",
    "SR_edge": "srEdge",
    "srDropping": "srDropping",
    "strangeOdds": "strangeOdds",
    "recommendation": "recommendation",
    "reason": "reason",
}


def with_team_names(
    sr: pd.DataFrame, id_to_name: dict[int, str], today_names: dict[str, dict[str, str]]
) -> pd.DataFrame:
    """Adds HomeTeamName and AwayTeamName: today's names by match id first, then club_meta names by team id."""

    def get_name(row: pd.Series, side: str) -> str:
        mid = row.get("match_id")
        if mid and mid in today_names:
            return today_names[mid][f"{side}_team"]
        tid = row.get(f"{side}_id")
        if pd.notna(tid):
            return id_to_name.get(int(tid), f"ID_{tid}")
        return f"UNK_{side}"

    sr = sr.copy()
    sr["HomeTeamName"] = sr.apply(lambda r: get_name(r, "home"), axis=1)
    sr["AwayTeamName"] = sr.apply(lambda r: get_name(r, "away"), axis=1)
    return sr


def match_features(f2: pd.DataFrame) -> pd.DataFrame:
    """Market signals, value-rating signals, srCompleteness, expertScore and the 1/X/2 pick of every match."""
    valid_mask = (f2[["close_1", "close_x", "close_2", "fair_1", "fair_x", "fair_2"]] > 1.0).all(axis=1)

    f2 = f2.copy()
    for c in ["edge_1", "edge_x", "edge_2", "steam_diff", "prob_gap_1", "prob_gap_2", "rating_diff", "lineup_adv"]:
        f2[c] = 0.0
    if valid_mask.any():
        f2 = with_market_signals(f2, valid_mask)
    f2["srDropping"] = f2["steam_diff"]
    f2 = with_value_rating_signals(f2)
    f2["srCompleteness"] = sr_quality(f2, valid_mask)

    f2["expertScore"] = expert_score(f2)
    # 1 above the draw zone, 2 below it, X inside it (edge rules may still promote the X)
    conditions = [f2["expertScore"] > DRAW_ZONE_MAX_SCORE, f2["expertScore"] < -DRAW_ZONE_MAX_SCORE]
    f2["pick12"] = np.select(conditions, ["1", "2"], default="X")
    return f2


def team_ranking(f2: pd.DataFrame) -> pd.DataFrame:
    """One row per team and match; away rows flip srDropping and do_drop (expertScore stays the home score)."""
    h = f2.assign(
        Team=f2["HomeTeamName"],
        Opp=f2["AwayTeamName"],
        Close=f2["close_1"].fillna(99.0),
        Fair=f2["fair_1"].fillna(99.0),
        SR_edge=f2["edge_1"],
        srDropping=f2["steam_diff"],
        is_home=True,
    )
    a = f2.assign(
        Team=f2["AwayTeamName"],
        Opp=f2["HomeTeamName"],
        Close=f2["close_2"].fillna(99.0),
        Fair=f2["fair_2"].fillna(99.0),
        SR_edge=f2["edge_2"].fillna(0),
        srDropping=-f2["steam_diff"],
        do_drop=-f2["do_drop"],
        is_home=False,
    )
    # No Analyst data: every team is in play without rotation risk; value and motivation default to 0 in the rules
    return pd.concat([h, a], ignore_index=True).assign(TeamStatus="IN_PLAY", TeamRotRisk=1.0)


def favoured_sides(ranking: pd.DataFrame) -> pd.DataFrame:
    """The favoured side of every match (the home row for X), best recommendation and strongest score first."""
    is_pick_1 = ranking["pick12"] == "1"
    is_pick_2 = ranking["pick12"] == "2"
    is_pick_x = ranking["pick12"] == "X"
    match_mask = (is_pick_1 & ranking["is_home"]) | (is_pick_2 & ~ranking["is_home"]) | (is_pick_x & ranking["is_home"])

    ranking = ranking.assign(
        _sort_rank=recommendation_rank(ranking["recommendation"]), _abs_score=ranking["expertScore"].abs()
    )
    return ranking[match_mask].sort_values(["_sort_rank", "_abs_score"], ascending=[True, False])


def sr_only_report(
    sr: pd.DataFrame, id_to_name: dict[int, str], today_names: dict[str, dict[str, str]]
) -> pd.DataFrame:
    """The SR-only report rows for a raw soccer-rating snapshot."""
    matches = match_features(with_team_names(cast_numeric(sr, ODDS_NUMERIC_COLUMNS), id_to_name, today_names))
    ranking = favoured_sides(format_recommendations(team_ranking(matches), allow_draws=True))

    report = ranking.rename(columns=REPORT_COLUMNS)
    for c in REPORT_COLUMNS.values():
        if c not in report.columns:
            report[c] = 0
    return round_numeric(report)[list(REPORT_COLUMNS.values())]
