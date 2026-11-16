"""Golden-file tests that pin the CSV files written by the scraper CLI, run offline.

`tests/fixtures/scraper/` holds a hand-written today-prediction page (CL, EL, an unknown league, a cup league,
national teams, ads and malformed rows) and club pages named the way `--local` looks them up (`Home-FC.html`).
Three runs cover the default cumulative files merged with existing ones (`existing/`), separate snapshots with
`--all-leagues`, the time window and `--skip-cups`, and the remote path with a fake fetcher and `--limit`.
The clock is frozen, so the snapshot date and the time window do not depend on when the tests run.

Regenerate the golden files only when a change of the output is intended, never to make a refactor pass:
`UPDATE_GOLDEN=1 uv run pytest tests/test_scraper_golden.py`, then review the diff of `tests/golden/scraper/`.
"""

import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.scraping import soccer_rating_cli

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


def run_cli(monkeypatch: pytest.MonkeyPatch, workdir: Path, output_dir: Path, *args: str) -> None:
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(soccer_rating_cli, "local_now", lambda: FROZEN_NOW)
    monkeypatch.setattr(soccer_rating_cli, "SoccerRatingFetcher", lambda: SimpleNamespace(fetch=fetch_fixture))
    monkeypatch.setattr(sys, "argv", ["soccer_rating_cli", "--output-dir", str(output_dir), *args])
    soccer_rating_cli.main()


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

    run_cli(monkeypatch, local_workdir(tmp_path), output_dir, "--local")

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

    run_cli(monkeypatch, tmp_path, output_dir, "--limit", "3", "--delay", "0")

    assert_matches_golden(output_dir, "remote")


def test_local_run_without_today_page_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    run_cli(monkeypatch, tmp_path, output_dir, "--local")

    assert list(output_dir.iterdir()) == []
