"""Soccer-rating market features: probabilities, edges, steam, value-rating signals and data quality."""

import numpy as np
import pandas as pd

from analyzer.config import (
    DO_DROP_SCALE,
    HIGH_QUALITY_MAX_ODDS_DISTANCE,
    MIN_STEAM_ODDS,
    NEUTRAL_DRAW_PROB,
    NEUTRAL_SIDE_PROB,
    PARTIAL_SR_QUALITY,
    RATING_DIFF_SCALE,
    STRANGE_ODDS_MIN_ABS,
    W_CLOSE,
    W_GAP,
    W_RATING,
    W_STEAM,
)

SIDES = ["1", "x", "2"]


def with_value_rating_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Adds do_drop and strangeOdds from the OO/DO/AO value ratings (ROI %, not odds); 0.0 without them.

    do_drop = (DO - OO) / 100, on the steam scale (log odds): positive means the home value improved.
    """
    df = df.copy()
    df["do_drop"] = (df["do"] - df["oo"]) / 100.0 if "do" in df.columns and "oo" in df.columns else 0.0
    df["strangeOdds"] = np.where(df["ao"].abs() > STRANGE_ODDS_MIN_ABS, df["ao"], 0.0) if "ao" in df.columns else 0.0
    return df


def with_market_signals(df: pd.DataFrame, valid_mask: pd.Series) -> pd.DataFrame:
    """For rows with valid odds: normalised close and fair probabilities, edges, steam and the rating difference."""
    df = df.copy()
    inv_close = (
        (1.0 / df.loc[valid_mask, "close_1"])
        + (1.0 / df.loc[valid_mask, "close_x"])
        + (1.0 / df.loc[valid_mask, "close_2"])
    )
    inv_fair = (
        (1.0 / df.loc[valid_mask, "fair_1"])
        + (1.0 / df.loc[valid_mask, "fair_x"])
        + (1.0 / df.loc[valid_mask, "fair_2"])
    )

    for side in SIDES:
        p_fair = (1.0 / df.loc[valid_mask, f"fair_{side}"]) / inv_fair
        p_close = (1.0 / df.loc[valid_mask, f"close_{side}"]) / inv_close

        df.loc[valid_mask, f"edge_{side}"] = p_fair - p_close
        df.loc[valid_mask, f"p_close_{side}"] = p_close
        df.loc[valid_mask, f"p_fair_{side}"] = p_fair
        df.loc[valid_mask, f"prob_gap_{side}"] = p_close - p_fair

        # Steam: ln(open / close)
        open_v = df.loc[valid_mask, f"open_{side}"].clip(lower=MIN_STEAM_ODDS)
        close_v = df.loc[valid_mask, f"close_{side}"].clip(lower=MIN_STEAM_ODDS)
        df.loc[valid_mask, f"steam_{side}"] = np.log(open_v / close_v)

    df.loc[valid_mask, "steam_diff"] = df.loc[valid_mask, "steam_1"] - df.loc[valid_mask, "steam_2"]
    df.loc[valid_mask, "rating_diff"] = df.loc[valid_mask, "team_rating_home"] - df.loc[valid_mask, "team_rating_away"]
    return df


def sr_quality(df: pd.DataFrame, valid_mask: pd.Series) -> np.ndarray:
    """1.0 for a HIGH confidence match close to the fair odds, 0.5 for other valid SR rows, 0.0 without SR data."""
    has_sr = df["fair_1"].notna() & valid_mask
    return np.where(
        has_sr
        & (df.get("match_confidence", "LOW") == "HIGH")
        & (df["odds_distance"] <= HIGH_QUALITY_MAX_ODDS_DISTANCE),
        1.0,
        np.where(has_sr, PARTIAL_SR_QUALITY, 0.0),
    )


def add_soccer_rating_features(f: pd.DataFrame, sr: pd.DataFrame) -> pd.DataFrame:
    """Merges SR data into the fixtures and calculates value edges with robust normalization."""
    edge_cols = ["edge_1", "edge_x", "edge_2"]

    if sr.empty:
        f = f.copy()
        zero_cols = ["sr_quality", "steam_diff", "srDropping", "prob_gap_1", "prob_gap_2", "rating_diff", "lineup_adv"]
        for c in [*edge_cols, *zero_cols]:
            f[c] = 0.0

        for side in SIDES:
            f[f"p_close_{side}"] = NEUTRAL_SIDE_PROB if side != "x" else NEUTRAL_DRAW_PROB
            f[f"p_fair_{side}"] = NEUTRAL_SIDE_PROB  # also for x (kept as it was)

        return with_value_rating_signals(f)

    f2 = f.merge(sr, on=["HomeKey", "AwayKey"], how="left", suffixes=("", "_sr"))

    # Safety: Filter out rows with invalid or zero odds to avoid division by zero/Inf
    mkt_cols = ["close_1", "close_x", "close_2"]
    fair_cols = ["fair_1", "fair_x", "fair_2"]
    open_cols = ["open_1", "open_x", "open_2"]
    valid_mask = (f2[mkt_cols + fair_cols + open_cols] > 1.0).all(axis=1)

    # Initialize defaults
    for c in [*edge_cols, "steam_diff", "prob_gap_1", "prob_gap_2", "rating_diff", "lineup_adv", "sr_quality"]:
        f2[c] = 0.0

    # Initialize probabilities and steam to neutral defaults
    for side in SIDES:
        f2[f"p_close_{side}"] = NEUTRAL_DRAW_PROB if side == "x" else NEUTRAL_SIDE_PROB
        f2[f"p_fair_{side}"] = NEUTRAL_DRAW_PROB if side == "x" else NEUTRAL_SIDE_PROB
        f2[f"prob_gap_{side}"] = 0.0
        f2[f"steam_{side}"] = 0.0

    if valid_mask.any():
        f2 = with_market_signals(f2, valid_mask)
        # Lineup advantage (only if expected)
        f2["lineup_adv"] = np.where(
            f2["lineup_type_today"] == "expected", f2["lineup_rating_home_today"] - f2["lineup_rating_away_today"], 0.0
        )

    f2["sr_quality"] = sr_quality(f2, valid_mask)
    f2["srDropping"] = f2["steam_diff"]
    # After the merge, so the OO/DO/AO value ratings of the SR data are there
    return with_value_rating_signals(f2)


def coverage_report(f2: pd.DataFrame) -> list[str]:
    """Console lines on how many fixtures found their SR match, with up to three missing ones."""
    has_sr_raw = f2["fair_1"].notna()
    coverage = has_sr_raw.mean()
    lines = [f"INFO: Soccer-rating coverage: {coverage:.0%}"]
    if coverage < 1.0:
        missing = f2[~has_sr_raw][["HomeTeamName", "AwayTeamName"]].head(3)
        if not missing.empty:
            missing_list = [f"{r.HomeTeamName} vs {r.AwayTeamName}" for _, r in missing.iterrows()]
            lines.append(f"DEBUG: Missing SR matches: {', '.join(missing_list)}")
    return lines


def expert_score(df: pd.DataFrame) -> pd.Series:
    """Home-side expert score from rating, close odds, steam (with the DO bonus) and probability gap.

    Positive favours the home team. Standard mode adds the lineup term (`W_LINEUP`) to this sum.
    """
    # A missing team rating adds nothing, like the other terms (NaN would turn every pick into X)
    s_rating = df["rating_diff"].fillna(0.0) / RATING_DIFF_SCALE
    p1 = df.get("p_close_1", pd.Series(0.5, index=df.index)).fillna(0.5)
    p2 = df.get("p_close_2", pd.Series(0.5, index=df.index)).fillna(0.5)
    s_close = np.log((p1 / p2).clip(0.01, 100))
    s_steam = df["steam_diff"].fillna(0.0)
    s_gap = (df["prob_gap_1"] - df["prob_gap_2"]).fillna(0.0)
    s_do_bonus = df["do_drop"].fillna(0.0) * DO_DROP_SCALE
    return W_RATING * s_rating + W_CLOSE * s_close + W_STEAM * (s_steam + s_do_bonus) + W_GAP * s_gap
