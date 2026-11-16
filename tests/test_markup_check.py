import time
from pathlib import Path

import pytest

from scraping.markup_check import MarkupReport, check_markup, markup_problems, today_report, with_team_page

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "scraper"
TODAY_HTML = (FIXTURES_DIR / "today-prediction.html").read_text(encoding="utf-8")
TEAM_HTML = (FIXTURES_DIR / "Home-FC.html").read_text(encoding="utf-8")
SNAPSHOT_DATE = "2026-02-05"


def test_report_counts_what_the_parsers_found() -> None:
    report, team_href = today_report(TODAY_HTML, SNAPSHOT_DATE)

    assert team_href == "/Home-FC/101/"
    # Valid matches on the fixture page in all-leagues mode; the short payload of Home FC's page does not count
    assert with_team_page(report, TEAM_HTML) == MarkupReport(8, 8, 3, team_ratings=True, club_ratings=True)
    assert markup_problems(with_team_page(report, TEAM_HTML)) == []


def test_report_names_every_missing_structure() -> None:
    report, team_href = today_report("<html><table class='bigtable'></table></html>", SNAPSHOT_DATE)

    assert team_href is None
    assert markup_problems(report) == [
        "no matches on the today page",
        "no odds payloads on the team page",
        "no Team Ratings (H/A) on the team page",
        "no Rating Total/Home/Away on the team page",
    ]


def test_report_flags_matches_without_odds() -> None:
    report, _ = today_report(TODAY_HTML.replace('<td align="center">3.40</td>', "<td></td>"), SNAPSHOT_DATE)

    assert (report.matches, report.matches_with_odds) == (8, 7)
    assert "some matches lack 1/X/2 odds" in markup_problems(with_team_page(report, TEAM_HTML))


def run_check(monkeypatch: pytest.MonkeyPatch, pages: dict[str, str]) -> tuple[int, list[object]]:
    calls: list[object] = []

    def fetch(url_path: str) -> str | None:
        calls.append(url_path)
        return pages.get(url_path)

    monkeypatch.setattr(time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    return check_markup(fetch, 3.0, SNAPSHOT_DATE), calls


def test_check_passes_on_the_expected_markup(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {"/today-prediction": TODAY_HTML, "/Home-FC/101/": TEAM_HTML}

    assert run_check(monkeypatch, pages) == (0, ["/today-prediction", ("sleep", 3.0), "/Home-FC/101/"])


@pytest.mark.parametrize("pages", [{}, {"/today-prediction": TODAY_HTML}, {"/today-prediction": "<html></html>"}])
def test_check_fails_when_a_page_or_structure_is_missing(
    monkeypatch: pytest.MonkeyPatch, pages: dict[str, str]
) -> None:
    exit_code, _ = run_check(monkeypatch, pages)

    assert exit_code == 1
