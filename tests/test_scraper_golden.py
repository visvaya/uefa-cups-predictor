"""Golden-file tests that pin the CSV files written by the scraper CLI, run offline.

`tests/fixtures/scraper/` holds a hand-written today-prediction page (CL, EL, an unknown league, a cup league,
national teams, ads and malformed rows) and club and national-team pages named the way `--local` looks them up
(`Home-FC.html`).
Three runs cover the default cumulative files merged with existing ones (`existing/`), separate snapshots with
`--all-leagues`, the time window and `--skip-cups`, and the remote path with a fake fetcher and `--limit`.
The clock is frozen, so the snapshot date and the time window do not depend on when the tests run.

Regenerate the golden files only when a change of the output is intended, never to make a refactor pass:
`UPDATE_GOLDEN=1 uv run pytest tests/test_scraper_golden.py`, then review the diff of `tests/golden/scraper/`.
"""

import logging
import os
import shutil
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from scraping import soccer_rating_cli
from scraping.fetcher import DEFAULT_USER_AGENT
from scraping.models import PayloadSource
from scraping.parsers import parse_today_prediction, payload_to_odds_development

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures" / "scraper"
GOLDEN_DIR = TESTS_DIR / "golden" / "scraper"
FROZEN_NOW = datetime(2026, 2, 5, 18, 0, tzinfo=UTC)
TODAY_PATH = "/today-prediction"


def fetch_fixture(url_path: str) -> str | None:
    """Serves `/today-prediction` and club links such as `/Home-FC/101/` from the fixtures; None when missing."""
    name = "today-prediction" if url_path == TODAY_PATH else url_path.strip("/").split("/")[0]
    path = FIXTURES_DIR / f"{name}.html"
    return path.read_text(encoding="utf-8") if path.exists() else None


def run_cli(monkeypatch: pytest.MonkeyPatch, workdir: Path, output_dir: Path, *args: str) -> list[tuple[str, object]]:
    """Runs the CLI offline; returns the fetcher's User-Agent, the fetches and the sleeps in the order they happened."""
    calls: list[tuple[str, object]] = []

    def fetch(url_path: str) -> str | None:
        calls.append(("fetch", url_path))
        return fetch_fixture(url_path)

    monkeypatch.chdir(workdir)
    monkeypatch.setattr(soccer_rating_cli, "local_now", lambda: FROZEN_NOW)

    def fetcher(user_agent: str) -> SimpleNamespace:
        calls.append(("user_agent", user_agent))
        return SimpleNamespace(fetch=fetch)

    monkeypatch.setattr(soccer_rating_cli, "SoccerRatingFetcher", fetcher)
    monkeypatch.setattr(time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    monkeypatch.setattr(sys, "argv", ["soccer_rating_cli", "--output-dir", str(output_dir), *args])
    soccer_rating_cli.main()
    return calls


def local_workdir(tmp_path: Path) -> Path:
    """The fixture pages in the current directory, where `--local` reads them."""
    workdir = tmp_path / "pages"
    shutil.copytree(FIXTURES_DIR, workdir, ignore=shutil.ignore_patterns("existing"))
    return workdir


def assert_matches_golden(output_dir: Path, scenario: str) -> None:
    """Compares every file the run wrote with its golden file as text (line endings normalised)."""
    golden_dir = GOLDEN_DIR / scenario
    written = sorted(p.name for p in output_dir.iterdir())
    if os.environ.get("UPDATE_GOLDEN") == "1":
        shutil.rmtree(golden_dir, ignore_errors=True)
        golden_dir.mkdir(parents=True)
        for name in written:
            (golden_dir / name).write_text(
                (output_dir / name).read_text(encoding="utf-8"), encoding="utf-8", newline=""
            )
    assert golden_dir.exists(), f"Missing {golden_dir}; create it with UPDATE_GOLDEN=1"
    assert written == sorted(p.name for p in golden_dir.iterdir())
    for name in written:
        assert (output_dir / name).read_text(encoding="utf-8") == (golden_dir / name).read_text(encoding="utf-8"), name


def test_local_cumulative_run_merges_existing_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    shutil.copytree(FIXTURES_DIR / "existing", output_dir)

    calls = run_cli(monkeypatch, local_workdir(tmp_path), output_dir, "--local")

    assert calls == [("user_agent", DEFAULT_USER_AGENT)]  # local mode neither fetches nor waits
    assert_matches_golden(output_dir, "cumulative")


def test_local_snapshot_run_filters_the_time_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    window = ("--min-start", "20", "--max-start", "300")

    run_cli(
        monkeypatch, local_workdir(tmp_path), output_dir, "--local", "--all-leagues", "--separate-snapshots", *window
    )

    assert_matches_golden(output_dir, "snapshots")


def test_local_snapshot_run_skips_cups(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    run_cli(monkeypatch, local_workdir(tmp_path), output_dir, "--local", "--all-leagues", "--skip-cups", "--limit", "2")

    assert_matches_golden(output_dir, "skip-cups")


def test_remote_run_fetches_pages_and_resolves_source_urls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    calls = run_cli(monkeypatch, tmp_path, output_dir, "--limit", "4", "--delay", "0.5", "--user-agent", "test/1.0")

    # The today page right away, then a pause before every team page; Home FC's page has the payload, Red Star's not
    club_pages = [
        "/Home-FC/101/",
        "/Red-Star/303/",
        "/Blue-City/404/",
        "/Land-A/n11/",
        "/Green-Park/505/",
        "/Old-Town/606/",
    ]
    assert calls == [("user_agent", "test/1.0"), ("fetch", TODAY_PATH)] + [
        call for href in club_pages for call in (("sleep", 0.5), ("fetch", href))
    ]
    assert_matches_golden(output_dir, "remote")


def test_site_timezone_moves_the_time_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    window = ("--local", "--all-leagues", "--min-start", "0", "--max-start", "60")

    workdir = local_workdir(tmp_path)
    run_cli(monkeypatch, workdir, tmp_path / "utc", *window)
    run_cli(monkeypatch, workdir, tmp_path / "paris", *window, "--site-timezone", "Europe/Paris")

    # 18:00 UTC is 19:00 in Paris: the window covers 18:00-19:00 on UTC clocks and 19:00-20:00 on Paris clocks
    def kickoffs(run: str) -> list[str]:
        return [str(t) for t in pd.read_csv(tmp_path / run / "today_matches.csv")["time_local"]]

    assert kickoffs("utc") == ["18:30", "19:00"]
    assert kickoffs("paris") == ["19:00", "20:00"]


def test_local_run_without_today_page_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    run_cli(monkeypatch, tmp_path, output_dir, "--local")

    assert list(output_dir.iterdir()) == []


def test_validation_report_flags_duplicates_missing_leagues_and_low_confidence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    matches = parse_today_prediction((FIXTURES_DIR / "today-prediction.html").read_text(encoding="utf-8"), "2026-02-05")
    checked = [*matches, matches[0], replace(matches[1], match_id="no-league", league_code="")]
    payload = ["Home FC", "Away FC", "0", "CLCUP"] + [str(v) for v in range(1, 16)]
    debug = {
        "name_match_level": 2,
        "matched_odds_stage": "close",
        "odds_distance": 0.5,
        "oo_match_gap": None,
        "match_confidence": "LOW",
    }
    dev = payload_to_odds_development(payload, matches[0], PayloadSource("/Home-FC/101/", None, None), debug)
    assert dev is not None

    with caplog.at_level(logging.INFO, logger=soccer_rating_cli.logger.name):
        soccer_rating_cli.validate_results(checked, [dev])

    records = [(r.levelname, r.getMessage()) for r in caplog.records if r.name == soccer_rating_cli.logger.name]
    # The ids of the matches without a payload come from a set, in no fixed order
    missing_level, missing_message = records.pop(4)
    assert missing_level == "WARNING"
    assert missing_message.startswith("Missing payloads for 5 matches: ")
    assert all(m.match_id in missing_message for m in [*matches[1:], checked[-1]])
    assert records == [
        ("INFO", "--- Validation Report ---"),
        ("ERROR", "Validation FAILED: Found 1 duplicate match_ids!"),
        ("ERROR", "Validation FAILED: Found 1 matches with missing league codes!"),
        ("INFO", "Payload Coverage: 16.7% (1/6)"),
        ("WARNING", "Quality Alert: Found 1 LOW confidence matches!"),
        ("INFO", "--------------------------"),
    ]
