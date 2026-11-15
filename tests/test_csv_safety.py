import pandas as pd
import pytest

from src.csv_safety import neutralize_cell, neutralize_formulas

TAB = chr(9)
CR = chr(13)
STRONG_BUY = chr(0x1F7E2) + " STRONG BUY"  # recommendation label as written by analyze.py


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2+3", "@SUM(A1)", TAB + "=1", CR + "=1", "=HYPERLINK(x)"])
def test_neutralize_cell_prefixes_formula_text(value: str) -> None:
    assert neutralize_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["Bodø/Glimt", "-", "+", "-1.5", "+2", "1.57", "", "'=already", STRONG_BUY])
def test_neutralize_cell_keeps_safe_text(value: str) -> None:
    assert neutralize_cell(value) == value


@pytest.mark.parametrize("value", [1.5, -3, None])
def test_neutralize_cell_keeps_non_text(value: object) -> None:
    assert neutralize_cell(value) == value


def test_neutralize_formulas_changes_only_text_columns() -> None:
    df = pd.DataFrame({"team": ["=evil()", "Ajax"], "odds": [-1.5, 2.0], "reason": ["-", "+cmd"]})
    result = neutralize_formulas(df)
    assert result["team"].tolist() == ["'=evil()", "Ajax"]
    assert result["odds"].tolist() == [-1.5, 2.0]
    assert result["reason"].tolist() == ["-", "'+cmd"]
    assert df["team"].tolist() == ["=evil()", "Ajax"]


def test_neutralize_formulas_is_idempotent() -> None:
    df = pd.DataFrame({"team": ["=evil()"]})
    once = neutralize_formulas(df)
    assert neutralize_formulas(once)["team"].tolist() == once["team"].tolist()
