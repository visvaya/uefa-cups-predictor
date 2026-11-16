# UEFA Cups Fantasy Predictor & Analyzer (CL & EL)

[![CI](https://github.com/visvaya/uefa-cups-predictor/actions/workflows/ci.yml/badge.svg)](https://github.com/visvaya/uefa-cups-predictor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Status:** maintained personal tool, run by hand during the UEFA league phase. There are no releases; `main` is the supported version. Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md); security reports: [SECURITY.md](SECURITY.md).

System for predicting results, assessing motivation, and rotation risk in European competitions (Champions League and Europa League) under the new league phase format. The system is based on probabilistic forecasts from Monte Carlo simulations ("The Analyst" data) and odds data from Soccer-rating. It is specifically designed for analyzing the final rounds of the league phase.

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

Odds (Soccer-rating) data:

- **Soccer-rating**: [https://www.soccer-rating.com/today-prediction](https://www.soccer-rating.com/today-prediction)

## Data Interpretation Logic

The system interprets source data (*Predicted Table*) as a set of probabilities, not rigid points.

### Key Input Parameters

- **LAST 16%**: Probability of occupying places 1–8 (direct qualification).
- **KO P/O% / KPO**: Probability of occupying places 9–24 (participation in play-offs).
- **QF%**: P(quarter-final) – used as a safe *floor* for progression chances.

### Calculating P(Top 24) – "Chance of Continuing Play"

The algorithm uses a hybrid approach to maintain mathematical consistency:

1. **Disjoint Check**: If `LAST 16% + KO P/O%` is less than or equal to 100%, we assume they represent separate finishing positions (1-8 and 9-24) and **sum them**.
2. **Anomaly Handling**: If the sum exceeds 100%, the data is inconsistent. In this case, we avoid the sum and take the **maximum** value from all available progress columns (`LAST 16`, `KPO`, `QF`, etc.).
3. **Knockout Floor**: Finally, we apply a "sanity floor": `P(Top 24)` must be **≥ QF%**. This handles cases where a team's reported chance of winning/reaching late stages is higher than the reported chance of surviving the league phase.

### Report Columns (Main Mode)

| Column | Description |
| :--- | :--- |
| **team / opp** | Analyzed team and its opponent. |
| **teamWinProb%** | Probability of winning (from predicted table). |
| **teamMot** | *Motivation Index* (0-100) – internal pressure for result. |
| **teamRotRisk** | *Rotation Risk* (1.0 - 2.3) – higher means greater risk of squad rotation. Raised by 10 % for both teams of a match with strange odds (see Soccer-rating Logic). |
| **teamStatus / oppStatus** | Progress status (`IN_PLAY`, `LOCKED`, `OUT`). |
| **expertScore** | **Synthetic Strength Signal**. Aggregate score from market, ratings, and lineups. If > 0, model favors this team. |
| **srEdge** | **Probability Edge**: `FairProb - MarketCloseProb`. Positive = Value found by SR model. |
| **srCompleteness** | **Signal Quality (0.0 - 1.0)**. 1.0 = High Confidence. |
| **srDropping** | **Market Steam**. Positive = odds are dropping (market confirmation). |
| **strangeOdds** | Market anomaly detection (>30), suggests insider info or sudden squad changes. |
| **recommendation** | Final advice (Strong Buy, Consider, Neutral, Caution, Avoid). |
| **reason** | List of key factors generating the advice. |

### SR-Only Mode

| Column | Description |
| :--- | :--- |
| **homeTeam / awayTeam** | Match participants. |
| **pick** | **Recommended Outcome**: `1` (Home), `X` (Draw), `2` (Away). |
| **expertScore** | Match signal strength from the picked side's view: > 0 favours it (for `X`, the home view). |
| **recommendation** | Advice based purely on market gaps and steam. |

### Understanding the 'Reason' Column

- **Status/Risk (Absolute Priority)**:
  - `Out of contention`: Team cannot reach Top 24. Always `🔴 AVOID`.
  - `Status LOCKED...`: Team has secured its spot. Always `🟠 CAUTION` due to high rotation risk.
  - `High rotation risk`: `teamRotRisk` >= 1.39. Always `🟠 CAUTION`.
- **Value/Signal**:
  - `High Value / Good Value`: High mathematical advantage based on motivation and win prob.
  - `Strong Expert Signal`: `|expertScore| > 1.50`, a strong model signal for either side; `Positive Signal` is the same for `|expertScore| > 0.50`. Apart from the `Sure Bet Pattern` and SR-only `X` picks, a row reaches `🟡 CONSIDER` or `🟢 STRONG BUY` only with a positive score (this row's team favoured).
- **Market Signals**:
  - `Sure Bet Pattern`: Unique combination of low odds (`<2.00`), Value (`Fair<2.20`) and strong Steam (`>0.03`).
  - `Steam (+)`: Market odds are dropping for this team.
  - `(Risk: Rising Odds)`: Mathematical value is high, but the market is betting against the team. Recommendation downgraded.

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

- `--limit N`: Process only N matches (useful for quick testing).
- `--delay N`: Set delay between requests (default 1.5s).
- `--local`: Use local HTML files (for debugging without network).
- `--output-dir PATH`: Custom output directory (default `data/soccer-rating`).
- `--all-leagues`: Fetch matches from ALL leagues (default: only CL & EL).
- `--separate-snapshots`: Save snapshot to a separate file (e.g., `match_odds_development_YYYY-MM-DD.csv`) instead of merging.
- `--min-start N`: Process matches starting at least N minutes from now.
- `--max-start N`: Process matches starting at most N minutes from now. Kickoff times are read in the machine's local timezone; a kickoff more than 12 hours in the past counts as the next day's fixture.
- `--skip-cups`: Skip matches whose league code contains `CUP` (e.g. `FACUP`); useful together with `--all-leagues`.

National team fixtures are skipped with a warning; only club matches are supported.

### Workflow

1. **Run Scraper**: `python -m scraping.soccer_rating_cli`
2. **Verify**: Check `data/soccer-rating/match_odds_development.csv` (or the dated snapshot when using `--separate-snapshots`) for new data.
3. **Analyze**: Run `python analyze.py` to generate the report.

## Usage & Structure

```bash
# Analyze both cups (CL and EL) - default
python analyze.py

# Analyze only Champions League
python analyze.py --cl

# Analyze only Europa League
python analyze.py --el

# Analyze with Polish Excel formatting (; separator, comma decimal)
python analyze.py --excel-pl
```

### Analyzer Arguments

- `--sr-only`: Run analysis independent of 'The Analyst' data (Market Signals only).
- `--input-file PATH`: Specify a snapshot file for SR-only mode (e.g., specific date).
- `--output-dir PATH`: Custom directory for analysis reports.

**Generated Reports:**

- `cl_recommendations.csv` – Results for Champions League.
- `el_recommendations.csv` – Results for Europa League.
- `sr_analysis_report_YYYY-MM-DD.csv` – Results for SR-Only mode (the date comes from the input snapshot name; without a dated input the file is `sr_analysis_report.csv`).

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
