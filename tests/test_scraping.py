import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import requests

from scraping.fetcher import DEFAULT_USER_AGENT, MAX_REDIRECTS, REQUEST_TIMEOUT_S, SoccerRatingFetcher, resolve_url
from scraping.parsers import (
    LEAGUES,
    WORLD_CLUB_ID_OFFSET,
    _extract_two_numbers,
    _normalize_time,
    name_match_score,
    norm_team,
    parse_today_prediction,
    payload_to_odds_row,
    team_id_from_href,
)
from scraping.soccer_rating_cli import minutes_until_kickoff, parse_args, site_clock, timezone_arg

BACKSLASH = chr(92)
ROBOTS_URL = "https://www.soccer-rating.com/robots.txt"
EVENING = datetime(2026, 2, 5, 18, 0, tzinfo=UTC)
WARSAW = ZoneInfo("Europe/Warsaw")


def test_minutes_until_kickoff_same_day() -> None:
    assert minutes_until_kickoff("21:00", EVENING) == 180


def test_minutes_until_kickoff_rolls_over_midnight() -> None:
    assert minutes_until_kickoff("01:00", EVENING) == 7 * 60


def test_minutes_until_kickoff_keeps_recent_past_negative() -> None:
    assert minutes_until_kickoff("17:30", EVENING) == -30


def test_minutes_until_kickoff_counts_real_minutes_across_spring_dst() -> None:
    # Warsaw skips 02:00-03:00 on 2026-03-29: 01:00 CET to 04:00 CEST is two hours
    assert minutes_until_kickoff("04:00", datetime(2026, 3, 29, 1, 0, tzinfo=WARSAW)) == 120


def test_minutes_until_kickoff_counts_real_minutes_across_autumn_dst() -> None:
    # Warsaw repeats 02:00-03:00 on 2026-10-25: 01:00 CEST to 04:00 CET is four hours
    assert minutes_until_kickoff("04:00", datetime(2026, 10, 25, 1, 0, tzinfo=WARSAW)) == 240


def test_minutes_until_kickoff_rolls_over_into_a_dst_change() -> None:
    # 23:30 CET on 2026-03-28 to 11:00 CEST the next day is 10.5 hours, not 11.5
    assert minutes_until_kickoff("11:00", datetime(2026, 3, 28, 23, 30, tzinfo=WARSAW)) == 630


def test_site_clock_reads_kickoffs_in_the_site_timezone() -> None:
    now = site_clock(EVENING, ZoneInfo("Europe/Paris"))
    assert now.utcoffset() == timedelta(hours=1)
    assert minutes_until_kickoff("21:00", now) == 120


def test_default_site_timezone_counts_real_minutes_across_dst(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["soccer-rating"])
    # 00:30 UTC on 2026-03-29 is 01:30 CET; 04:00 that night is CEST, 02:00 UTC
    now = site_clock(datetime(2026, 3, 29, 0, 30, tzinfo=UTC), parse_args().site_timezone)
    assert minutes_until_kickoff("04:00", now) == 90


def test_timezone_arg_rejects_unknown_names() -> None:
    assert timezone_arg("Europe/Warsaw") == WARSAW
    for name in ["Mars/Base", "../etc", ""]:
        with pytest.raises(argparse.ArgumentTypeError):
            timezone_arg(name)


def test_minutes_until_kickoff_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        minutes_until_kickoff("tbd", EVENING)


def test_team_id_from_href() -> None:
    assert team_id_from_href("/Sturm-Graz/1294/") == 1294
    # Clubs outside Europe ("/w<id>/") are numbered apart: /Zob-Ahan/w250/ and /FC-Metz/250/ are different clubs
    assert team_id_from_href("/UTC-Cajamarca/w3353/") == WORLD_CLUB_ID_OFFSET + 3353
    assert team_id_from_href("/Zob-Ahan/w250/") != team_id_from_href("/FC-Metz/250/")
    # National teams have their own id namespace, kept apart from clubs by the sign
    assert team_id_from_href("/Germany/n28/") == -28
    with pytest.raises(ValueError):
        team_id_from_href("/no-id-here/")


def test_normalize_time() -> None:
    assert _normalize_time("2100") == "21:00"
    assert _normalize_time(" 9:30 ") == "9:30"


def test_extract_two_numbers_reads_odds_and_lineup_rating() -> None:
    # Cell format observed on soccer-rating.com: "<odds><br/>∅&nbsp;<rating>"
    assert _extract_two_numbers("1.57 ∅\xa068") == (1.57, 68.0)


def test_extract_two_numbers_ignores_decimal_part_without_rating() -> None:
    assert _extract_two_numbers("1.12") == (1.12, None)
    assert _extract_two_numbers("16.00") == (16.0, None)


def test_name_match_score() -> None:
    assert norm_team("  Bodø/Glimt ") == "bodo glimt"
    assert norm_team("Kobenhavn") == norm_team("København")
    assert name_match_score("Home FC", "Away FC", "home fc", "away fc") == 2
    assert name_match_score("Home FC", "Away FC", "away fc", "home fc") == 1
    assert name_match_score("Home FC", "Away FC", "other", "team") == 0


def _today_row(home_href: str, away_href: str) -> str:
    return (
        "<tr><td>21:00</td><td>55.1</td><td></td>"
        f'<td><a href="{home_href}">Home FC</a> - <a href="{away_href}">Away FC</a></td>'
        '<td align="center"><b>1.57</b><br/>∅&nbsp;68</td><td>4.20</td>'
        '<td align="center">5.25<br/>∅&nbsp;52</td></tr>'
    )


def _today_page(*rows: str) -> str:
    return (
        '<table class="bigtable"><tr><td>Football Prediction Today</td></tr>'
        '<tr><td colspan="8">CLCUP Champions League</td></tr>' + "".join(rows) + "</table>"
    )


def test_parse_today_prediction_reads_club_match() -> None:
    matches = parse_today_prediction(_today_page(_today_row("/Home-FC/101/", "/Away-FC/202/")), "2026-02-05")
    assert len(matches) == 1
    match = matches[0]
    assert match.match_id == "2026-02-05_CLCUP_101_202"
    assert (match.odd_1_today, match.lineup_rating_home_today) == (1.57, 68.0)
    assert (match.odd_x_today, match.lineup_rating_away_today) == (4.2, 52.0)


def test_parse_today_prediction_reads_national_team_links() -> None:
    page = _today_page(
        _today_row("/Antigua-Barbuda/n206/", "/Other/n300/"), _today_row("/Home-FC/n101/", "/Away-FC/101/")
    )
    matches = parse_today_prediction(page, "2026-02-05")
    assert [(m.home_id, m.away_id) for m in matches] == [(-206, -300), (-101, 101)]
    assert matches[0].match_id == "2026-02-05_CLCUP_-206_-300"


def test_parse_today_prediction_names_unknown_leagues_without_changing_leagues() -> None:
    page = _today_page(_today_row("/Home-FC/101/", "/Away-FC/202/")).replace(
        "</table>",
        '<tr><td colspan="8">AR1 Primera Division</td></tr>'
        + _today_row("/Home-AR/301/", "/Away-AR/402/")
        + "</table>",
    )
    leagues_before = dict(LEAGUES)

    matches = parse_today_prediction(page, "2026-02-05", all_leagues=True)

    assert [(m.league_code, m.league_name) for m in matches] == [
        ("CLCUP", "Champions League"),
        ("AR1", "Primera Division"),
    ]
    assert leagues_before == LEAGUES


def test_payload_to_odds_row_requires_full_payload() -> None:
    assert payload_to_odds_row(["a"] * 5) == {}
    parts = ["Home", "Away", "0", "CLCUP"] + [str(v) for v in range(1, 16)]
    row = payload_to_odds_row(parts)
    assert row["league_code_payload"] == "CLCUP"
    assert row["oo"] == 1.0
    assert row["fair_2"] == 15.0


@pytest.mark.parametrize(
    ("url_path", "expected"),
    [
        ("/today-prediction", "https://www.soccer-rating.com/today-prediction"),
        ("Ajax/123/", "https://www.soccer-rating.com/Ajax/123/"),
        ("https://www.soccer-rating.com/Ajax/123/", "https://www.soccer-rating.com/Ajax/123/"),
        ("https://SOCCER-RATING.com/x", "https://soccer-rating.com/x"),
        ("https://www.soccer-rating.com:443/x?a=1#top", "https://www.soccer-rating.com/x?a=1"),
        (" /Ajax/123/" + chr(10), "https://www.soccer-rating.com/Ajax/123/"),
    ],
)
def test_resolve_url_accepts_site_urls(url_path: str, expected: str) -> None:
    assert resolve_url(url_path) == expected


@pytest.mark.parametrize(
    "url_path",
    [
        "https://evil.example/x",
        "http://www.soccer-rating.com/x",
        "https://www.soccer-rating.com@evil.example/x",
        "https://www.soccer-rating.com.evil.example/x",
        "file:///etc/passwd",
        "http://127.0.0.1:8080/",
        "https://[",
        "https://user:pass@www.soccer-rating.com/x",
        "https://www.soccer-rating.com:8443/x",
        "https://evil.example" + BACKSLASH + "@www.soccer-rating.com/x",
        "https://www.soccer-rating.com/x y",
        "https://www.soccer-rating.com/x" + chr(10) + "Host: evil",
    ],
)
def test_resolve_url_rejects_other_urls(url_path: str) -> None:
    assert resolve_url(url_path) is None


def page(
    text: str = "", location: str | None = None, status: int = 200, content: bytes | None = None
) -> SimpleNamespace:
    """A stand-in for requests.Response with only what fetch reads (`content` defaults to `text` in UTF-8)."""
    return SimpleNamespace(
        is_redirect=location is not None,
        headers={"location": location} if location else {},
        text=text,
        content=text.encode("utf-8") if content is None else content,
        status_code=status,
    )


def fetcher_with(
    monkeypatch: pytest.MonkeyPatch,
    responses: Sequence[SimpleNamespace | Exception],
    robots: SimpleNamespace | Exception | None = None,
    delay_s: float = 0.0,
) -> tuple[SoccerRatingFetcher, list[str]]:
    """A fetcher whose requests get `responses` (or raise them) in order, after `robots` (default: empty, allow all).

    The returned list records the requested URLs and, as "sleep <seconds>", every pause longer than zero.
    """
    requested: list[str] = []

    def sleep(seconds: float) -> None:
        requested.extend([f"sleep {seconds}"] if seconds else [])

    fetcher = SoccerRatingFetcher(delay_s=delay_s, sleep=sleep)
    queue = [page() if robots is None else robots, *responses]

    def get(url: str, timeout: int, allow_redirects: bool) -> SimpleNamespace:
        assert (allow_redirects, timeout) == (False, REQUEST_TIMEOUT_S)
        requested.append(url)
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(fetcher.session, "get", get)
    return fetcher, requested


def test_fetch_follows_redirects_on_the_site(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher, requested = fetcher_with(monkeypatch, [page(location="/Ajax/123/"), page(text="club")])
    assert fetcher.fetch("/Ajax/") == "club"
    assert requested == [ROBOTS_URL, "https://www.soccer-rating.com/Ajax/", "https://www.soccer-rating.com/Ajax/123/"]


def test_fetch_stops_at_a_redirect_off_the_site(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher, requested = fetcher_with(monkeypatch, [page(location="http://127.0.0.1:8080/"), page(text="secret")])
    assert fetcher.fetch("/Ajax/") is None
    assert requested == [ROBOTS_URL, "https://www.soccer-rating.com/Ajax/"]


def test_fetch_stops_after_the_redirect_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = [page(location="/loop/") for _ in range(MAX_REDIRECTS + 2)]
    fetcher, requested = fetcher_with(monkeypatch, loop)
    assert fetcher.fetch("/loop/") is None
    assert len(requested) == 1 + MAX_REDIRECTS + 1


def test_fetch_sends_an_honest_user_agent() -> None:
    user_agent = SoccerRatingFetcher().session.headers["User-Agent"]
    assert user_agent == DEFAULT_USER_AGENT
    assert "uefa-cups-predictor" in user_agent
    assert "https://github.com/visvaya/uefa-cups-predictor" in user_agent
    assert SoccerRatingFetcher("custom/1.0").session.headers["User-Agent"] == "custom/1.0"


def test_fetch_reads_robots_once_and_skips_disallowed_paths(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    robots = "User-Agent: *" + chr(10) + "Disallow: /chart.pl" + chr(10)
    fetcher, requested = fetcher_with(monkeypatch, [page(text="today"), page(text="club")], robots=page(text=robots))

    assert fetcher.fetch("/today-prediction") == "today"
    assert fetcher.fetch("/chart.pl?id=1") is None
    assert fetcher.fetch("/Ajax/123/") == "club"

    assert requested == [
        ROBOTS_URL,
        "https://www.soccer-rating.com/today-prediction",
        "https://www.soccer-rating.com/Ajax/123/",
    ]
    assert "disallowed by robots.txt" in caplog.text


def test_fetch_skips_a_redirect_into_a_disallowed_path(monkeypatch: pytest.MonkeyPatch) -> None:
    robots = "User-Agent: *" + chr(10) + "Disallow: /private/" + chr(10)
    fetcher, requested = fetcher_with(monkeypatch, [page(location="/private/x")], robots=page(text=robots))

    assert fetcher.fetch("/Ajax/") is None
    assert requested == [ROBOTS_URL, "https://www.soccer-rating.com/Ajax/"]


def test_fetch_waits_the_delay_between_robots_txt_and_the_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher, requested = fetcher_with(monkeypatch, [page(text="today"), page(text="club")], delay_s=2.5)

    assert fetcher.fetch("/today-prediction") == "today"
    assert fetcher.fetch("/Ajax/123/") == "club"

    # Later pages are paced by the caller (the club page reader), so the fetcher waits only once
    assert requested == [
        ROBOTS_URL,
        "sleep 2.5",
        "https://www.soccer-rating.com/today-prediction",
        "https://www.soccer-rating.com/Ajax/123/",
    ]


def test_fetch_reads_robots_txt_as_utf8_whatever_requests_guessed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Without a charset, requests decodes text/plain as ISO-8859-1; RFC 9309 robots.txt files are UTF-8.
    robots_utf8 = ("User-Agent: *" + chr(10) + "Disallow: /caf" + chr(0xE9) + "/" + chr(10)).encode("utf-8")
    robots = page(text=robots_utf8.decode("iso-8859-1"), content=robots_utf8)
    fetcher, requested = fetcher_with(monkeypatch, [page(text="ok")], robots=robots)

    assert fetcher.fetch("/caf%C3%A9/x") is None
    assert requested == [ROBOTS_URL]


def test_fetch_treats_a_missing_robots_txt_as_allowing_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher, requested = fetcher_with(monkeypatch, [page(text="today")], robots=page(text="Not found", status=404))

    assert fetcher.fetch("/today-prediction") == "today"
    assert requested == [ROBOTS_URL, "https://www.soccer-rating.com/today-prediction"]


@pytest.mark.parametrize(
    "robots",
    [
        page(text="Disallow: /chart.pl", status=503),
        requests.ConnectionError("down"),
        page(location="https://evil.example/"),
    ],
)
def test_fetch_stops_when_robots_txt_is_unreachable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, robots: SimpleNamespace | Exception
) -> None:
    fetcher, requested = fetcher_with(monkeypatch, [page(text="today")], robots=robots)

    assert fetcher.fetch("/today-prediction") is None
    assert fetcher.fetch("/Ajax/123/") is None
    assert requested == [ROBOTS_URL]
    assert "robots.txt is unreachable" in caplog.text


def test_fetch_returns_none_on_an_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    fetcher, _ = fetcher_with(monkeypatch, [page(text="Server error", status=500)])

    assert fetcher.fetch("/today-prediction") is None


def test_fetch_survives_a_malformed_redirect_target(monkeypatch: pytest.MonkeyPatch) -> None:
    def send(_adapter: object, request: requests.PreparedRequest, **_kwargs: object) -> requests.Response:
        response = requests.Response()
        response.status_code = 302
        response.headers["location"] = "https://["
        response.url = request.url or ""
        response.request = request
        response._content = b""
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    assert SoccerRatingFetcher().fetch("/x") is None
