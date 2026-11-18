"""The soccer-rating tab's rows, built from `sr_only_ranking`'s frame (one row per match, the favoured side)."""

from datetime import date, datetime

import pandas as pd

from analyzer.page.model import MatchRow, Pick, PickOdds, SrFacts
from analyzer.page.texts import fold, kickoff_at, level_of
from analyzer.recommendations import MISSING_ODDS

# pick12 -> the pick and the suffix of its odds columns
_PICKS: dict[str, tuple[Pick, str]] = {"1": ("1", "1"), "X": ("X", "x"), "2": ("2", "2")}


def odds_or_none(value: float) -> float | None:
    """Odds as a number, or None for the frames' missing odds (99 or NaN)."""
    return None if pd.isna(value) or value == MISSING_ODDS else float(value)


def pick_odds(r: pd.Series, side: str) -> PickOdds:
    """The open, close and fair odds of one outcome (`side` 1, x or 2); absent columns give None too."""
    return PickOdds(*(odds_or_none(r.get(f"{kind}_{side}", MISSING_ODDS)) for kind in ("open", "close", "fair")))


def _fact(value: float) -> float:
    return 0.0 if pd.isna(value) else float(value)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _row(r: pd.Series) -> MatchRow:
    pick, side = _PICKS[r["pick12"]]
    day = date.fromisoformat(r["snapshot_date"])
    return MatchRow(
        home=r["HomeTeamName"],
        away=r["AwayTeamName"],
        pick=pick,
        level=level_of(r["recommendation"]),
        reason=r["reason"],
        day=day,
        kickoff=kickoff_at(day, r["time_local"]),
        group=r["league_code"],
        group_name=_text(r["league_name"]) or r["league_code"],
        odds=pick_odds(r, side),
        score=float(r["expertScore"]),
        sr=SrFacts(
            edge=_fact(r["SR_edge"]),
            steam=_fact(r["srDropping"]),
            ao=_fact(r["strangeOdds"]),
            quality=_fact(r["srCompleteness"]),
            home_href=_text(r["home_href"]) or None,
            away_href=_text(r["away_href"]) or None,
        ),
        cup=None,
    )


def _order(row: MatchRow) -> tuple[date, bool, float, str]:
    kickoff = row.kickoff.timestamp() if row.kickoff else 0.0
    return (row.day or date.min, row.kickoff is None, kickoff, fold(row.home))


def sr_match_rows(ranking: pd.DataFrame) -> tuple[MatchRow, ...]:
    """The rows by day, then kickoff (matches without a time last), then home name.

    The score is `expertScore` as the report shows it (2 decimals); odds of 99 or NaN become None, NaN facts 0.0.
    """
    ranking = ranking.assign(expertScore=ranking["expertScore"].round(2))
    rows = [_row(r) for _, r in ranking.iterrows()]
    return tuple(sorted(rows, key=_order))


def latest_scrape(sr: pd.DataFrame) -> datetime | None:
    """The newest `scraped_at` of a snapshot as an aware UTC time; None without the column or a readable value."""
    if "scraped_at" not in sr.columns:
        return None
    latest = pd.to_datetime(sr["scraped_at"], errors="coerce", utc=True).max()
    return None if pd.isna(latest) else latest.to_pydatetime()
