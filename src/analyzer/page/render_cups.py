"""The cups tab of the results page: one card per match, grouped by cup, with both teams in the details."""

from collections.abc import Callable
from datetime import date

from analyzer.page.model import CupFacts, CupSection, MatchRow, TeamFacts
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
    signal_terms,
    signal_texts,
)
from analyzer.page.texts import (
    ANALYST_SLUGS,
    CUP_DAY,
    CUP_NO_DATA,
    CUPS_COUNT,
    CUPS_KNOWN_TIMES,
    CUPS_NO_KNOWN_TIMES,
    CUPS_NO_TIMES,
    CUPS_ONE_TIME,
    CUPS_SOURCES,
    CUPS_TIMES,
    CUPS_TITLE,
    EN_DASH,
    HEADS,
    KEY_POINTS_FULL,
    LABELS,
    LEVEL_NAMES,
    ON_WEEKDAYS,
    STATUS_NAMES,
    WITHOUT_DAY,
    WITHOUT_TIME,
    and_list,
    day_month_span,
    matches_phrase,
    pl_number,
)

_SORTS = ("match", "pick", "odds", "win", "mot", "value", "level")
_WIN_RANGE = RangeSpec("win", "winprob", LABELS["win_pct"], HEADS["win"], 1, 0)
_MOT_RANGE = RangeSpec("mot", "motivation", LABELS["motivation"], LABELS["motivation"], 5, 0)
_VALUE_RANGE = RangeSpec("value", "value", HEADS["value"], HEADS["value"], 1, 0)
# The details' lines for both teams: label, key of its explanation, then the value of one team's row
_TEAM_LINES: tuple[tuple[str, str, Callable[[TeamFacts], str]], ...] = (
    (HEADS["odds"], "odds", lambda team: number_or(team.close, LABELS["no_data"])),
    (LABELS["win_prob"], "winprob", lambda team: f"{pl_number(team.win_pct, 1)}%"),
    (LABELS["motivation"], "motivation", lambda team: pl_number(team.motivation, 0)),
    (LABELS["status"], "status", lambda team: STATUS_NAMES.get(team.status, team.status)),
    (LABELS["rotation"], "rotation", lambda team: pl_number(team.rotation, 2)),
    (HEADS["value"], "value", lambda team: pl_number(team.value, 1)),
    (HEADS["ocena"], "score", lambda team: number_or(team.score, LABELS["no_data"])),
    (LABELS["edge"], "edgeval", lambda team: number_or(team.edge, LABELS["no_data"], edge_text)),
    (HEADS["level"], "levels", lambda team: LEVEL_NAMES[team.level]),
)


def _picked(row: MatchRow) -> tuple[CupFacts, TeamFacts]:
    """The match's cup facts and the picked team's row."""
    cup = row.cup
    if cup is None:
        raise ValueError(f"A cup row without its cup facts: {row.home} - {row.away}")
    return cup, cup.away if row.pick == "2" else cup.home


def _shown_motivation(motivation: float) -> float:
    """Motivation as the page shows it (a whole number), so the range filter keeps what the reader sees."""
    return float(f"{motivation:.0f}")


def _days(rows: tuple[MatchRow, ...]) -> list[date]:
    """The distinct days of the rows, in order."""
    return sorted({row.day for row in rows if row.day is not None})


def _days_phrase(days: list[date]) -> str:
    """Every day of a cup, such as "we wtorek 20.01 i w środę 21.01.2026" (the year once, at the end)."""
    parts = [f"{ON_WEEKDAYS[day.weekday()]} {day:%d.%m}" for day in days]
    return and_list([*parts[:-1], f"{parts[-1]}.{days[-1].year}"])


def _cup_days(cup: CupSection) -> str | None:
    """The intro's sentence on a cup's days, with the count of its matches without a day; None without any day."""
    days = _days(cup.rows)
    if not days:
        return None
    undated = sum(row.day is None for row in cup.rows)
    without = f" ({WITHOUT_DAY.format(matches=matches_phrase(undated))})" if undated else ""
    return CUP_DAY.format(cup=cup.name, days=_days_phrase(days) + without)


def _times_sentence(rows: tuple[MatchRow, ...]) -> str:
    """The kickoff times; "all matches start at" only when every match has a known kickoff."""
    times = _times(rows)
    untimed = sum(row.kickoff is None for row in rows)
    without = WITHOUT_TIME.format(matches=matches_phrase(untimed))
    if not times:
        # "No soccer-rating data" only when no match has odds either
        has_odds = any(row.odds.close is not None for row in rows)
        return CUPS_NO_KNOWN_TIMES.format(without=without) if has_odds else CUPS_NO_TIMES
    if untimed:
        return CUPS_KNOWN_TIMES.format(times=and_list(times), without=without)
    if len(times) == 1:
        return CUPS_ONE_TIME.format(time=times[0])
    return CUPS_TIMES.format(times=and_list(times))


def _times(rows: tuple[MatchRow, ...]) -> list[str]:
    """The distinct kickoff times of the rows, in order."""
    return sorted({f"{row.kickoff:%H:%M}" for row in rows if row.kickoff is not None})


def _match_facts(row: MatchRow, cup: CupFacts) -> list[tuple[str, str | None, str]]:
    """Kickoff, the 1/X/2 chances, the pick's odds movement and fair odds: label, key of its explanation, value."""
    chances = (
        f"1: {pl_number(cup.home_win_pct, 1)}% · X: {pl_number(cup.draw_pct, 1)}% · "
        f"2: {pl_number(cup.away_win_pct, 1)}%"
    )
    return [
        (LABELS["start"], None, kickoff_text(row)),
        (LABELS["chances"], "winprob", chances),
        (LABELS["pick_odds"], "oddsmove", odds_move(row.odds, " · ")),
        (LABELS["fair"], "fair", number_or(row.odds.fair, LABELS["no_data"])),
    ]


def _both_teams(row: MatchRow, cup: CupFacts, picked: TeamFacts) -> dict[str, object]:
    """The match and both teams side by side: its facts, one line per indicator and the signals of each team."""
    other = cup.home if row.pick == "2" else cup.away
    return {
        "facts": _match_facts(row, cup),
        "lines": [(label, key, value(cup.home), value(cup.away)) for label, key, value in _TEAM_LINES],
        "terms": signal_terms([picked.reason, other.reason]),
        "home_signals": signal_texts(cup.home.reason),
        "away_signals": signal_texts(cup.away.reason),
    }


def _row(index: int, row: MatchRow) -> dict[str, object]:
    cup, team = _picked(row)
    close = number_or(row.odds.close, EN_DASH)
    win, motivation, value = f"{pl_number(team.win_pct, 1)}%", pl_number(team.motivation, 0), pl_number(team.value, 1)
    own = [
        ("s-win", team.win_pct),
        ("s-mot", team.motivation),
        ("s-value", team.value),
        ("status", team.status),
        ("win", round(team.win_pct, 1)),
        ("mot", _shown_motivation(team.motivation)),
        ("value", round(team.value, 1)),
    ]
    return {
        **row_context(index, row, own),
        "pick": team.team,
        "close": close,
        "win": win,
        "motivation": motivation,
        "value": value,
        "numbers": [
            (HEADS["odds"], None, close),
            (HEADS["win"], "winprob", win),
            (HEADS["mot"], "motivation", motivation),
            (LABELS["value_short"], "value", value),
        ],
        "both": _both_teams(row, cup, team),
    }


def _group(index: int, cup: CupSection, first_row: int) -> Group:
    """A cup's matches under its name and days; without rows its no-data notice with a link to the data."""
    if not cup.rows:
        return Group(index, cup.name, "", [], CUP_NO_DATA.format(slug=ANALYST_SLUGS[cup.prefix]))
    days = _days(cup.rows)
    timed = all(row.kickoff is not None for row in cup.rows)
    return Group(
        index,
        f"{cup.name}, {day_month_span(days[0], days[-1])}" if days else cup.name,
        # A round of the league phase has a fixed count of matches, so the bar gives the kickoff times when
        # every match has one, and the count of shown matches otherwise
        f"· {and_list(_times(cup.rows))}" if timed else "",
        [_row(first_row + n, row) for n, row in enumerate(cup.rows)],
    )


def _groups(cups: tuple[CupSection, ...]) -> list[Group]:
    groups, first_row = [], 0
    for index, cup in enumerate(cups):
        groups.append(_group(index, cup, first_row))
        first_row += len(cup.rows)
    return groups


def _intro(cups: tuple[CupSection, ...], rows: tuple[MatchRow, ...]) -> list[str]:
    sentences = [CUPS_COUNT.format(matches=matches_phrase(len(rows)))]
    sentences += [sentence for sentence in map(_cup_days, cups) if sentence is not None]
    sentences.append(_times_sentence(rows))
    return [" ".join(sentences), CUPS_SOURCES]


def _filters(rows: tuple[MatchRow, ...]) -> dict[str, object]:
    teams = [_picked(row)[1] for row in rows]
    return {
        **common_filters(rows),
        "cups": counted((row.group, row.group_name) for row in rows),
        "statuses": counted((team.status, STATUS_NAMES.get(team.status, team.status)) for team in teams),
        "win": range_field(_WIN_RANGE, [round(team.win_pct, 1) for team in teams]),
        "mot": range_field(_MOT_RANGE, [_shown_motivation(team.motivation) for team in teams]),
        "value": range_field(_VALUE_RANGE, [round(team.value, 1) for team in teams]),
    }


def cups_view(cups: tuple[CupSection, ...]) -> dict[str, object]:
    """What the cups tab's template needs; without matches in any cup only its heading and each cup's notice."""
    rows = tuple(row for cup in cups for row in cup.rows)
    view: dict[str, object] = {
        "key": "full",
        "title": CUPS_TITLE,
        "title_date": None,
        "has_matches": bool(rows),
        "groups": _groups(cups),
    }
    if not rows:
        return view
    return {
        **view,
        "key_points": KEY_POINTS_FULL,
        "intro": _intro(cups, rows),
        "filters": _filters(rows),
        "sort_keys": _SORTS,
    }
