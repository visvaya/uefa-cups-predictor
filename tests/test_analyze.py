import re
import shutil
from codecs import BOM_UTF8
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analyzer.cli import league_frames, main
from analyzer.config import ROTATION_RISK_MAX, STRANGE_ODDS_ROTATION_FACTOR
from analyzer.data import (
    ODDS_NUMERIC_COLUMNS,
    TABLE_NUMERIC_COLUMNS,
    cast_numeric,
    cup_rows,
    latest_snapshots,
    load_club_names,
    load_league_data,
    load_today_names,
    read_smart_csv,
)
from analyzer.errors import AnalyzerInputError
from analyzer.league import validated_inputs
from analyzer.model import enrich_table, integrity_report, pressure_vector, with_strange_odds_rotation
from analyzer.names import norm_key
from analyzer.sr_only import sr_only_ranking, sr_only_report

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


def test_strange_odds_raise_the_rotation_risk_of_both_teams_up_to_the_cap() -> None:
    matches = pd.DataFrame({"Risk_H": [1.2, 1.2, 2.2], "Risk_A": [1.0, 1.0, 1.3], "strangeOdds": [35.0, 0.0, -40.0]})

    raised = with_strange_odds_rotation(matches)

    factor = STRANGE_ODDS_ROTATION_FACTOR
    assert raised["Risk_H"].tolist() == pytest.approx([1.2 * factor, 1.2, ROTATION_RISK_MAX])
    assert raised["Risk_A"].tolist() == pytest.approx([1.0 * factor, 1.0, 1.3 * factor])
    assert matches["Risk_H"].tolist() == [1.2, 1.2, 2.2]


def test_read_smart_csv_raises_input_error_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AnalyzerInputError, match="Missing file"):
        read_smart_csv(tmp_path / "missing.csv")


def test_read_smart_csv_rejects_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "latin1.csv"
    path.write_bytes(("Team;Pts\nM" + chr(0xFC) + "nchen;3\n").encode("latin-1"))
    with pytest.raises(UnicodeDecodeError):
        read_smart_csv(path)


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


@pytest.mark.parametrize("path", sorted((REPO_DIR / "data").glob("**/*_example.csv")), ids=lambda p: p.name)
def test_example_csv_starts_with_at_most_one_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(BOM_UTF8 * 2)


def _league_dir(tmp_path: Path) -> Path:
    """A base dir holding the CL example inputs under their real names; returns the league folder."""
    league = tmp_path / "data" / "theanalyst" / "champions-league"
    league.mkdir(parents=True)
    shutil.copy(EXAMPLE_TABLE, league / "cl_table_predicted.csv")
    shutil.copy(EXAMPLE_TABLE.with_name("cl_fixtures_example.csv"), league / "cl_fixtures.csv")
    return league


def _rewrite_table(league: Path, change: Callable[[pd.DataFrame], pd.DataFrame]) -> None:
    path = league / "cl_table_predicted.csv"
    change(read_smart_csv(path).astype(str)).to_csv(path, sep=";", index=False)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("", "KO P/0%"), ("99,5%", "99,5%"), ("<1", "<1")],
    ids=["blank", "percent-sign", "less-than"],
)
def test_load_league_data_rejects_an_unreadable_table_cell(tmp_path: Path, cell: str, expected: str) -> None:
    league = _league_dir(tmp_path)
    _rewrite_table(league, lambda df: df.assign(**{"KO P/0%": [cell, *df["KO P/0%"].iloc[1:]]}))

    with pytest.raises(AnalyzerInputError, match=re.escape(expected)):
        load_league_data(tmp_path, "cl")


def test_load_league_data_rejects_a_misnamed_column(tmp_path: Path) -> None:
    league = _league_dir(tmp_path)
    _rewrite_table(league, lambda df: df.rename(columns={"KO P/0%": "KO P/O%"}))

    with pytest.raises(AnalyzerInputError, match=re.escape("KO P/0%")):
        load_league_data(tmp_path, "cl")


def test_load_league_data_rejects_a_table_in_fractions(tmp_path: Path) -> None:
    league = _league_dir(tmp_path)
    columns = ["LEAGUE%", "KO P/0%", "LAST 16%", "QF%", "SF%", "FINAL%", "WINNER%"]
    _rewrite_table(
        league,
        lambda df: df.assign(**{c: (df[c].str.replace(",", ".").astype(float) / 100).astype(str) for c in columns}),
    )

    with pytest.raises(AnalyzerInputError, match="percent"):
        load_league_data(tmp_path, "cl")


def test_validated_inputs_rejects_a_team_playing_twice(tmp_path: Path) -> None:
    _league_dir(tmp_path)
    fixtures, table = load_league_data(tmp_path, "cl")
    fixtures.loc[1, "HomeTeam"] = fixtures.loc[0, "HomeTeam"]

    with pytest.raises(AnalyzerInputError, match="more than once"):
        validated_inputs(fixtures, table, "cl")


def test_validated_inputs_rejects_a_duplicate_table_team(tmp_path: Path) -> None:
    _league_dir(tmp_path)
    fixtures, table = load_league_data(tmp_path, "cl")
    table.loc[1, "TEAM"] = table.loc[0, "TEAM"]

    with pytest.raises(AnalyzerInputError, match="more than once"):
        validated_inputs(fixtures, table, "cl")


def test_enrich_table_treats_a_rounded_sum_just_over_100_as_consistent() -> None:
    zero = {c: 0.0 for c in TABLE_NUMERIC_COLUMNS}
    rows = [{**zero, "XPOS": 20.0, "KO P/0%": ko, "LAST 16%": 50.0} for ko in (50.0, 50.01)]

    enriched = enrich_table(pd.DataFrame(rows))

    assert enriched["Motivation"].iloc[1] == pytest.approx(enriched["Motivation"].iloc[0], abs=0.5)


@pytest.mark.parametrize(
    ("analyst", "soccer_rating"),
    [
        ("Arsenal", "Arsenal FC"),
        ("Leverkusen", "Bayer Leverkusen"),
        ("PSV", "PSV Eindhoven"),
        ("Barcelona", "FC Barcelona"),
        ("Inter", "Inter Milan"),
    ],
)
def test_norm_key_matches_the_soccer_rating_names_of_cl_clubs(analyst: str, soccer_rating: str) -> None:
    assert norm_key(analyst) == norm_key(soccer_rating)


def test_load_league_data_rejects_a_percentage_out_of_range(tmp_path: Path) -> None:
    league = _league_dir(tmp_path)
    _rewrite_table(league, lambda df: df.assign(**{"LAST 16%": ["150", *df["LAST 16%"].iloc[1:]]}))

    with pytest.raises(AnalyzerInputError, match=re.escape("LAST 16%")):
        load_league_data(tmp_path, "cl")


def test_load_league_data_rejects_a_table_without_team_names(tmp_path: Path) -> None:
    league = _league_dir(tmp_path)
    _rewrite_table(league, lambda df: df.rename(columns={"TEAM": "CLUB"}))

    with pytest.raises(AnalyzerInputError, match="TEAM"):
        load_league_data(tmp_path, "cl")


def test_enrich_table_sums_a_rounded_pair_whose_float_sum_exceeds_the_limit() -> None:
    zero = {c: 0.0 for c in TABLE_NUMERIC_COLUMNS}
    rows = [{**zero, "XPOS": 20.0, "KO P/0%": 49.95, "LAST 16%": l16} for l16 in (50.05, 50.06)]

    enriched = enrich_table(pd.DataFrame(rows))

    assert enriched["Motivation"].iloc[1] == pytest.approx(enriched["Motivation"].iloc[0], abs=0.5)


def test_latest_snapshots_keeps_the_later_row_of_a_large_file() -> None:
    # Numpy sorts more than 16 rows with an unstable algorithm, which used to keep the earlier row
    ids = [f"m{i}" for i in range(30)]
    old = pd.DataFrame({"match_id": ids, "snapshot_date": "2026-11-17", "close_1": 2.0})
    new = old.assign(close_1=1.5)

    latest = latest_snapshots(pd.concat([old, new], ignore_index=True))

    assert set(latest["close_1"]) == {1.5}


def test_latest_snapshots_does_not_prefer_a_row_without_a_date() -> None:
    rows = pd.DataFrame({"match_id": ["m1", "m1"], "snapshot_date": ["2026-11-17", "unknown"], "close_1": [1.5, 2.0]})

    assert latest_snapshots(rows)["close_1"].tolist() == [1.5]


def test_cup_rows_takes_the_conference_league_code() -> None:
    sr = pd.DataFrame({"league_code": ["CLCUP", "ELCUP", "ECLCUP"], "match_id": ["a", "b", "c"]})

    assert cup_rows(sr, "ecl")["match_id"].tolist() == ["c"]


def test_main_runs_the_conference_league_only_when_its_files_exist(tmp_path: Path) -> None:
    examples = REPO_DIR / "data" / "theanalyst"
    for prefix, league in (("cl", "champions-league"), ("el", "europa-league")):
        target = tmp_path / "data" / "theanalyst" / league
        target.mkdir(parents=True)
        for kind in ("fixtures", "table_predicted"):
            shutil.copy(examples / league / f"{prefix}_{kind}_example.csv", target / f"{prefix}_{kind}.csv")

    main(tmp_path, [])
    assert not (tmp_path / "ecl_recommendations.csv").exists()

    target = tmp_path / "data" / "theanalyst" / "conference-league"
    target.mkdir(parents=True)
    for kind in ("fixtures", "table_predicted"):
        shutil.copy(examples / "conference-league" / f"ecl_{kind}_example.csv", target / f"ecl_{kind}.csv")
    main(tmp_path, [])
    assert (tmp_path / "ecl_recommendations.csv").exists()


def test_main_reports_a_missing_conference_league_file_when_asked_for_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(tmp_path, ["--ecl"])

    assert "conference-league" in capsys.readouterr().out


def _mixed_layout_table(rows: list[tuple[float, float]]) -> pd.DataFrame:
    """A 36-team table in The Analyst's January 2026 layout: (KO P/0%, LAST 16%) per row, other columns 0.

    Eight teams sure of the top 8, then the given rows, then teams out; KO P/0% sums to 1600 and the direct
    LAST 16% (rows where it adds up with KO P/0% to 100) to 800.
    """
    pairs = [(0.0, 100.0)] * 8 + rows
    pairs += [(0.0, 0.0)] * (36 - len(pairs))
    zero = {c: 0.0 for c in TABLE_NUMERIC_COLUMNS}
    return pd.DataFrame(
        [{**zero, "XPOS": float(i + 1), "KO P/0%": ko, "LAST 16%": l16} for i, (ko, l16) in enumerate(pairs)]
    )


# 14 sure play-off teams, a Fenerbahce-like row (KO 100, LAST 16 61) and a Monaco-like pair whose KO adds up to 100
MIXED_ROWS = [(100.0, 0.0)] * 14 + [(100.0, 61.17), (72.67, 16.59), (27.33, 5.0)]


def test_enrich_table_reads_no_top8_chance_from_a_play_off_route_last16() -> None:
    enriched = enrich_table(_mixed_layout_table(MIXED_ROWS))

    fenerbahce = enriched.iloc[22]
    assert fenerbahce["Status"] == "LOCKED_PLAYOFFS"


def test_enrich_table_counts_only_the_play_off_chance_of_a_team_that_can_still_drop_out() -> None:
    table = _mixed_layout_table(MIXED_ROWS)
    same_without_last16 = table.copy()
    same_without_last16.loc[23, "LAST 16%"] = 0.0

    monaco = enrich_table(table).iloc[23]
    expected = enrich_table(same_without_last16).iloc[23]

    assert monaco["Motivation"] == pytest.approx(expected["Motivation"])


def test_integrity_report_names_the_reading_of_last16() -> None:
    lines = integrity_report(_mixed_layout_table(MIXED_ROWS), "CL")

    assert any("LAST 16%" in line and line.startswith("OK") for line in lines)


def test_latest_snapshots_prefers_the_later_scrape_over_file_order() -> None:
    rows = pd.DataFrame(
        {
            "match_id": ["m1", "m1"],
            "snapshot_date": ["2026-11-17", "2026-11-17"],
            "scraped_at": ["2026-11-17T15:00:00+00:00", "2026-11-17T09:00:00+00:00"],
            "close_1": [1.5, 2.0],
        }
    )

    assert latest_snapshots(rows)["close_1"].tolist() == [1.5]


def _fixture_sr_only(
    function: Callable[[pd.DataFrame, dict[int, str], dict[str, dict[str, str]], str], pd.DataFrame],
) -> pd.DataFrame:
    sr = cast_numeric(read_smart_csv(SR_FIXTURES_DIR / "match_odds_development_2026-01-28.csv"), ODDS_NUMERIC_COLUMNS)
    today = load_today_names(SR_FIXTURES_DIR / "today_matches.csv") or {}
    return function(sr, load_club_names(SR_FIXTURES_DIR / "club_meta.csv"), today, ".")


def test_sr_only_report_has_kickoff_columns() -> None:
    report = _fixture_sr_only(sr_only_report).set_index(["homeTeam", "awayTeam"])

    assert list(report.reset_index().columns[:5]) == ["homeTeam", "awayTeam", "date", "time", "league"]
    # Alpha FC - Beta United is in today's rows, Gamma SC - Delta Town is not
    assert report.loc[("Alpha FC", "Beta United"), ["date", "time", "league"]].tolist() == [
        "2026-01-28",
        "20:00",
        "XX1",
    ]
    assert report.loc[("Gamma SC", "Delta Town"), "time"] == ""


def test_sr_only_ranking_keeps_the_match_columns() -> None:
    ranking = _fixture_sr_only(sr_only_ranking).set_index("match_id")

    alpha = ranking.loc["2026-01-28_XX1_201_202"]
    assert alpha["close_1"] == pytest.approx(1.6)
    assert alpha[["home_href", "league_name"]].tolist() == ["/Alpha-FC/201/", "Synthetic League"]
    assert ranking.loc["2026-01-28_XX1_203_204", "home_href"] == ""


def _el_base_dir(tmp_path: Path) -> Path:
    """A base dir holding the EL example inputs under their real names and the fixture soccer-rating files."""
    league = tmp_path / "data" / "theanalyst" / "europa-league"
    league.mkdir(parents=True)
    for kind in ("fixtures", "table_predicted"):
        shutil.copy(
            REPO_DIR / "data" / "theanalyst" / "europa-league" / f"el_{kind}_example.csv", league / f"el_{kind}.csv"
        )
    shutil.copytree(SR_FIXTURES_DIR, tmp_path / "data" / "soccer-rating")
    return tmp_path


def test_league_ranking_links_team_rows_to_their_match(tmp_path: Path) -> None:
    f, ranking, _ = league_frames(_el_base_dir(tmp_path), "el")

    assert len(ranking) == 2 * len(f)
    for row in ranking.itertuples():
        match = f.loc[row.match_index]
        assert row.Team == (match["HomeTeamName"] if row.is_home else match["AwayTeamName"])


def test_league_frames_keep_kickoff_and_odds(tmp_path: Path) -> None:
    f, _, lines = league_frames(_el_base_dir(tmp_path), "el")

    assert {"snapshot_date", "open_1", "close_x", "fair_2", "HomeTeam", "AwayTeam", "Draw%"} <= set(f.columns)
    team_o = f.set_index("HomeTeam").loc["Team O"]
    assert team_o["time_local"] == "18:45"
    assert team_o["close_x"] == pytest.approx(3.9)
    assert any(line.startswith("INFO: Soccer-rating coverage") for line in lines)


def test_sr_only_report_falls_back_to_the_club_name_for_an_empty_today_name(tmp_path: Path) -> None:
    today = tmp_path / "today_matches.csv"
    today.write_text("match_id,home_team,away_team\n2026-01-28_XX1_201_202,,Beta United\n", encoding="utf-8")
    sr = cast_numeric(read_smart_csv(SR_FIXTURES_DIR / "match_odds_development_2026-01-28.csv"), ODDS_NUMERIC_COLUMNS)

    report = sr_only_report(sr, {201: "Alpha Club"}, load_today_names(today) or {}, ".")

    assert "Alpha Club" in report["homeTeam"].tolist()
    assert "" not in report["homeTeam"].tolist()
