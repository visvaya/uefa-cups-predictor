"""The Analyst model: table integrity, team status, motivation, rotation risk and the value index."""

import numpy as np
import pandas as pd

from src.analyzer.config import (
    LOCKED_MIN_PROB,
    LOCKED_PLAYOFFS_MAX_TOP8_PROB,
    MOTIVATION_BASE,
    MOTIVATION_SEED_WEIGHT,
    MOTIVATION_SURVIVAL_WEIGHT,
    MOTIVATION_TOP8_WEIGHT,
    OPP_FACTOR_MAX,
    OPP_LOW_MOTIVATION_BONUS,
    OPP_LOW_MOTIVATION_CENTER,
    OPP_LOW_MOTIVATION_WIDTH,
    OUT_MAX_SURVIVAL_PROB,
    ROTATION_BASE,
    ROTATION_MOTIVATION_RELIEF,
    ROTATION_RISK_MAX,
    ROTATION_STATUS_BONUSES,
    SEED_MAX_XPOS,
    SEED_MIN_PLAYOFF_PROB,
    SEED_MIN_XPOS,
    SEED_PEAK_XPOS,
    SEED_WIDTH_XPOS,
    STATUS_BONUSES,
    VALUE_BASE_SHARE,
    VALUE_MAX,
    VALUE_MOTIVATION_SHARE,
)


def sigmoid(x: pd.Series) -> pd.Series:
    """Standard sigmoid function."""
    return 1 / (1 + np.exp(-x))


def pressure_vector(p: pd.Series, beta: float = 0.35) -> pd.Series:
    """PRESSURE() - Measures uncertainty around transition thresholds."""
    p_val = np.clip(p, 0.0, 1.0)
    res = (2 * np.minimum(p_val, 1 - p_val)) ** beta
    return np.where((p_val > 0) & (p_val < 1), res, 0.0)


def integrity_report(df: pd.DataFrame, league_name: str) -> list[str]:
    """Console lines of the data integrity audit of a predicted table."""
    lines = [f"\n--- {league_name} DATA INTEGRITY REPORT ---"]

    cols_to_check = ["LAST 16%", "KO P/0%", "QF%", "SF%", "FINAL%", "WINNER%"]

    # Range check
    out_of_range = (df[cols_to_check] < 0) | (df[cols_to_check] > 100)
    if out_of_range.any().any():
        lines.append("WARNING: VALUES OUT OF RANGE [0, 100] DETECTED!")

    # Monotonicity
    viol = ~(
        (df["WINNER%"] <= df["FINAL%"] + 1e-6) & (df["FINAL%"] <= df["SF%"] + 1e-6) & (df["SF%"] <= df["QF%"] + 1e-6)
    )
    if viol.any():
        lines.append(f"WARNING: MONOTONICITY VIOLATIONS ({viol.sum() or 0} teams)")
    else:
        lines.append("OK: Monotonicity (W<=F<=SF<=Q)")

    # Top 24 Consistency
    raw_sum = df["LAST 16%"] + df["KO P/0%"]
    anom = raw_sum > 100.0001
    if anom.any():
        lines.append(f"WARNING: INCONSISTENT TOP 24 (Sum > 100% for {anom.sum() or 0} teams)")
    else:
        lines.append("OK: Top 24 Consistency")
    lines.append("-" * 30)
    return lines


def enrich_table(table: pd.DataFrame) -> pd.DataFrame:
    """Calculates status, motivation, and risk indices."""
    df = table.copy()

    def to_unit(col: str) -> pd.Series:
        return df[col].fillna(0.0).clip(0, 100) / 100.0

    l16, kpo, qf, sf, fnl, wnr = (to_unit(c) for c in ["LAST 16%", "KO P/0%", "QF%", "SF%", "FINAL%", "WINNER%"])

    # Survival Probability
    raw_sum = l16 + kpo
    p_surv = np.where(raw_sum <= 1.000001, raw_sum, np.maximum.reduce([l16, kpo, qf, sf, fnl, wnr]))
    p_surv = np.maximum.reduce([p_surv, qf, sf, fnl, wnr]).clip(0, 1)

    p_top8 = l16

    # Status classification
    df["Status"] = "IN_PLAY"
    df.loc[p_surv <= OUT_MAX_SURVIVAL_PROB, "Status"] = "OUT"
    df.loc[p_top8 >= LOCKED_MIN_PROB, "Status"] = "LOCKED_DIRECT_RO16"
    df.loc[(p_surv >= LOCKED_MIN_PROB) & (p_top8 <= LOCKED_PLAYOFFS_MAX_TOP8_PROB), "Status"] = "LOCKED_PLAYOFFS"

    # Motivation logic
    m_surv = MOTIVATION_SURVIVAL_WEIGHT * pressure_vector(p_surv)
    m_t8 = MOTIVATION_TOP8_WEIGHT * pressure_vector(p_top8)
    seed_p = np.exp(-(((df["XPOS"] - SEED_PEAK_XPOS) / SEED_WIDTH_XPOS) ** 2))
    in_seed_range = (df["XPOS"] >= SEED_MIN_XPOS) & (df["XPOS"] <= SEED_MAX_XPOS) & (kpo > SEED_MIN_PLAYOFF_PROB)
    m_seed = np.where(in_seed_range, MOTIVATION_SEED_WEIGHT * seed_p, 0.0)

    df["Motivation"] = (MOTIVATION_BASE + m_surv + m_t8 + m_seed).clip(0, 100)

    # Rotation Risk logic
    rot = 1.0 + df["Status"].map(ROTATION_STATUS_BONUSES).fillna(0.0)

    relief = ROTATION_MOTIVATION_RELIEF * (df["Motivation"] / 100.0)
    df["RotRisk"] = (rot * (ROTATION_BASE - relief)).clip(1.0, ROTATION_RISK_MAX)
    return df


def calculate_values(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized calculation of Value Indices for home and away teams."""

    def calc_val(pfx: str, opp: str, win_col: str) -> pd.Series:
        tm_m, op_m = df[f"Mot_{pfx}"] / 100.0, df[f"Mot_{opp}"] / 100.0
        st_b = df[f"Status_{opp}"].map(STATUS_BONUSES).fillna(0.0)
        mot_b = OPP_LOW_MOTIVATION_BONUS * sigmoid((OPP_LOW_MOTIVATION_CENTER - op_m) / OPP_LOW_MOTIVATION_WIDTH)
        opp_dead = (1.0 + st_b + mot_b).clip(1.0, OPP_FACTOR_MAX)

        # Based on Win% instead of EV; the motivation multiplier rewards motivation
        multiplier = VALUE_BASE_SHARE + VALUE_MOTIVATION_SHARE * tm_m
        return (100 * df[win_col] * multiplier * opp_dead / df[f"Risk_{pfx}"]).clip(0, VALUE_MAX)

    return df.assign(Val_H=calc_val("H", "A", "HomeWin%"), Val_A=calc_val("A", "H", "AwayWin%"))
