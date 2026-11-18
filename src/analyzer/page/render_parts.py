"""Values both tabs of the results page share, shaped for the templates: data attributes, signals, filters, number
text and typesetting.

The markup is in `templates/`. A plain text from the inputs reaches it as a `str` and is escaped by autoescape; only
a `Markup` is left as it is.
"""

import math
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass

from markupsafe import Markup, escape

from analyzer.page.model import Level, MatchRow, PickOdds
from analyzer.page.texts import (
    HEADS,
    LABELS,
    LEVEL_NAMES,
    LEVEL_RANKS,
    MINUS,
    SIGNAL_SHORT,
    SIGNAL_TERMS,
    TERMS,
    WEEKDAYS,
    WORD_JOINER,
    fold,
    pl_number,
)

# The longest last pair of heading words (both words and the space) that is joined; a 21-character pair overflowed
# the column of a 320 px phone
_JOINED_PAIR_MAX_CHARS = 16
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
class Group:
    """One section of a view: its index, heading, note on the bar (empty: the count of shown rows) and rows.

    A cup without data has no rows and a `notice` instead.
    """

    index: int
    title: str
    note: str
    rows: list[dict[str, object]]
    notice: str = ""


def _signal_parts(reason: str) -> list[str]:
    return [part.strip() for part in reason.split(";") if part.strip() not in ("", "-")]


def signal_keys(reason: str) -> list[str]:
    """The explanation keys of the signals in a report reason, in their order."""
    return [key for part in _signal_parts(reason) for prefix, key in SIGNAL_TERMS if part.startswith(prefix)]


def _shown_signal(text: str) -> str:
    for raw, short in SIGNAL_SHORT.items():
        text = text.replace(raw, short)
    return text.replace("(-", "(" + MINUS)


def signal_texts(reason: str) -> list[str]:
    """The signals of a reason as the page shows them."""
    return [_shown_signal(part) for part in _signal_parts(reason)]


def signal_terms(reasons: list[str]) -> str:
    """The keys of one explanation for all signals in the given reasons, so the signals themselves stay plain text."""
    return " ".join(dict.fromkeys(key for reason in reasons for key in signal_keys(reason)))


def number_or(value: float | None, missing: str, shown: Callable[[float], str] = pl_number) -> str:
    """A number as `shown` writes it (two decimals by default), or `missing` when the inputs have none."""
    return missing if value is None else shown(value)


def edge_text(edge: float) -> Markup:
    """The model's edge in percentage points, with its sign."""
    return Markup("{}&nbsp;{}").format(pl_number(edge * 100, 0, sign=True), LABELS["points"])


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


def row_context(index: int, row: MatchRow, own: Sequence[tuple[str, object]]) -> dict[str, object]:
    """What both tabs' match rows share: the data they sort, filter and search by (then the tab's `own`) and signals.

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
        # Filters compare the value as shown (two decimals), so a range keeps what the reader sees
        ("odds", None if row.odds.close is None else round(row.odds.close, 2)),
        *own,
        ("signals", " ".join(signal_keys(row.reason))),
        ("teams", f"{fold(row.home)} {fold(row.away)}"),
    ]
    return {
        "index": index,
        "row": row,
        "attrs": [(name, value) for name, value in pairs if value is not None],
        "signals": signal_texts(row.reason),
        "terms": signal_terms([row.reason]),
    }


def counted(pairs: Iterable[tuple[str, str]]) -> dict[str, tuple[str, int]]:
    """Per code its label and how many rows have it, in the order the codes first occur."""
    out: dict[str, tuple[str, int]] = {}
    for code, label in pairs:
        out[code] = (label, out.get(code, (label, 0))[1] + 1)
    return out


def level_counts(rows: tuple[MatchRow, ...]) -> list[tuple[Level, str, int]]:
    """The levels the rows have, with their names and counts."""
    counts = {level: sum(row.level == level for row in rows) for level in LEVEL_NAMES}
    return [(level, name, counts[level]) for level, name in LEVEL_NAMES.items() if counts[level]]


_ODDS_RANGE = RangeSpec("odds", "odds", HEADS["odds"], HEADS["odds"], 0.05, 2)


def range_field(spec: RangeSpec, values: list[float]) -> dict[str, object] | None:
    """A from-to pair whose spinbuttons start at the data's bounds, rounded outwards to the step; None without data."""
    if not values:
        return None
    low = round(math.floor(min(values) / spec.step + 1e-9) * spec.step, 6)
    high = round(math.ceil(max(values) / spec.step - 1e-9) * spec.step, 6)
    return {
        **asdict(spec),
        "low": low,
        "high": high,
        "spins": [
            {"bound": bound, "word": LABELS[word], "start": start, "text": pl_number(start, spec.digits)}
            for bound, word, start in (("min", "from", low), ("max", "to", high))
        ],
    }


def signal_counts(rows: tuple[MatchRow, ...]) -> list[tuple[str, str, int]]:
    """Signals with their explanation titles and counts, the most frequent first."""
    counts = counted((key, key) for row in rows for key in dict.fromkeys(signal_keys(row.reason)))
    return [(key, TERMS[key][0], n) for key, (_, n) in sorted(counts.items(), key=lambda item: -item[1][1])]


def common_filters(rows: tuple[MatchRow, ...]) -> dict[str, object]:
    """The filters both tabs have: levels, closing odds (over the odds as shown) and signals."""
    odds = [round(row.odds.close, 2) for row in rows if row.odds.close is not None]
    return {"levels": level_counts(rows), "odds": range_field(_ODDS_RANGE, odds), "signals": signal_counts(rows)}


def keep_last_words(title: str) -> str:
    """A heading's last two words joined by a no-break space, so its last line never holds one word.

    Only a short pair is joined: a longer one could be wider than a narrow phone's column.
    """
    head, space, tail = title.rpartition(" ")
    pair = f"{head.rpartition(' ')[2]} {tail}"
    if not space or len(pair) > _JOINED_PAIR_MAX_CHARS:
        return escape(title)
    return Markup("{}&nbsp;{}").format(head, tail)


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
