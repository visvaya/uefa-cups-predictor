from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import analyze

EXAMPLE_TABLE = Path(analyze.BASE_DIR) / "data" / "theanalyst" / "champions-league" / "cl_table_predicted_example.csv"
TABLE_NUMERIC_COLS = ["XPOS", "XPTS", "LEAGUE%", "KO P/0%", "LAST 16%", "QF%", "SF%", "FINAL%", "WINNER%"]


def test_norm_key_strips_diacritics_and_applies_name_fix() -> None:
    assert analyze.norm_key("  Bodø/Glimt ") == "bodo/glimt"
    assert analyze.norm_key("Atlético Madrid") == "atletico"
    assert analyze.norm_key("Nottm Forest") == "nottingham forest"


def test_norm_key_handles_missing_values() -> None:
    assert analyze.norm_key(None) == ""
    assert analyze.norm_key(np.nan) == ""


def test_pressure_vector_peaks_at_threshold_and_vanishes_at_certainty() -> None:
    p = pd.Series([0.0, 0.5, 1.0, 0.25])
    result = analyze.pressure_vector(p)
    assert result[0] == 0.0
    assert result[1] == pytest.approx(1.0)
    assert result[2] == 0.0
    assert 0.0 < result[3] < result[1]


def test_read_smart_csv_detects_semicolon_separator(tmp_path: Path) -> None:
    path = tmp_path / "semi.csv"
    path.write_text("A;B\n1,5;2\n", encoding="utf-8-sig")
    df = analyze.read_smart_csv(path)
    assert list(df.columns) == ["A", "B"]


def test_read_smart_csv_detects_comma_separator(tmp_path: Path) -> None:
    path = tmp_path / "comma.csv"
    path.write_text("A,B\n1.5,2\n", encoding="utf-8")
    df = analyze.read_smart_csv(path)
    assert list(df.columns) == ["A", "B"]
    assert df.loc[0, "A"] == pytest.approx(1.5)


def test_cast_numeric_accepts_comma_decimals() -> None:
    df = pd.DataFrame({"X": ["1,5", "2.25", "bad"]})
    result = analyze.cast_numeric(df, ["X"])
    assert result["X"].tolist() == [1.5, 2.25, 0.0]


def test_enrich_table_on_example_data_produces_bounded_indices() -> None:
    table = analyze.cast_numeric(analyze.read_smart_csv(EXAMPLE_TABLE), TABLE_NUMERIC_COLS)
    enriched = analyze.enrich_table(table, "CL")

    assert set(enriched["Status"]) <= {"IN_PLAY", "OUT", "LOCKED_DIRECT_RO16", "LOCKED_PLAYOFFS"}
    assert enriched["Motivation"].between(0, 100).all()
    assert enriched["RotRisk"].between(1.0, 2.3).all()
