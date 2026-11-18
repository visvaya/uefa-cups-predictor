"""Input files: CSV reading, the data directory layout, the loaders of both sources and their clean-up."""

from pathlib import Path

import pandas as pd

from analyzer.errors import AnalyzerInputError
from analyzer.names import norm_key
from analyzer.sr_only import TODAY_MATCH_COLUMNS

LEAGUE_DIRS = {"cl": "champions-league", "el": "europa-league", "ecl": "conference-league"}
# soccer-rating league code of each cup
CUP_CODES = {"cl": "CLCUP", "el": "ELCUP", "ecl": "ECLCUP"}
FIXTURES_NUMERIC_COLUMNS = ["HomeWin%", "Draw%", "AwayWin%"]
TABLE_NUMERIC_COLUMNS = ["XPOS", "XPTS", "LEAGUE%", "KO P/0%", "LAST 16%", "QF%", "SF%", "FINAL%", "WINNER%"]
# Percent columns of the Analyst table (every fixtures column is one);
# a file whose values never exceed 1 holds fractions instead
TABLE_PERCENT_COLUMNS = ["LEAGUE%", "KO P/0%", "LAST 16%", "QF%", "SF%", "FINAL%", "WINNER%"]
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


def require_columns(df: pd.DataFrame, cols: list[str], name: str) -> None:
    """Raises AnalyzerInputError naming the `cols` that `df` (read from file `name`) lacks."""
    if missing := [c for c in cols if c not in df.columns]:
        raise AnalyzerInputError(f"{name}: missing columns {missing}")


def analyst_numbers(df: pd.DataFrame, cols: list[str], percent_cols: list[str], name: str) -> pd.DataFrame:
    """Copy of an Analyst file with `cols` as floats (dot or comma decimals).

    Raises AnalyzerInputError for a missing column, a blank or unreadable cell, a percentage outside 0 to 100, or
    percent columns that hold fractions (no value above 1): silently reading 0 there would mark teams OUT.
    """
    require_columns(df, cols, name)
    df = df.copy()
    for c in cols:
        values = pd.to_numeric(df[c].astype(str).str.strip().str.replace(",", "."), errors="coerce")
        if bad := df.loc[values.isna(), c].fillna("").astype(str).tolist():
            raise AnalyzerInputError(f"{name}: unreadable values in column {c}: {bad}")
        df[c] = values
    for c in percent_cols:
        if bad := df.loc[~df[c].between(0, 100), c].tolist():
            raise AnalyzerInputError(f"{name}: values outside 0 to 100 in column {c}: {bad}")
    if (df[percent_cols] <= 1).all().all():
        raise AnalyzerInputError(f"{name}: {percent_cols} must be in percent (0 to 100), not fractions")
    return df


def read_smart_csv(path: Path) -> pd.DataFrame:
    """Reads UTF-8 CSV (BOM optional) with the separator taken from the header (; or ,).

    Raises AnalyzerInputError when the file is missing; a file that is not UTF-8 raises UnicodeDecodeError.
    """
    try:
        with path.open(encoding="utf-8-sig") as f:
            sep = ";" if ";" in f.readline() else ","
        return pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    except FileNotFoundError as err:
        raise AnalyzerInputError(f"Missing file: {path}") from err


def soccer_rating_dir(base_dir: Path) -> Path:
    return base_dir / "data" / "soccer-rating"


def analyst_paths(base_dir: Path, prefix: str) -> tuple[Path, Path]:
    """The cup's Analyst fixtures and predicted table files (prefix cl/el/ecl)."""
    data_dir = base_dir / "data" / "theanalyst" / LEAGUE_DIRS[prefix]
    return data_dir / f"{prefix}_fixtures.csv", data_dir / f"{prefix}_table_predicted.csv"


def load_league_data(base_dir: Path, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Loads fixtures and predicted table for a given league prefix (cl/el)."""
    fixtures_path, table_path = analyst_paths(base_dir, prefix)
    fixtures_name, table_name = fixtures_path.name, table_path.name
    fixtures, table = read_smart_csv(fixtures_path), read_smart_csv(table_path)
    require_columns(fixtures, ["HomeTeam", "AwayTeam"], fixtures_name)
    require_columns(table, ["TEAM"], table_name)
    return (
        analyst_numbers(fixtures, FIXTURES_NUMERIC_COLUMNS, FIXTURES_NUMERIC_COLUMNS, fixtures_name),
        analyst_numbers(table, TABLE_NUMERIC_COLUMNS, TABLE_PERCENT_COLUMNS, table_name),
    )


def cup_rows(sr: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Rows of the cup's soccer-rating league code (`CUP_CODES`)."""
    return sr[sr["league_code"] == CUP_CODES[prefix]].copy()


def by_snapshot_date(sr: pd.DataFrame) -> pd.DataFrame:
    """Rows from the oldest snapshot to the newest; a row without a date or scrape time counts as the oldest.

    Within one date the scrape time (`scraped_at`, when the file has it) decides. The sort is stable, so rows
    without a scrape time keep their file order and the later row stays last.
    """
    sr = sr.assign(snapshot_date=pd.to_datetime(sr["snapshot_date"], errors="coerce"))
    if "scraped_at" in sr.columns:
        sr = sr.assign(scraped_at=pd.to_datetime(sr["scraped_at"], errors="coerce", utc=True))
        sr = sr.sort_values("scraped_at", kind="stable", na_position="first")
    return sr.sort_values("snapshot_date", kind="stable", na_position="first")


def latest_snapshots(sr: pd.DataFrame) -> pd.DataFrame:
    """The latest snapshot per match (avoids duplicates), with the odds columns cast to float."""
    if "match_id" in sr.columns:
        if "snapshot_date" in sr.columns:
            sr = by_snapshot_date(sr)
        sr = sr.drop_duplicates(["match_id"], keep="last")
    elif "snapshot_date" in sr.columns:
        sr = by_snapshot_date(sr).drop_duplicates(["home_id", "away_id"], keep="last")
    return cast_numeric(sr, ODDS_NUMERIC_COLUMNS)


def with_today_columns(sr: pd.DataFrame, today: pd.DataFrame) -> pd.DataFrame:
    """Adds today's kickoff, lineup ratings and type (today_matches.csv) by match_id; empty ones without a match_id."""
    today = cast_numeric(today, ["lineup_rating_home_today", "lineup_rating_away_today"])
    if "match_id" in sr.columns and "match_id" in today.columns:
        today_cols = [
            "match_id",
            "time_local",
            "lineup_rating_home_today",
            "lineup_rating_away_today",
            "lineup_type_today",
        ]
        # reindex: a today file without time_local or without the lineup columns merges with empty values instead
        # of raising; "" is the one value of a missing kickoff
        merged = sr.merge(today.reindex(columns=today_cols), on="match_id", how="left")
        return merged.assign(time_local=merged["time_local"].fillna(""))
    return sr.assign(
        time_local="",
        lineup_rating_home_today=float("nan"),
        lineup_rating_away_today=float("nan"),
        lineup_type_today="",
    )


def with_team_keys(sr: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Maps team ids to name keys through club_meta.csv and keeps one row per mapped pair of keys."""
    key_by_id = meta.set_index(meta["team_id"].astype(str))["team_name"].map(norm_key).to_dict()
    sr = sr.assign(HomeKey=sr["home_id"].astype(str).map(key_by_id), AwayKey=sr["away_id"].astype(str).map(key_by_id))
    # Drop records that couldn't be mapped
    sr = sr.dropna(subset=["HomeKey", "AwayKey"])
    # Deduplicate strictly on valid keys to prevent Cartesian products in merge
    return sr.drop_duplicates(subset=["HomeKey", "AwayKey"], keep="last")


def load_soccer_rating(base_dir: Path, prefix: str) -> tuple[pd.DataFrame, list[str]]:
    """Latest soccer-rating odds of the cup with lineups and team keys, and warnings on missing optional files.

    The frame is empty when there is nothing to merge.
    """
    sr_dir = soccer_rating_dir(base_dir)
    path = sr_dir / "match_odds_development.csv"
    if not path.exists():
        return pd.DataFrame(), []

    sr = cup_rows(read_smart_csv(path), prefix)
    if sr.empty:
        return pd.DataFrame(), []
    meta_path = sr_dir / "club_meta.csv"
    if not meta_path.exists():
        # Without club_meta.csv the team ids cannot be mapped to the fixtures' names
        return pd.DataFrame(), [
            f"WARNING: {meta_path.name} not found: team ids cannot be mapped, running without soccer-rating data"
        ]

    notes = []
    today_path = sr_dir / "today_matches.csv"
    if today_path.exists():
        today = read_smart_csv(today_path)
    else:
        today = pd.DataFrame()
        notes.append(f"WARNING: {today_path.name} not found: running without lineups")
    sr = with_today_columns(latest_snapshots(sr), today)
    return with_team_keys(sr, read_smart_csv(meta_path)), notes


def load_club_names(path: Path) -> dict[int, str]:
    """Team id -> name from club_meta.csv; empty when the file is missing."""
    if not path.exists():
        return {}
    meta = read_smart_csv(path)
    names: dict[int, str] = meta.set_index("team_id")["team_name"].to_dict()
    return names


TODAY_COLUMNS = ["home_team", "away_team", *TODAY_MATCH_COLUMNS]


def load_today_names(path: Path) -> dict[str, dict[str, str]] | None:
    """Match id -> today's TODAY_COLUMNS (missing ones as "") from today_matches.csv.

    None when the file lacks match_id, home_team or away_team.
    """
    today = read_smart_csv(path)
    if "match_id" in today.columns and "home_team" in today.columns and "away_team" in today.columns:
        rows = today.set_index("match_id").reindex(columns=TODAY_COLUMNS).astype(object).fillna("").astype(str)
        names: dict[str, dict[str, str]] = rows.to_dict("index")
        return names
    return None
