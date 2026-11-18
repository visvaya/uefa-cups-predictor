"""The results page's row model: what the adapters build from the analyzer's frames and the renderer shows.

`kickoff` is aware, in `PAGE_TIMEZONE`; `edge` is a fraction (0.04 = 4 percentage points); `win_pct` and the
chances are percentages (0 to 100). `None` stands for a value the inputs do not have.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

Level = Literal["strong", "consider", "neutral", "caution", "avoid"]
Pick = Literal["1", "X", "2"]


@dataclass(frozen=True)
class PickOdds:
    """The picked outcome's odds: at the market's open and close, and the model's fair odds."""

    open: float | None
    close: float | None
    fair: float | None


@dataclass(frozen=True)
class SrFacts:
    """Soccer-rating details of a match; the hrefs are site paths of the clubs' pages."""

    edge: float
    steam: float
    ao: float
    quality: float
    home_href: str | None
    away_href: str | None


@dataclass(frozen=True)
class TeamFacts:
    """One team's row of a cup report."""

    team: str
    win_pct: float
    motivation: float
    status: str
    rotation: float
    value: float
    score: float
    edge: float
    level: Level
    reason: str
    close: float | None


@dataclass(frozen=True)
class CupFacts:
    """The match's 1/X/2 chances and both teams' rows (None when the report has no row for a team)."""

    home_win_pct: float
    draw_pct: float
    away_win_pct: float
    home: TeamFacts | None
    away: TeamFacts | None


@dataclass(frozen=True)
class MatchRow:
    """One match of either tab: `sr` is set on the soccer-rating tab, `cup` on the cups tab."""

    home: str
    away: str
    pick: Pick
    level: Level
    reason: str
    day: date | None
    kickoff: datetime | None
    group: str
    group_name: str
    odds: PickOdds
    score: float
    sr: SrFacts | None
    cup: CupFacts | None


@dataclass(frozen=True)
class CupSection:
    """The matches of one cup (report prefix such as `cl`)."""

    prefix: str
    name: str
    rows: tuple[MatchRow, ...]


@dataclass(frozen=True)
class PageData:
    """Everything the page shows, with the scrape time (None when unknown) and the generation time."""

    sr_rows: tuple[MatchRow, ...]
    cups: tuple[CupSection, ...]
    scraped_at: datetime | None
    generated_at: datetime
