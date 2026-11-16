"""Golden-file tests that pin the complete CSV reports of the analyzer.

They cover `run_league` for both cups and `run_sr_only`, each in the default and the `--excel-pl` format,
so a refactor of the analyzer cannot change a value, label, row order or column order unnoticed.

Inputs: the tracked The Analyst examples (`data/theanalyst/**/*_example.csv`; two rows of the Europa League table
are edited in `EL_TABLE_EDITS` so that both LOCKED statuses occur) and the synthetic soccer-rating set in
`tests/fixtures/soccer-rating/`. Line endings are normalised, since pandas writes CRLF on Windows.

Regenerate the golden files only when a change of the reports is intended (a new rule, threshold or column), never
to make a refactor pass: `UPDATE_GOLDEN=1 uv run pytest tests/test_golden_reports.py`, then review the diff of
`tests/golden/` before committing it.
"""

import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from analyzer.cli import run_league, run_sr_only
from analyzer.config import VALUE_MAX

TESTS_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = TESTS_DIR.parent / "data" / "theanalyst"
SR_FIXTURES_DIR = TESTS_DIR / "fixtures" / "soccer-rating"
GOLDEN_DIR = TESTS_DIR / "golden"
LEAGUE_DIRS = {"cl": "champions-league", "el": "europa-league"}
SR_ONLY_INPUT = "match_odds_development_2026-01-28.csv"
# Team A reaches LAST 16% 99 (LOCKED_DIRECT_RO16), Team X KO P/0% 97 with LAST 16% 2 (LOCKED_PLAYOFFS).
EL_TABLE_EDITS = {
    "1;Team A;18,0;8,0;2,0;90,0;": "1;Team A;18,0;8,0;1,0;99,0;",
    "24;Team X;8,2;0,0;94,0;": "24;Team X;8,2;0,0;97,0;",
}
FORMATS = pytest.mark.parametrize("excel_pl", [False, True], ids=["default", "excel-pl"])


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """Lays out the inputs under the names the analyzer expects; the tests pass this directory as `base_dir`."""
    for prefix, league in LEAGUE_DIRS.items():
        league_dir = tmp_path / "data" / "theanalyst" / league
        league_dir.mkdir(parents=True)
        for kind in ("fixtures", "table_predicted"):
            shutil.copyfile(EXAMPLES_DIR / league / f"{prefix}_{kind}_example.csv", league_dir / f"{prefix}_{kind}.csv")

    el_table = tmp_path / "data" / "theanalyst" / "europa-league" / "el_table_predicted.csv"
    text = el_table.read_text(encoding="utf-8")
    for old, new in EL_TABLE_EDITS.items():
        assert old in text, f"EL example table changed, update EL_TABLE_EDITS: {old}"
        text = text.replace(old, new)
    el_table.write_text(text, encoding="utf-8", newline="")

    shutil.copytree(SR_FIXTURES_DIR, tmp_path / "data" / "soccer-rating")
    return tmp_path


def assert_matches_golden(report: Path, golden_name: str) -> None:
    """Compares the report with its golden file as text (BOM kept, line endings normalised)."""
    actual = report.read_text(encoding="utf-8")
    golden = GOLDEN_DIR / golden_name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        golden.write_text(actual, encoding="utf-8", newline="")
    assert golden.exists(), f"Missing {golden}; create it with UPDATE_GOLDEN=1"
    assert actual == golden.read_text(encoding="utf-8")


def golden_suffix(excel_pl: bool) -> str:
    return "_excel_pl" if excel_pl else ""


@FORMATS
@pytest.mark.parametrize("prefix", ["cl", "el"])
def test_analyze_league_report_matches_golden(base_dir: Path, prefix: str, excel_pl: bool) -> None:
    run_league(base_dir, prefix, excel_pl=excel_pl)

    assert_matches_golden(
        base_dir / f"{prefix}_recommendations.csv", f"{prefix}_recommendations{golden_suffix(excel_pl)}.csv"
    )


@FORMATS
def test_analyze_sr_only_report_matches_golden(base_dir: Path, excel_pl: bool) -> None:
    output_dir = base_dir / "recommendations"
    output_dir.mkdir()

    run_sr_only(base_dir, base_dir / "data" / "soccer-rating" / SR_ONLY_INPUT, output_dir, excel_pl=excel_pl)

    assert_matches_golden(
        output_dir / "sr_analysis_report_2026-01-28.csv", f"sr_analysis_report{golden_suffix(excel_pl)}.csv"
    )


def test_analyze_sr_only_reads_the_files_beside_its_input(base_dir: Path) -> None:
    # A snapshot in its own folder brings its own team names; the default folder's would not match its matches
    run_dir = base_dir / "elsewhere" / "run"
    shutil.move(base_dir / "data" / "soccer-rating", run_dir)
    output_dir = base_dir / "new" / "recommendations"

    run_sr_only(base_dir, run_dir / SR_ONLY_INPUT, output_dir)

    assert_matches_golden(output_dir / "sr_analysis_report_2026-01-28.csv", "sr_analysis_report.csv")


def test_league_report_carries_the_value_index_it_ranks_by(base_dir: Path) -> None:
    # teamValue is the value index (ValFinal): within one recommendation level the rows are ordered by it
    run_league(base_dir, "cl")

    report = pd.read_csv(base_dir / "cl_recommendations.csv")
    cols = list(report.columns)
    assert cols.index("teamValue") == cols.index("teamMot") + 1
    assert report["teamValue"].between(0, VALUE_MAX).all()
    for _, rows in report.groupby("recommendation", sort=False):
        assert rows["teamValue"].is_monotonic_decreasing


def test_analyze_league_runs_without_lineups(base_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (base_dir / "data" / "soccer-rating" / "today_matches.csv").unlink()

    run_league(base_dir, "el")

    out = capsys.readouterr().out
    assert "WARNING: today_matches.csv not found: running without lineups" in out
    assert "SUCCESS: Saved: el_recommendations.csv" in out


def test_analyze_league_runs_without_soccer_rating_when_club_meta_is_missing(
    base_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (base_dir / "data" / "soccer-rating" / "club_meta.csv").unlink()

    run_league(base_dir, "cl")

    out = capsys.readouterr().out
    assert "WARNING: club_meta.csv not found: team ids cannot be mapped, running without soccer-rating data" in out
    assert "SUCCESS: Saved: cl_recommendations.csv" in out
