"""The soccer-rating tab of the results page: one card per match, grouped by day."""

from datetime import date, datetime

from analyzer.page.model import MatchRow, PageData, SrFacts
from analyzer.page.render_parts import (
    Group,
    RangeSpec,
    common_filters,
    counted,
    edge_text,
    kickoff_text,
    number_or,
    odds_move,
    range_field,
    row_context,
)
from analyzer.page.texts import (
    EN_DASH,
    HEADS,
    KEY_POINTS_SR,
    LABELS,
    PICK_NAMES,
    SR_COUNT,
    SR_FIRST_LAST,
    SR_PAGE_TIME,
    SR_SCRAPED,
    SR_TITLE,
    SR_TITLE_ON,
    WEEKDAYS,
    WITHOUT_TIME,
    club_link,
    date_span,
    day_heading,
    matches_phrase,
    pl_number,
    stamp,
)

_SORTS = ("time", "match", "pick", "odds", "ocena", "level")
_SCORE_RANGE = RangeSpec("ocena", "score", HEADS["ocena"], HEADS["ocena"], 0.1, 1)


def sr_days(rows: tuple[MatchRow, ...]) -> tuple[date, date] | None:
    """The first and last day of the matches, or None when no row has a day."""
    days = [row.day for row in rows if row.day is not None]
    return (min(days), max(days)) if days else None


def _signed(value: float) -> str:
    return pl_number(value, sign=True)


def _facts(row: MatchRow) -> SrFacts:
    if row.sr is None:
        raise ValueError(f"A soccer-rating row without its soccer-rating facts: {row.home} - {row.away}")
    return row.sr


def _league(row: MatchRow) -> str:
    """The competition's code and name; the code alone when the inputs have no name."""
    return f"({row.group})" if row.group_name == row.group else f"({row.group}) {row.group_name}"


def _details(row: MatchRow, sr: SrFacts) -> list[tuple[str, str | None, str]]:
    """The details' lines: label, key of its explanation (if it has one) and value."""
    no_data = LABELS["no_data"]
    return [
        (LABELS["start"], None, kickoff_text(row)),
        (HEADS["odds"], "oddsmove", odds_move(row.odds, ", ")),
        (LABELS["fair"], "fair", number_or(row.odds.fair, no_data)),
        (LABELS["edge"], "edgeval", number_or(sr.edge, no_data, edge_text)),
        (LABELS["steam"], "steamval", number_or(sr.steam, no_data, _signed)),
        (LABELS["ao"], "aoval", LABELS["none"] if sr.ao == 0 else pl_number(sr.ao, 0, sign=True)),
        (LABELS["quality"], "quality", pl_number(sr.quality, 1)),
    ]


def _row(index: int, row: MatchRow) -> dict[str, object]:
    sr = _facts(row)
    home, away = club_link(row.home, sr.home_href), club_link(row.away, sr.away_href)
    close = number_or(row.odds.close, EN_DASH)
    score = number_or(row.score, EN_DASH)
    kickoff = row.kickoff
    own = [
        ("s-time", None if kickoff is None else f"{kickoff:%Y-%m-%d %H:%M}"),
        ("s-ocena", row.score),
        ("pick", row.pick),
        ("ocena", None if row.score is None else round(row.score, 2)),
        ("start", None if kickoff is None else kickoff.isoformat()),
    ]
    return {
        **row_context(index, row, own),
        "time": EN_DASH if kickoff is None else f"{kickoff:%H:%M}",
        "league": _league(row),
        "pick": {"1": home, "2": away}.get(row.pick, LABELS["draw"]),
        "home": home,
        "away": away,
        "close": close,
        "score": score,
        "numbers": [(HEADS["odds"], None, close), (HEADS["ocena"], "score", score)],
        "details": _details(row, sr),
    }


def _groups(rows: tuple[MatchRow, ...]) -> list[Group]:
    days: dict[date | None, list[tuple[int, MatchRow]]] = {}
    for index, row in enumerate(rows):
        days.setdefault(row.day, []).append((index, row))
    return [
        Group(
            n,
            day_heading(day) if day else LABELS["no_data"].capitalize(),
            "",
            [_row(index, row) for index, row in pairs],
        )
        for n, (day, pairs) in enumerate(days.items())
    ]


def _filters(rows: tuple[MatchRow, ...]) -> dict[str, object]:
    leagues = counted((row.group, _league(row)) for row in rows)
    return {
        **common_filters(rows),
        "leagues": dict(sorted(leagues.items(), key=lambda item: (-item[1][1], item[0]))),
        "picks": counted((pick, PICK_NAMES[pick]) for pick in ("1", "X", "2") for row in rows if row.pick == pick),
        "score": range_field(_SCORE_RANGE, [round(row.score, 2) for row in rows if row.score is not None]),
    }


def _when(kickoff: datetime) -> str:
    return f"{WEEKDAYS[kickoff.weekday()]} {kickoff.day}.{kickoff.month:02d}.{kickoff.year}, {kickoff:%H:%M}"


def _intro(data: PageData) -> str:
    kickoffs = sorted(row.kickoff for row in data.sr_rows if row.kickoff is not None)
    sentences = [SR_COUNT.format(matches=matches_phrase(len(data.sr_rows)))]
    untimed = len(data.sr_rows) - len(kickoffs)
    if kickoffs:
        sentences.append(SR_FIRST_LAST.format(first=_when(kickoffs[0]), last=_when(kickoffs[-1])))
    if untimed:
        sentences.append(f"{WITHOUT_TIME.format(matches=matches_phrase(untimed))}.")
    if kickoffs:
        sentences.append(SR_PAGE_TIME)
    if data.scraped_at is not None:
        sentences.append(SR_SCRAPED.format(stamp=stamp(data.scraped_at)))
    return " ".join(sentences)


def sr_view(data: PageData) -> dict[str, object]:
    """What the soccer-rating tab's template needs; without matches only its heading, no-data notice and no more."""
    rows = data.sr_rows
    days = sr_days(rows)
    view: dict[str, object] = {
        "key": "sr",
        "title": SR_TITLE_ON if days else SR_TITLE,
        "title_date": date_span(*days) if days else None,
        "has_matches": bool(rows),
        "groups": _groups(rows),
    }
    if not rows:
        return view
    return {
        **view,
        "key_points": KEY_POINTS_SR,
        "intro": [_intro(data)],
        "filters": _filters(rows),
        "sort_keys": _SORTS,
    }
