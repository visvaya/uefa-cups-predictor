"""Command line: argument parsing, the two report flows and the results page (read inputs, decide, print and write)."""

import argparse
import re
import sys
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from analyzer.config import PAGE_TIMEZONE
from analyzer.data import (
    LEAGUE_DIRS,
    ODDS_NUMERIC_COLUMNS,
    analyst_paths,
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
from analyzer.page.cup_rows import cup_section, cup_section_without_data
from analyzer.page.model import CupSection, MatchRow, PageData
from analyzer.page.render import render_page
from analyzer.page.sr_rows import latest_scrape, sr_match_rows
from analyzer.soccer_rating import add_soccer_rating_features, coverage_report
from analyzer.sr_only import sr_only_ranking, sr_only_report, valid_odds
from csv_safety import neutralize_formulas

SNAPSHOT_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
CUMULATIVE_SNAPSHOT = "match_odds_development.csv"  # the scraper's file of every snapshot, in the soccer-rating dir
PAGE_DECIMAL = ","  # the results page shows numbers in its reasons with a decimal comma


def decimal_separator(excel_pl: bool) -> str:
    """The decimal separator of a report: a comma for Polish Excel, a point otherwise."""
    return "," if excel_pl else "."


def write_report(report: pd.DataFrame, path: Path, excel_pl: bool) -> None:
    """Writes the report CSV: `;` and decimal comma for Polish Excel, `,` and decimal point otherwise."""
    if excel_pl:
        neutralize_formulas(report).to_csv(path, sep=";", index=False, encoding="utf-8-sig", decimal=",")
    else:
        neutralize_formulas(report).to_csv(path, sep=",", index=False, encoding="utf-8", decimal=".")


def league_frames(base_dir: Path, prefix: str) -> tuple[pd.DataFrame, list[str]]:
    """One cup's match frame and the console lines on its inputs (the ranking is built with `league_ranking`).

    The lines are the integrity report, the soccer-rating notes and, with soccer-rating data, its coverage.
    """
    fixtures, table = validated_inputs(*load_league_data(base_dir, prefix), prefix)
    lines = integrity_report(table, LEAGUE_NAMES[prefix])
    sr, notes = load_soccer_rating(base_dir, prefix)
    matches = add_soccer_rating_features(match_frame(fixtures, enrich_table(table)), sr)
    lines = [*lines, *notes, *([] if sr.empty else coverage_report(matches))]
    return calculate_values(with_strange_odds_rotation(matches)), lines


def run_league(base_dir: Path, prefix: str, excel_pl: bool = False) -> None:
    """Standard mode for one cup (cl/el/ecl): writes `<prefix>_recommendations.csv` to `base_dir`."""
    league_name = LEAGUE_NAMES[prefix]
    out_path = base_dir / f"{prefix}_recommendations.csv"

    f, lines = league_frames(base_dir, prefix)
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
    return names or {}


def sr_snapshot(path: Path) -> pd.DataFrame:
    """A soccer-rating snapshot with numeric odds; a missing file or one without a valid odds row is an input error."""
    if not path.exists():
        raise AnalyzerInputError(f"Input file not found: {path}")
    sr = cast_numeric(read_smart_csv(path), ODDS_NUMERIC_COLUMNS)
    if not valid_odds(sr).any():
        raise AnalyzerInputError(f"No match with valid odds in {path.name}")
    return sr


def run_sr_only(base_dir: Path, input_file: Path | None, output_dir: Path | None, excel_pl: bool = False) -> None:
    """SR-only mode: writes `sr_analysis_report[_<date>].csv` to `output_dir` (default `base_dir`, created if missing).

    Team names and lineups come from the scraper's files beside the snapshot, which one scraper run wrote together.
    """
    # The named snapshot, or the cumulative file when none is named
    path = input_file or soccer_rating_dir(base_dir) / CUMULATIVE_SNAPSHOT
    sr_dir = path.parent
    sr = sr_snapshot(path)
    print(f"INFO: Loaded SR data from: {path.name}")

    m = SNAPSHOT_DATE.search(path.name)
    date_str = f"_{m.group(1)}" if m else ""
    names = load_club_names(sr_dir / "club_meta.csv")
    today = today_names(sr_dir / "today_matches.csv")
    if today:
        print(f"INFO: Loaded {len(today)} active match names from today_matches.csv")
    report = sr_only_report(sr, names, today, decimal_separator(excel_pl))

    print("\n--- SR-ONLY ANALYSIS TOP 10 RECOMMENDATIONS ---")
    print(report.head(10).to_string(index=False))
    out_path = (output_dir or base_dir) / f"sr_analysis_report{date_str}.csv"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(report, out_path, excel_pl)
        print(f"SUCCESS: Saved SR-Only report to: {out_path}")
    except PermissionError:
        print(f"FAILED to save {out_path}")


def page_sr_rows(base_dir: Path, input_file: Path | None) -> tuple[tuple[MatchRow, ...], datetime | None]:
    """The soccer-rating tab's rows and scrape time; no rows, with a warning, when the cumulative file is missing.

    A named snapshot that is missing is an input error, as in the SR-only report.
    """
    path = input_file or soccer_rating_dir(base_dir) / CUMULATIVE_SNAPSHOT
    if input_file is None and not path.exists():
        print(f"WARNING: {path.name} not found: the soccer-rating tab shows no matches")
        return (), None
    sr = sr_snapshot(path)
    scraped_at = latest_scrape(sr)
    names = load_club_names(path.parent / "club_meta.csv")
    ranking = sr_only_ranking(sr, names, today_names(path.parent / "today_matches.csv"), PAGE_DECIMAL)
    return sr_match_rows(ranking), scraped_at


def page_cup(base_dir: Path, prefix: str) -> CupSection:
    """One cup's section; its no-data notice, with a warning, when its Analyst fixtures or table are missing.

    Every warning names its cup, since the page prints no per-cup headings.
    """
    league_name = LEAGUE_NAMES[prefix]
    missing = [path.name for path in analyst_paths(base_dir, prefix) if not path.exists()]
    if missing:
        print(f"WARNING: {league_name}: {' and '.join(missing)} not found: no matches shown")
        return cup_section_without_data(prefix)
    f, lines = league_frames(base_dir, prefix)
    for line in lines:
        if line.startswith("WARNING: "):
            print(f"WARNING: {league_name}: {line.removeprefix('WARNING: ')}")
    return cup_section(prefix, f, league_ranking(f, PAGE_DECIMAL))


def run_page(base_dir: Path, input_file: Path | None, prefixes: list[str], out: Path) -> None:
    """Writes the results page to `out` (its folder created if missing) from the snapshot and the chosen cups.

    The soccer-rating tab reads `input_file`, or the cumulative file when none is named; prints the warnings on the
    inputs and one SUCCESS line. A page that cannot be saved prints `ERROR: ...` and exits with code 1, so a
    scheduled run fails visibly.
    """
    sr_rows, scraped_at = page_sr_rows(base_dir, input_file)
    cups = tuple(page_cup(base_dir, prefix) for prefix in prefixes)
    data = PageData(sr_rows, cups, scraped_at, datetime.now(ZoneInfo(PAGE_TIMEZONE)))
    template = files("analyzer.page").joinpath("template.html").read_text(encoding="utf-8")
    page = render_page(data, template)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8", newline="")
        cup_matches = sum(len(cup.rows) for cup in cups)
        print(f"SUCCESS: Saved results page to: {out} ({len(sr_rows)} + {cup_matches} matches)")
    except OSError as err:
        print(f"ERROR: Could not save the results page to {out}: {err}")
        sys.exit(1)


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
    parser.add_argument("--input-file", type=Path, help="Path to specific SR snapshot file (for --sr-only and --page)")
    parser.add_argument("--output-dir", type=Path, help="Directory to save output files")
    parser.add_argument(
        "--page", type=Path, metavar="PATH", help="Write the results page (one HTML file) instead of the CSV reports"
    )
    args = parser.parse_args(argv)
    if args.page and args.sr_only:
        parser.error("--page cannot be combined with --sr-only")
    return args


def main(base_dir: Path, argv: list[str] | None = None) -> None:
    """Runs the analyzer on the data under `base_dir`; an input error prints `ERROR: ...` and exits with code 1."""
    args = parse_args(argv)
    try:
        if args.sr_only:
            run_sr_only(base_dir, args.input_file, args.output_dir, excel_pl=args.excel_pl)
            return
        chosen = [prefix for prefix in LEAGUE_DIRS if getattr(args, prefix)]
        if args.page:
            # The page shows every cup; one without inputs shows its no-data notice
            run_page(base_dir, args.input_file, chosen or list(LEAGUE_DIRS), args.page)
            return
        # Without a flag: the Champions and Europa League, and the Conference League when its fixtures are there
        ecl_fixtures, _ = analyst_paths(base_dir, "ecl")
        for prefix in chosen or ["cl", "el", *(["ecl"] if ecl_fixtures.exists() else [])]:
            run_league(base_dir, prefix, excel_pl=args.excel_pl)
    except AnalyzerInputError as err:
        print(f"ERROR: {err}")
        sys.exit(1)


def run() -> None:
    """Console script `analyze`: runs the analyzer on the data under the current directory."""
    main(Path.cwd())
