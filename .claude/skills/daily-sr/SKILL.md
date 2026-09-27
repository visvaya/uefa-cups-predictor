---
name: daily-sr
description: Run the daily Soccer-rating pipeline - scrape today's matches into a dated snapshot, then generate the SR-only recommendation report in Polish Excel format. Use only when the user explicitly asks for the daily run, because it sends live requests to soccer-rating.com.
disable-model-invocation: true
---

Run the daily SR-only pipeline from the repository root. Extra scraper flags from the user's request (in Claude Code they arrive as `$ARGUMENTS`) override the defaults below, e.g. `--min-start 0 --max-start 300` or `--limit 5`.

1. Compute today's date as `YYYY-MM-DD` in local time (the scraper names snapshots with `datetime.now()`).
2. Run the scraper (network access, takes several minutes because of the per-request delay):
   `python -m src.scraping.soccer_rating_cli --all-leagues --skip-cups --separate-snapshots --min-start 20 --max-start 700`
   If the user passed a flag that is already in the defaults, keep only the user's value.
3. Confirm that `data/soccer-rating/match_odds_development_<date>.csv` exists. If the scraper logged "No matches match the criteria", stop and report that instead of running the analyzer.
4. Run the analyzer:
   `python analyze.py --excel-pl --sr-only --input-file data/soccer-rating/match_odds_development_<date>.csv --output-dir recommendations`
5. Report: number of matches scraped, the path of the generated `recommendations/sr_analysis_report_<date>.csv`, and the top rows by `expertScore` (pick, recommendation). Report any `WARNING`/`ERROR` lines from both steps verbatim.

Do not commit anything: the snapshot and the report are gitignored data.
If the scraper crashes or most matches lack payloads, the site markup may have changed; report it instead of retrying in a loop.
