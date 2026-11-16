"""Input files: CSV reading, the data directory layout, the loaders of both sources and their clean-up."""

from pathlib import Path

import pandas as pd

from src.analyzer.errors import AnalyzerInputError
from src.analyzer.names import norm_key

LEAGUE_DIRS = {"cl": "champions-league", "el": "europa-league"}
FIXTURES_NUMERIC_COLUMNS = ["HomeWin%", "Draw%", "AwayWin%"]
TABLE_NUMERIC_COLUMNS = ["XPOS", "XPTS", "LEAGUE%", "KO P/0%", "LAST 16%", "QF%", "SF%", "FINAL%", "WINNER%"]
ODDS_NUMERIC_COLUMNS = [
    "oo",
    "do",
    "ao",
    "open_1",
    "open_x",
    "open_2",
    "drop_1",
    "drop_x",
    "drop_2",
    "close_1",
    "close_x",
    "close_2",
    "fair_1",
    "fair_x",
    "fair_2",
    "odds_distance",
    "team_rating_home",
    "team_rating_away",
]


def cast_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Copy of `df` with the present `cols` cast to float (dot or comma decimals; unreadable values become 0.0)."""
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0.0)
    return df


def read_smart_csv(path: Path) -> pd.DataFrame:
    """Reads CSV with automatic separator detection (handles ; and ,); raises AnalyzerInputError when missing."""
    try:
        # Try reading a few lines to detect separator
        with path.open(encoding="utf-8-sig") as f:
            first_line = f.readline()
            sep = ";" if ";" in first_line else ","

        return pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Fallback to standard utf-8
        with path.open(encoding="utf-8") as f:
            first_line = f.readline()
            sep = ";" if ";" in first_line else ","
        return pd.read_csv(path, sep=sep, encoding="utf-8")
    except FileNotFoundError as err:
        raise AnalyzerInputError(f"Missing file: {path}") from err


def soccer_rating_dir(base_dir: Path) -> Path:
    return base_dir / "data" / "soccer-rating"


def load_league_data(base_dir: Path, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Loads fixtures and predicted table for a given league prefix (cl/el)."""
    data_dir = base_dir / "data" / "theanalyst" / LEAGUE_DIRS[prefix]
    fixtures = read_smart_csv(data_dir / f"{prefix}_fixtures.csv")
    table = read_smart_csv(data_dir / f"{prefix}_table_predicted.csv")
    return cast_numeric(fixtures, FIXTURES_NUMERIC_COLUMNS), cast_numeric(table, TABLE_NUMERIC_COLUMNS)


def cup_rows(sr: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Rows of the cup's league code: cl -> CLCUP, el -> ELCUP."""
    league_code = "CLCUP" if prefix == "cl" else "ELCUP"
    return sr[sr["league_code"] == league_code].copy()


def latest_snapshots(sr: pd.DataFrame) -> pd.DataFrame:
    """The latest snapshot per match (avoids duplicates), with the odds columns cast to float."""
    if "match_id" in sr.columns:
        if "snapshot_date" in sr.columns:
            sr = sr.assign(snapshot_date=pd.to_datetime(sr["snapshot_date"], errors="coerce"))
            sr = sr.sort_values("snapshot_date").drop_duplicates(["match_id"], keep="last")
        else:
            sr = sr.drop_duplicates(["match_id"], keep="last")
    elif "snapshot_date" in sr.columns:
        sr = sr.assign(snapshot_date=pd.to_datetime(sr["snapshot_date"], errors="coerce"))
        sr = sr.sort_values("snapshot_date").drop_duplicates(["home_id", "away_id"], keep="last")
    return cast_numeric(sr, ODDS_NUMERIC_COLUMNS)


def with_lineups(sr: pd.DataFrame, today: pd.DataFrame) -> pd.DataFrame:
    """Adds today's lineup ratings and type (today_matches.csv) by match_id."""
    today = cast_numeric(today, ["lineup_rating_home_today", "lineup_rating_away_today"])
    if "match_id" in sr.columns and "match_id" in today.columns:
        lineup_cols = ["match_id", "lineup_rating_home_today", "lineup_rating_away_today", "lineup_type_today"]
        return sr.merge(today[lineup_cols], on="match_id", how="left")
    return sr


def with_team_keys(sr: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Maps team ids to name keys through club_meta.csv and keeps one row per mapped pair of keys."""
    key_by_id = meta.set_index(meta["team_id"].astype(str))["team_name"].map(norm_key).to_dict()
    sr = sr.assign(HomeKey=sr["home_id"].astype(str).map(key_by_id), AwayKey=sr["away_id"].astype(str).map(key_by_id))
    # Drop records that couldn't be mapped
    sr = sr.dropna(subset=["HomeKey", "AwayKey"])
    # Deduplicate strictly on valid keys to prevent Cartesian products in merge
    return sr.drop_duplicates(subset=["HomeKey", "AwayKey"], keep="last")


def load_soccer_rating(base_dir: Path, prefix: str) -> pd.DataFrame:
    """Latest soccer-rating odds of the cup with lineups and team keys; empty when there is nothing to merge."""
    sr_dir = soccer_rating_dir(base_dir)
    path = sr_dir / "match_odds_development.csv"
    if not path.exists():
        return pd.DataFrame()

    sr = cup_rows(read_smart_csv(path), prefix)
    if sr.empty:
        return pd.DataFrame()

    sr = latest_snapshots(sr)
    today_path = sr_dir / "today_matches.csv"
    if today_path.exists():
        sr = with_lineups(sr, read_smart_csv(today_path))
    meta_path = sr_dir / "club_meta.csv"
    if not meta_path.exists():
        # No club_meta.csv: no team keys, so this fails with KeyError as before (known debt)
        return sr.dropna(subset=["HomeKey", "AwayKey"])
    return with_team_keys(sr, read_smart_csv(meta_path))


def load_club_names(path: Path) -> dict[int, str]:
    """Team id -> name from club_meta.csv; empty when the file is missing."""
    if not path.exists():
        return {}
    meta = read_smart_csv(path)
    names: dict[int, str] = meta.set_index("team_id")["team_name"].to_dict()
    return names


def load_today_names(path: Path) -> dict[str, dict[str, str]] | None:
    """Match id -> {home_team, away_team} from today_matches.csv; None when the file lacks these columns."""
    today = read_smart_csv(path)
    if "match_id" in today.columns and "home_team" in today.columns and "away_team" in today.columns:
        names: dict[str, dict[str, str]] = today.set_index("match_id")[["home_team", "away_team"]].to_dict("index")
        return names
    return None
