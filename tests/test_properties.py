"""Property-based tests for the functions that handle text from third-party pages."""

from contextlib import suppress
from decimal import Decimal
from urllib.parse import urlsplit

from hypothesis import example, given
from hypothesis import strategies as st
from urllib3.util import parse_url

from src.csv_safety import FORMULA_PREFIXES, neutralize_cell
from src.scraping.fetcher import resolve_url
from src.scraping.parsers import (
    _extract_float,
    _extract_two_numbers,
    _normalize_time,
    make_match_id,
    name_match_score,
    norm_team,
    parse_clip_payloads,
    parse_team_ratings,
    parse_today_prediction,
    payload_to_odds_row,
    team_id_from_href,
)

BACKSLASH = chr(92)
ids = st.integers(min_value=0, max_value=10**9)
ascii_words = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126))

# URL pieces that parsers disagree on, so generated links reach the interesting branches of resolve_url.
url_pieces = st.sampled_from(
    [
        "https:",
        "http:",
        "HTTPS:",
        "javascript:",
        "//",
        "/",
        "///",
        "soccer-rating.com",
        "www.soccer-rating.com",
        "WWW.Soccer-Rating.com",
        "evil.com",
        "soccer-rating.com.evil.com",
        "@",
        ":",
        ":443",
        ":8080",
        ":0",
        "?",
        "#",
        "%2f",
        "%40",
        ".",
        "..",
        "[::1]",
        "127.0.0.1",
        "user:pass",
        BACKSLASH,
        chr(9),
        chr(0xFF0E),  # fullwidth full stop, NFKC folds it to "."
        chr(0x2100),  # account of, NFKC folds it to "a/c"
        "a",
        "x=1",
    ]
)
piece_runs = st.lists(url_pieces, max_size=4).map("".join)
links = st.one_of(
    st.text(),
    st.tuples(
        st.sampled_from(["", "https:", "http:", "HTTPS:", "javascript:"]),
        st.sampled_from(["", "/", "//", "///", BACKSLASH * 2, "/" + BACKSLASH]),
        piece_runs,
        piece_runs,
    ).map("".join),
)
bases = st.sampled_from(
    [
        "https://www.soccer-rating.com/",
        "https://soccer-rating.com/",
        "https://www.soccer-rating.com/football/today/",
        "https://www.soccer-rating.com/Ajax/1234/?x=1",
    ]
)


# The contract, written out here so that a wider production allowlist would fail the property.
SITE_HOSTS = frozenset({"soccer-rating.com", "www.soccer-rating.com"})


@given(link=links, base=bases)
@example(link="https://user@evil.com", base="https://www.soccer-rating.com/")
@example(link="https://soccer-rating.com:443@evil.com/", base="https://www.soccer-rating.com/")
@example(link="//evil.com/x", base="https://www.soccer-rating.com/")
@example(link="https://soccer-rating.com" + BACKSLASH + "@evil.com/", base="https://www.soccer-rating.com/")
def test_resolve_url_stays_on_https_soccer_rating(link: str, base: str) -> None:
    url = resolve_url(link, base=base)
    if url is None:
        return
    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.hostname in SITE_HOSTS
    assert parts.username is None and parts.password is None
    assert parts.port is None
    assert parts.fragment == ""
    # The HTTP client (requests) parses URLs with urllib3: it must see the same host.
    parsed = parse_url(url)
    assert parsed.scheme == "https"
    assert parsed.host in SITE_HOSTS
    assert parsed.auth is None
    assert parsed.port is None


@given(link=links, base=bases)
def test_resolve_url_is_idempotent(link: str, base: str) -> None:
    url = resolve_url(link, base=base)
    if url is not None:
        assert resolve_url(url) == url
        assert resolve_url(url, base=base) == url


@given(st.one_of(st.text(), st.integers(), st.floats(), st.none(), st.booleans()))
@example("=1+1")
@example("-1.5")
@example("-")
@example(float("nan"))
def test_neutralize_cell(value: object) -> None:
    result = neutralize_cell(value)
    if not isinstance(value, str):
        # Identity, not equality: NaN is not equal to itself.
        assert result is value
        assert neutralize_cell(result) is result
        return
    assert isinstance(result, str)
    assert neutralize_cell(result) == result
    assert result in (value, "'" + value)
    if result.startswith(FORMULA_PREFIXES):
        assert len(value) < 2 or _is_number(value)


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


@given(slug=st.text(alphabet=st.characters(categories=["L"], exclude_characters="/")), team_id=ids)
def test_team_id_from_href_reads_back_the_id(slug: str, team_id: int) -> None:
    assert team_id_from_href(f"/{slug}/{team_id}/") == team_id
    assert team_id_from_href(f"https://www.soccer-rating.com/{slug}/w{team_id}/") == team_id


@given(st.text())
def test_team_id_from_href_returns_int_or_raises_value_error(href: str) -> None:
    with suppress(ValueError):  # the documented failure for links without a numeric segment
        assert team_id_from_href(href) >= 0


@given(
    snapshot_date=st.dates().map(str),
    league=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1),
    home_id=ids,
    away_id=ids,
)
def test_make_match_id_round_trips(snapshot_date: str, league: str, home_id: int, away_id: int) -> None:
    assert make_match_id(snapshot_date, league, home_id, away_id).split("_") == [
        snapshot_date,
        league,
        str(home_id),
        str(away_id),
    ]


@given(st.text())
def test_normalize_time_is_idempotent(text: str) -> None:
    once = _normalize_time(text)
    assert _normalize_time(once) == once
    assert once == once.strip()


@given(hour=st.integers(0, 23), minute=st.integers(0, 59), padding=st.sampled_from(["", " ", chr(9)]))
def test_normalize_time_formats_four_digits(hour: int, minute: int, padding: str) -> None:
    assert _normalize_time(f"{padding}{hour:02d}{minute:02d}{padding}") == f"{hour:02d}:{minute:02d}"
    assert _normalize_time(f"{hour}:{minute:02d}") == f"{hour}:{minute:02d}"


@given(st.text())
def test_extract_float_never_raises(text: str) -> None:
    value = _extract_float(text)
    assert value is None or isinstance(value, float)


@given(
    value=st.decimals(min_value=-1000, max_value=1000, places=2, allow_nan=False),
    prefix=st.sampled_from(["", " ", "x ", "@"]),
    comma=st.booleans(),
)
def test_extract_float_reads_a_written_number(value: Decimal, prefix: str, comma: bool) -> None:
    written = f"{value}".replace(".", "," if comma else ".")
    assert _extract_float(prefix + written + " %") == float(f"{value}")


@given(st.text())
def test_extract_two_numbers_shape(text: str) -> None:
    first, second = _extract_two_numbers(text)
    assert first is None or isinstance(first, float)
    if second is not None:
        assert first is not None
        assert second >= 10
        assert second == int(second)


@given(odd=st.decimals(min_value=1, max_value=99, places=2), rating=st.integers(10, 999))
def test_extract_two_numbers_reads_odd_and_rating(odd: Decimal, rating: int) -> None:
    assert _extract_two_numbers(f"{odd} {chr(0x2205)} {rating}") == (float(f"{odd}"), float(rating))
    assert _extract_two_numbers(f"{odd}") == (float(f"{odd}"), None)


@given(st.text())
def test_norm_team_output_shape(name: str) -> None:
    result = norm_team(name)
    assert all(char in "abcdefghijklmnopqrstuvwxyz0123456789 " for char in result)
    assert result == result.strip()
    assert "  " not in result
    assert norm_team(result) == result


@given(ascii_words)
def test_norm_team_ignores_ascii_case(name: str) -> None:
    assert norm_team(name.upper()) == norm_team(name.lower())


teams = st.text(max_size=20)


@given(home=teams, away=teams, payload_home=teams, payload_away=teams)
def test_name_match_score(home: str, away: str, payload_home: str, payload_away: str) -> None:
    score = name_match_score(home, away, payload_home, payload_away)
    assert score in (0, 1, 2)
    assert name_match_score(home, away, home, away) == 2
    assert name_match_score(home, away, away, home) >= 1
    assert name_match_score(away, home, payload_away, payload_home) == score
    if score == 2:
        assert name_match_score(home, away, payload_away, payload_home) >= 1


@given(st.lists(st.text(), max_size=18))
def test_payload_to_odds_row_rejects_short_payloads(parts: list[str]) -> None:
    assert payload_to_odds_row(parts) == {}


@given(st.lists(st.text(), min_size=19, max_size=22))
def test_payload_to_odds_row_never_raises(parts: list[str]) -> None:
    row = payload_to_odds_row(parts)
    assert row == {} or len(row) == 19


@given(
    names=st.lists(st.text(alphabet=st.characters(exclude_characters=",")), min_size=4, max_size=4),
    nums=st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=15, max_size=15),
)
def test_payload_to_odds_row_reads_numbers(names: list[str], nums: list[float]) -> None:
    row = payload_to_odds_row([*names, *map(repr, nums)])
    assert [row["home_team_payload"], row["away_team_payload"], row["some_flag"], row["league_code_payload"]] == names
    assert list(row.values())[4:] == nums


html_pieces = st.sampled_from(
    [
        '<table class="bigtable">',
        "</table>",
        "<tr>",
        '<td colspan="7">',
        "<td>",
        "</td>",
        "<b>",
        '<a href="/Ajax/1234/">',
        '<a href="javascript:copyToClipboard(',
        "')\">",
        "</a>",
        "Football Prediction Today",
        "CLCUP Champions League",
        "Team Ratings (H/A)",
        "1.57<br/>",
        chr(0x2205) + "&nbsp;68",
        "2100",
        ",",
        "'",
        '"',
    ]
)
pages = st.one_of(st.text(), st.lists(st.one_of(html_pieces, st.text(max_size=5)), max_size=30).map("".join))


@given(pages)
def test_parsers_return_empty_values_on_arbitrary_text(text: str) -> None:
    # Tag names cannot be written as entities, so text without the tag cannot hold a match.
    tags = text.lower()
    matches = parse_today_prediction(text, "2026-02-05")
    assert isinstance(matches, list)
    assert matches == [] or "<table" in tags
    payloads = parse_clip_payloads(text)
    assert all(isinstance(part, str) for payload in payloads for part in payload)
    assert payloads == [] or "<a" in tags
    ratings = parse_team_ratings(text)
    assert all(value is None or isinstance(value, float) for value in ratings)
    assert ratings == (None, None) or "<td" in tags
