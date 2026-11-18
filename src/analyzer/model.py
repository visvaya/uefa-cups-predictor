"""The Analyst model: table integrity, team status, motivation, rotation risk and the value index."""

import numpy as np
import pandas as pd

from analyzer.config import (
    COLUMN_SUM_TOLERANCE_PCT,
    DIRECT_QUALIFIERS,
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
    PLAYOFF_PLACES,
    ROTATION_BASE,
    ROTATION_MOTIVATION_RELIEF,
    ROTATION_RISK_MAX,
    ROTATION_STATUS_BONUSES,
    SEED_PEAK_XPOS,
    SEED_WIDTH_XPOS,
    STATUS_BONUSES,
    STRANGE_ODDS_ROTATION_FACTOR,
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


def direct_rows(df: pd.DataFrame) -> pd.Series | None:
    """Rows whose LAST 16% is P(top 8) in The Analyst's January 2026 layout, or None when the sums do not show it.

    A row is direct when LAST 16% + KO P/0% is 100 or LAST 16% is below QF% (it then cannot mean "reaches the last
    16"); the layout holds when KO P/0% sums to the play-off places and the direct LAST 16% to the top 8.
    """
    l16, ko, qf = df["LAST 16%"], df["KO P/0%"], df["QF%"]
    direct = ((l16 + ko - 100).abs() <= 0.01 + 1e-9) | (qf > l16)
    playoff_sum_ok = abs(ko.sum() - 100 * PLAYOFF_PLACES) <= COLUMN_SUM_TOLERANCE_PCT
    top8_sum_ok = abs(l16[direct].sum() - 100 * DIRECT_QUALIFIERS) <= COLUMN_SUM_TOLERANCE_PCT
    return direct if playoff_sum_ok and top8_sum_ok else None


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

    # Top 24 Consistency: what LAST 16% means in this table
    direct = direct_rows(df)
    if direct is not None:
        lines.append(
            f"OK: LAST 16% read as P(top 8) in {int(direct.sum())} rows, as the play-off route in the others "
            "(KO P/0% and LAST 16% column sums match)"
        )
    elif ((df["LAST 16%"] + df["KO P/0%"]) > 100.01).any():
        lines.append("WARNING: INCONSISTENT TOP 24 (LAST 16% + KO P/0% > 100) and column sums of no known layout")
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

    direct = direct_rows(df)
    if direct is not None:
        # January 2026 layout: P(top 8) is LAST 16% in direct rows only, and P(top 24) adds the play-off places
        p_top8 = l16.where(direct, 0.0)
        p_surv = p_top8 + kpo
    else:
        # Unknown layout: LAST 16% read as P(top 8); a sum above 100 falls back to the largest progress value.
        # Two values rounded to 2 decimals can sum to 100.01 (fractions: 1.0001, plus float error) and still be
        # consistent
        raw_sum = l16 + kpo
        p_surv = np.where(raw_sum <= 1.0001 + 1e-9, raw_sum, np.maximum.reduce([l16, kpo, qf, sf, fnl, wnr]))
        p_top8 = l16
    p_surv = np.maximum.reduce([p_surv, qf, sf, fnl, wnr]).clip(0, 1)

    # Status classification
    df["Status"] = "IN_PLAY"
    df.loc[p_surv <= OUT_MAX_SURVIVAL_PROB, "Status"] = "OUT"
    df.loc[p_top8 >= LOCKED_MIN_PROB, "Status"] = "LOCKED_DIRECT_RO16"
    df.loc[(p_surv >= LOCKED_MIN_PROB) & (p_top8 <= LOCKED_PLAYOFFS_MAX_TOP8_PROB), "Status"] = "LOCKED_PLAYOFFS"

    # Motivation logic
    m_surv = MOTIVATION_SURVIVAL_WEIGHT * pressure_vector(p_surv)
    m_t8 = MOTIVATION_TOP8_WEIGHT * pressure_vector(p_top8)
    seed_p = np.exp(-(((df["XPOS"] - SEED_PEAK_XPOS) / SEED_WIDTH_XPOS) ** 2))
    m_seed = MOTIVATION_SEED_WEIGHT * kpo * seed_p

    df["Motivation"] = (MOTIVATION_BASE + m_surv + m_t8 + m_seed).clip(0, 100)

    # Rotation Risk logic
    rot = 1.0 + df["Status"].map(ROTATION_STATUS_BONUSES).fillna(0.0)

    relief = ROTATION_MOTIVATION_RELIEF * (df["Motivation"] / 100.0)
    df["RotRisk"] = (rot * (ROTATION_BASE - relief)).clip(1.0, ROTATION_RISK_MAX)
    return df


def with_strange_odds_rotation(f: pd.DataFrame) -> pd.DataFrame:
    """Raises Risk_H and Risk_A of a match with strange odds by STRANGE_ODDS_ROTATION_FACTOR, capped.

    Both teams, because the anomaly does not say which side carries the hidden factor (injuries, rotation).
    """
    factor = np.where(f["strangeOdds"] != 0, STRANGE_ODDS_ROTATION_FACTOR, 1.0)
    return f.assign(
        Risk_H=(f["Risk_H"] * factor).clip(upper=ROTATION_RISK_MAX),
        Risk_A=(f["Risk_A"] * factor).clip(upper=ROTATION_RISK_MAX),
    )


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
