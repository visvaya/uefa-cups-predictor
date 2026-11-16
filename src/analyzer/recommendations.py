"""Recommendation rules: labels, reasons and the rounding of a ranking with one row per team and match."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.analyzer.config import (
    CONSIDER_DRAW_MAX_SCORE,
    DOMINANT_STEAM_DIFF,
    DRAW_MIN_FAIR_PROB,
    DRAW_MIN_SR_EDGE,
    DRAW_MIN_STEAM,
    GOOD_SR_EDGE,
    GOOD_VALUE,
    HIGH_ROTATION_RISK,
    HIGH_VALUE,
    MIN_MOTIVATION,
    PERFECT_DRAW_MAX_SCORE,
    POSITIVE_SIGNAL,
    REASON_MIN_SR_EDGE,
    REASON_MIN_STEAM,
    STEAM_ALIGNED_MIN,
    STRANGE_ODDS_MIN_ABS,
    STRONG_SIGNAL,
    SURE_BET_MAX_CLOSE,
    SURE_BET_MAX_FAIR,
    SURE_BET_MIN_STEAM,
)

# The labels are also the sort keys of the reports (see RECOMMENDATION_ORDER)
STRONG_BUY = "🟢 STRONG BUY"
CONSIDER = "🟡 CONSIDER"
NEUTRAL = "⚪ NEUTRAL"
CAUTION = "🟠 CAUTION"
AVOID = "🔴 AVOID"
RECOMMENDATION_ORDER = {STRONG_BUY: 0, CONSIDER: 1, NEUTRAL: 2, CAUTION: 3, AVOID: 4}
# The last report columns of both modes, in this order: soccer-rating signals and the recommendation.
SIGNAL_REPORT_COLUMNS = {
    "SR_edge": "srEdge",
    "srDropping": "srDropping",
    "strangeOdds": "strangeOdds",
    "recommendation": "recommendation",
    "reason": "reason",
}

ROUND_2_COLUMNS = (
    "TeamRotRisk",
    "SR_edge",
    "srDropping",
    "expertScore",
    "Close",
    "Fair",
    "edge_x",
    "steam_x",
)
ROUND_1_COLUMNS = (
    "TeamMot",
    "OppMot",
    "Val",
    "ValFinal",
    "strangeOdds",
    "sr_quality",
    "srCompleteness",
)


@dataclass(frozen=True)
class Signals:
    """Per-row inputs and conditions shared by the labels and the reasons."""

    is_out: pd.Series
    is_locked: pd.Series
    rot_high: pd.Series
    val: pd.Series
    score: pd.Series
    pick: pd.Series
    close: pd.Series
    fair: pd.Series
    sr_drop: pd.Series
    sr_edge: pd.Series
    is_home: pd.Series
    steam_aligned: pd.Series
    is_sure_bet: pd.Series
    is_high_val: pd.Series
    is_good_val: pd.Series
    is_strong_sig: pd.Series
    is_pos_sig: pd.Series


def column_or(ranking: pd.DataFrame, column: str, default: object) -> pd.Series:
    """The column, or a constant Series on the ranking's index when it is missing."""
    return ranking.get(column, pd.Series(default, index=ranking.index))


def read_signals(ranking: pd.DataFrame) -> Signals:
    val = ranking.get("ValFinal", ranking.get("Val", pd.Series(0, index=ranking.index)))
    score = column_or(ranking, "expertScore", 0)
    # Missing odds fall back to 99 (no bet), missing steam to 0
    close = column_or(ranking, "Close", 99.0).fillna(99.0)
    fair = column_or(ranking, "Fair", 99.0).fillna(99.0)
    sr_drop = column_or(ranking, "srDropping", 0).fillna(0)
    do_drop = column_or(ranking, "do_drop", 0).fillna(0)

    return Signals(
        is_out=ranking["TeamStatus"] == "OUT",
        is_locked=ranking["TeamStatus"].str.upper().str.startswith("LOCKED", na=False),
        rot_high=ranking["TeamRotRisk"] >= HIGH_ROTATION_RISK,
        val=val,
        score=score,
        pick=column_or(ranking, "pick12", ""),
        close=close,
        fair=fair,
        sr_drop=sr_drop,
        sr_edge=column_or(ranking, "SR_edge", 0).fillna(0),
        is_home=column_or(ranking, "is_home", True),
        steam_aligned=(sr_drop + do_drop) >= STEAM_ALIGNED_MIN,
        is_sure_bet=(close < SURE_BET_MAX_CLOSE) & (fair < SURE_BET_MAX_FAIR) & (sr_drop > SURE_BET_MIN_STEAM),
        is_high_val=val >= HIGH_VALUE,
        is_good_val=val >= GOOD_VALUE,
        is_strong_sig=score.abs() > STRONG_SIGNAL,
        is_pos_sig=score.abs() > POSITIVE_SIGNAL,
    )


def draw_conditions(ranking: pd.DataFrame, s: Signals) -> tuple[pd.Series, pd.Series]:
    """STRONG BUY and CONSIDER conditions for an X pick: a tight score and a market that favours neither side."""
    steam_1 = column_or(ranking, "steam_1", 0).fillna(0)
    steam_2 = column_or(ranking, "steam_2", 0).fillna(0)
    steam_x = column_or(ranking, "steam_x", 0).fillna(0)

    steam_diff_abs = (steam_1 - steam_2).abs()
    is_home_dominant = (steam_1 > steam_2) & (steam_diff_abs > DOMINANT_STEAM_DIFF)
    is_away_dominant = (steam_2 > steam_1) & (steam_diff_abs > DOMINANT_STEAM_DIFF)
    market_undecided = ~(is_home_dominant | is_away_dominant)

    p_fair_x = column_or(ranking, "p_fair_x", 0).fillna(0)
    market_or_fair_confirm = (steam_x >= DRAW_MIN_STEAM) | (p_fair_x > DRAW_MIN_FAIR_PROB)
    edge_ok = s.sr_edge > DRAW_MIN_SR_EDGE

    is_perfect_x = (s.pick == "X") & (s.score.abs() < PERFECT_DRAW_MAX_SCORE)
    cond_strong_x = is_perfect_x & market_undecided & market_or_fair_confirm & edge_ok

    is_consider_x = (s.pick == "X") & (s.score.abs() < CONSIDER_DRAW_MAX_SCORE)
    cond_consider_x = is_consider_x & market_undecided & (steam_x >= 0.0) & edge_ok
    return cond_strong_x, cond_consider_x


def labels(ranking: pd.DataFrame, s: Signals, allow_draws: bool) -> np.ndarray:
    """Recommendation per row. Priority: status, then the sure bet pattern, then the model and market signals."""
    team_mot = column_or(ranking, "TeamMot", 0)
    opp_mot = column_or(ranking, "OppMot", 0)
    is_motivated = (team_mot >= MIN_MOTIVATION) & (team_mot > opp_mot)

    # Away rows carry a flipped expertScore in standard mode, so score > 0 means this row's team is favoured
    is_my_pick = s.score > 0
    if allow_draws:
        is_my_pick = is_my_pick | (s.pick == "X")

    cond_strong = is_my_pick & (s.is_high_val | s.is_strong_sig) & s.steam_aligned & is_motivated
    cond_consider = is_my_pick & (s.is_good_val | (s.sr_edge > GOOD_SR_EDGE) | s.is_pos_sig)
    if allow_draws and "edge_x" in ranking.columns:
        cond_strong_x, cond_consider_x = draw_conditions(ranking, s)
        cond_strong = cond_strong | cond_strong_x
        cond_consider = cond_consider | cond_consider_x

    conditions = [
        s.is_out,
        s.rot_high | s.is_locked,  # absolute priority over market signals
        s.is_sure_bet,
        cond_strong,
        cond_consider | (cond_strong & ~s.steam_aligned),
    ]
    return np.select(conditions, [AVOID, CAUTION, STRONG_BUY, STRONG_BUY, CONSIDER], default=NEUTRAL)


def number_text(values: pd.Series, decimal: str) -> pd.Series:
    """The values rounded to 2 decimals as text, with `decimal` as the decimal separator."""
    return values.round(2).astype(str).str.replace(".", decimal, regex=False)


def reasons(ranking: pd.DataFrame, s: Signals, allow_draws: bool, decimal: str) -> pd.Series:
    """The `reason` column: the rules that fired, joined with "; ", or "-" when none did.

    Numbers in the text use `decimal` as the decimal separator, like the numeric columns of the report.
    """

    def r(cond: pd.Series, text: str | pd.Series) -> np.ndarray:
        return np.where(cond, text + "; ", "")

    reason_s = pd.Series("", index=ranking.index)

    reason_s += r(s.is_out, "Out of contention")
    reason_s += r(s.rot_high, "High rotation risk")
    reason_s += r(s.is_locked, "Status " + ranking["TeamStatus"].astype(str))
    reason_s += r(s.is_sure_bet, "Sure Bet Pattern")
    reason_s += r(s.is_high_val, "High Value")
    reason_s += r(~s.is_high_val & s.is_good_val, "Good Value")
    reason_s += r(s.is_strong_sig, "Strong Expert Signal")
    reason_s += r(~s.is_strong_sig & s.is_pos_sig, "Positive Signal")

    had_stats = s.is_high_val | s.is_strong_sig
    reason_s += r(had_stats & ~s.steam_aligned & ~s.is_sure_bet, "(Risk: Rising Odds)")
    reason_s += r(s.sr_drop > REASON_MIN_STEAM, "Steam (+)")
    reason_s += r(s.sr_drop < -REASON_MIN_STEAM, "Steam (-)")

    so = ranking.get("strangeOdds", pd.Series(0)).fillna(0)
    reason_s += r(so.abs() > STRANGE_ODDS_MIN_ABS, "Strange Odds (" + so.astype(int).astype(str) + ")")

    reason_s += r(s.sr_edge > REASON_MIN_SR_EDGE, "SR Edge")
    reason_s += r(s.sr_edge < -REASON_MIN_SR_EDGE, "Market Confidence")

    if allow_draws:
        lean_str = np.where(s.score > 0, "Lean: 1X", "Lean: X2")
        steam_x_val = number_text(column_or(ranking, "steam_x", 0).fillna(0), decimal)
        reason_s += r((s.pick == "X") & s.is_home, lean_str + " (SteamX " + steam_x_val + ")")

    ao_fair_str = "AO(" + number_text(s.close, decimal) + ") > Fair(" + number_text(s.fair, decimal) + ")"
    reason_s += r(s.val >= HIGH_VALUE, ao_fair_str)

    reason_s = reason_s.str.strip().str.rstrip(";")
    return reason_s.where(reason_s != "", "-")


def rounded(ranking: pd.DataFrame) -> pd.DataFrame:
    """Win probability as a percentage, odds, edges and scores to 2 decimals, indices to 1."""
    ranking = ranking.copy()
    if "TeamWinProb%" in ranking.columns:
        ranking["TeamWinProb%"] = (ranking["TeamWinProb%"] * 100).round(1)
    for decimals, columns in ((2, ROUND_2_COLUMNS), (1, ROUND_1_COLUMNS)):
        for c in columns:
            if c in ranking.columns:
                ranking[c] = pd.to_numeric(ranking[c], errors="coerce").round(decimals)
    return ranking


def format_recommendations(ranking: pd.DataFrame, allow_draws: bool, decimal: str) -> pd.DataFrame:
    """Adds recommendation labels and reasons and rounds numeric values.

    Args:
        allow_draws: If False (Analyst mode), skips Draw specific logic.
        decimal: Decimal separator of the numbers in the reasons.
    """
    s = read_signals(ranking)
    ranking = ranking.assign(recommendation=labels(ranking, s, allow_draws))
    ranking["reason"] = reasons(ranking, s, allow_draws, decimal)
    return rounded(ranking)


def recommendation_rank(recommendation: pd.Series) -> pd.Series:
    """Sort key of a label: STRONG BUY first, AVOID last."""
    return recommendation.map(RECOMMENDATION_ORDER).fillna(99).astype(int)


def round_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Copy with every numeric column rounded to 2 decimals (the report precision)."""
    df = df.copy()
    for col in df.select_dtypes(include=[np.number]).columns:
        df[col] = df[col].round(2)
    return df
