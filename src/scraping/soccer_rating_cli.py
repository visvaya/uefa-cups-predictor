import time
import pandas as pd
import logging
import argparse
from datetime import datetime
from pathlib import Path
from .fetcher import SoccerRatingFetcher
from .parsers import (
    parse_today_prediction, 
    parse_club_page, 
    parse_team_ratings,
    parse_clip_payloads, 
    payload_to_odds_row,
    payload_to_odds_development,
    pick_best_payload
)
from .models import ClubMeta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_results(matches, all_odds_dev):
    logger.info("--- Validation Report ---")
    
    # 1. Duplicates
    match_ids = [m.match_id for m in matches]
    unique_ids = set(match_ids)
    if len(match_ids) != len(unique_ids):
        logger.error(f"Validation FAILED: Found {len(match_ids) - len(unique_ids)} duplicate match_ids!")
    else:
        logger.info(f"Validation OK: No duplicate match_ids ({len(unique_ids)} unique).")

    # 2. League codes
    # If we are in all leagues mode, this shouldn't be an error.
    # We can check if any league code is suspicious (e.g. empty)
    invalid_leagues = [m.league_code for m in matches if not m.league_code]
    if invalid_leagues:
        logger.error(f"Validation FAILED: Found {len(invalid_leagues)} matches with missing league codes!")
    else:
        logger.info(f"Validation OK: League codes extracted for all {len(matches)} matches.")

    # 3. Coverage
    matched_ids = {d.match_id for d in all_odds_dev}
    coverage = len(matched_ids) / len(unique_ids) if unique_ids else 0
    logger.info(f"Payload Coverage: {coverage:.1%} ({len(matched_ids)}/{len(unique_ids)})")
    if coverage < 1.0:
        missing = unique_ids - matched_ids
        logger.warning(f"Missing payloads for {len(missing)} matches: {list(missing)}")

    # 4. Quality
    low_conf = [d for d in all_odds_dev if d.match_confidence == "LOW"]
    if low_conf:
        logger.warning(f"Quality Alert: Found {len(low_conf)} LOW confidence matches!")
    else:
        logger.info("Quality OK: No LOW confidence matches found.")
    
    logger.info("--------------------------")

def main():
    parser = argparse.ArgumentParser(description="Soccer-Rating ETL Scraper CLI")
    parser.add_argument("--local", action="store_true", help="Use local files for testing")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of matches to process")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds")
    parser.add_argument("--output-dir", type=str, default="data/soccer-rating", help="Output directory")
    parser.add_argument("--all-leagues", action="store_true", help="Capture matches from ALL leagues, not just CL/EL")
    parser.add_argument("--separate-snapshots", action="store_true", help="Save match odds to separate daily snapshot files")
    parser.add_argument("--min-start", type=int, default=None, help="Process matches starting at least N minutes from now")
    parser.add_argument("--max-start", type=int, default=None, help="Process matches starting at most N minutes from now")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    fetcher = SoccerRatingFetcher()
    
    if args.local:
        logger.info("Running in LOCAL mode.")
        if Path("today-prediction.html").exists():
            with open("today-prediction.html", "r", encoding="utf-8") as f:
                today_html = f.read()
        else:
            logger.error("today-prediction.html not found.")
            return
    else:
        today_html = fetcher.fetch("/today-prediction")
    
    if not today_html:
        logger.error("Failed to get today predictions.")
        return

    matches = parse_today_prediction(today_html, snapshot_date, all_leagues=args.all_leagues)
    logger.info(f"Loaded {len(matches)} total matches (all matching leagues).")

    # Time Window Filtering
    if args.min_start is not None or args.max_start is not None:
        filtered_matches = []
        now = datetime.now()
        for m in matches:
            # Parse time "HH:MM". Assume today's date + local timezone logic (as site seems to follow user expectation)
            # Warning: this is simplistic. Site timezone might differ.
            try:
                hm = datetime.strptime(m.time_local, "%H:%M")
                match_dt = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
                # If match time is much earlier than now (e.g. 00:30 vs 23:00), assume it's next day? 
                # Or if match is 23:00 and now is 00:30, match was yesterday?
                # For simplicity, just use today's date as base. 
                # Better approach: check diff. 
                
                diff_min = (match_dt - now).total_seconds() / 60.0
                
                if args.min_start is not None and diff_min < args.min_start:
                    continue # Too soon or already started
                if args.max_start is not None and diff_min > args.max_start:
                    continue # Too late
                
                filtered_matches.append(m)
            except Exception as e:
                logger.warning(f"Could not parse time {m.time_local} for {m.match_id}: {e}")
                
        logger.info(f"Filtered matches: {len(filtered_matches)} (from {len(matches)}) based on time window.")
        matches = filtered_matches
    
    if not matches:
        logger.warning("No matches match the criteria. Exiting.")
        return

    all_odds_dev = []
    all_clubs = {} # team_id -> ClubMeta
    all_cups = []  # list of ClubCup

    count = 0
    for match in matches:
        if args.limit and count >= args.limit:
            break
        
        logger.info(f"Processing Match: {match.home_team} vs {match.away_team} ({match.match_id})")
        
        match_team_ratings = {"home": None, "away": None}
        raw_candidates = []

        # Pre-populate ClubMeta with basic info to ensure mapping exists even if we skip the page logic
        for tid, tname in [(match.home_id, match.home_team), (match.away_id, match.away_team)]:
            if tid not in all_clubs:
                all_clubs[tid] = ClubMeta(
                    team_id=tid,
                    team_name=tname,
                    rating_total=None, rating_home=None, rating_away=None
                )

        # Try both home and away club pages to find the odds development payload
        # Optimization: Stop as soon as we find valid candidates (avoid redundant request)
        for team_type, href in [("home", match.home_href), ("away", match.away_href)]:
            team_id = match.home_id if team_type == "home" else match.away_id
            team_name = match.home_team if team_type == "home" else match.away_team
            
            if args.local:
                # Try specific team file or generic club.html
                # Convert "Sturm Graz" -> "sturm-graz" or "Sturm-Graz"
                slug_variants = [
                    team_name.replace(" ", "-"),
                    team_name.replace(" ", "-").lower(),
                    team_name.replace(" ", "_"),
                    # Try some specific mappings if needed (heuristic)
                    team_name.lower().replace(" ", "-"),
                ]
                local_candidates = [Path(f"{s}.html") for s in slug_variants] + [Path("club.html")]
                html_path = next((p for p in local_candidates if p.exists()), None)
                
                if html_path:
                    logger.info(f"Using local file {html_path} for {team_name}")
                    with open(html_path, "r", encoding="utf-8") as f:
                        club_html = f.read()
                else:
                    logger.warning(f"No local file for {team_name}, skipping.")
                    continue
            else:
                time.sleep(args.delay)
                club_html = fetcher.fetch(href)

            if not club_html:
                logger.warning(f"Could not fetch club page for {team_name} ({team_id}).")
                continue
            
            # Extract Team Ratings (H/A)
            tr_h, tr_a = parse_team_ratings(club_html)
            if tr_h and tr_a:
                match_team_ratings["home"] = tr_h
                match_team_ratings["away"] = tr_a

            # Parse Club Meta (overwrite fallback with data from page)
            meta, cups = parse_club_page(club_html, team_id)
            all_clubs[team_id] = meta
            all_cups.extend(cups)
            
            # Extract raw payloads for later scoring
            found_new_candidates = False
            for payload_parts in parse_clip_payloads(club_html):
                row = payload_to_odds_row(payload_parts)
                if row:
                    row["_raw_parts"] = payload_parts
                    row["_source_href"] = href
                    raw_candidates.append(row)
                    found_new_candidates = True
            
            # If we found candidates, we likely have the match data.
            # No need to check the opponent's page for the exact same data.
            if found_new_candidates:
                break

        # Select the best candidate using advanced strategy
        best_row, debug = pick_best_payload(match.__dict__, raw_candidates)
        
        if best_row:
            source_url = fetcher.BASE_URL + best_row["_source_href"] if not args.local else best_row["_source_href"]
            dev = payload_to_odds_development(
                best_row["_raw_parts"],
                match.match_id,
                snapshot_date,
                match.league_code,
                match.home_id,
                match.away_id,
                source_url,
                debug,
                team_rating_home=match_team_ratings["home"],
                team_rating_away=match_team_ratings["away"]
            )
            if dev:
                all_odds_dev.append(dev)
                logger.info(f"Matched {match.match_id} (conf={debug['match_confidence']}, stage={debug['matched_odds_stage']}, dist={debug['odds_distance']:.4f})")
                if debug['match_confidence'] == "LOW":
                    logger.warning(f"Low confidence match for {match.match_id}")
        else:
            logger.warning(f"No matching odds payload discovered for {match.match_id}")

        count += 1

    def save_cumulative(df_new, filename, id_cols, sort_col=None):
        path = output_dir / filename
        if path.exists():
            try:
                df_old = pd.read_csv(path)
                df = pd.concat([df_old, df_new], ignore_index=True)
            except Exception as e:
                logger.warning(f"Could not read existing {filename}: {e}")
                df = df_new
        else:
            df = df_new
        
        if sort_col:
            df = df.sort_values(sort_col, ascending=True)
            
        df = df.drop_duplicates(subset=id_cols, keep="last")
        df.to_csv(path, index=False)
        return len(df)

    # Save Results
    if matches:
        df_today = pd.DataFrame([m.__dict__ for m in matches])
        df_today.to_csv(output_dir / "today_matches.csv", index=False)
    
    if all_odds_dev:
        df_dev = pd.DataFrame([d.__dict__ for d in all_odds_dev])
        # Define and enforce column order
        id_cols_dev = ["match_id", "snapshot_date", "home_id", "away_id", "league_code", "source_url"]
        rem_cols_dev = [c for c in df_dev.columns if c not in id_cols_dev]
        df_dev = df_dev[id_cols_dev + rem_cols_dev]
        df_dev = df_dev[id_cols_dev + rem_cols_dev]
        
        if args.separate_snapshots:
            # Separate snapshot mode: distinct file per day, no overwriting of whole history,
            # but merge within the file to deduplicate if run multiple times same day.
            snap_filename = f"match_odds_development_{snapshot_date}.csv"
            total = save_cumulative(df_dev, snap_filename, ["match_id"], "snapshot_date")
            logger.info(f"Saved snapshot to {snap_filename} (Total records in file: {total})")
        else:
            # Default mode: cumulative main file
            total = save_cumulative(df_dev, "match_odds_development.csv", ["match_id"], "snapshot_date")
            # Final pass: reload and filter to ensure no legacy columns from concat
            df_final = pd.read_csv(output_dir / "match_odds_development.csv")
            df_final = df_final[id_cols_dev + rem_cols_dev]
            df_final.to_csv(output_dir / "match_odds_development.csv", index=False)
            logger.info(f"Updated match_odds_development.csv (Total records: {total})")
    
    if all_clubs:
        df_clubs = pd.DataFrame([c.__dict__ for c in all_clubs.values()])
        # Strictly enforce: team_id, team_name, rating_total, rating_home, rating_away
        cols_clubs = ["team_id", "team_name", "rating_total", "rating_home", "rating_away"]
        df_clubs = df_clubs[cols_clubs]
        total = save_cumulative(df_clubs, "club_meta.csv", ["team_id"], "team_id")
        # Final pass: reload and filter
        df_final = pd.read_csv(output_dir / "club_meta.csv")
        df_final = df_final[cols_clubs]
        df_final.to_csv(output_dir / "club_meta.csv", index=False)
        logger.info(f"Updated club_meta.csv (Total records: {total})")
    
    if all_cups:
        df_cups = pd.DataFrame([c.__dict__ for c in all_cups])
        total = save_cumulative(df_cups, "club_cups.csv", ["team_id", "cup_code"])
        logger.info(f"Updated club_cups.csv (Total records: {total})")

    logger.info(f"ETL Complete. Outputs in {output_dir}")
    validate_results(matches, all_odds_dev)

if __name__ == "__main__":
    main()
