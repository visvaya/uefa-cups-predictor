"""Command line: argument parsing and the two report flows (read inputs, decide, print and write)."""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from analyzer.data import (
    LEAGUE_DIRS,
    ODDS_NUMERIC_COLUMNS,
    cast_numeric,
    load_club_names,
    load_league_data,
    load_soccer_rating,
    load_today_names,
    read_smart_csv,
    soccer_rating_dir,
)
from analyzer.errors import AnalyzerInputError
from analyzer.league import LEAGUE_NAMES, league_ranking, league_report, match_frame, validated_inputs
from analyzer.model import calculate_values, enrich_table, integrity_report, with_strange_odds_rotation
from analyzer.soccer_rating import add_soccer_rating_features, coverage_report
from analyzer.sr_only import sr_only_report, valid_odds
from csv_safety import neutralize_formulas

SNAPSHOT_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def decimal_separator(excel_pl: bool) -> str:
    """The decimal separator of a report: a comma for Polish Excel, a point otherwise."""
    return "," if excel_pl else "."


def write_report(report: pd.DataFrame, path: Path, excel_pl: bool) -> None:
    """Writes the report CSV: `;` and decimal comma for Polish Excel, `,` and decimal point otherwise."""
    if excel_pl:
        neutralize_formulas(report).to_csv(path, sep=";", index=False, encoding="utf-8-sig", decimal=",")
    else:
        neutralize_formulas(report).to_csv(path, sep=",", index=False, encoding="utf-8", decimal=".")


def league_frames(base_dir: Path, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """One cup's match frame, its team ranking (decimal point in reasons) and the console lines on its inputs.

    The lines are the integrity report, the soccer-rating notes and, with soccer-rating data, its coverage.
    """
    fixtures, table = validated_inputs(*load_league_data(base_dir, prefix), prefix)
    lines = integrity_report(table, LEAGUE_NAMES[prefix])
    sr, notes = load_soccer_rating(base_dir, prefix)
    matches = add_soccer_rating_features(match_frame(fixtures, enrich_table(table)), sr)
    lines = [*lines, *notes, *([] if sr.empty else coverage_report(matches))]
    f = calculate_values(with_strange_odds_rotation(matches))
    return f, league_ranking(f, "."), lines


def run_league(base_dir: Path, prefix: str, excel_pl: bool = False) -> None:
    """Standard mode for one cup (cl/el/ecl): writes `<prefix>_recommendations.csv` to `base_dir`."""
    league_name = LEAGUE_NAMES[prefix]
    out_path = base_dir / f"{prefix}_recommendations.csv"

    f, _, lines = league_frames(base_dir, prefix)
    print("\n".join(lines))
    report = league_report(f, decimal_separator(excel_pl))

    print(f"\n--- {league_name} TOP 10 RECOMMENDATIONS ---")
    print(report.head(10).to_string(index=False))
    try:
        write_report(report, out_path, excel_pl)
        print(f"SUCCESS: Saved: {out_path.name}")
    except PermissionError:
        print(f"FAILED to save {out_path.name}")


def today_names(path: Path) -> dict[str, dict[str, str]]:
    """Today's names, kickoff and links by match id for the SR-only report; empty, with a warning, when unavailable."""
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
    """SR-only mode: writes `sr_analysis_report[_<date>].csv` to `output_dir` (default `base_dir`, created if missing).

    Team names and lineups come from the scraper's files beside the snapshot, which one scraper run wrote together.
    """
    # The named snapshot, or the cumulative file when none is named
    path = input_file or soccer_rating_dir(base_dir) / "match_odds_development.csv"
    sr_dir = path.parent
    if not path.exists():
        raise AnalyzerInputError(f"Input file not found: {path}")
    print(f"INFO: Loading SR data from: {path.name}")

    m = SNAPSHOT_DATE.search(path.name)
    date_str = f"_{m.group(1)}" if m else ""
    sr = cast_numeric(read_smart_csv(path), ODDS_NUMERIC_COLUMNS)
    if not valid_odds(sr).any():
        raise AnalyzerInputError(f"No match with valid odds in {path.name}")
    names = load_club_names(sr_dir / "club_meta.csv")
    report = sr_only_report(sr, names, today_names(sr_dir / "today_matches.csv"), decimal_separator(excel_pl))

    print("\n--- SR-ONLY ANALYSIS TOP 10 RECOMMENDATIONS ---")
    print(report.head(10).to_string(index=False))
    out_path = (output_dir or base_dir) / f"sr_analysis_report{date_str}.csv"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(report, out_path, excel_pl)
        print(f"SUCCESS: Saved SR-Only report to: {out_path}")
    except PermissionError:
        print(f"FAILED to save {out_path}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UEFA Cups Fantasy Analyzer")
    parser.add_argument("--cl", action="store_true", help="Analyze Champions League")
    parser.add_argument("--el", action="store_true", help="Analyze Europa League")
    parser.add_argument("--ecl", action="store_true", help="Analyze Conference League")
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
        chosen = [prefix for prefix in LEAGUE_DIRS if getattr(args, prefix)]
        # Without a flag: the Champions and Europa League, and the Conference League when its fixtures are there
        ecl_fixtures = base_dir / "data" / "theanalyst" / LEAGUE_DIRS["ecl"] / "ecl_fixtures.csv"
        for prefix in chosen or ["cl", "el", *(["ecl"] if ecl_fixtures.exists() else [])]:
            run_league(base_dir, prefix, excel_pl=args.excel_pl)
    except AnalyzerInputError as err:
        print(f"ERROR: {err}")
        sys.exit(1)


def run() -> None:
    """Console script `analyze`: runs the analyzer on the data under the current directory."""
    main(Path.cwd())
