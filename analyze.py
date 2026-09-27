import pandas as pd
import numpy as np
import unicodedata
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# ========================================
# CONFIGURATION & CONSTANTS
# ========================================
BASE_DIR: Path = Path(__file__).parent

NAME_FIX: Dict[str, str] = {
    # Diacritics/Variants
    "boda/glimt": "bodo/glimt",
    "kabenhavn": "kobenhavn",
    "atletico madrid": "atletico",
    "atletico de madrid": "atletico",
    "real": "real madrid",
    "nottm forest": "nottingham forest",
    
    # Europa League: Analyst -> Soccer-rating
    "sturm": "sturm graz",
    "brann": "sk brann bergen",
    "maccabi ta": "maccabi tel aviv",
    "go ahead": "go ahead eagles",
    "crvena zvezda": "crvena zvezda belgrade",
    "fcsb": "steaua bukarest",
    "plzen": "fk viktoria plzen",
    "nice": "ogc nice",
    "ferencvaros": "ferencvaros budapest",
    "young boys": "young boys bern",
    "rangers": "glasgow rangers",
    "feyenoord": "feyenoord rotterdam",
    "paok": "paok saloniki",
    "porto": "fc porto",
    "salzburg": "red bull salzburg",
    "celtic": "celtic glasgow",
    "utrecht": "fc utrecht",
    "basel": "fc basel",
    "midtjylland": "fc midtjylland",
    "celta": "celta de vigo",
    "braga": "sporting braga",
    "genk": "krc genk",
    "malmo": "malmo ff",
    "lille": "osc lille",
    "freiburg": "sc freiburg",
    "bologna": "bologna fc",
    "lyon": "olympique lyon",
    "roma": "as roma",
    "ludogorets": "ludogorets razgrad",
    "betis": "betis sevilla",
    "stuttgart": "vfb stuttgart",
    
    # Champions League variants (proactive)
    "man city": "manchester city",
    "paris sg": "paris saint-germain",
    "spurs": "tottenham hotspur",
    "ajax": "ajax amsterdam",
    "newcastle": "newcastle united",
    "r. union sg": "royal union saint-gilloise",
    "athletic": "athletic bilbao",
}

# Status Point Bonuses for Value Calculation
STATUS_BONUSES: Dict[str, float] = {
    "OUT": 0.22,
    "LOCKED_DIRECT_RO16": 0.12,
    "LOCKED_PLAYOFFS": 0.15
}

# Weight for Soccer-rating signal

# Score Weights for Pick 1/2
W_RATING = 0.2  # Team Rating diff
W_CLOSE = 0.6   # Close log odds
W_STEAM = 0.4   # Market steam diff
W_GAP = 0.1     # Probability gap diff
W_LINEUP = 0.1  # Lineup advantage

# ========================================
# HELPERS: NORMALIZATION & MAPPING
# ========================================


def remove_diacritics(s: str) -> str:
    """Removes diacritics and normalizes text to ASCII (includes ø, ł, æ, etc.)."""
    mapping: Dict[int | str, int | str | None] = {
        '\u00f8': 'o', '\u00d8': 'O', '\u0142': 'l', '\u0141': 'L', 
        '\u00e6': 'ae', '\u00c6': 'AE', '\u00e5': 'a', '\u00c5': 'A'
    }
    s = s.translate(str.maketrans(mapping))
    normalized = unicodedata.normalize('NFD', s)
    return "".join(c for c in normalized if unicodedata.category(c) != 'Mn')

def norm_key(s: Optional[str]) -> str:
    """Creates a normalized key for team names."""
    if pd.isna(s) or s is None: return ""
    s = remove_diacritics(str(s)).strip().lower()
    return NAME_FIX.get(s, s)

# ========================================
# CORE MATH & LOGIC
# ========================================
def sigmoid(x: pd.Series) -> pd.Series:
    """Standard sigmoid function."""
    return 1 / (1 + np.exp(-x))

def pressure_vector(p: pd.Series, beta: float = 0.35) -> pd.Series:
    """PRESSURE() - Measures uncertainty around transition thresholds."""
    p_val = np.clip(p, 0.0, 1.0)
    res = (2 * np.minimum(p_val, 1 - p_val)) ** beta
    return np.where((p_val > 0) & (p_val < 1), res, 0.0)

# ========================================
# DATA ENGINE
# ========================================
def cast_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Utility to clean and cast columns to float. Handles both dot and comma decimals."""
    for c in cols:
        if c in df.columns:
            # Convert to string, replace comma with dot, then back to numeric
            df[c] = pd.to_numeric(
                df[c].astype(str).str.replace(",", "."), 
                errors="coerce"
            ).fillna(0.0)
    return df

def read_smart_csv(path: Path) -> pd.DataFrame:
    """Reads CSV with automatic separator detection (handles ; and ,)."""
    try:
        # Try reading a few lines to detect separator
        with open(path, 'r', encoding='utf-8-sig') as f:
            first_line = f.readline()
            sep = ';' if ';' in first_line else ','
        
        return pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Fallback to standard utf-8
        with open(path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            sep = ';' if ';' in first_line else ','
        return pd.read_csv(path, sep=sep, encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: Missing file: {path}")
        sys.exit(1)

def load_soccer_rating(prefix: str) -> pd.DataFrame:
    """Loads market data from Soccer-rating and maps to team names."""
    sr_dir = BASE_DIR / "data" / "soccer-rating"
    path = sr_dir / "match_odds_development.csv"
    if not path.exists():
        return pd.DataFrame()

    sr = read_smart_csv(path)
    
    # Filter by league code: cl -> CLCUP, el -> ELCUP
    league_code = "CLCUP" if prefix == "cl" else "ELCUP"
    sr = sr[sr["league_code"] == league_code].copy()
    if sr.empty:
        return pd.DataFrame()

    # Filter for the latest snapshot per match to avoid duplicates
    if "match_id" in sr.columns:
        if "snapshot_date" in sr.columns:
            sr["snapshot_date"] = pd.to_datetime(sr["snapshot_date"], errors="coerce")
            sr = sr.sort_values("snapshot_date").drop_duplicates(["match_id"], keep="last")
        else:
            sr = sr.drop_duplicates(["match_id"], keep="last")
    elif "snapshot_date" in sr.columns:
        sr["snapshot_date"] = pd.to_datetime(sr["snapshot_date"], errors="coerce")
        sr = sr.sort_values("snapshot_date").drop_duplicates(["home_id", "away_id"], keep="last")

    num_cols = ["oo","do","ao", "open_1","open_x","open_2", "drop_1","drop_x","drop_2",
                "close_1","close_x","close_2", "fair_1","fair_x","fair_2", "odds_distance",
                "team_rating_home", "team_rating_away"]
    sr = cast_numeric(sr, num_cols)

    # Load today_matches.csv for lineups
    today_path = sr_dir / "today_matches.csv"
    if today_path.exists():
        today = read_smart_csv(today_path)
        today = cast_numeric(today, ["lineup_rating_home_today", "lineup_rating_away_today"])
        # Merge by match_id
        if "match_id" in sr.columns and "match_id" in today.columns:
            lineup_cols = ["match_id", "lineup_rating_home_today", "lineup_rating_away_today", "lineup_type_today"]
            sr = sr.merge(today[lineup_cols], on="match_id", how="left")

    # Normalize keys using club_meta.csv
    sr_dir = BASE_DIR / "data" / "soccer-rating"
    meta_path = sr_dir / "club_meta.csv"
    if meta_path.exists():
        meta = read_smart_csv(meta_path)
        meta["TeamKey"] = meta["team_name"].map(norm_key)
        # Ensure ID is string for mapping
        name_map = meta.set_index(meta["team_id"].astype(str))["TeamKey"].to_dict()
        sr["HomeKey"] = sr["home_id"].astype(str).map(name_map)
        sr["AwayKey"] = sr["away_id"].astype(str).map(name_map)
    
    # Drop records that couldn't be mapped
    sr = sr.dropna(subset=["HomeKey", "AwayKey"])
    
    # Deduplicate strictly on valid keys to prevent Cartesian products in merge
    sr = sr.drop_duplicates(subset=["HomeKey", "AwayKey"], keep="last")
    
    return sr

def add_soccer_rating_features(f: pd.DataFrame, sr: pd.DataFrame) -> pd.DataFrame:
    """Merges SR data and calculates value edges with robust normalization."""
    edge_cols = ["edge_1", "edge_x", "edge_2"]
    
    # Create do_drop, strangeOdds, srDropping BEFORE early return
    # These columns should always exist, regardless of SR data
    if "do" in f.columns and "oo" in f.columns:
        f["do_drop"] = (f["do"] - f["oo"]) / 100.0
    else:
        f["do_drop"] = 0.0
        
    if "ao" in f.columns:
        f["strangeOdds"] = np.where(f["ao"].abs() > 30, f["ao"], 0.0)
    else:
        f["strangeOdds"] = 0.0
        
    f["srDropping"] = 0.0  # Default, will be overwritten if SR data exists
    
    if sr.empty:
        for c in edge_cols + ["sr_quality", "steam_diff", "prob_gap_1", "prob_gap_2", "rating_diff", "lineup_adv"]: 
            f[c] = 0.0

        for side in ["1", "x", "2"]:
            f[f"p_close_{side}"] = 0.333 if side != "x" else 0.334
            f[f"p_fair_{side}"] = 0.333

        return f

    f2 = f.merge(sr, on=["HomeKey", "AwayKey"], how="left", suffixes=("", "_sr"))
    
    # Coverage report
    has_sr_raw = f2["fair_1"].notna()
    coverage = has_sr_raw.mean()
    print(f"INFO: Soccer-rating coverage: {coverage:.0%}")
    if coverage < 1.0:
        missing = f2[~has_sr_raw][["HomeTeamName", "AwayTeamName"]].head(3)
        if not missing.empty:
            missing_list = [f"{r.HomeTeamName} vs {r.AwayTeamName}" for _, r in missing.iterrows()]
            print(f"DEBUG: Missing SR matches: {', '.join(missing_list)}")

    # Safety: Filter out rows with invalid or zero odds to avoid division by zero/Inf
    mkt_cols = ["close_1", "close_x", "close_2"]
    fair_cols = ["fair_1", "fair_x", "fair_2"]
    open_cols = ["open_1", "open_x", "open_2"]
    valid_mask = (f2[mkt_cols + fair_cols + open_cols] > 1.0).all(axis=1)

    # Initialize defaults
    for c in edge_cols + ["steam_diff", "prob_gap_1", "prob_gap_2", "rating_diff", "lineup_adv", "sr_quality"]: 
        f2[c] = 0.0
    
    # Initialize probabilities and steam to neutral defaults
    for side in ["1", "x", "2"]:
        # Use 0.333 as neutral probability if unavailable
        f2[f"p_close_{side}"] = 0.334 if side == "x" else 0.333
        f2[f"p_fair_{side}"] = 0.334 if side == "x" else 0.333
        f2[f"prob_gap_{side}"] = 0.0
        f2[f"steam_{side}"] = 0.0

    # Probability and Steam calculations
    if valid_mask.any():
        # Normalized Market Probabilities (Close)
        inv_close = (1.0 / f2.loc[valid_mask, "close_1"]) + (1.0 / f2.loc[valid_mask, "close_x"]) + (1.0 / f2.loc[valid_mask, "close_2"])
        # Normalized Fair Probabilities
        inv_fair = (1.0 / f2.loc[valid_mask, "fair_1"]) + (1.0 / f2.loc[valid_mask, "fair_x"]) + (1.0 / f2.loc[valid_mask, "fair_2"])
        
        for side in ["1", "x", "2"]:
            p_fair = (1.0 / f2.loc[valid_mask, f"fair_{side}"]) / inv_fair
            p_close = (1.0 / f2.loc[valid_mask, f"close_{side}"]) / inv_close
            
            f2.loc[valid_mask, f"edge_{side}"] = (p_fair - p_close)
            f2.loc[valid_mask, f"p_close_{side}"] = p_close
            f2.loc[valid_mask, f"p_fair_{side}"] = p_fair
            f2.loc[valid_mask, f"prob_gap_{side}"] = p_close - p_fair
            
            # Steam: ln(open / close)
            open_v = f2.loc[valid_mask, f"open_{side}"].clip(lower=1.01)
            close_v = f2.loc[valid_mask, f"close_{side}"].clip(lower=1.01)
            f2.loc[valid_mask, f"steam_{side}"] = np.log(open_v / close_v)

        f2.loc[valid_mask, "steam_diff"] = f2.loc[valid_mask, "steam_1"] - f2.loc[valid_mask, "steam_2"]
        f2.loc[valid_mask, "rating_diff"] = f2.loc[valid_mask, "team_rating_home"] - f2.loc[valid_mask, "team_rating_away"]
        
        # Lineup advantage (only if expected)
        f2["lineup_adv"] = np.where(
            f2["lineup_type_today"] == "expected",
            f2["lineup_rating_home_today"] - f2["lineup_rating_away_today"],
            0.0
        )

    # sr_quality gating
    has_sr = f2["fair_1"].notna() & valid_mask
    f2["sr_quality"] = np.where(
        has_sr & (f2.get("match_confidence", "LOW") == "HIGH") & (f2["odds_distance"] <= 0.01),
        1.0,
        np.where(has_sr, 0.5, 0.0)
    )
    
    
    # Update srDropping with actual steam_diff when SR data exists
    # (was initialized to 0.0 at function start)
    if "steam_diff" in f2.columns:
        f2["srDropping"] = f2["steam_diff"]

    return f2

def load_league_data(prefix: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads fixtures and predicted table for a given league prefix (cl/el)."""
    league_dir = "champions-league" if prefix == "cl" else "europa-league"
    data_dir = BASE_DIR / "data" / "theanalyst" / league_dir
    
    fixtures_path = data_dir / f"{prefix}_fixtures.csv"
    table_path = data_dir / f"{prefix}_table_predicted.csv"

    f, t = read_smart_csv(fixtures_path), read_smart_csv(table_path)
    
    fixtures_num = ["HomeWin%", "Draw%", "AwayWin%"]
    table_num = ["XPOS", "XPTS", "LEAGUE%", "KO P/0%", "LAST 16%", "QF%", "SF%", "FINAL%", "WINNER%"]

    return cast_numeric(f, fixtures_num), cast_numeric(t, table_num)

def validate_integrity(df: pd.DataFrame, league_name: str) -> None:
    """Audits data integrity."""
    print(f"\n--- {league_name} DATA INTEGRITY REPORT ---")
    
    cols_to_check = ["LAST 16%", "KO P/0%", "QF%", "SF%", "FINAL%", "WINNER%"]
    
    # Range check
    out_of_range = (df[cols_to_check] < 0) | (df[cols_to_check] > 100)
    if out_of_range.any().any():
        print(f"WARNING: VALUES OUT OF RANGE [0, 100] DETECTED!")
    
    # Monotonicity
    viol = ~(
        (df["WINNER%"] <= df["FINAL%"] + 1e-6) & 
        (df["FINAL%"] <= df["SF%"] + 1e-6) & 
        (df["SF%"] <= df["QF%"] + 1e-6)
    )
    if viol.any():
        print(f"WARNING: MONOTONICITY VIOLATIONS ({viol.sum() or 0} teams)")
    else:
        print("OK: Monotonicity (W<=F<=SF<=Q)")

    # Top 24 Consistency
    raw_sum = df["LAST 16%"] + df["KO P/0%"]
    anom = raw_sum > 100.0001
    if anom.any():
        print(f"WARNING: INCONSISTENT TOP 24 (Sum > 100% for {anom.sum() or 0} teams)")
    else:
        print("OK: Top 24 Consistency")
    print("-" * 30)

def enrich_table(table: pd.DataFrame, league_name: str) -> pd.DataFrame:
    """Calculates status, motivation, and risk indices."""
    df = table.copy()
    validate_integrity(df, league_name)

    # Normalization helper
    s = lambda col: df[col].fillna(0.0).clip(0, 100) / 100.0
    
    l16, kpo, qf, sf, fnl, wnr = (s(c) for c in ["LAST 16%", "KO P/0%", "QF%", "SF%", "FINAL%", "WINNER%"])

    # Survival Probability
    raw_sum = l16 + kpo
    p_surv = np.where(raw_sum <= 1.000001, raw_sum, np.maximum.reduce([l16, kpo, qf, sf, fnl, wnr]))
    p_surv = np.maximum.reduce([p_surv, qf, sf, fnl, wnr]).clip(0, 1)
    
    p_top8 = l16

    # Status classification
    df["Status"] = "IN_PLAY"
    df.loc[p_surv <= 0.015, "Status"] = "OUT"
    df.loc[p_top8 >= 0.985, "Status"] = "LOCKED_DIRECT_RO16"
    df.loc[(p_surv >= 0.985) & (p_top8 <= 0.02), "Status"] = "LOCKED_PLAYOFFS"

    # Motivation logic
    m_surv = 65 * pressure_vector(p_surv)
    m_t8 = 45 * pressure_vector(p_top8)
    seed_p = np.exp(-((df["XPOS"] - 12.5) / 4.0) ** 2)
    m_seed = np.where((df["XPOS"] >= 7) & (df["XPOS"] <= 18) & (kpo > 0.4), 22 * seed_p, 0.0)
    
    df["Motivation"] = (12 + m_surv + m_t8 + m_seed).clip(0, 100)

    # Rotation Risk logic
    rot_map = {"OUT": 0.95, "LOCKED_DIRECT_RO16": 0.65, "LOCKED_PLAYOFFS": 0.38}
    rot = (1.0 + df["Status"].map(rot_map).fillna(0.0))
    
    df["RotRisk"] = (rot * (1.15 - 0.35 * (df["Motivation"] / 100.0))).clip(1.0, 2.3)
    return df

def calculate_values(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized calculation of Value Indices for home and away teams."""
    def calc_val(pfx, opp, win_col):
        tm_m, op_m = df[f"Mot_{pfx}"] / 100.0, df[f"Mot_{opp}"] / 100.0
        st_b = df[f"Status_{opp}"].map(STATUS_BONUSES).fillna(0.0)
        mot_b = 0.18 * sigmoid((0.45 - op_m) / 0.08)
        opp_dead = (1.0 + st_b + mot_b).clip(1.0, 1.35)
        
        # New Formula: Base on Win% instead of EV
        # Multiplier (0.55 + 0.45*tm_m) kept similar to reward motivation
        # We might slighty boost specific coefficients if needed to keep scale 0-140
        return (100 * df[win_col] * (0.60 + 0.40 * tm_m) * opp_dead / df[f"Risk_{pfx}"]).clip(0, 140)

    df["Val_H"] = calc_val("H", "A", "HomeWin%")
    df["Val_A"] = calc_val("A", "H", "AwayWin%")
    return df

def format_recommendations(ranking: pd.DataFrame, allow_draws: bool = True) -> pd.DataFrame:
    """
    Adds recommendation labels, reasons, and rounds numeric values (Vectorized).
    
    Args:
        allow_draws: If False (Analyst mode), skips Draw specific logic.
    """
    # 1. Pre-calculate Conditions (Masks)
    # -----------------------------------
    # Status
    is_out = ranking["TeamStatus"] == "OUT"
    is_locked = ranking["TeamStatus"].str.upper().str.startswith("LOCKED", na=False)
    rot_high = ranking["TeamRotRisk"] >= 1.39
    
    # Values & Scores
    val = ranking.get("ValFinal", ranking.get("Val", pd.Series(0, index=ranking.index)))
    score = ranking.get("expertScore", pd.Series(0, index=ranking.index))
    pick = ranking.get("pick12", pd.Series("", index=ranking.index))
    
    # Odds & Steam
    # Ensure columns exist (fallback to 0/99)
    close_val = ranking.get("Close", pd.Series(99.0, index=ranking.index)).fillna(99.0)
    fair_val = ranking.get("Fair", pd.Series(99.0, index=ranking.index)).fillna(99.0)
    sr_drop = ranking.get("srDropping", pd.Series(0, index=ranking.index)).fillna(0)
    do_drop = ranking.get("do_drop", pd.Series(0, index=ranking.index)).fillna(0)
    
    # Steam Alignment Logic
    steam_total = sr_drop + do_drop
    steam_aligned = steam_total >= -0.01

    # Sure Bet Pattern
    is_sure_bet = (close_val < 2.00) & (fair_val < 2.20) & (sr_drop > 0.03)

    # Signal Thresholds
    is_high_val = val >= 70
    is_good_val = val >= 50
    is_strong_sig = score.abs() > 1.50
    is_pos_sig = score.abs() > 0.5
    
    # New Motivation filter for Strong Buy
    team_mot = ranking.get("TeamMot", pd.Series(0, index=ranking.index))
    opp_mot = ranking.get("OppMot", pd.Series(0, index=ranking.index))
    is_motivated = (team_mot >= 50) & (team_mot > opp_mot)
    
    # SR Edge Support
    sr_edge_col = "SR_edge" if "SR_edge" in ranking.columns else "srEdge"
    sr_edge = ranking.get(sr_edge_col, pd.Series(0, index=ranking.index)).fillna(0)
    is_high_edge = sr_edge > 0.08
    is_good_edge = sr_edge > 0.04
    
    # Directionality Check
    is_home = ranking.get("is_home", pd.Series(True, index=ranking.index)) 
    
    # "My Pick" logic - Since we now flip expertScore for Away in analyze_league, 
    # score > 0 always means this row's team is favored by the model.
    is_my_pick = score > 0
    if allow_draws:
        is_my_pick = is_my_pick | (pick == "X")
    
    # Detailed Pick Logic
    # Added filter: is_motivated for STRONG BUY (WinProb removed as it is part of Value)
    cond_strong = is_my_pick & (is_high_val | is_strong_sig) & steam_aligned & is_motivated
    cond_consider = is_my_pick & (is_good_val | is_good_edge | is_pos_sig)
    
    # If Pick is X, check logic
    if allow_draws and "edge_x" in ranking.columns:
         is_perfect_x = (pick == "X") & (pd.Series(score, index=ranking.index).abs() < 0.05)
         
         # Get individual steam values
         steam_1 = ranking.get("steam_1", pd.Series(0, index=ranking.index)).fillna(0)
         steam_2 = ranking.get("steam_2", pd.Series(0, index=ranking.index)).fillna(0)
         steam_x = ranking.get("steam_x", pd.Series(0, index=ranking.index)).fillna(0)
         
         steam_diff_abs = (steam_1 - steam_2).abs()
         is_home_dominant = (steam_1 > steam_2) & (steam_diff_abs > 0.30)
         is_away_dominant = (steam_2 > steam_1) & (steam_diff_abs > 0.30)
         market_undecided = ~(is_home_dominant | is_away_dominant)
         
         p_fair_x = ranking.get("p_fair_x", pd.Series(0, index=ranking.index)).fillna(0)
         market_or_fair_confirm = (steam_x >= 0.01) | (p_fair_x > 0.2)
         
         cond_strong_x = is_perfect_x & market_undecided & market_or_fair_confirm & (sr_edge > -0.03)
         
         is_consider_x = (pick == "X") & (pd.Series(score, index=ranking.index).abs() < 0.10)
         cond_consider_x = is_consider_x & market_undecided & (steam_x >= 0.0) & (sr_edge > -0.03)
         
         cond_strong = cond_strong | cond_strong_x
         cond_consider = cond_consider | cond_consider_x

    # 2. Determine Base Recommendation
    # PRIORITY: Status > Sure Bet > Regular Signals
    conditions = [
        is_out,                                         # AVOID
        (rot_high | is_locked),                         # CAUTION (Absolute priority over market signals)
        is_sure_bet,                                    # STRONG BUY
        cond_strong,                                    # STRONG BUY
        cond_consider | (cond_strong & ~steam_aligned)  # CONSIDER
    ]
    choices = ["🔴 AVOID", "🟠 CAUTION", "🟢 STRONG BUY", "🟢 STRONG BUY", "🟡 CONSIDER"]
    ranking["recommendation"] = np.select(conditions, choices, default="⚪ NEUTRAL")
    
    # 3. Construct Reasons
    def r(cond, text): return np.where(cond, text + "; ", "")
    reason_s = pd.Series("", index=ranking.index)
    
    reason_s += r(is_out, "Out of contention")
    reason_s += r(rot_high, "High rotation risk")
    reason_s += r(is_locked, "Status " + ranking["TeamStatus"].astype(str))
    reason_s += r(is_sure_bet, "Sure Bet Pattern")
    reason_s += r(is_high_val, "High Value")
    reason_s += r(~is_high_val & is_good_val, "Good Value")
    reason_s += r(is_strong_sig, "Strong Expert Signal")
    reason_s += r(~is_strong_sig & is_pos_sig, "Positive Signal")
    
    had_stats = (is_high_val | is_strong_sig)
    reason_s += r(had_stats & ~steam_aligned & ~is_sure_bet, "(Risk: Rising Odds)")
    reason_s += r(sr_drop > 0.05, "Steam (+)")
    reason_s += r(sr_drop < -0.05, "Steam (-)")
    
    so = ranking.get("strangeOdds", pd.Series(0)).fillna(0)
    reason_s += r(so.abs() > 30, "Strange Odds (" + so.astype(int).astype(str) + ")")
    
    reason_s += r(sr_edge > 0.05, "SR Edge")
    reason_s += r(sr_edge < -0.05, "Market Confidence")

    if allow_draws:
        lean_str = np.where(score > 0, "Lean: 1X", "Lean: X2")
        steam_x_val = ranking.get("steam_x", pd.Series(0, index=ranking.index)).fillna(0).round(2).astype(str)
        reason_s += r((pick == "X") & is_home, lean_str + " (SteamX " + steam_x_val + ")")
    
    ao_fair_str = "AO(" + close_val.round(2).astype(str) + ") > Fair(" + fair_val.round(2).astype(str) + ")"
    reason_s += r(val >= 70, ao_fair_str)

    ranking["reason"] = reason_s.str.strip().str.rstrip(";")
    ranking.loc[ranking["reason"] == "", "reason"] = "-"
    
    # Rounding
    if "TeamWinProb%" in ranking.columns:
        ranking["TeamWinProb%"] = (ranking["TeamWinProb%"] * 100).round(1)
        
    for c in ["TeamRotRisk", "teamRotRisk", "SR_edge", "srEdge", "srDropping", "expertScore", "Close", "Fair", "edge_x", "steam_x"]: 
        if c in ranking.columns: ranking[c] = pd.to_numeric(ranking[c], errors="coerce").round(2)
    for c in ["TeamMot", "OppMot", "teamMot", "oppMot", "Val", "ValFinal", "valFinal", "strangeOdds", "sr_quality", "srCompleteness"]: 
        if c in ranking.columns: ranking[c] = pd.to_numeric(ranking[c], errors="coerce").round(1)
        
    return ranking

def analyze_league(prefix: str, excel_pl: bool = False):
    """Main execution flow for a specific league."""
    l_name = "CHAMPIONS LEAGUE" if prefix == "cl" else "EUROPA LEAGUE"
    out_path = BASE_DIR / f"{prefix}_recommendations.csv"
    
    fixtures, table = load_league_data(prefix)
    
    if len(table) != 36: print(f"ERROR: {l_name} table must have 36 teams."); sys.exit(1)
    if len(fixtures) != 18: print(f"ERROR: {l_name} fixtures must have 18 matches."); sys.exit(1)

    # Normalization
    fixtures["HomeKey"] = fixtures["HomeTeam"].map(norm_key)
    fixtures["AwayKey"] = fixtures["AwayTeam"].map(norm_key)
    table["TeamKey"] = table["TEAM"].map(norm_key)

    # Validation
    known = set(table["TeamKey"])
    used = set(fixtures["HomeKey"]).union(set(fixtures["AwayKey"]))
    if missing := sorted(used - known):
        print(f"ERROR: Missing teams in {prefix}_table: {missing}"); sys.exit(1)

    # Enrichment & Merge
    table = enrich_table(table, l_name)
    t_clean = table[["TeamKey", "TEAM", "Status", "Motivation", "RotRisk"]].set_index("TeamKey")

    f = fixtures.merge(t_clean, left_on="HomeKey", right_index=True)
    f = f.rename(columns={"TEAM": "HomeTeamName", "Status": "Status_H", "Motivation": "Mot_H", "RotRisk": "Risk_H"})
    f = f.merge(t_clean, left_on="AwayKey", right_index=True)
    f = f.rename(columns={"TEAM": "AwayTeamName", "Status": "Status_A", "Motivation": "Mot_A", "RotRisk": "Risk_A"})

    # Probs
    p_sum = (f["HomeWin%"] + f["Draw%"] + f["AwayWin%"]).replace(0, 1)
    for c in ["HomeWin%", "Draw%", "AwayWin%"]: f[c] = (f[c] / p_sum).fillna(0.0)
    
    # Soccer-rating integration
    sr = load_soccer_rating(prefix)
    f = add_soccer_rating_features(f, sr)

    # Final Calcs
    f = calculate_values(f)

    # Flatten & Rank
    for col in ["edge_1", "edge_2", "close_1", "close_2", "fair_1", "fair_2"]:
        if col not in f.columns:
            f[col] = 0.0 if "edge" in col else 99.0
    
    h_cols = ["HomeTeamName", "AwayTeamName", "HomeWin%", "Mot_H", "Risk_H", "Status_H", "Val_H", "Mot_A", "Status_A", "edge_1", "sr_quality", "srDropping", "strangeOdds", "do_drop", "close_1", "fair_1"]
    a_cols = ["AwayTeamName", "HomeTeamName", "AwayWin%", "Mot_A", "Risk_A", "Status_A", "Val_A", "Mot_H", "Status_H", "edge_2", "sr_quality", "srDropping", "strangeOdds", "do_drop", "close_2", "fair_2"]
    
    h = f[h_cols].copy()
    a = f[a_cols].copy()
    h["is_home"] = True
    a["is_home"] = False
    
    # Adjust srDropping/edge for Away perspective
    a["srDropping"] = -a["srDropping"]
    if "do_drop" in a.columns: a["do_drop"] = -a["do_drop"]

    # Internal usage names
    base_cols = ["Team", "Opp", "TeamWinProb%", "TeamMot", "TeamRotRisk", "TeamStatus", "Val", "OppMot", "OppStatus", "SR_edge", "sr_quality", "srDropping", "strangeOdds", "do_drop", "Close", "Fair", "is_home"]
    h.columns = a.columns = base_cols
    
    ranking = pd.concat([h, a], ignore_index=True)
    ranking["SR_edge"] = ranking["SR_edge"].fillna(0.0)
    ranking["sr_quality"] = ranking["sr_quality"].fillna(0.0)
    ranking["srDropping"] = ranking["srDropping"].fillna(0.0)
    ranking["strangeOdds"] = ranking["strangeOdds"].fillna(0.0)
    ranking["ValFinal"] = ranking["Val"]
    
    # ========================================
    # EXPERT SCORE 1/2 LOGIC
    # ========================================
    s_rating_home = f["rating_diff"] / 300.0
    p1 = f.get("p_close_1", pd.Series(0.5, index=f.index)).fillna(0.5)
    p2 = f.get("p_close_2", pd.Series(0.5, index=f.index)).fillna(0.5)
    s_close_home = np.log((p1 / p2).clip(0.01, 100))
    s_steam_home = f["steam_diff"].fillna(0.0)
    s_gap_home = (f["prob_gap_1"] - f["prob_gap_2"]).fillna(0.0)
    s_lineup_home = (f["lineup_adv"] / 10.0).fillna(0.0)
    s_do_bonus = f["do_drop"].fillna(0.0) * 2.0
    
    score_home = W_RATING * s_rating_home + W_CLOSE * s_close_home + \
                 W_STEAM * (s_steam_home + s_do_bonus) + W_GAP * s_gap_home + W_LINEUP * s_lineup_home
    f["matchExpertScore"] = score_home
    f["matchPick12"] = np.where(f["matchExpertScore"] > 0, "1", "2")

    # Flatten & Rank
    for col in ["edge_1", "edge_2", "close_1", "close_2", "fair_1", "fair_2"]:
        if col not in f.columns:
            f[col] = 0.0 if "edge" in col else 99.0
    
    h_cols = ["HomeTeamName", "AwayTeamName", "HomeWin%", "Mot_H", "Risk_H", "Status_H", "Val_H", "Mot_A", "Status_A", "edge_1", "sr_quality", "srDropping", "strangeOdds", "do_drop", "close_1", "fair_1", "matchExpertScore", "matchPick12"]
    a_cols = ["AwayTeamName", "HomeTeamName", "AwayWin%", "Mot_A", "Risk_A", "Status_A", "Val_A", "Mot_H", "Status_H", "edge_2", "sr_quality", "srDropping", "strangeOdds", "do_drop", "close_2", "fair_2", "matchExpertScore", "matchPick12"]
    
    h = f[h_cols].copy()
    a = f[a_cols].copy()
    h["is_home"] = True
    a["is_home"] = False
    
    # Perspective-based scores for ranking
    h["expertScore"] = h["matchExpertScore"]
    a["expertScore"] = -a["matchExpertScore"] # Flip for Away perspective
    
    # Adjust srDropping/edge for Away perspective
    a["srDropping"] = -a["srDropping"]
    if "do_drop" in a.columns: a["do_drop"] = -a["do_drop"]

    # Internal usage names
    base_cols = ["Team", "Opp", "TeamWinProb%", "TeamMot", "TeamRotRisk", "TeamStatus", "Val", "OppMot", "OppStatus", "SR_edge", "sr_quality", "srDropping", "strangeOdds", "do_drop", "Close", "Fair", "matchExpertScore", "matchPick12", "is_home", "expertScore"]
    h.columns = a.columns = base_cols
    
    ranking = pd.concat([h, a], ignore_index=True)
    ranking["SR_edge"] = ranking["SR_edge"].fillna(0.0)
    ranking["sr_quality"] = ranking["sr_quality"].fillna(0.0)
    ranking["srDropping"] = ranking["srDropping"].fillna(0.0)
    ranking["strangeOdds"] = ranking["strangeOdds"].fillna(0.0)
    ranking["ValFinal"] = ranking["Val"]
    
    # Apply Recommendations (Unified logic, no draws)
    ranking = format_recommendations(ranking, allow_draws=False)
    
    # Sort
    rec_order = {"🟢 STRONG BUY": 0, "🟡 CONSIDER": 1, "⚪ NEUTRAL": 2, "🟠 CAUTION": 3, "🔴 AVOID": 4}
    def get_sort_rank(status):
        for k, v in rec_order.items():
            if status.startswith(k): return v
        return 99

    ranking["_sort_rank"] = ranking["recommendation"].apply(get_sort_rank)
    ranking = ranking.sort_values(["_sort_rank", "ValFinal"], ascending=[True, False])
    ranking = ranking.drop(columns=["_sort_rank"])

    print(f"\n--- {l_name} TOP 10 RECOMMENDATIONS ---")
    
    final_cols = [
        "team", "opp", "teamWinProb%", "teamRotRisk", "teamMot", "oppMot", 
        "teamStatus", "oppStatus", "expertScore",
        "srCompleteness", "srEdge", "srDropping", "strangeOdds",
        "recommendation", "reason"
    ]
    
    rename_map = {
        "Team": "team", "Opp": "opp", "TeamWinProb%": "teamWinProb%", "TeamRotRisk": "teamRotRisk",
        "TeamMot": "teamMot", "OppMot": "oppMot", "TeamStatus": "teamStatus", "OppStatus": "oppStatus",
        "SR_edge": "srEdge", "sr_quality": "srCompleteness", "srDropping": "srDropping",
        "strangeOdds": "strangeOdds", "reason": "reason"
    }
    
    ranking_final = ranking.rename(columns=rename_map)[final_cols].copy()
    
    # Round all numeric columns
    for col in ranking_final.select_dtypes(include=[np.number]).columns:
        ranking_final[col] = ranking_final[col].round(2)

    print(ranking_final.head(10).to_string(index=False))
    
    try:
        if excel_pl:
            ranking_final.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig", decimal=",")
        else:
            ranking_final.to_csv(out_path, sep=",", index=False, encoding="utf-8", decimal=".")
        print(f"SUCCESS: Saved: {out_path.name}")
    except PermissionError:
        print(f"FAILED to save {out_path.name}")

def analyze_sr_only(input_file: Optional[Path], output_dir: Optional[Path], excel_pl: bool = False):
    """Execution flow for SR-only analysis (no The Analyst data)."""
    
    # 1. Determine Input File
    if input_file and input_file.exists():
        path = input_file
    else:
        # Default to standard cumulative file
        path = BASE_DIR / "data" / "soccer-rating" / "match_odds_development.csv"
    
    if not path.exists():
        print(f"ERROR: Input file not found: {path}")
        sys.exit(1)

    print(f"INFO: Loading SR data from: {path.name}")
    
    # 2. Extract Date for Filename (if input_file provided)
    import re
    date_str = ""
    # Try YYYY-MM-DD in filename
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if m:
        date_str = f"_{m.group(1)}"
    
    # 3. Load Data directly
    sr = read_smart_csv(path)
    
    # Needs basic numeric casting
    num_cols = ["oo","do","ao", "open_1","open_x","open_2", "drop_1","drop_x","drop_2",
                "close_1","close_x","close_2", "fair_1","fair_x","fair_2", "odds_distance",
                "team_rating_home", "team_rating_away"]
    sr = cast_numeric(sr, num_cols)

    # 4. Feature Engineering (SR-Only)
    # Since we have no fixtures file, SR data IS the fixture list.
    # Map columns to match what `add_soccer_rating_features` expects/produces
    # It expects: HomeKey, AwayKey, fair_1, close_1, etc.
    
    # We rename 'home_id'/'away_id' to HomeTeamName etc for display if names missing?
    # Actually SR file has `home_id`, `away_id` but typically NO team names unless we join with club_meta
    # BUT wait, the scraping saves `match_odds_development.csv` with just IDs.
    # We NEED team names.
    
    # Load club_meta to map IDs to Names (Fallback)
    meta_path = BASE_DIR / "data" / "soccer-rating" / "club_meta.csv"
    id_to_name = {}
    if meta_path.exists():
        meta = read_smart_csv(meta_path)
        # map id -> team_name
        id_to_name = meta.set_index("team_id")["team_name"].to_dict()
    
    # Load today_matches.csv for Names (Priority)
    today_path = BASE_DIR / "data" / "soccer-rating" / "today_matches.csv"
    today_map = {}
    if today_path.exists():
        try:
            today_df = read_smart_csv(today_path)
            if "match_id" in today_df.columns and "home_team" in today_df.columns and "away_team" in today_df.columns:
                today_map = today_df.set_index("match_id")[["home_team", "away_team"]].to_dict('index')
                print(f"INFO: Loaded {len(today_map)} active match names from today_matches.csv")
        except Exception as e:
            print(f"WARNING: Could not load today_matches.csv for name mapping: {e}")

    # Map IDs to Names with Priority logic
    def get_name(row, side):
        # 1. Try Match ID in Today Matches
        mid = row.get("match_id")
        if mid and mid in today_map:
            return today_map[mid][f"{side}_team"]
        
        # 2. Key Fallback: ID from club_meta
        tid_col = f"{side}_id"
        tid = row.get(tid_col)
        if pd.notna(tid):
            return id_to_name.get(int(tid), f"ID_{tid}")
        
        return f"UNK_{side}"

    sr["HomeTeamName"] = sr.apply(lambda r: get_name(r, "home"), axis=1)
    sr["AwayTeamName"] = sr.apply(lambda r: get_name(r, "away"), axis=1)
    
    # Prepare DataFrame 'f2' compatible structure
    # We need: close_1, fair_1, etc.
    f2 = sr.copy()
    
    valid_mask = (f2[["close_1", "close_x", "close_2", "fair_1", "fair_x", "fair_2"]] > 1.0).all(axis=1)
    
    # Initialize calculated columns
    for c in ["edge_1", "edge_x", "edge_2", "steam_diff", "prob_gap_1", "prob_gap_2", "rating_diff", "lineup_adv", "srDropping", "strangeOdds"]:
        f2[c] = 0.0

    # Calculate Probability & Steam
    if valid_mask.any():
        inv_close = (1.0 / f2.loc[valid_mask, "close_1"]) + (1.0 / f2.loc[valid_mask, "close_x"]) + (1.0 / f2.loc[valid_mask, "close_2"])
        inv_fair = (1.0 / f2.loc[valid_mask, "fair_1"]) + (1.0 / f2.loc[valid_mask, "fair_x"]) + (1.0 / f2.loc[valid_mask, "fair_2"])
        
        for side in ["1", "x", "2"]:
            p_fair = (1.0 / f2.loc[valid_mask, f"fair_{side}"]) / inv_fair
            p_close = (1.0 / f2.loc[valid_mask, f"close_{side}"]) / inv_close
            
            f2.loc[valid_mask, f"edge_{side}"] = (p_fair - p_close)
            f2.loc[valid_mask, f"p_close_{side}"] = p_close
            f2.loc[valid_mask, f"p_fair_{side}"] = p_fair
            f2.loc[valid_mask, f"prob_gap_{side}"] = p_close - p_fair
            
            # Steam
            open_v = f2.loc[valid_mask, f"open_{side}"].clip(lower=1.01)
            close_v = f2.loc[valid_mask, f"close_{side}"].clip(lower=1.01)
            f2.loc[valid_mask, f"steam_{side}"] = np.log(open_v / close_v)

        f2.loc[valid_mask, "steam_diff"] = f2.loc[valid_mask, "steam_1"] - f2.loc[valid_mask, "steam_2"]
        f2.loc[valid_mask, "rating_diff"] = f2.loc[valid_mask, "team_rating_home"] - f2.loc[valid_mask, "team_rating_away"]
        
    f2["srDropping"] = f2["steam_diff"]
    
    # Explicit DO signal boost
    # OO/DO/AO are Value Ratings (ROI%), not Odds. 
    # Positive = Good Value. Negative = Bad Value.
    # Improvement (Steam) = DO > OO.
    # Calculation: (DO - OO) / 100.0 to match steam scale (log odds)
    if "do" in f2.columns and "oo" in f2.columns:
        f2["do_drop"] = (f2["do"] - f2["oo"]) / 100.0
    else:
        f2["do_drop"] = 0.0

    # Strange Odds Logic
    if "ao" in f2.columns:
        f2["strangeOdds"] = np.where(f2["ao"].abs() > 30, f2["ao"], 0.0)
        
    # Quality
    has_sr = f2["fair_1"].notna() & valid_mask
    f2["srCompleteness"] = np.where(
        has_sr & (f2.get("match_confidence", "LOW") == "HIGH") & (f2["odds_distance"] <= 0.01),
        1.0,
        np.where(has_sr, 0.5, 0.0)
    )

    # 5. Recommendation Logic (SR-Only)
    # No Mot, Risk, Status from Analyst.
    # Base recommendation purely on Market Signals.
    
    # Expert Score
    s_rating_home = f2["rating_diff"] / 300.0
    
    p1 = f2.get("p_close_1", pd.Series(0.5, index=f2.index)).fillna(0.5)
    p2 = f2.get("p_close_2", pd.Series(0.5, index=f2.index)).fillna(0.5)
    s_close_home = np.log((p1 / p2).clip(0.01, 100))
    
    s_steam_home = f2["steam_diff"].fillna(0.0)
    s_gap_home = (f2["prob_gap_1"] - f2["prob_gap_2"]).fillna(0.0)
    
    # DO Bonus: If do_drop > 0, slightly boost steam component or overall score
    # Let's add it as a small bonus to steam weight effect
    s_do_bonus = f2["do_drop"].fillna(0.0) * 2.0 # Scale it up

    score_home = W_RATING * s_rating_home + W_CLOSE * s_close_home + \
                 W_STEAM * (s_steam_home + s_do_bonus) + W_GAP * s_gap_home
    
    
    f2["expertScore"] = score_home
    
    # Pick Logic:
    # 1: Score > 0.1
    # 2: Score < -0.1
    # X: Between -0.1 and 0.1 (Tight zone)
    
    # Default based on score
    conditions = [
        f2["expertScore"] > 0.1,
        f2["expertScore"] < -0.1
    ]
    choices = ["1", "2"]
    f2["pick12"] = np.select(conditions, choices, default="X")
    
    # Override for High Draw Value?
    # If edge_x > 0.10 (Huge Draw Value) -> Force X consideration?
    # Let's rely on default 'X' capturing the 'uncertain' middle, and then Recommendation logic promoting it based on Edge.
    
    # 6. Build Ranking Table (Standardized for format_recommendations)
    # --------------------------------------------------------------
    
    # Prepare common columns
    # We populate dummy Analyst columns to satisfy format_recommendations schema if needed,
    # though vectorized version uses .get() so it's safe.
    
    # Home Perspective
    h = f2.copy()
    h["Team"] = h["HomeTeamName"]
    h["Opp"] = h["AwayTeamName"]
    h["Close"] = h["close_1"].fillna(99.0)
    h["Fair"] = h["fair_1"].fillna(99.0)
    h["SR_edge"] = h["edge_1"]
    h["srDropping"] = h["steam_diff"]
    # do_drop is (do-oo)/100. Assuming positive = home value/steam.
    h["do_drop"] = h["do_drop"]
    h["edge_x"] = h["edge_x"] # Pass Draw Edge
    h["steam_x"] = h["steam_x"] # Pass Draw Steam
    h["steam_1"] = h["steam_1"] # Pass Home Steam (for dominance logic)
    h["steam_2"] = h["steam_2"] # Pass Away Steam (for dominance logic)
    h["p_fair_x"] = h["p_fair_x"] # Pass Fair Draw Probability
    h["is_home"] = True

    # Away Perspective
    a = f2.copy()
    a["Team"] = a["AwayTeamName"]
    a["Opp"] = a["HomeTeamName"]
    a["Close"] = a["close_2"].fillna(99.0)
    a["Fair"] = a["fair_2"].fillna(99.0)
    a["SR_edge"] = a["edge_2"].fillna(0)
    a["srDropping"] = -a["steam_diff"] # Flip for Away perspective
    a["do_drop"] = -a["do_drop"] # Flip (do-oo) for Away perspective
    a["edge_x"] = a["edge_x"] # Pass Draw Edge
    a["steam_x"] = a["steam_x"] # Pass Draw Steam
    a["steam_1"] = a["steam_1"] # Pass Home Steam (for dominance logic)
    a["steam_2"] = a["steam_2"] # Pass Away Steam (for dominance logic)
    a["p_fair_x"] = a["p_fair_x"] # Pass Fair Draw Probability
    a["is_home"] = False

    ranking = pd.concat([h, a], ignore_index=True)

    # Fill Missing Analyst Columns with Defaults
    ranking["valFinal"] = 0.0 # No Analyst Value
    ranking["TeamStatus"] = "IN_PLAY"
    ranking["TeamRotRisk"] = 1.0
    ranking["teamWinProb%"] = 0.5
    ranking["TeamMot"] = 0
    ranking["OpMot"] = 0
    
    # Apply Recommendations (Unified logic, draws allowed)
    ranking = format_recommendations(ranking, allow_draws=True)
    
    # 7. Sort & Output
    # ----------------
    rec_order = {"🟢 STRONG BUY": 0, "🟡 CONSIDER": 1, "⚪ NEUTRAL": 2, "🟠 CAUTION": 3, "🔴 AVOID": 4}
    
    ranking["_sort_rank"] = ranking["recommendation"].map(rec_order).fillna(99).astype(int)
    ranking["_abs_score"] = ranking["expertScore"].abs()
    
    # FILTER: Show only favored side per match
    is_pick_1 = ranking["pick12"] == "1"
    is_pick_2 = ranking["pick12"] == "2"
    is_pick_x = ranking["pick12"] == "X"
    
    match_mask = (is_pick_1 & ranking["is_home"]) | \
                 (is_pick_2 & ~ranking["is_home"]) | \
                 (is_pick_x & ranking["is_home"])
    
    ranking = ranking[match_mask].copy()
    ranking = ranking.sort_values(["_sort_rank", "_abs_score"], ascending=[True, False])
    
    print(f"\n--- SR-ONLY ANALYSIS TOP 10 RECOMMENDATIONS ---")
    
    result_cols = [
        "homeTeam", "awayTeam", "expertScore", "pick",
        "srCompleteness", "srEdge", "srDropping", "strangeOdds",
        "recommendation", "reason"
    ]
    
    rename_map = {
        "HomeTeamName": "homeTeam", "AwayTeamName": "awayTeam", 
        "SR_edge": "srEdge", 
        "expertScore": "expertScore", "pick12": "pick",
        "srCompleteness": "srCompleteness", "srDropping": "srDropping", "strangeOdds": "strangeOdds",
        "recommendation": "recommendation", "reason": "reason"
    }
    
    final_df = ranking.rename(columns=rename_map)
    # Ensure columns exist
    for c in result_cols:
        key = rename_map.get(c, c)
        if key not in final_df.columns:
            final_df[key] = 0
    
    # Final rounding
    for col in final_df.select_dtypes(include=[np.number]).columns:
        final_df[col] = final_df[col].round(2)
            
    final_view = final_df[[rename_map.get(c, c) for c in result_cols]].copy()
    
    print(final_view.head(10).to_string(index=False))
    
    # Save
    if output_dir:
        out_path = output_dir / f"sr_analysis_report{date_str}.csv"
    else:
        out_path = BASE_DIR / f"sr_analysis_report{date_str}.csv"
        
    try:
        if excel_pl:
            final_view.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig", decimal=",")
        else:
            final_view.to_csv(out_path, sep=",", index=False, encoding="utf-8", decimal=".")
        print(f"SUCCESS: Saved SR-Only report to: {out_path}")
    except PermissionError:
        print(f"FAILED to save {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UEFA Cups Fantasy Analyzer")
    parser.add_argument("--cl", action="store_true", help="Analyze Champions League")
    parser.add_argument("--el", action="store_true", help="Analyze Europa League")
    parser.add_argument("--excel-pl", action="store_true", help="Output in Polish Excel format (; separator, , decimal)")
    
    # New Arguments
    parser.add_argument("--sr-only", action="store_true", help="Run analysis based ONLY on Soccer-rating data (no Analyst dependency)")
    parser.add_argument("--input-file", type=Path, help="Path to specific SR snapshot file (for --sr-only)")
    parser.add_argument("--output-dir", type=Path, help="Directory to save output files")
    
    args = parser.parse_args()

    if args.sr_only:
        analyze_sr_only(args.input_file, args.output_dir, excel_pl=args.excel_pl)
    else:
        # Standard Mode
        run_all = not (args.cl or args.el)
        if run_all or args.cl: analyze_league("cl", excel_pl=args.excel_pl)
        if run_all or args.el: analyze_league("el", excel_pl=args.excel_pl)
