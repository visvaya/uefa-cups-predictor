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
    "boda/glimt": "bodo/glimt",
    "kabenhavn": "kobenhavn",
    "atletico madrid": "atletico",
    "atletico de madrid": "atletico",
    "real": "real madrid",
    "nottm forest": "nottingham forest",
}

# Status Point Bonuses for Value Calculation
STATUS_BONUSES: Dict[str, float] = {
    "OUT": 0.22,
    "LOCKED_DIRECT_RO16": 0.12,
    "LOCKED_PLAYOFFS": 0.15
}

# Values for recommendations
RECOMMENDATION_LEVELS = [
    ("🔴 AVOID (OUT)", lambda df: df["Status"] == "OUT"),
    ("🟠 CAUTION (Rotation)", lambda df: df["Risk"] >= 1.6),
    ("🟢 STRONG BUY", lambda df: df["Val"] >= 70),
    ("🟡 CONSIDER", lambda df: df["Val"] >= 50),
]

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

def load_league_data(prefix: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads fixtures and predicted table for a given league prefix (cl/el)."""
    league_dir = "champions-league" if prefix == "cl" else "europa-league"
    data_dir = BASE_DIR / "data" / league_dir
    
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
        print(f"⚠️  VALUES OUT OF RANGE [0, 100] DETECTED!")
    
    # Monotonicity
    viol = ~(
        (df["WINNER%"] <= df["FINAL%"] + 1e-6) & 
        (df["FINAL%"] <= df["SF%"] + 1e-6) & 
        (df["SF%"] <= df["QF%"] + 1e-6)
    )
    if viol.any():
        print(f"⚠️  MONOTONICITY VIOLATIONS ({viol.sum() or 0} teams)")
    else:
        print("✅ Monotonicity (W<=F<=SF<=Q): OK")

    # Top 24 Consistency
    raw_sum = df["LAST 16%"] + df["KO P/0%"]
    anom = raw_sum > 100.0001
    if anom.any():
        print(f"⚠️  INCONSISTENT TOP 24 (Sum > 100% for {anom.sum() or 0} teams)")
    else:
        print("✅ Top 24 Consistency: OK")
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
    def calc_val(pfx, opp):
        tm_m, op_m = df[f"Mot_{pfx}"] / 100.0, df[f"Mot_{opp}"] / 100.0
        st_b = df[f"Status_{opp}"].map(STATUS_BONUSES).fillna(0.0)
        mot_b = 0.18 * sigmoid((0.45 - op_m) / 0.08)
        opp_dead = (1.0 + st_b + mot_b).clip(1.0, 1.35)
        return (100 * (df[f"EV_{pfx}"] / 3.0) * (0.55 + 0.45 * tm_m) * opp_dead / df[f"Risk_{pfx}"]).clip(0, 140)

    df["Val_H"] = calc_val("H", "A")
    df["Val_A"] = calc_val("A", "H")
    return df

def format_recommendations(ranking: pd.DataFrame) -> pd.DataFrame:
    """Adds recommendation labels and rounds numeric values."""
    cond = [check(ranking) for _, check in RECOMMENDATION_LEVELS]
    choices = [label for label, _ in RECOMMENDATION_LEVELS]
    ranking["Recommendation"] = np.select(cond, choices, default="⚪ NEUTRAL")

    ranking["Win%"] = (ranking["Win%"] * 100).round(1)
    for c in ["EV", "Risk"]: ranking[c] = ranking[c].round(2)
    for c in ["Mot", "OpMot", "Val"]: ranking[c] = ranking[c].round(1)
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

    # Probs & EV
    p_sum = (f["HomeWin%"] + f["Draw%"] + f["AwayWin%"]).replace(0, 1)
    for c in ["HomeWin%", "Draw%", "AwayWin%"]: f[c] = (f[c] / p_sum).fillna(0.0)
    f["EV_H"] = 3 * f["HomeWin%"] + 1 * f["Draw%"]
    f["EV_A"] = 3 * f["AwayWin%"] + 1 * f["Draw%"]

    # Final Calcs
    f = calculate_values(f)

    # Flatten & Rank
    h = f[["HomeTeamName", "AwayTeamName", "HomeWin%", "EV_H", "Mot_H", "Risk_H", "Status_H", "Val_H", "Mot_A", "Status_A"]].copy()
    a = f[["AwayTeamName", "HomeTeamName", "AwayWin%", "EV_A", "Mot_A", "Risk_A", "Status_A", "Val_A", "Mot_H", "Status_H"]].copy()
    
    idx_cols = ["Team", "Opp", "Win%", "EV", "Mot", "Risk", "Status", "Val", "OpMot", "OpStatus"]
    h.columns = a.columns = idx_cols
    
    ranking = pd.concat([h, a]).sort_values("Val", ascending=False)
    ranking = format_recommendations(ranking)

    print(f"\n--- {l_name} TOP 10 RECOMMENDATIONS ---")
    print(ranking.head(10).to_string(index=False))
    
    try:
        if excel_pl:
            ranking.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig", decimal=",")
        else:
            ranking.to_csv(out_path, sep=",", index=False, encoding="utf-8", decimal=".")
        print(f"✅ Saved: {out_path.name}")
    except PermissionError:
        print(f"❌ FAILED to save {out_path.name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UEFA Cups Fantasy Analyzer")
    parser.add_argument("--cl", action="store_true", help="Analyze Champions League")
    parser.add_argument("--el", action="store_true", help="Analyze Europa League")
    parser.add_argument("--excel-pl", action="store_true", help="Output in Polish Excel format (; separator, , decimal)")
    args = parser.parse_args()

    run_all = not (args.cl or args.el)
    if run_all or args.cl: analyze_league("cl", excel_pl=args.excel_pl)
    if run_all or args.el: analyze_league("el", excel_pl=args.excel_pl)
