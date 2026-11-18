"""`analyze --page`: the inputs it reads, how missing ones show and the one line it prints."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from analyzer.cli import main, run_page
from analyzer.errors import AnalyzerInputError
from analyzer.page.sr_rows import latest_scrape
from analyzer.page.texts import ANALYST_SLUGS, SR_NO_DATA
from tests.inputs import el_base_dir
from tests.test_page_render import view_of

SNAPSHOT = Path("data") / "soccer-rating" / "match_odds_development_2026-01-28.csv"


def test_page_writes_both_tabs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base_dir = el_base_dir(tmp_path)
    out = tmp_path / "recommendations" / "index.html"

    run_page(base_dir, base_dir / SNAPSHOT, ["el"], out)

    page = out.read_text(encoding="utf-8")
    sr_rows = view_of(page, "sr").count('<tr class="m ')
    cup_rows = view_of(page, "full").count('<tr class="m ')
    assert sr_rows > 0
    assert cup_rows > 0
    # The example EL table has one monotonicity violation, so its warning comes first
    assert capsys.readouterr().out.splitlines() == [
        "WARNING: MONOTONICITY VIOLATIONS (1 teams)",
        f"SUCCESS: Saved results page to: {out} ({sr_rows} + {cup_rows} matches)",
    ]


def test_page_without_snapshot_shows_no_data(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base_dir = el_base_dir(tmp_path)
    (base_dir / "data" / "soccer-rating" / "match_odds_development.csv").unlink()
    out = tmp_path / "index.html"

    run_page(base_dir, None, ["cl", "el"], out)

    page = out.read_text(encoding="utf-8")
    assert SR_NO_DATA in page.replace("&nbsp;", " ")
    assert '<tr class="m ' not in view_of(page, "sr")
    # The CL inputs are missing too: its no-data notice, while the EL rows stay
    assert f"competition/{ANALYST_SLUGS['cl']}/predictions" in view_of(page, "full")
    assert '<tr class="m ' in view_of(page, "full")
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1].startswith(f"SUCCESS: Saved results page to: {out} (0 + ")
    assert all(line.startswith("WARNING: ") for line in lines[:-1])
    assert any("match_odds_development.csv" in line for line in lines[:-1])


def test_page_rejects_a_named_snapshot_that_is_missing(tmp_path: Path) -> None:
    base_dir = el_base_dir(tmp_path)

    with pytest.raises(AnalyzerInputError, match="Input file not found"):
        run_page(base_dir, base_dir / "missing.csv", ["el"], tmp_path / "index.html")

    assert not (tmp_path / "index.html").exists()


def test_main_writes_the_page_with_the_default_cups(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base_dir = el_base_dir(tmp_path)
    out = tmp_path / "index.html"

    main(base_dir, ["--page", str(out)])

    page = out.read_text(encoding="utf-8")
    assert f"competition/{ANALYST_SLUGS['cl']}/predictions" in page
    assert f"competition/{ANALYST_SLUGS['ecl']}/predictions" not in page
    assert capsys.readouterr().out.splitlines()[-1].startswith("SUCCESS: Saved results page to: ")
    assert not list(base_dir.glob("*_recommendations.csv"))


def test_main_rejects_page_with_sr_only(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(tmp_path, ["--page", str(tmp_path / "index.html"), "--sr-only"])

    assert exit_info.value.code == 2


def test_latest_scrape_is_the_newest_aware_time() -> None:
    sr = pd.DataFrame({"scraped_at": ["2026-11-16T09:00:00+01:00", "", "2026-11-16T10:30:00+00:00"]})

    assert latest_scrape(sr) == datetime(2026, 11, 16, 10, 30, tzinfo=UTC)


@pytest.mark.parametrize("sr", [pd.DataFrame({"match_id": ["a"]}), pd.DataFrame({"scraped_at": ["", None]})])
def test_latest_scrape_is_none_without_times(sr: pd.DataFrame) -> None:
    assert latest_scrape(sr) is None
