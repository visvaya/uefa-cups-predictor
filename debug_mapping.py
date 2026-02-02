import pandas as pd
import numpy as np
import unicodedata
from typing import Dict, Optional

NAME_FIX = {
    "sturm": "sturm graz",
    "brann": "sk brann bergen",
    "maccabi ta": "maccabi tel aviv",
    "go ahead": "go ahead eagles",
    "crvena zvezda": "crvena zvezda belgrade",
    "fcsb": "steaua bukarest",
    "plzen": "fk viktoria plzen",
    "nice": "ogc nice",
    "ferencvaros": "ferencvaros budapest",
    "young boys": "young boys bern",
    "rangers": "glasgow rangers",
    "feyenoord": "feyenoord rotterdam",
    "paok": "paok saloniki",
    "porto": "fc porto",
    "salzburg": "red bull salzburg",
    "celtic": "celtic glasgow",
    "utrecht": "fc utrecht",
    "basel": "fc basel",
    "midtjylland": "fc midtjylland",
    "celta": "celta de vigo",
    "braga": "sporting braga",
    "genk": "krc genk",
    "malmo": "malmo ff",
    "lille": "osc lille",
    "freiburg": "sc freiburg",
    "bologna": "bologna fc",
    "lyon": "olympique lyon",
    "roma": "as roma",
    "ludogorets": "ludogorets razgrad",
    "betis": "betis sevilla",
    "stuttgart": "vfb stuttgart",
}

def remove_diacritics(s: str) -> str:
    mapping = {
        '\u00f8': 'o', '\u00d8': 'O', '\u0142': 'l', '\u0141': 'L', 
        '\u00e6': 'ae', '\u00c6': 'AE', '\u00e5': 'a', '\u00c5': 'A'
    }
    s = s.translate(str.maketrans(mapping))
    normalized = unicodedata.normalize('NFD', s)
    return "".join(c for c in normalized if unicodedata.category(c) != 'Mn')

def norm_key(s: Optional[str]) -> str:
    if pd.isna(s) or s is None: return ""
    s = remove_diacritics(str(s)).strip().lower()
    return NAME_FIX.get(s, s)

print("--- DEBUG MAPPING ---")
el_fix = pd.read_csv("data/theanalyst/europa-league/el_fixtures.csv", sep=";")
el_fix["HomeKey"] = el_fix["HomeTeam"].map(norm_key)
el_fix["AwayKey"] = el_fix["AwayTeam"].map(norm_key)

row = el_fix[el_fix["HomeTeam"].str.contains("Crvena", na=False)]
print("Analyst Row for Crvena:")
print(row[["HomeTeam", "AwayTeam", "HomeKey", "AwayKey"]])

sr = pd.read_csv("data/soccer-rating/match_odds_development.csv")
meta = pd.read_csv("data/soccer-rating/club_meta.csv")
meta["TeamKey"] = meta["team_name"].map(norm_key)
name_map = meta.set_index(meta["team_id"].astype(str))["TeamKey"].to_dict()

sr["HomeKey"] = sr["home_id"].astype(str).map(name_map)
sr["AwayKey"] = sr["away_id"].astype(str).map(name_map)

sr_match = sr[sr["home_id"] == 1294]
print("\nSR Match for Crvena (1294):")
if not sr_match.empty:
    print(sr_match[["home_id", "away_id", "HomeKey", "AwayKey"]])
else:
    print("NOT FOUND IN match_odds_development.csv")

print("\nCelta in meta:")
celta_meta = meta[meta["team_id"] == 1039]
if not celta_meta.empty:
    print(celta_meta[["team_id", "team_name", "TeamKey"]])
else:
    print("NOT FOUND IN club_meta.csv")

print("\nJoin Check:")
joined = el_fix.merge(sr, on=["HomeKey", "AwayKey"], how="inner")
print(f"Total inner joined rows: {len(joined)}")
if not joined[joined["HomeKey"] == "crvena zvezda belgrade"].empty:
    print("Join SUCCESS for Crvena")
else:
    print("Join FAILED for Crvena")
