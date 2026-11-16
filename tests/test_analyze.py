import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analyzer.cli import main
from src.analyzer.data import TABLE_NUMERIC_COLUMNS, cast_numeric, read_smart_csv
from src.analyzer.errors import AnalyzerInputError
from src.analyzer.model import enrich_table, pressure_vector
from src.analyzer.names import norm_key

REPO_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_TABLE = REPO_DIR / "data" / "theanalyst" / "champions-league" / "cl_table_predicted_example.csv"
SR_FIXTURES_DIR = REPO_DIR / "tests" / "fixtures" / "soccer-rating"


def test_norm_key_strips_diacritics_and_applies_name_fix() -> None:
    assert norm_key("  Bodø/Glimt ") == "bodo/glimt"
    assert norm_key("Atlético Madrid") == "atletico"
    assert norm_key("Nottm Forest") == "nottingham forest"


def test_norm_key_handles_missing_values() -> None:
    assert norm_key(None) == ""
    assert norm_key(np.nan) == ""


def test_pressure_vector_peaks_at_threshold_and_vanishes_at_certainty() -> None:
    p = pd.Series([0.0, 0.5, 1.0, 0.25])
    result = pressure_vector(p)
    assert result[0] == 0.0
    assert result[1] == pytest.approx(1.0)
    assert result[2] == 0.0
    assert 0.0 < result[3] < result[1]


def test_read_smart_csv_detects_semicolon_separator(tmp_path: Path) -> None:
    path = tmp_path / "semi.csv"
    path.write_text("A;B\n1,5;2\n", encoding="utf-8-sig")
    df = read_smart_csv(path)
    assert list(df.columns) == ["A", "B"]


def test_read_smart_csv_detects_comma_separator(tmp_path: Path) -> None:
    path = tmp_path / "comma.csv"
    path.write_text("A,B\n1.5,2\n", encoding="utf-8")
    df = read_smart_csv(path)
    assert list(df.columns) == ["A", "B"]
    assert df.loc[0, "A"] == pytest.approx(1.5)


def test_cast_numeric_accepts_comma_decimals() -> None:
    df = pd.DataFrame({"X": ["1,5", "2.25", "bad"]})
    result = cast_numeric(df, ["X"])
    assert result["X"].tolist() == [1.5, 2.25, 0.0]


def test_enrich_table_on_example_data_produces_bounded_indices() -> None:
    table = cast_numeric(read_smart_csv(EXAMPLE_TABLE), TABLE_NUMERIC_COLUMNS)
    enriched = enrich_table(table)

    assert set(enriched["Status"]) <= {"IN_PLAY", "OUT", "LOCKED_DIRECT_RO16", "LOCKED_PLAYOFFS"}
    assert enriched["Motivation"].between(0, 100).all()
    assert enriched["RotRisk"].between(1.0, 2.3).all()


def test_read_smart_csv_raises_input_error_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AnalyzerInputError, match="Missing file"):
        read_smart_csv(tmp_path / "missing.csv")


@pytest.mark.parametrize(
    ("argv", "message"),
    [([], "ERROR: Missing file: "), (["--sr-only"], "ERROR: Input file not found: ")],
    ids=["standard", "sr-only"],
)
def test_main_reports_missing_input_and_exits_with_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(tmp_path, argv)

    assert exit_info.value.code == 1
    assert capsys.readouterr().out.startswith(message)


def test_sr_only_stops_when_no_match_has_valid_odds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    snapshot = tmp_path / "match_odds_development_2026-02-06.csv"
    header = "match_id,home_id,away_id,open_1,open_x,open_2,close_1,close_x,close_2,fair_1,fair_x,fair_2,"
    header += "odds_distance,team_rating_home,team_rating_away"
    snapshot.write_text(header + "\nm1,1,2,2.0,3.4,3.6,0,0,0,0,0,0,0.0,1500,1450\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        main(tmp_path, ["--sr-only", "--input-file", str(snapshot), "--output-dir", str(tmp_path)])

    assert exit_info.value.code == 1
    assert capsys.readouterr().out.splitlines()[-1] == f"ERROR: No match with valid odds in {snapshot.name}"
    assert not list(tmp_path.glob("sr_analysis_report*.csv"))


def test_sr_only_stops_when_the_named_input_file_is_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copytree(SR_FIXTURES_DIR, tmp_path / "data" / "soccer-rating")
    missing = tmp_path / "data" / "soccer-rating" / "match_odds_development_2026-02-07.csv"

    with pytest.raises(SystemExit) as exit_info:
        main(tmp_path, ["--sr-only", "--input-file", str(missing), "--output-dir", str(tmp_path)])

    assert exit_info.value.code == 1
    assert capsys.readouterr().out.splitlines()[-1] == f"ERROR: Input file not found: {missing}"
    assert not list(tmp_path.glob("sr_analysis_report*.csv"))
