from __future__ import annotations
import re
from bs4 import BeautifulSoup
from typing import Optional
from .models import TodayMatch, ClubMeta, ClubCup, OddsDevelopment

LEAGUES = {
    "CLCUP": "Champions League",
    "ELCUP": "Europa League",
}

RE_TIME_4 = re.compile(r"^\d{4}$")          # 2100
RE_TIME_COLON = re.compile(r"^\d{1,2}:\d{2}$")  # 21:00
RE_FLOAT = re.compile(r"(-?\d+(?:\.\d+)?)")
RE_INT = re.compile(r"(\d+)$")
# RE_LEAGUE = re.compile(r"\b(CLCUP|ELCUP)\b") # Deprecated: now we capture any 2+ uppercase chars if needed, or rely on logic
RE_LEAGUE_STRICT = re.compile(r"\b(CLCUP|ELCUP)\b")
RE_CLIP = re.compile(r"copyToClipboard\('([^']+)'\)")
RE_TEAM_ID = re.compile(r"/[w]?(\d+)/")

def team_id_from_href(href: str) -> int:
    m = RE_TEAM_ID.search(href)
    if not m:
        raise ValueError(f"Could not extract team_id from href={href}")
    return int(m.group(1))

def make_match_id(snapshot_date: str, league_code: str, home_id: int, away_id: int) -> str:
    return f"{snapshot_date}_{league_code}_{home_id}_{away_id}"

def _normalize_time(s: str) -> str:
    s = s.strip()
    if RE_TIME_COLON.match(s):
        return s
    if RE_TIME_4.match(s):
        return f"{s[:2]}:{s[2:]}"
    return s

def _extract_float(s: str) -> Optional[float]:
    m = RE_FLOAT.search(s.replace(",", "."))
    return float(m.group(1)) if m else None

def _extract_two_numbers(td_text: str) -> tuple[Optional[float], Optional[float]]:
    txt = " ".join(td_text.split())
    first = _extract_float(txt)
    second = None
    m = RE_INT.search(txt)
    if m and first is not None:
        val = int(m.group(1))
        if val >= 10:
            second = float(val)
    return first, second

def parse_today_prediction(html: str, snapshot_date: str, all_leagues: bool = False) -> list[TodayMatch]:
    soup = BeautifulSoup(html, "lxml")

    match_table = None
    for t in soup.find_all("table", class_="bigtable"):
        if t.find(string=re.compile(r"Football Prediction Today", re.I)):
            match_table = t
            break
    
    if match_table is None:
        return []

    out: list[TodayMatch] = []
    current_league: Optional[str] = None

    for tr in match_table.find_all("tr"):
        # AD DETECTION: Skip rows with "Live Betting Tips!" or adsbygoogle script
        tr_str = str(tr)
        if "Live Betting Tips!" in tr_str or "adsbygoogle" in tr_str:
            continue

        tds = tr.find_all("td")

        if len(tds) == 1 and (tds[0].get("colspan") in ["7", "8"]):
            txt = " ".join(tds[0].stripped_strings)
            
            # Try to extract league code. 
            # It usually looks like "Code  League Name" e.g. "AR1  Primera Division"
            # We will use the first word as code data.
            parts = txt.split(maxsplit=1)
            if parts:
                code_candidate = parts[0]
                # Validation: League code should be short and mostly uppercase/numbers (e.g., AR1, CLCUP)
                # Skip noise like "Top Football Prediction Today"
                if not code_candidate.isupper() and not any(c.isdigit() for c in code_candidate):
                    # If it's something like "Top", skip it
                    continue
                if len(code_candidate) > 10:
                    continue
                
                # If checking strict leagues, validation:
                if not all_leagues:
                    m = RE_LEAGUE_STRICT.search(txt)
                    if m:
                        current_league = m.group(1)
                    else:
                        current_league = None
                else:
                    # Capture whatever is the first token as the league code
                    current_league = code_candidate
                    # For safety, maybe ensure it looks like a code (uppercase, alphanumeric)
                    # But the site seems consistent: "AR1 ...", "CLCUP ...", etc.
                    # We might want to populate LEAGUES dict dynamically? 
                    # For now just pass the code through.
                    if current_league not in LEAGUES:
                        # Add dynamic entry to avoid KeyError later if we rely on LEAGUES[code]
                        # Or just use the rest of the string as name
                        league_name = parts[1] if len(parts) > 1 else current_league
                        LEAGUES[current_league] = league_name

            continue

        if not current_league:
            continue
        
        if not all_leagues and current_league not in ["CLCUP", "ELCUP"]:
            continue

        if len(tds) < 7:
            continue

        time_str = _normalize_time(" ".join(tds[0].stripped_strings))
        odds_rating_oo = _extract_float(" ".join(tds[1].stripped_strings))

        teams_td = tds[3]
        a_tags = teams_td.find_all("a", href=True)
        if len(a_tags) < 2:
            continue

        home_a, away_a = a_tags[0], a_tags[1]
        home_team = home_a.get_text(" ", strip=True)
        away_team = away_a.get_text(" ", strip=True)
        home_href = home_a["href"]
        away_href = away_a["href"]

        home_id = team_id_from_href(home_href)
        away_id = team_id_from_href(away_href)
        match_id = make_match_id(snapshot_date, current_league, home_id, away_id)

        value_side = None
        if home_a.find_parent("b") is not None:
            value_side = "HOME"
        elif away_a.find_parent("b") is not None:
            value_side = "AWAY"

        odd_1, lr_home = _extract_two_numbers(tds[4].get_text(" ", strip=True))
        odd_x, _ = _extract_two_numbers(tds[5].get_text(" ", strip=True))
        odd_2, lr_away = _extract_two_numbers(tds[6].get_text(" ", strip=True))

        lineup_type = None
        row_imgs = tr.find_all("img", src=True)
        srcs = " ".join(img["src"] for img in row_imgs)
        if "shirtgrey.png" in srcs:
            lineup_type = "expected"
        elif re.search(r"/shirt\.png|shirt\.png", srcs):
            lineup_type = "live"

        out.append(TodayMatch(
            match_id=match_id,
            snapshot_date=snapshot_date,
            league_code=current_league,
            league_name=LEAGUES[current_league],
            time_local=time_str,
            home_id=home_id,
            away_id=away_id,
            home_team=home_team,
            away_team=away_team,
            home_href=home_href,
            away_href=away_href,
            value_side=value_side,
            odds_rating_oo_today=odds_rating_oo,
            odd_1_today=odd_1,
            odd_x_today=odd_x,
            odd_2_today=odd_2,
            lineup_rating_home_today=lr_home,
            lineup_rating_away_today=lr_away,
            lineup_type_today=lineup_type,
        ))

    return out

def parse_club_page(html: str, team_id: int) -> tuple[ClubMeta, list[ClubCup]]:
    soup = BeautifulSoup(html, "lxml")
    th = soup.find("th")
    team_name = th.get_text(" ", strip=True) if th else "Unknown"
    txt = soup.get_text(" ", strip=True)

    def pick(label: str) -> Optional[float]:
        m = re.search(rf"{re.escape(label)}[:]?\s*(\d+(?:\.\d+)?)", txt, re.I)
        return float(m.group(1)) if m else None

    cups_list = []
    # Match large letters and commas, stop before next label (capitalized word + colon)
    m_cups = re.search(r"Cups[:]?\s*([A-Z0-9, ]+?)(?=\s*[A-Z][a-z]+[:]|Rating|$)", txt)
    if m_cups:
        raw_cups = [c.strip() for c in m_cups.group(1).split(",") if c.strip()]
        for cup in raw_cups:
            cups_list.append(ClubCup(team_id=team_id, cup_code=cup))

    meta = ClubMeta(
        team_id=team_id,
        team_name=team_name,
        rating_total=pick("Rating Total"),
        rating_home=pick("Rating Home"),
        rating_away=pick("Rating Away"),
    )
    
    return meta, cups_list

import unicodedata
import numpy as np

def norm_team(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # remove diacritics
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def rel_err(a: np.ndarray, b: np.ndarray) -> float:
    # Average relative error; stable for odds > 1
    # Avoid division by zero just in case
    b = np.where(b == 0, 1e-9, b)
    return float(np.mean(np.abs(a - b) / b))

def payload_odds_vectors(p: dict) -> dict[str, np.ndarray]:
    return {
        "open":  np.array([p["open_1"],  p["open_x"],  p["open_2"] ], dtype=float),
        "drop":  np.array([p["drop_1"],  p["drop_x"],  p["drop_2"] ], dtype=float),
        "close": np.array([p["close_1"], p["close_x"], p["close_2"]], dtype=float),
        "fair":  np.array([p["fair_1"],  p["fair_x"],  p["fair_2"] ], dtype=float),
    }

def name_match_score(match_home: str, match_away: str, payload_home: str, payload_away: str) -> int:
    # 2 = perfect match (home-home and away-away)
    # 1 = inverted match (home-away and away-home)
    # 0 = no name match
    mh, ma = norm_team(match_home), norm_team(match_away)
    ph, pa = norm_team(payload_home), norm_team(payload_away)
    if mh == ph and ma == pa:
        return 2
    if mh == pa and ma == ph:
        return 1
    return 0

def pick_best_payload(match_row: dict, payload_candidates: list[dict]) -> tuple[Optional[dict], dict]:
    """
    payload_candidates: list of dicts from payload_to_odds_row() + home_team_payload/away_team_payload/etc.
    Returns: (best_payload_dict, debug_dict)
    """
    wanted_league = match_row["league_code"]
    # We use today_matches column names: odd_1_today, etc.
    today_vec = np.array([match_row["odd_1_today"], match_row["odd_x_today"], match_row["odd_2_today"]], dtype=float)

    scored = []
    for p in payload_candidates:
        if p.get("league_code_payload") != wanted_league:
            continue

        nm = name_match_score(
            match_row["home_team"], match_row["away_team"], 
            p["home_team_payload"], p["away_team_payload"]
        )

        vecs = payload_odds_vectors(p)
        stage_scores = {stage: rel_err(today_vec, v) for stage, v in vecs.items()}
        best_stage = min(stage_scores, key=stage_scores.get)
        best_dist = stage_scores[best_stage]

        oo_gap = None
        if match_row.get("odds_rating_oo_today") is not None:
            oo_gap = abs(float(match_row["odds_rating_oo_today"]) - float(p["oo"]))

        scored.append((nm, best_dist, oo_gap if oo_gap is not None else 1e9, best_stage, p))

    if not scored:
        return None, {"reason": "NO_CANDIDATES_AFTER_LEAGUE_FILTER"}

    # sort: najpierw nazwy (2>1>0), potem dystans kursów, potem oo_gap
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))

    nm, best_dist, oo_gap, best_stage, best = scored[0]
    
    confidence = "HIGH"
    if best_dist > 0.03 or nm < 1:
        confidence = "LOW"
    elif best_dist > 0.01 or nm < 2:
        confidence = "MEDIUM"

    debug = {
        "name_match_level": nm,
        "matched_odds_stage": best_stage,
        "odds_distance": best_dist,
        "oo_match_gap": None if oo_gap == 1e9 else oo_gap,
        "match_confidence": confidence,
        "n_candidates": len(scored),
    }
    return best, debug

def parse_clip_payloads(html: str) -> list[list[str]]:
    soup = BeautifulSoup(html, "lxml")
    payloads = []
    for a in soup.find_all("a", href=True):
        m = RE_CLIP.search(a["href"])
        if m:
            payloads.append(m.group(1).split(","))
    return payloads

def parse_team_ratings(html: str) -> tuple[Optional[float], Optional[float]]:
    """
    Extracts Team Ratings (H/A) from the table (e.g., from club-view page).
    HTML format: <tr><td>Team Ratings (H/A)</td><td>2083.96</td><td>2029.40</td></tr>
    """
    soup = BeautifulSoup(html, "lxml")
    td = soup.find("td", string=re.compile(r"^Team Ratings", re.I))
    if not td:
        return None, None
    
    tr = td.find_parent("tr")
    if not tr:
        return None, None
    
    tds = tr.find_all("td")
    if len(tds) < 3:
        return None, None
    
    home_val = _extract_float(tds[1].get_text(" ", strip=True))
    away_val = _extract_float(tds[2].get_text(" ", strip=True))
    
    return home_val, away_val

def payload_to_odds_row(parts: list[str]) -> dict:
    if len(parts) < 19:
        return {}
    
    try:
        nums = list(map(float, parts[4:]))
        return {
            "home_team_payload": parts[0],
            "away_team_payload": parts[1],
            "some_flag": parts[2],
            "league_code_payload": parts[3],
            "oo": nums[0], "do": nums[1], "ao": nums[2],
            "open_1": nums[3], "open_x": nums[4], "open_2": nums[5],
            "drop_1": nums[6], "drop_x": nums[7], "drop_2": nums[8],
            "close_1": nums[9], "close_x": nums[10], "close_2": nums[11],
            "fair_1": nums[12], "fair_x": nums[13], "fair_2": nums[14],
        }
    except (ValueError, IndexError):
        return {}

def payload_to_odds_development(
    parts: list[str], 
    match_id: str, 
    snapshot_date: str, 
    league_code: str, 
    home_id: int, 
    away_id: int, 
    source_url: str, 
    debug: dict,
    team_rating_home: Optional[float] = None,
    team_rating_away: Optional[float] = None
) -> Optional[OddsDevelopment]:
    row = payload_to_odds_row(parts)
    if not row:
        return None
    
    return OddsDevelopment(
        match_id=match_id,
        snapshot_date=snapshot_date,
        league_code=league_code,
        home_id=home_id,
        away_id=away_id,
        oo=row["oo"], do=row["do"], ao=row["ao"],
        open_1=row["open_1"], open_x=row["open_x"], open_2=row["open_2"],
        drop_1=row["drop_1"], drop_x=row["drop_x"], drop_2=row["drop_2"],
        close_1=row["close_1"], close_x=row["close_x"], close_2=row["close_2"],
        fair_1=row["fair_1"], fair_x=row["fair_x"], fair_2=row["fair_2"],
        team_rating_home=team_rating_home,
        team_rating_away=team_rating_away,
        source_url=source_url,
        name_match_level=debug["name_match_level"],
        matched_odds_stage=debug["matched_odds_stage"],
        odds_distance=debug["odds_distance"],
        oo_match_gap=debug["oo_match_gap"],
        match_confidence=debug["match_confidence"]
    )
