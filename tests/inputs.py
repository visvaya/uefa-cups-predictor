"""Test inputs and helpers shared by several test modules: the synthetic soccer-rating set, an EL base dir built
from it, and the tabs of a results page."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from analyzer.data import ODDS_NUMERIC_COLUMNS, cast_numeric, load_club_names, load_today_names, read_smart_csv

REPO_DIR = Path(__file__).resolve().parents[1]
SR_FIXTURES_DIR = REPO_DIR / "tests" / "fixtures" / "soccer-rating"


def fixture_sr_only(
    function: Callable[[pd.DataFrame, dict[int, str], dict[str, dict[str, str]], str], pd.DataFrame],
    decimal: str = ".",
) -> pd.DataFrame:
    """`function` (`sr_only_report` or `sr_only_ranking`) applied to the fixture soccer-rating files."""
    sr = cast_numeric(read_smart_csv(SR_FIXTURES_DIR / "match_odds_development_2026-01-28.csv"), ODDS_NUMERIC_COLUMNS)
    today = load_today_names(SR_FIXTURES_DIR / "today_matches.csv") or {}
    return function(sr, load_club_names(SR_FIXTURES_DIR / "club_meta.csv"), today, decimal)


def el_base_dir(tmp_path: Path) -> Path:
    """A base dir holding the EL example inputs under their real names and the fixture soccer-rating files."""
    league = tmp_path / "data" / "theanalyst" / "europa-league"
    league.mkdir(parents=True)
    for kind in ("fixtures", "table_predicted"):
        shutil.copy(
            REPO_DIR / "data" / "theanalyst" / "europa-league" / f"el_{kind}_example.csv", league / f"el_{kind}.csv"
        )
    shutil.copytree(SR_FIXTURES_DIR, tmp_path / "data" / "soccer-rating")
    return tmp_path


def text_of(page: str) -> str:
    """The page as a reader sees its words: no-break spaces as spaces, without the joiners after hyphens."""
    return page.replace("&nbsp;", " ").replace(chr(0x2060), "")


def view_of(page: str, key: str) -> str:
    """One tab of a results page: the soccer-rating tab ends where the cups tab starts, which runs to the page's end."""
    sr, full = page.index('id="view-sr"'), page.index('id="view-full"')
    return page[sr:full] if key == "sr" else page[full:]
