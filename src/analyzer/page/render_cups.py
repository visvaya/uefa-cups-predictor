"""The cups tab of the results page: one card per match, grouped by cup, with both teams in the details."""

from collections.abc import Callable
from datetime import date
from html import escape

from analyzer.page.model import CupFacts, CupSection, MatchRow, TeamFacts
from analyzer.page.render_parts import (
    ODDS_RANGE,
    SEARCH,
    Group,
    RangeSpec,
    TableShape,
    ViewParts,
    card_cell,
    counted,
    detail_row,
    edge_text,
    group_checks,
    keep_last_words,
    key_points,
    kickoff_text,
    level_cells,
    level_filter,
    match_button,
    number_or,
    odds_move,
    range_field,
    row_open,
    section,
    signal_box,
    signals,
    signals_term,
    sort_buttons,
    sort_th,
    term,
    view_block,
    view_section,
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

_SHAPE = TableShape(
    "full",
    '<col class="f-g"><col class="f-p"><col class="f-k"><col class="f-w"><col class="f-m"><col class="f-s">'
    '<col class="f-r">',
    f"<tr>{sort_th('match', None)}{sort_th('pick', 'pick')}{sort_th('odds', 'odds', True)}"
    f"{sort_th('win', 'winprob', True)}{sort_th('mot', 'motivation', True)}{sort_th('value', 'value', True)}"
    f"{sort_th('level', 'levels')}</tr>",
)
_SORTS = ("match", "pick", "odds", "win", "mot", "value", "level")
_WIN_RANGE = RangeSpec("win", "winprob", LABELS["win_pct"], HEADS["win"], 1, 0)
_MOT_RANGE = RangeSpec("mot", "motivation", LABELS["motivation"], LABELS["motivation"], 5, 0)
_VALUE_RANGE = RangeSpec("value", "value", HEADS["value"], HEADS["value"], 1, 0)
# The details' lines for both teams: label, then the value of one team's row
_TEAM_LINES: tuple[tuple[str, Callable[[TeamFacts], str]], ...] = (
    (term("odds", HEADS["odds"]), lambda team: number_or(team.close, LABELS["no_data"])),
    (term("winprob", LABELS["win_prob"]), lambda team: f"{pl_number(team.win_pct, 1)}%"),
    (term("motivation", LABELS["motivation"]), lambda team: pl_number(team.motivation, 0)),
    (term("status", LABELS["status"]), lambda team: escape(STATUS_NAMES.get(team.status, team.status))),
    (term("rotation", LABELS["rotation"]), lambda team: pl_number(team.rotation, 2)),
    (term("value", HEADS["value"]), lambda team: pl_number(team.value, 1)),
    (term("score", HEADS["ocena"]), lambda team: number_or(team.score, LABELS["no_data"])),
    (term("edgeval", LABELS["edge"]), lambda team: number_or(team.edge, LABELS["no_data"], edge_text)),
    (term("levels", HEADS["level"]), lambda team: LEVEL_NAMES[team.level]),
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


def _match_facts(row: MatchRow, cup: CupFacts) -> list[tuple[str, str]]:
    """Kickoff, the 1/X/2 chances, the pick's odds movement and fair odds."""
    chances = (
        f"1: {pl_number(cup.home_win_pct, 1)}% · X: {pl_number(cup.draw_pct, 1)}% · "
        f"2: {pl_number(cup.away_win_pct, 1)}%"
    )
    return [
        (LABELS["start"], kickoff_text(row)),
        (term("winprob", LABELS["chances"]), chances),
        (term("oddsmove", LABELS["pick_odds"]), odds_move(row.odds, " · ")),
        (term("fair", LABELS["fair"]), number_or(row.odds.fair, LABELS["no_data"])),
    ]


def _team_head(name: str, picked: bool) -> str:
    tag = "b" if picked else "span"
    return f'<{tag} role="columnheader" translate="no">{escape(name)}</{tag}>'


def _both_teams(row: MatchRow, cup: CupFacts, picked: TeamFacts) -> str:
    """The match and both teams side by side, home left and away right (a grid with table roles)."""
    other = cup.home if row.pick == "2" else cup.away
    sigs = signals_term([picked.reason, other.reason])
    lines = [*_TEAM_LINES, (sigs, lambda team: signals(team.reason) or LABELS["none"])]
    facts = "".join(
        f'<div role="row"><span role="rowheader">{label}</span><span role="cell" class="wide" aria-colspan="2">'
        f"{value}</span></div>"
        for label, value in _match_facts(row, cup)
    )
    head = (
        f'<div role="row" class="teams-row"><span role="columnheader">{LABELS["indicator"]}</span>'
        f"{_team_head(row.home, row.pick != '2')}{_team_head(row.away, row.pick == '2')}</div>"
    )
    body = "".join(
        f'<div role="row"><span role="rowheader">{label}</span><span role="cell">{value(cup.home)}</span>'
        f'<span role="cell">{value(cup.away)}</span></div>'
        for label, value in lines
    )
    return f'<div class="both" role="table" aria-label="{LABELS["both_teams"]}">{facts}{head}{body}</div>'


def _row(index: int, row: MatchRow) -> str:
    cup, team = _picked(row)
    close = number_or(row.odds.close, EN_DASH)
    pick = f'<span translate="no">{escape(team.team)}</span>'
    win, motivation, value = f"{pl_number(team.win_pct, 1)}%", pl_number(team.motivation, 0), pl_number(team.value, 1)
    tag = row_open(
        row,
        [
            ("s-win", team.win_pct),
            ("s-mot", team.motivation),
            ("s-value", team.value),
            ("status", team.status),
            ("win", team.win_pct),
            ("mot", _shown_motivation(team.motivation)),
            ("value", team.value),
        ],
    )
    numbers = [
        (HEADS["odds"], close),
        (term("winprob", HEADS["win"]), win),
        (term("motivation", HEADS["mot"]), motivation),
        (term("value", LABELS["value_short"]), value),
    ]
    return f"""{tag}
<td class="g">{match_button("full", index, row)}</td>
<td class="p">({row.pick}) {pick}</td>
<td class="k num">{close}</td>
<td class="w num">{win}</td>
<td class="mo num">{motivation}</td>
<td class="s num">{value}</td>
{level_cells(row)}
{card_cell(row, pick, numbers)}
</tr>
{detail_row("full", index, 7, _both_teams(row, cup, team))}"""


def _section(index: int, cup: CupSection, first_row: int) -> str:
    """A cup's matches under its name and days; without rows its no-data notice with a link to the data."""
    if not cup.rows:
        notice = CUP_NO_DATA.format(slug=ANALYST_SLUGS[cup.prefix])
        return f'<section class="day-sec"><h2 class="nodata">{keep_last_words(cup.name)}</h2><p>{notice}</p></section>'
    days = _days(cup.rows)
    timed = all(row.kickoff is not None for row in cup.rows)
    return section(
        _SHAPE,
        Group(
            index,
            f"{cup.name}, {day_month_span(days[0], days[-1])}" if days else cup.name,
            # A round of the league phase has a fixed count of matches, so the bar gives the kickoff times when
            # every match has one, and the count of shown matches otherwise
            f"· {and_list(_times(cup.rows))}" if timed else "",
            "\n".join(_row(first_row + n, row) for n, row in enumerate(cup.rows)),
        ),
    )


def _sections(cups: tuple[CupSection, ...]) -> str:
    parts, first_row = [], 0
    for index, cup in enumerate(cups):
        parts.append(_section(index, cup, first_row))
        first_row += len(cup.rows)
    return "\n".join(parts)


def _intro(cups: tuple[CupSection, ...], rows: tuple[MatchRow, ...]) -> str:
    sentences = [CUPS_COUNT.format(matches=matches_phrase(len(rows)))]
    sentences += [sentence for sentence in map(_cup_days, cups) if sentence is not None]
    sentences.append(_times_sentence(rows))
    return f"{key_points(KEY_POINTS_FULL)}<p>{' '.join(sentences)}</p><p>{CUPS_SOURCES}</p>"


def _filters(rows: tuple[MatchRow, ...]) -> str:
    teams = [_picked(row)[1] for row in rows]
    cups = counted((row.group, row.group_name) for row in rows)
    statuses = counted((team.status, STATUS_NAMES.get(team.status, team.status)) for team in teams)
    closes = [row.odds.close for row in rows if row.odds.close is not None]
    return f"""{SEARCH}
{level_filter(rows)}
<fieldset>
<legend>{LABELS["competitions"]}</legend>
{group_checks("league", cups)}
</fieldset>
<fieldset>
<legend>{term("status", LABELS["status_filter"])}</legend>
{group_checks("status", statuses)}
</fieldset>
{range_field(ODDS_RANGE, closes)}
{range_field(_WIN_RANGE, [team.win_pct for team in teams])}
{range_field(_MOT_RANGE, [_shown_motivation(team.motivation) for team in teams])}
{range_field(_VALUE_RANGE, [team.value for team in teams])}
{signal_box(rows)}
"""


def cups_view(cups: tuple[CupSection, ...]) -> str:
    """The cups tab; without matches in any cup only its heading and each cup's no-data notice."""
    rows = tuple(row for cup in cups for row in cup.rows)
    if not rows:
        return view_section("full", CUPS_TITLE, _sections(cups))
    return view_block(
        ViewParts("full", CUPS_TITLE, _intro(cups, rows), _filters(rows), _sections(cups), sort_buttons("full", _SORTS))
    )
