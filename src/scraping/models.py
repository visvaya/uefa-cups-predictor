from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


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
    value_side: Optional[str]
    odds_rating_oo_today: Optional[float]
    odd_1_today: Optional[float]
    odd_x_today: Optional[float]
    odd_2_today: Optional[float]
    lineup_rating_home_today: Optional[float]
    lineup_rating_away_today: Optional[float]
    lineup_type_today: Optional[str]


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
    oo_match_gap: Optional[float]
    match_confidence: str  # "HIGH", "MEDIUM", "LOW"

    team_rating_home: Optional[float]
    team_rating_away: Optional[float]


@dataclass
class ClubMeta:
    team_id: int
    team_name: str
    rating_total: Optional[float]
    rating_home: Optional[float]
    rating_away: Optional[float]


@dataclass
class ClubCup:
    team_id: int
    cup_code: str
