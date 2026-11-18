"""The soccer-rating tab of the results page: one card per match, grouped by day."""

from datetime import date, datetime
from html import escape

from analyzer.page.model import MatchRow, PageData, SrFacts
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
    details_list,
    edge_text,
    group_checks,
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
    sort_buttons,
    sort_th,
    term,
    view_block,
    view_section,
)
from analyzer.page.texts import (
    EN_DASH,
    HEADS,
    KEY_POINTS_SR,
    LABELS,
    PICK_NAMES,
    SR_COUNT,
    SR_FIRST_LAST,
    SR_NO_DATA,
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

_SHAPE = TableShape(
    "sr",
    '<col class="c-t"><col class="c-g"><col class="c-p"><col class="c-k"><col class="c-s"><col class="c-r">',
    f"<tr>{sort_th('time', None)}{sort_th('match', None)}{sort_th('pick', 'pick')}{sort_th('odds', 'odds', True)}"
    f"{sort_th('ocena', 'score', True)}{sort_th('level', 'levels')}</tr>",
)
_SORTS = ("time", "match", "pick", "odds", "ocena", "level")
_SCORE_RANGE = RangeSpec("ocena", "score", HEADS["ocena"], HEADS["ocena"], 0.1, 1)


def sr_days(rows: tuple[MatchRow, ...]) -> tuple[date, date] | None:
    """The first and last day of the matches, or None when no row has a day."""
    days = [row.day for row in rows if row.day is not None]
    return (min(days), max(days)) if days else None


def _facts(row: MatchRow) -> SrFacts:
    if row.sr is None:
        raise ValueError(f"A soccer-rating row without its soccer-rating facts: {row.home} - {row.away}")
    return row.sr


def _league(row: MatchRow) -> str:
    """The competition's code and name; the code alone when the inputs have no name."""
    return f"({row.group})" if row.group_name == row.group else f"({row.group}) {row.group_name}"


def _pick(row: MatchRow, sr: SrFacts) -> str:
    if row.pick == "1":
        return club_link(row.home, sr.home_href)
    if row.pick == "2":
        return club_link(row.away, sr.away_href)
    return LABELS["draw"]


def _details(row: MatchRow, sr: SrFacts) -> str:
    return details_list(
        [
            (LABELS["start"], kickoff_text(row)),
            (term("oddsmove", HEADS["odds"]), odds_move(row.odds, ", ")),
            (term("fair", LABELS["fair"]), number_or(row.odds.fair, LABELS["no_data"])),
            (term("edgeval", LABELS["edge"]), edge_text(sr.edge)),
            (term("steamval", LABELS["steam"]), pl_number(sr.steam, sign=True)),
            (term("aoval", LABELS["ao"]), LABELS["none"] if sr.ao == 0 else pl_number(sr.ao, 0, sign=True)),
            (term("quality", LABELS["quality"]), pl_number(sr.quality, 1)),
            (LABELS["clubs"], f"{club_link(row.home, sr.home_href)}, {club_link(row.away, sr.away_href)}"),
        ]
    )


def _row(index: int, row: MatchRow) -> str:
    sr = _facts(row)
    pick = _pick(row, sr)
    close = number_or(row.odds.close, EN_DASH)
    score = pl_number(row.score)
    kickoff = row.kickoff
    tag = row_open(
        row,
        [
            ("s-time", None if kickoff is None else f"{kickoff:%Y-%m-%d %H:%M}"),
            ("s-ocena", row.score),
            ("pick", row.pick),
            ("ocena", row.score),
            ("start", None if kickoff is None else kickoff.isoformat()),
        ],
    )
    return f"""{tag}
<td class="t">{EN_DASH if kickoff is None else f"{kickoff:%H:%M}"}</td>
<td class="g">{match_button("sr", index, row)}<br><small translate="no">{escape(_league(row))}</small></td>
<td class="p">({row.pick}) {pick}</td>
<td class="k num">{close}</td>
<td class="s num">{score}</td>
{level_cells(row)}
{card_cell(row, pick, [(HEADS["odds"], close), (term("score", HEADS["ocena"]), score)])}
</tr>
{detail_row("sr", index, 6, f'<dl class="det">{_details(row, sr)}</dl>')}"""


def _sections(rows: tuple[MatchRow, ...]) -> str:
    days: dict[date | None, list[tuple[int, MatchRow]]] = {}
    for index, row in enumerate(rows):
        days.setdefault(row.day, []).append((index, row))
    return "\n".join(
        section(
            _SHAPE,
            Group(
                n,
                day_heading(day) if day else LABELS["no_data"].capitalize(),
                "",
                "\n".join(_row(index, row) for index, row in pairs),
            ),
        )
        for n, (day, pairs) in enumerate(days.items())
    )


def _filters(rows: tuple[MatchRow, ...]) -> str:
    leagues = counted((row.group, _league(row)) for row in rows)
    by_size = dict(sorted(leagues.items(), key=lambda item: (-item[1][1], item[0])))
    picks = counted((pick, PICK_NAMES[pick]) for pick in ("1", "X", "2") for row in rows if row.pick == pick)
    closes = [row.odds.close for row in rows if row.odds.close is not None]
    return f"""{SEARCH}
{level_filter(rows)}
<fieldset data-group="league">
<legend>{LABELS["competitions"]}</legend>
<details class="lg-filter">
<summary><span class="group-state"></span></summary>
<div class="lg-pop">
<p><input type="search" class="lg-search" placeholder="{LABELS["search_competition_example"]}" autocomplete="off" \
aria-label="{LABELS["search_competition"]}"></p>
<p class="lg-none" hidden><small>{LABELS["no_competition"]}</small></p>
<p class="acts">{LABELS["choose"]} <button type="button" class="act" data-all="league">{LABELS["all"]}</button> · \
<button type="button" class="act" data-none="league">{LABELS["no_option"]}</button></p>
{group_checks("league", by_size)}
</div>
</details>
</fieldset>
<fieldset>
<legend>{term("pick", HEADS["pick"])}</legend>
{group_checks("pick", picks)}
</fieldset>
{range_field(ODDS_RANGE, closes)}
{range_field(_SCORE_RANGE, [row.score for row in rows])}
{signal_box(rows)}
<fieldset>
<legend>{LABELS["time"]}</legend>
<label><input type="checkbox" class="upcoming"><span>{LABELS["hide_started"]}</span></label>
</fieldset>
"""


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
    return f"{key_points(KEY_POINTS_SR)}<p>{' '.join(sentences)}</p>"


def sr_view(data: PageData) -> str:
    """The soccer-rating tab; without matches only its heading and a no-data notice."""
    rows = data.sr_rows
    if not rows:
        return view_section("sr", SR_TITLE, f"<p>{SR_NO_DATA}</p>")
    days = sr_days(rows)
    title = f'{SR_TITLE_ON} <span class="nw">{date_span(*days)}</span>' if days else SR_TITLE
    return view_block(ViewParts("sr", title, _intro(data), _filters(rows), _sections(rows), sort_buttons("sr", _SORTS)))
