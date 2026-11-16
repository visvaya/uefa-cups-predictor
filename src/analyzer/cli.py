"""Command line: argument parsing and the two report flows (read inputs, decide, print and write)."""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from src.analyzer.data import (
    ODDS_NUMERIC_COLUMNS,
    cast_numeric,
    load_club_names,
    load_league_data,
    load_soccer_rating,
    load_today_names,
    read_smart_csv,
    soccer_rating_dir,
)
from src.analyzer.errors import AnalyzerInputError
from src.analyzer.league import LEAGUE_NAMES, league_report, match_frame, validated_inputs
from src.analyzer.model import calculate_values, enrich_table, integrity_report
from src.analyzer.soccer_rating import add_soccer_rating_features, coverage_report
from src.analyzer.sr_only import sr_only_report, valid_odds
from src.csv_safety import neutralize_formulas

SNAPSHOT_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def write_report(report: pd.DataFrame, path: Path, excel_pl: bool) -> None:
    """Writes the report CSV: `;` and decimal comma for Polish Excel, `,` and decimal point otherwise."""
    if excel_pl:
        neutralize_formulas(report).to_csv(path, sep=";", index=False, encoding="utf-8-sig", decimal=",")
    else:
        neutralize_formulas(report).to_csv(path, sep=",", index=False, encoding="utf-8", decimal=".")


def run_league(base_dir: Path, prefix: str, excel_pl: bool = False) -> None:
    """Standard mode for one cup (cl/el): writes `<prefix>_recommendations.csv` to `base_dir`."""
    league_name = LEAGUE_NAMES[prefix]
    out_path = base_dir / f"{prefix}_recommendations.csv"

    fixtures, table = validated_inputs(*load_league_data(base_dir, prefix), prefix)
    print("\n".join(integrity_report(table, league_name)))
    matches = match_frame(fixtures, enrich_table(table))

    sr = load_soccer_rating(base_dir, prefix)
    matches = add_soccer_rating_features(matches, sr)
    if not sr.empty:
        print("\n".join(coverage_report(matches)))
    report = league_report(calculate_values(matches))

    print(f"\n--- {league_name} TOP 10 RECOMMENDATIONS ---")
    print(report.head(10).to_string(index=False))
    try:
        write_report(report, out_path, excel_pl)
        print(f"SUCCESS: Saved: {out_path.name}")
    except PermissionError:
        print(f"FAILED to save {out_path.name}")


def today_names(path: Path) -> dict[str, dict[str, str]]:
    """Today's team names by match id for the SR-only report; empty, with a warning, when unavailable."""
    if not path.exists():
        return {}
    try:
        names = load_today_names(path)
    except (OSError, UnicodeDecodeError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        print(f"WARNING: Could not load today_matches.csv for name mapping: {e}")
        return {}
    if names is None:
        return {}
    print(f"INFO: Loaded {len(names)} active match names from today_matches.csv")
    return names


def run_sr_only(base_dir: Path, input_file: Path | None, output_dir: Path | None, excel_pl: bool = False) -> None:
    """SR-only mode: writes `sr_analysis_report[_<date>].csv` to `output_dir` (default `base_dir`)."""
    sr_dir = soccer_rating_dir(base_dir)
    # The cumulative file unless an existing snapshot is given
    path = input_file if input_file and input_file.exists() else sr_dir / "match_odds_development.csv"
    if not path.exists():
        raise AnalyzerInputError(f"Input file not found: {path}")
    print(f"INFO: Loading SR data from: {path.name}")

    m = SNAPSHOT_DATE.search(path.name)
    date_str = f"_{m.group(1)}" if m else ""
    sr = cast_numeric(read_smart_csv(path), ODDS_NUMERIC_COLUMNS)
    if not valid_odds(sr).any():
        raise AnalyzerInputError(f"No match with valid odds in {path.name}")
    report = sr_only_report(sr, load_club_names(sr_dir / "club_meta.csv"), today_names(sr_dir / "today_matches.csv"))

    print("\n--- SR-ONLY ANALYSIS TOP 10 RECOMMENDATIONS ---")
    print(report.head(10).to_string(index=False))
    out_path = (output_dir or base_dir) / f"sr_analysis_report{date_str}.csv"
    try:
        write_report(report, out_path, excel_pl)
        print(f"SUCCESS: Saved SR-Only report to: {out_path}")
    except PermissionError:
        print(f"FAILED to save {out_path}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UEFA Cups Fantasy Analyzer")
    parser.add_argument("--cl", action="store_true", help="Analyze Champions League")
    parser.add_argument("--el", action="store_true", help="Analyze Europa League")
    parser.add_argument(
        "--excel-pl", action="store_true", help="Output in Polish Excel format (; separator, , decimal)"
    )
    parser.add_argument(
        "--sr-only", action="store_true", help="Run analysis based ONLY on Soccer-rating data (no Analyst dependency)"
    )
    parser.add_argument("--input-file", type=Path, help="Path to specific SR snapshot file (for --sr-only)")
    parser.add_argument("--output-dir", type=Path, help="Directory to save output files")
    return parser.parse_args(argv)


def main(base_dir: Path, argv: list[str] | None = None) -> None:
    """Runs the analyzer on the data under `base_dir`; an input error prints `ERROR: ...` and exits with code 1."""
    args = parse_args(argv)
    try:
        if args.sr_only:
            run_sr_only(base_dir, args.input_file, args.output_dir, excel_pl=args.excel_pl)
            return
        run_all = not (args.cl or args.el)
        for prefix, selected in (("cl", args.cl), ("el", args.el)):
            if run_all or selected:
                run_league(base_dir, prefix, excel_pl=args.excel_pl)
    except AnalyzerInputError as err:
        print(f"ERROR: {err}")
        sys.exit(1)
