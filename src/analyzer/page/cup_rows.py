"""The cups tab's rows, built from one cup's match frame (`league_frames`) and its team rows (`league_ranking`)."""

from datetime import date

import pandas as pd

from analyzer.page.model import CupFacts, CupSection, MatchRow, Pick, TeamFacts
from analyzer.page.sr_rows import odds_or_none, pick_odds
from analyzer.page.texts import CUP_NAMES, LEVEL_RANKS, kickoff_at, level_of


def _team(r: pd.Series, name: str) -> TeamFacts:
    # Without soccer-rating data for the match (quality 0) the score and edge are missing, not zero
    has_sr = r["sr_quality"] != 0
    return TeamFacts(
        team=name,
        win_pct=float(r["TeamWinProb%"]),
        motivation=float(r["TeamMot"]),
        status=r["TeamStatus"],
        rotation=float(r["TeamRotRisk"]),
        value=float(r["ValFinal"]),
        score=float(r["expertScore"]) if has_sr else None,
        edge=float(r["SR_edge"]) if has_sr else None,
        level=level_of(r["recommendation"]),
        reason=r["reason"],
        close=odds_or_none(r["Close"]),
    )


def _rank(team: TeamFacts) -> tuple[int, float]:
    """Sort key of a team row: better level first, then higher value."""
    return (LEVEL_RANKS[team.level], -team.value)


def _row(prefix: str, m: pd.Series, home: TeamFacts, away: TeamFacts) -> MatchRow:
    pick: Pick = "2" if _rank(away) < _rank(home) else "1"
    chosen = away if pick == "2" else home
    snapshot = m.get("snapshot_date")
    day: date | None = None if pd.isna(snapshot) else pd.Timestamp(snapshot).date()
    return MatchRow(
        home=m["HomeTeam"],
        away=m["AwayTeam"],
        pick=pick,
        level=chosen.level,
        reason=chosen.reason,
        day=day,
        kickoff=None if day is None else kickoff_at(day, m["time_local"]),
        group=prefix,
        group_name=CUP_NAMES[prefix],
        odds=pick_odds(m, pick),
        score=chosen.score,
        sr=None,
        # The frame's chances are fractions; one decimal, as the team rows show theirs
        cup=CupFacts(
            home_win_pct=round(float(m["HomeWin%"]) * 100, 1),
            draw_pct=round(float(m["Draw%"]) * 100, 1),
            away_win_pct=round(float(m["AwayWin%"]) * 100, 1),
            home=home,
            away=away,
        ),
    )


def cup_section(prefix: str, matches: pd.DataFrame, ranking: pd.DataFrame) -> CupSection:
    """One row per match, picking the side with the better level, then the higher value, then home.

    Rows are ordered by the picked side's level, then its value descending; `matches` comes without soccer-rating
    columns when the cup has no soccer-rating data, and then the odds, day and kickoff are None.
    """
    teams = {(r["match_index"], bool(r["is_home"])): r for _, r in ranking.iterrows()}
    ranked = []
    for index, m in matches.iterrows():
        home = _team(teams[index, True], m["HomeTeam"])
        away = _team(teams[index, False], m["AwayTeam"])
        ranked.append((min(_rank(home), _rank(away)), _row(prefix, m, home, away)))
    rows = tuple(row for _, row in sorted(ranked, key=lambda pair: pair[0]))
    return CupSection(prefix, CUP_NAMES[prefix], rows)


def cup_section_without_data(prefix: str) -> CupSection:
    """A cup with no inputs: no rows, so the page shows its no-data notice."""
    return CupSection(prefix, CUP_NAMES[prefix], ())
