from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TodayMatch:
    match_id: str
    snapshot_date: str
    league_code: str
    league_name: str
    time_local: str
    home_id: int
    away_id: int
    home_team: str
    away_team: str
    home_href: str
    away_href: str
    value_side: str | None
    odds_rating_oo_today: float | None
    odd_1_today: float | None
    odd_x_today: float | None
    odd_2_today: float | None
    lineup_rating_home_today: float | None
    lineup_rating_away_today: float | None
    lineup_type_today: str | None


@dataclass
class OddsDevelopment:
    match_id: str
    snapshot_date: str
    league_code: str
    home_id: int
    away_id: int
    oo: float
    do: float
    ao: float
    open_1: float
    open_x: float
    open_2: float
    drop_1: float
    drop_x: float
    drop_2: float
    close_1: float
    close_x: float
    close_2: float
    fair_1: float
    fair_x: float
    fair_2: float
    source_url: str

    # Debug/Diagnostic fields
    name_match_level: int  # 0, 1, 2
    matched_odds_stage: str  # "open", "drop", "close", "fair"
    odds_distance: float  # relative error
    oo_match_gap: float | None
    match_confidence: str  # "HIGH", "MEDIUM", "LOW"

    team_rating_home: float | None
    team_rating_away: float | None


@dataclass
class ClubMeta:
    team_id: int
    team_name: str
    rating_total: float | None
    rating_home: float | None
    rating_away: float | None


@dataclass
class ClubCup:
    team_id: int
    cup_code: str
