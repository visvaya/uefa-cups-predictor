# UEFA Cups Fantasy Predictor & Analyzer (CL & EL)

[![CI](https://github.com/visvaya/uefa-cups-predictor/actions/workflows/ci.yml/badge.svg)](https://github.com/visvaya/uefa-cups-predictor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Status:** maintained personal tool, run by hand during the UEFA league phase. There are no releases; `main` is the supported version. Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md); security reports: [SECURITY.md](SECURITY.md).

System for predicting results, assessing motivation, and rotation risk in European competitions (Champions League, Europa League and Conference League) under the new league phase format. The system is based on probabilistic forecasts from Monte Carlo simulations ("The Analyst" data) and odds data from Soccer-rating. It is specifically designed for analyzing the final rounds of the league phase.

Allows creating a "lock/in_play/out" map:

- **LOCK**: Result already secured (Top 8 or Top 24 guaranteed).
- **IN_PLAY**: Fighting at the qualification threshold.
- **OUT**: No mathematical chance of progression.

> **Note**: This tool is specifically designed for analyzing the **final round** of the league phase, where motivation and rotation risks are most critical. For a deeper dive into the mathematical logic used, see [interpretation.md](interpretation.md).

## Installation

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`.

```bash
git clone https://github.com/visvaya/uefa-cups-predictor.git
cd uefa-cups-predictor
uv sync --locked --no-dev   # creates .venv with the locked runtime dependencies and the project
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

Alternatively, prefix commands with `uv run` instead of activating the environment. The environment also provides
two commands: `analyze` (same as `python analyze.py`) and `soccer-rating` (same as
`python -m scraping.soccer_rating_cli`).

Input data is not included in the repository (see [How to Get Data](#how-to-get-data)); only the `_example.csv` templates are tracked. Run all commands from the repository root.

## Key Features

- **Status Model (UEFA Art. 17 Compliance)**: Classifies clubs based on mathematical progression chances:
  - `OUT`: No chance for Top 24.
  - `LOCKED_DIRECT_RO16`: Guaranteed spot in the top eight (direct qualification).
  - `LOCKED_PLAYOFFS`: Guaranteed progression, but no chance for Top 8 (play-offs).
  - `IN_PLAY`: Fight for key positions continues.
- **Motivation Index (Mot)**: Custom *Pressure Vector* algorithm assessing "win pressure". Peak values occur at qualification thresholds (spots 8/9 and 24/25).
- **Rotation Risk (Risk)**: Detects "safe" teams likely to rotate their squad before the knockout phase.
- **Opponent Dead Bonus (`opp_dead`)**: Automatic attractiveness bonus for a team playing against a rival that is already `OUT` or has nothing left to play for.
- **International & Excel Ready**: Output format is standardized for international use (comma `,` separator, dot `.` decimal). Polish local format is available via flag.

## How to Get Data

To legally and correctly prepare files for the analyzer, follow these steps:

1. **Visit The Analyst**: Go to the links provided in the [Data Sources](#data-sources) section.
2. **Select Tabs**: For tables, ensure you select the **'Predicted'** tab.
3. **Manual Copy-Paste**:
    - Select the data in the table on the website with your mouse.
    - Copy (Ctrl+C) and paste (Ctrl+V) into Excel or Google Sheets.
4. **Save as CSV**:
    - In Excel, use `File > Save As` and select **CSV UTF-8 (Comma delimited) (*.csv)**.
    - Ensure the column headers match the requirements.

## Data Sources

The script relies on data exported from **The Analyst** (Opta):

- **CL Table**: [theanalyst.com/competition/uefa-champions-league/table](https://theanalyst.com/competition/uefa-champions-league/table) (use 'Predicted' tab)
- **CL Fixtures**: [theanalyst.com/competition/uefa-champions-league/fixtures](https://theanalyst.com/competition/uefa-champions-league/fixtures)
- **EL Table**: [theanalyst.com/competition/uefa-europa-league/table](https://theanalyst.com/competition/uefa-europa-league/table) (use 'Predicted' tab)
- **EL Fixtures**: [theanalyst.com/competition/uefa-europa-league/fixtures](https://theanalyst.com/competition/uefa-europa-league/fixtures)
- **ECL Table and Fixtures**: [theanalyst.com/competition/uefa-conference-league/predictions](https://theanalyst.com/competition/uefa-conference-league/predictions) (save them with the same columns as the CL and EL files, as `ecl_fixtures.csv` and `ecl_table_predicted.csv` in `data/theanalyst/conference-league/`)

Odds (Soccer-rating) data:

- **Soccer-rating**: [https://www.soccer-rating.com/today-prediction](https://www.soccer-rating.com/today-prediction)

## Data Interpretation Logic

The system interprets source data (*Predicted Table*) as a set of probabilities, not rigid points.

### Key Input Parameters

- **LAST 16%**: Probability of occupying places 1–8 (direct qualification) in the rows where it adds up with `KO P/0%` to 100; see below for the other rows.
- **KO P/0% / KPO** (the header is written with a zero): Probability of occupying places 9–24 (participation in play-offs).
- **QF%**: P(quarter-final) – used as a safe *floor* for progression chances.

### Calculating P(Top 24) – "Chance of Continuing Play"

The table and fixtures must give every number in percent (0 to 100, dot or comma decimals); a missing column, a blank or unreadable cell (such as `<1` or `99,5%`), a table in fractions, or a team listed or playing twice stops the run with an error.

`LAST 16%` is P(top 8) only in the rows where it adds up with `KO P/0%` to 100; in the other rows of The Analyst's January 2026 tables it is the chance of reaching the last 16 through the play-off. When the column sums confirm that layout (`KO P/0%` sums to 1600 and the direct `LAST 16%` to 800), P(top 24) is P(top 8) plus `KO P/0%`; otherwise the algorithm sums both columns when they are consistent, falls back to the maximum progress column when the sum exceeds 100.01% (two rounded values may reach 100.01), and warns. It never goes below `QF%`. The steps are described in [interpretation.md](interpretation.md#5-ptop-24-calculation-logic).

### Report Columns (Main Mode)

| Column | Description |
| :--- | :--- |
| **team / opp** | Analyzed team and its opponent. |
| **teamWinProb%** | Probability of winning, from the fixtures file (`HomeWin%`, `Draw%`, `AwayWin%` rescaled to sum to 100). |
| **teamMot** | *Motivation Index* (0-100) – internal pressure for result. |
| **teamValue** | *Value Index* (0 to about 135; capped at 140): win probability weighted by the team's motivation, raised when the opponent is `OUT`, `LOCKED` or unmotivated, divided by `teamRotRisk` (formula and weights in `src/analyzer/config.py`). 70 or more is `High Value`, 50 or more `Good Value`; rows of one recommendation are ordered by it. |
| **teamRotRisk** | *Rotation Risk* (1.0 - 2.3) – higher means greater risk of squad rotation. Raised by 10 % for both teams of a match with strange odds (see Soccer-rating Logic). |
| **teamStatus / oppStatus** | Progress status (`IN_PLAY`, `LOCKED`, `OUT`). |
| **expertScore** | **Synthetic Strength Signal**. Aggregate score from market, ratings, and lineups. If > 0, model favors this team. |
| **srEdge** | **Probability Edge**: `FairProb - MarketCloseProb` of this team's win, or of the draw for an `X` pick (the same for both sides, so the label does not depend on who plays at home). Positive = Value found by SR model. |
| **srCompleteness** | **Signal Quality (0.0 - 1.0)**. 1.0 = High Confidence. |
| **srDropping** | **Market Steam** of this team's own odds: `ln(open / close)`. Positive = its odds are dropping (market confirmation). The expert score uses the difference of both sides' steam instead. |
| **strangeOdds** | Market anomaly detection (>30), suggests insider info or sudden squad changes. |
| **recommendation** | Final advice (Strong Buy, Consider, Neutral, Caution, Avoid). |
| **reason** | List of key factors generating the advice. |

### SR-Only Mode

| Column | Description |
| :--- | :--- |
| **homeTeam / awayTeam** | Match participants. |
| **date** | Snapshot date of the match (`snapshot_date`). |
| **time** | Kickoff time from `today_matches.csv` as the site shows it (site time, Europe/Paris by default); empty when the match is not in that file. |
| **league** | Soccer-rating league code (`league_code`). |
| **pick** | **Recommended Outcome**: `1` (Home), `X` (Draw), `2` (Away). |
| **expertScore** | Match signal strength from the picked side's view: > 0 favours it (for `X`, the home view). In SR-only mode it is mostly the closing price, so a high score marks a clear favourite rather than value over the market. |
| **recommendation** | Advice based purely on market gaps and steam. Without motivation data a `1` or `2` pick reaches `🟢 STRONG BUY` only through the `Sure Bet Pattern`. |

### Understanding the 'Reason' Column

Every limit below is compared with the value as the report shows it (rounded), so a shown `teamRotRisk` of 1.39 is always `🟠 CAUTION` and a shown `srDropping` of 0.05 is not above 0.05.

- **Status/Risk (Absolute Priority)**:
  - `Out of contention`: Team cannot reach Top 24. Always `🔴 AVOID`.
  - `Status LOCKED...`: Team has secured its spot. Always `🟠 CAUTION` due to high rotation risk.
  - `High rotation risk`: `teamRotRisk` >= 1.39. Always `🟠 CAUTION`.
- **Value/Signal**:
  - `High Value / Good Value`: High mathematical advantage based on motivation and win prob.
  - `Strong Expert Signal`: `expertScore > 1.50`, a strong model signal for this row's team; `Positive Signal` is the same for `expertScore > 0.50`. The team the score is against gets neither. Apart from the SR-only `Sure Bet Pattern` and `X` picks, a row reaches `🟡 CONSIDER` or `🟢 STRONG BUY` only with a positive score (this row's team favoured).
  - `Close(x) > Fair(y)`: with `High Value`, this team's closing odds next to its fair odds, with `>`, `<` or `=` as they compare; left out without soccer-rating odds.
- **Market Signals**:
  - `Sure Bet Pattern`: Unique combination of low odds (`<2.00`), Value (`Fair<2.20`) and strong Steam (`>0.03`). It counts, and is named in the reason, only when the score favours this team and its pick is `1` or `2` (never an `X` pick); in standard mode the motivation rule of `🟢 STRONG BUY` must hold too (`teamMot` >= 50 and above `oppMot`). When it counts, the row is `🟢 STRONG BUY` ahead of the other signals; otherwise the other rules decide.
  - `Steam (+)`: This team's own odds dropped by more than 0.05 in log terms (`Steam (-)`: rose by more than that). The `Sure Bet Pattern` and `(Risk: Rising Odds)` read the same own steam.
  - `(Risk: Rising Odds)`: `High Value` or a `Strong Expert Signal` (either is enough), while this team's odds are rising (own steam plus the soccer-rating drop below -0.01) and no counted `Sure Bet Pattern` overrides it. In standard mode it keeps the row from `🟢 STRONG BUY`; in SR-only mode it is a warning only, because there `🟢 STRONG BUY` comes from the `Sure Bet Pattern` or a draw rule.
  - `Lean: 1X` / `Lean: X2` (SR-only, `X` picks): the side the score leans to; a score of exactly 0 reads `Lean: X2`. `SteamX` is the steam on the draw.
  - `No valid odds` (SR-only): the snapshot has no usable odds for the match, so it stays `⚪ NEUTRAL`.
  - `(No Steam Confirmation)` (SR-only): a `Strong Expert Signal` whose odds did not fall enough for the `Sure Bet Pattern`; the row stays `🟡 CONSIDER` because the market has not confirmed the signal.

## Soccer-rating Logic

Odds are used as a **dynamic market signal** to enrich the static predictions from The Analyst. It represents the "live" consensus of bookmakers and professional bettors.

1. **Market Consistency**: If model's favorite also has dropping odds (Steam), motivation and confidence are boosted.
2. **Strange Odds Anomaly**: If a market rating adjustment is significant (|AO| > 30), the rotation risk of both teams in that match is multiplied by 1.10 (capped at 2.3) to account for possible hidden factors (injuries, internal rotation); the anomaly does not say which side carries them. The raised risk also lowers the Value Index, which divides by it. Standard mode only; SR-only mode has no rotation risk. With today's weights the raise alone cannot make a row `🟠 CAUTION`: an `IN_PLAY` team's risk stays below 1.11, and 1.11 x 1.10 is below the 1.39 threshold, so `Strange Odds (n)` in the reason is enough to explain it.

## Scraping Data

To update the Soccer-rating data (odds, steam, ratings), run:

```bash
python -m scraping.soccer_rating_cli
```

- **Default behavior**: Fetches today's predictions from `soccer-rating.com`, scrapes match details, odds history, and team ratings.
- **Outputs**: Saves CSV files to `data/soccer-rating/`.

### Arguments

- `--limit N`: Process only the first N matches, N at least 1 (useful for quick testing); the payload coverage is counted over those N.
- `--delay N`: Set delay between requests (default 1.5s).
- `--user-agent TEXT`: Override the User-Agent header. By default the scraper identifies itself as `uefa-cups-predictor` with a link to this repository. It reads the site's `robots.txt` once per run and skips paths it disallows; a missing `robots.txt` (4xx) allows everything, while a server or network error fetching it stops all requests of the run (RFC 9309).
- `--local`: Use local HTML files (for debugging without network).
- `--output-dir PATH`: Custom output directory (default `data/soccer-rating`).
- `--all-leagues`: Fetch matches from ALL leagues (default: only CL & EL).
- `--separate-snapshots`: Save the snapshot to a file of its day (e.g., `match_odds_development_YYYY-MM-DD.csv`) instead of the cumulative `match_odds_development.csv`; a second run on the same day merges into that file, and the newer row of a match wins. Every odds row carries `scraped_at` (UTC time of the run): a merge keeps the newest reading of a match by it even when a slower run saves last, and league analysis (`--cl`, `--el`, `--ecl`) uses it to pick the newest row of the cumulative file (`--sr-only` reads its input file as it is); `today_matches.csv` is merged by match the same way, so a later run keeps the lineups of matches only an earlier run saw.
- `--min-start N`: Process matches starting at least N minutes from now.
- `--max-start N`: Process matches starting at most N minutes from now. Each kickoff is on the date of the page that lists it: an `00:00` kickoff on the today page has already started. When the window ends after midnight, the next day's page is read too (as with `--days`), so matches after midnight are not lost; the local mode stays on the today page.
- `--days N`: Also read the site's day pages for the next N days (0-6, e.g. `/today-prediction/tuesday`); match ids start with the kickoff date and the snapshot file keeps the scrape date. Needs the live site, so it cannot be combined with `--local`.
- `--site-timezone ZONE`: IANA timezone the site shows kickoff times in (default `Europe/Paris`); the time window counts real minutes, also across a DST change. The default follows the site's "Timezone" selector, which showed "GMT +1 Paris" on 2026-11-16 for a request without cookies; whether that default follows DST or the visitor's location was not established, so override it if the site shows times in another zone.

Match filters (combinable, applied after the time window; each logs what it dropped):

- `--skip-cups`: Skip every cup (league code contains `CUP`, e.g. `FACUP`, `CLCUP`).
- `--skip-domestic-cups`: Skip cups that are neither UEFA nor other continental club cups. Cup codes are classified in one table (`CUP_CODES` in `src/scraping/match_filters.py`); a `CUP` code missing from it counts as domestic, and the run logs `Unclassified cup code <code> (<name>)` so that it can be classified.
- `--skip-uefa-cups`: Skip the UEFA club competitions `CLCUP`, `ELCUP`, `ECLCUP` and `WCLCUP` (Women's Champions League).
- `--skip-other-continental-cups`: Skip continental club cups outside UEFA (`CLICUP`, `AFCCUP`, `CCCUP`, `CPCUP`, `AFCUP`, `ASEANCUP`, the codes seen so far; the list is `OTHER_CONTINENTAL_CLUB_CUPS` in `src/scraping/match_filters.py`).
- `--skip-national-teams`: Skip matches of national teams.
- `--leagues CODE[,CODE...]`: Keep only the listed league codes (e.g. `CLCUP,ELCUP,AR1`); implies reading all leagues of the page.

With `--all-leagues`, `--skip-domestic-cups --skip-other-continental-cups` keeps the leagues and the UEFA cups.

National-team matches (links such as `/Germany/n28/`) are scraped like club matches. Their team ids are stored as negative numbers (`-28`), because the site numbers national teams separately from clubs; the analyzer's CL/EL reports never contain them, so they only show up in the SR-only report.

### Checking the site's markup

The parser tests run on hand-written HTML, so they do not notice when soccer-rating.com changes its markup. Run this manual check now and then (and after any parser change):

```bash
soccer-rating --check-markup
```

It fetches the today page and the first match's home team page (two requests plus `robots.txt`, with the usual delay), runs the parsers and logs the number of matches, matches with 1/X/2 odds, odds payloads and whether the team ratings were found. It stores nothing and exits with status 1 when any expected structure is missing.

### Workflow

1. **Run Scraper**: `python -m scraping.soccer_rating_cli`
2. **Verify**: Check `data/soccer-rating/match_odds_development.csv` (or the dated snapshot when using `--separate-snapshots`) for new data.
3. **Analyze**: Run `python analyze.py` to generate the report.

## Usage & Structure

```bash
# Analyze CL and EL, and the Conference League when its files are present - default
python analyze.py

# Analyze only Champions League
python analyze.py --cl

# Analyze only Europa League
python analyze.py --el

# Analyze only Conference League
python analyze.py --ecl

# Analyze with Polish Excel formatting (; separator, comma decimal)
python analyze.py --excel-pl
```

### Analyzer Arguments

- `--sr-only`: Run analysis independent of 'The Analyst' data (Market Signals only).
- `--input-file PATH`: Specify a snapshot file for SR-only mode or the results page (e.g., specific date). Team names and lineups are read from `club_meta.csv` and `today_matches.csv` in the same folder, so keep a scraper run's files together (`soccer-rating --output-dir`).
- `--output-dir PATH`: Custom directory for analysis reports, created if missing.
- `--page PATH`: Write the results page instead of the CSV reports (see [Results Page](#results-page)).

**Generated Reports:**

- `cl_recommendations.csv` – Results for Champions League.
- `el_recommendations.csv` – Results for Europa League.
- `ecl_recommendations.csv` – Results for Conference League.
- `sr_analysis_report_YYYY-MM-DD.csv` – Results for SR-Only mode (the date comes from the input snapshot name; without a dated input the file is `sr_analysis_report.csv`).

### Results Page

```bash
python analyze.py --page recommendations/index.html --input-file data/soccer-rating/match_odds_development_2026-11-16.csv
```

`--page PATH` writes one static HTML file (in Polish) with two tabs, and no CSV reports; the folder is created if missing. The page needs no server: open it in a browser. Like every `*.html` outside the package, it is gitignored.

- **Soccer-rating tab**: the snapshot named with `--input-file`, or `data/soccer-rating/match_odds_development.csv` when none is named, with `club_meta.csv` and `today_matches.csv` from the same folder for team names and kickoff times.
- **Cups tab**: the cups chosen with `--cl`, `--el` and `--ecl`, or the default set of the standard mode; each cup reads its The Analyst fixtures and predicted table, and soccer-rating odds and kickoff times from `data/soccer-rating/match_odds_development.csv` when that file is present.

Kickoff, scrape and generation times are shown in Polish time (`Europe/Warsaw`). Missing data shows on the page instead of failing the run: without the cumulative soccer-rating file the soccer-rating tab says there are no matches, a cup without its fixtures or table file shows a no-data notice with a link to The Analyst, and a cup without soccer-rating data has no odds or kickoff times. A named `--input-file` that does not exist, or an input file that cannot be read, stops the run with `ERROR: ...` (exit code 1), as the reports do. The run prints the input warnings and one line, `SUCCESS: Saved results page to: <path> (<n> + <m> matches)`, with the match counts of the two tabs. `--page` cannot be combined with `--sr-only`.

## Data Integrity Requirements

For correct operation, input CSV files must meet these standards:

- **Encoding**: UTF-8 or UTF-8 with BOM.
- **Separator**: Automatic detection (handles `;` or `,`).
- **Numbers**: Handles both comma and dot decimal separators.
- **Audit**: Every run prints a data integrity report checking stage monotonicity (`WINNER ≤ FINAL ≤ ... ≤ QF`) and Top 24 consistency.

## Troubleshooting & Console Logs

In standard mode every run prints a data integrity report for each cup's predicted table, headed `--- CHAMPIONS LEAGUE DATA INTEGRITY REPORT ---` (or `EUROPA LEAGUE`). Here is how to interpret the output:

- **`OK: Monotonicity (W<=F<=SF<=Q)`** and **`OK: Top 24 Consistency`**: Data is mathematically consistent.
- **`WARNING: INCONSISTENT TOP 24 (Sum > 100% for N teams)`**: The source data has rows where P(Top 8) + P(9-24) > 100%. The script uses the Anomaly Handling logic (maximum value) for these teams.
- **`WARNING: MONOTONICITY VIOLATIONS (N teams)`**: A team has a higher probability of reaching a later stage than an earlier one (e.g., `FINAL% > SF%`). The values are used as they are; only the Knockout Floor above applies.
- **`WARNING: VALUES OUT OF RANGE [0, 100] DETECTED!`**: A stage probability lies outside 0-100; it is clipped to that range.
- **`ERROR: Missing teams in cl_table: [...]`**: A team name in the fixtures file doesn't match the names in the predicted table, and the run stops with exit code 1. Fix this using the `NAME_FIX` dictionary (see below).
- **`WARNING: today_matches.csv not found: running without lineups`**: The soccer-rating odds are used without the lineup term.
- **`WARNING: club_meta.csv not found: team ids cannot be mapped, running without soccer-rating data`**: The cup is analysed from The Analyst data alone.
- **`ERROR: Input file not found: <path>`** (SR-only): the file named with `--input-file`, or `data/soccer-rating/match_odds_development.csv` when none is named, does not exist; the run stops with exit code 1.

## Customizing Team Names (NAME_FIX)

Team names often differ between lists (e.g., "Real" vs "Real Madrid"). To fix this without editing the raw CSV files, modify the `NAME_FIX` dictionary in `src/analyzer/names.py`:

```python
NAME_FIX: Dict[str, str] = {
    "your source name": "target name in table",
    "real": "real madrid",
    "nottm forest": "nottingham forest",
}
```

The script automatically converts names to lowercase and removes special characters for more robust matching.

## Data Preparation (Manual Alignment)

If you are using the `_example` files as templates:

1. Open the `_example.csv` file in a text editor or Excel.
2. Replace the placeholder names (Team A, Team B) with actual team names from the source website.
3. Ensure numerical values use consistent formatting (the script auto-detects either `.` or `,` as a decimal separator, but consistency per file is recommended).
4. Save the file without the `_example` suffix (e.g., as `cl_fixtures.csv`) in the correct folder for the script to detect it.

## Future Work

### Automation & Independence

- **Own Monte Carlo Simulation**: Developing an internal simulator to become independent of external providers and have full control over league phase scenarios.
- **TheAnalyst Scraper**: Automating data collection from Opta/The Analyst to eliminate the manual copy-paste process.

### Script Calibration

- Compare pre-round predictions vs. real outcomes to tune motivation weights.
- Empirical verification of `LOCKED` and `OUT` thresholds based on historical round 8 behavior.
- Calculate "expected rank / expected points" vs. actual results.

### Squad Rotation Modeling

- **Weighted Recency**: Using EMA (Exponential Moving Average) of minutes played (last month > season start).
- **Economic Approach**: Comparing the market value of the starting XI vs. the total squad value (Ratio < 0.60 = heavy rotation).

### Notifications

- Real-time notification system for detected betting opportunities.

## Development

```bash
uv sync --locked                     # runtime and development dependencies
uv run python -m scripts.gate        # every code check CI runs, with a summary
git config core.hooksPath .githooks  # once per checkout: commit message and staged-file checks
```

The gate (`scripts/gate.py`) runs lint and formatting (ruff), type checking (mypy), layer boundaries (import-linter,
contracts in `pyproject.toml`), dead code (vulture), duplicated code (pylint), the unit tests with the coverage
threshold (pytest) and a scan of tracked files for em dashes, stray emoji and excluded paths. It runs every step even
after a failure and exits 1 if any failed.

The commit hooks check Conventional Commit subjects, attribution trailers, em dashes and emoji, and run ruff on staged Python files. Two optional per-checkout settings stay out of the repository: `hooks.excludedPaths` (file names and `directory/` entries that must never be committed) and `hooks.ownerIdentities` (the only author and committer e-mails `pre-commit` accepts). See `scripts/git_hooks.py`.

The same checks run in GitHub Actions on every push to `main`, on pull requests and weekly.

## Disclaimer

This project is an analytical tool for fantasy football and research. It does not guarantee results and is not financial or betting advice. Data belongs to its respective providers (The Analyst / Opta, Soccer-rating); check their terms of use before collecting or redistributing it.

## License

[MIT](LICENSE) © 2026 visvaya
