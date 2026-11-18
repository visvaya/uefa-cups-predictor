"""HTML fragments both tabs of the results page share: explained words, filters, sort controls, cells and sections.

Every value from the inputs is escaped here or by the caller before it joins the markup; texts from `texts` are
trusted page markup.
"""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape

from analyzer.page.model import Level, MatchRow, PickOdds
from analyzer.page.texts import (
    EN_DASH,
    HEADS,
    HINT,
    LABELS,
    LEVEL_NAMES,
    LEVEL_RANKS,
    MINUS,
    SIGNAL_NAMES,
    SIGNAL_SHORT,
    SIGNAL_TERMS,
    SORT_NAMES,
    WEEKDAYS,
    WORD_JOINER,
    fold,
    pl_number,
)

# The order both tabs start in: best recommendation first
DEFAULT_SORT = "level:asc"
# One letter words that must not end a line, after a space or an opening parenthesis (Polish typesetting)
_SHORT_WORD = re.compile(r"(?<=[\s(])([aiouwzAIOUWZ]) ")
# Text between tags: attributes, data values and URLs are inside tags and stay as they are
_TEXT = re.compile(r">[^<]*")


@dataclass(frozen=True)
class RangeSpec:
    """A from-to filter over one numeric `data-<key>` of the rows; `label` is the legend, `name` the field name."""

    key: str
    term: str
    label: str
    name: str
    step: float
    digits: int


@dataclass(frozen=True)
class TableShape:
    """The table every section of a view shares: the view key, its column widths and its head row."""

    view: str
    cols: str
    head: str


@dataclass(frozen=True)
class Group:
    """One section of a view: its index, heading, note on the bar (empty: the count of shown rows) and rows."""

    index: int
    title: str
    note: str
    rows: str


@dataclass(frozen=True)
class ViewParts:
    """One tab: key, heading, the folding intro, the filters, the sections and the sort buttons."""

    key: str
    title: str
    intro: str
    filters: str
    sections: str
    sort: str


def term(key: str, text: str, extra: str = "") -> str:
    """A word that explains itself on tap (and on hover where there is a mouse)."""
    return (
        f'<button type="button" class="term{extra}" data-term="{key}" aria-controls="tip" '
        f'aria-expanded="false">{text}</button>'
    )


def marker(level: Level) -> str:
    """The level's icon; the neutral level has none."""
    return "" if level == "neutral" else f'<span class="mk mk-{level}" aria-hidden="true"></span>'


def _signal_parts(reason: str) -> list[str]:
    return [part.strip() for part in reason.split(";") if part.strip() not in ("", "-")]


def signal_keys(reason: str) -> list[str]:
    """The explanation keys of the signals in a report reason, in their order."""
    return [key for part in _signal_parts(reason) for prefix, key in SIGNAL_TERMS if part.startswith(prefix)]


def _signal(text: str) -> str:
    for raw, short in SIGNAL_SHORT.items():
        text = text.replace(raw, short)
    return f'<span class="sig" translate="no">{escape(text.replace("(-", "(" + MINUS))}</span>'


def signals(reason: str) -> str:
    """The signals of a reason as plain text spans; empty when the reason has none."""
    return "; ".join(_signal(part) for part in _signal_parts(reason))


def signals_term(reasons: list[str]) -> str:
    """One explanation for all signals in the given reasons, so the signals themselves stay plain text."""
    keys = " ".join(dict.fromkeys(key for reason in reasons for key in signal_keys(reason)))
    return (
        f'<button type="button" class="term" data-term="signals" data-terms="{keys}" '
        f'aria-controls="tip" aria-expanded="false">{LABELS["signals"]}</button>'
    )


def number_or(value: float | None, missing: str) -> str:
    """A number with two decimals as Polish text writes it, or `missing` when the inputs have none."""
    return missing if value is None else pl_number(value)


def edge_text(edge: float) -> str:
    """The model's edge in percentage points, with its sign."""
    return f"{pl_number(edge * 100, 0, sign=True)}&nbsp;{LABELS['points']}"


def odds_move(odds: PickOdds, separator: str) -> str:
    """The pick's odds at the market's open and close; "brak danych" when both are missing."""
    if odds.open is None and odds.close is None:
        return LABELS["no_data"]
    opened, closed = (number_or(value, LABELS["no_data"]) for value in (odds.open, odds.close))
    return f"{LABELS['open']} {opened}{separator}{LABELS['close']} {closed}"


def kickoff_text(row: MatchRow) -> str:
    """The match's weekday, date and kickoff, as much of it as is known."""
    if row.day is None:
        return LABELS["no_data"]
    day = f"{WEEKDAYS[row.day.weekday()]} {row.day.day}.{row.day.month:02d}"
    return day if row.kickoff is None else f"{day}, {row.kickoff:%H:%M}"


def details_list(items: list[tuple[str, str]]) -> str:
    return "".join(f"<div><dt>{label}</dt> <dd>{value}</dd></div>" for label, value in items)


def row_open(row: MatchRow, own: list[tuple[str, object]]) -> str:
    """A match row's opening tag: the data both tabs sort, filter and search by, then the tab's `own` data.

    A value the inputs do not have (None) gets no attribute, so its row drops out only when that range is narrowed.
    The pick sorts 1, X, 2, then by the picked team's name (the home team's for a draw).
    """
    picked = row.away if row.pick == "2" else row.home
    pairs = [
        ("level", row.level),
        ("s-match", fold(row.home)),
        ("s-pick", f"{'1X2'.index(row.pick)} {fold(picked)}"),
        ("s-odds", row.odds.close),
        ("s-level", LEVEL_RANKS[row.level]),
        ("league", row.group),
        ("odds", row.odds.close),
        *own,
        ("signals", " ".join(signal_keys(row.reason))),
        ("teams", f"{fold(row.home)} {fold(row.away)}"),
    ]
    attrs = "".join(f' data-{key}="{escape(str(value))}"' for key, value in pairs if value is not None)
    return f'<tr class="m {row.level}"{attrs}>'


def detail_row(view: str, index: int, columns: int, content: str) -> str:
    """The hidden row under a match that its name opens."""
    return f'<tr class="d" id="{view}-d-{index}" hidden><td colspan="{columns}">{content}</td></tr>'


def match_button(view: str, index: int, row: MatchRow) -> str:
    """The match name, which opens its details; the picked team is bold, neither for a draw."""
    home = f"<b>{escape(row.home)}</b>" if row.pick == "1" else escape(row.home)
    away = f"<b>{escape(row.away)}</b>" if row.pick == "2" else escape(row.away)
    return (
        f'<button type="button" class="mt" aria-expanded="false" aria-controls="{view}-d-{index}" '
        f'title="{LABELS["show_details"]}"><span class="teams" translate="no">{home} {EN_DASH} {away}</span></button>'
    )


def level_cells(row: MatchRow) -> str:
    """The recommendation column (signals under it) and the card's recommendation line."""
    level = term(row.level, LEVEL_NAMES[row.level], " lv")
    shown = signals(row.reason)
    under = f'<br><small><span class="lab">{signals_term([row.reason])}:</span> {shown}</small>' if shown else ""
    return f'<td class="r">{level}{under}</td>\n<td class="n1"><span class="lab">{HEADS["level"]}:</span> {level}</td>'


def card_cell(row: MatchRow, pick: str, numbers: list[tuple[str, str]]) -> str:
    """The card layout's cell: the pick on its own line, the numbers in a strip, then the signals."""
    strip = "\n".join(f'<div class="num"><dt>{label}</dt><dd>{value}</dd></div>' for label, value in numbers)
    shown = signals(row.reason)
    sigs = f'<p class="sigs"><span class="lab">{signals_term([row.reason])}:</span><span>{shown}</span></p>'
    return (
        f'<td class="c"><dl class="strip">\n<div><dt>{HEADS["pick"]}</dt><dd class="pk"><span>({row.pick})</span> '
        f"{pick}</dd></div>\n{strip}\n</dl>{sigs if shown else ''}</td>"
    )


def counted(pairs: Iterable[tuple[str, str]]) -> dict[str, tuple[str, int]]:
    """Per code its label and how many rows have it, in the order the codes first occur."""
    out: dict[str, tuple[str, int]] = {}
    for code, label in pairs:
        out[code] = (label, out.get(code, (label, 0))[1] + 1)
    return out


def group_checks(name: str, groups: dict[str, tuple[str, int]]) -> str:
    return "\n".join(
        f'<label><input type="checkbox" name="{name}" value="{escape(code)}" checked>'
        f'<span><span translate="no">{escape(label)}</span> ({n})</span></label>'
        for code, (label, n) in groups.items()
    )


def level_filter(rows: tuple[MatchRow, ...]) -> str:
    """Ticks for the levels the rows have, with their counts."""
    counts = {level: sum(row.level == level for row in rows) for level in LEVEL_NAMES}
    checks = "\n".join(
        f'<label><input type="checkbox" name="level" value="{level}" checked><span>{marker(level)}{name} '
        f"({counts[level]})</span></label>"
        for level, name in LEVEL_NAMES.items()
        if counts[level]
    )
    return f"<fieldset>\n<legend>{term('levels', HEADS['level'])}</legend>\n{checks}\n</fieldset>"


SEARCH = f"""<fieldset>
<legend>{LABELS["search_team"]}</legend>
<label><input type="search" class="search" placeholder="{LABELS["search_team_example"]}" autocomplete="off" \
aria-label="{LABELS["search_team"]}"></label>
</fieldset>"""


def _spin_box(spec: RangeSpec, bounds: tuple[float, float], bound: str) -> str:
    low, high = bounds
    start, word = (low, LABELS["from"]) if bound == "min" else (high, LABELS["to"])
    text = pl_number(start, spec.digits)
    name = f"{spec.name} {word}"
    return (
        f'<span class="spin"><button type="button" class="stp" data-dir="-1" aria-label="{name}: {LABELS["less"]}">'
        f"{MINUS}</button>"
        f'<input type="text" inputmode="decimal" class="rng" role="spinbutton" data-range="{spec.key}" '
        f'data-bound="{bound}" data-min="{low}" data-max="{high}" data-step="{spec.step}" data-digits="{spec.digits}" '
        f'data-start="{start}" value="{text}" aria-valuemin="{low}" aria-valuemax="{high}" aria-valuenow="{start}" '
        f'aria-valuetext="{text}" aria-label="{name}" autocomplete="off">'
        f'<button type="button" class="stp" data-dir="1" aria-label="{name}: {LABELS["more"]}">+</button></span>'
    )


ODDS_RANGE = RangeSpec("odds", "odds", HEADS["odds"], HEADS["odds"], 0.05, 2)


def range_field(spec: RangeSpec, values: list[float]) -> str:
    """A from-to pair whose spinbuttons start at the data's bounds, rounded outwards to the step; empty without data."""
    if not values:
        return ""
    bounds = (
        round(math.floor(min(values) / spec.step + 1e-9) * spec.step, 6),
        round(math.ceil(max(values) / spec.step - 1e-9) * spec.step, 6),
    )
    return f"""<fieldset class="range">
<legend>{term(spec.term, spec.label)}</legend>
<span class="pair"><span class="w">{LABELS["from"]}</span> {_spin_box(spec, bounds, "min")}</span>
<span class="pair"><span class="w">{LABELS["to"]}</span> {_spin_box(spec, bounds, "max")}</span>
<small class="rng-msg" role="status"></small>
<small class="edge-msg" role="status"></small>
</fieldset>"""


def signal_box(rows: tuple[MatchRow, ...]) -> str:
    """Signals as an any-of filter, the most frequent first: none ticked shows every match."""
    counts = counted((key, key) for row in rows for key in dict.fromkeys(signal_keys(row.reason)))
    checks = "\n".join(
        f'<label><input type="checkbox" name="signal" value="{key}"><span><span translate="no">'
        f"{escape(SIGNAL_NAMES[key])}</span> ({n})</span></label>"
        for key, (_, n) in sorted(counts.items(), key=lambda item: -item[1][1])
    )
    return f"""<fieldset data-any="signal">
<legend>{LABELS["signals"]}</legend>
<details class="lg-filter">
<summary><span class="group-state"></span></summary>
<div class="lg-pop">
<p><small>{LABELS["signal_note"]}</small></p>
<p class="acts"><button type="button" class="act" data-none="signal">{LABELS["clear_choice"]}</button></p>
{checks}
</div>
</details>
</fieldset>"""


def sort_th(key: str, term_key: str | None, numeric: bool = False) -> str:
    """A column head that sorts on click and explains itself on hover (where there is a mouse)."""
    data_term = f' data-term="{term_key}"' if term_key else ""
    cls = ' class="num"' if numeric else ""
    return (
        f'<th{cls} aria-sort="none"><button type="button" class="sort" data-key="{key}"{data_term}>'
        f'{HEADS[key]}<span class="dir" aria-hidden="true"></span></button></th>'
    )


def sort_buttons(view: str, keys: tuple[str, ...]) -> str:
    """The card layout's counterpart of the column heads: the same sort keys as a row of buttons."""
    buttons = " ".join(
        f'<button type="button" class="sort" data-key="{key}">{SORT_NAMES[key]}'
        '<span class="dir" aria-hidden="true"></span></button>'
        for key in keys
    )
    return (
        f'<div class="sort-line" role="group" aria-labelledby="{view}-sort-l"><span id="{view}-sort-l">'
        f"{LABELS['sorting']}</span> {buttons}\n"
        f'<input type="hidden" class="sort-by" value="{DEFAULT_SORT}" data-default="{DEFAULT_SORT}"></div>'
    )


def section(shape: TableShape, group: Group) -> str:
    """A group of matches under a heading bar that folds it away."""
    after = f"<small>{group.note}</small>" if group.note else '<small class="day-count"></small>'
    target = f"{shape.view}-g-{group.index}"
    return f"""<section class="day-sec"><h2><button type="button" class="day" aria-expanded="true" \
aria-controls="{target}">{keep_last_words(group.title)} {after}</button></h2>
<div class="wrap" id="{target}"><table class="t-{shape.view}">
<colgroup>{shape.cols}</colgroup>
<thead>{shape.head}</thead>
<tbody>
{group.rows}
</tbody></table></div></section>"""


def key_points(lines: tuple[str, ...]) -> str:
    """A short summary under the heading: where to start and which values are good."""
    items = "".join(f"<li>{line}</li>" for line in lines)
    return f'<div class="keys"><ul>{items}</ul></div>'


def view_section(key: str, title: str, body: str) -> str:
    """A tab's block; the cups tab is shown first, the page script switches between them."""
    hidden = " hidden" if key != "full" else ""
    heading = f"<h1>{keep_last_words(title)}</h1>"
    return f'<section class="view" id="view-{key}" data-view="{key}"{hidden}>\n{heading}\n{body}\n</section>'


def view_block(view: ViewParts) -> str:
    """A tab with matches: intro, hint, filters, the count of shown matches, the sort row and the sections."""
    return view_section(
        view.key,
        view.title,
        f"""<details class="fold about" open>
<summary>{LABELS["about"]}</summary>
{view.intro}
</details>
<hr>
{HINT}
<hr>
<details class="fold filter-box">
<summary>{LABELS["filters"]} <span class="filter-state">{LABELS["all_matches"]}</span></summary>
<form class="filters" onsubmit="return false">
{view.filters}
<p><button type="reset" class="act">{LABELS["clear_filters"]}</button></p>
</form>
</details>
<p class="shown" aria-live="polite"></p>
{view.sort}
<hr>
{view.sections}""",
    )


def keep_last_words(title: str) -> str:
    """A heading whose last line never holds one word: the last space before any markup becomes a no-break space."""
    text, tag, markup = title.partition("<")
    head, space, tail = text.rpartition(" ")
    return f"{head}&nbsp;{tail}{tag}{markup}" if space else title


def typeset(text: str, space: str) -> str:
    """Text as the page sets it: a one-letter word joins the next with `space`, no line ends at a hyphen.

    The joiner keeps hyphenated names whole (Bosnia-Herzegovina, soccer-rating). CSS has no property that stops a
    break after a hyphen alone: `white-space: nowrap` would also stop a name wider than its column from wrapping,
    which `overflow-wrap: anywhere` still allows with the joiner.
    """
    return _SHORT_WORD.sub(lambda word: word.group(1) + space, text).replace("-", "-" + WORD_JOINER)


def typeset_html(html: str) -> str:
    """`typeset` on the text between tags, with `&nbsp;`."""
    return _TEXT.sub(lambda text: typeset(text.group(), "&nbsp;"), html)
