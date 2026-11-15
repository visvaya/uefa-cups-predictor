"""Keeps spreadsheet applications from running text cells of CSV output as formulas.

Team names, links and other text come from third-party pages, and the reports are opened in Excel.
"""

import pandas as pd

FORMULA_PREFIXES = ("=", "+", "-", "@", chr(9), chr(13))


def neutralize_cell(value: object) -> object:
    """Prefixes text that a spreadsheet would treat as a formula with an apostrophe.

    Numbers written as text (`-1.5`) and single characters (the `-` placeholder) are kept as they are.
    """
    if not isinstance(value, str) or len(value) < 2 or not value.startswith(FORMULA_PREFIXES):
        return value
    try:
        float(value)
    except ValueError:
        return "'" + value
    return value


def neutralize_formulas(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of `df` with every text column passed through `neutralize_cell`."""
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    return df.assign(**{str(column): df[column].map(neutralize_cell) for column in text_columns})
