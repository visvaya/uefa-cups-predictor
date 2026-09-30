# UEFA Cups Fantasy Predictor & Analyzer (CL & EL)

[![CI](https://github.com/visvaya/uefa-cups-predictor/actions/workflows/ci.yml/badge.svg)](https://github.com/visvaya/uefa-cups-predictor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

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
uv sync --locked --no-dev   # creates .venv with the locked runtime dependencies
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

Alternatively, prefix commands with `uv run` instead of activating the environment.

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
| **teamRotRisk** | *Rotation Risk* (1.0 - 2.3) – higher means greater risk of squad rotation. |
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
| **expertScore** | Global match signal strength. |
| **recommendation** | Advice based purely on market gaps and steam. |

### Understanding the 'Reason' Column

- **Status/Risk (Absolute Priority)**:
  - `Out of contention`: Team cannot reach Top 24. Always `🔴 AVOID`.
  - `Status LOCKED...`: Team has secured its spot. Always `🟠 CAUTION` due to high rotation risk.
  - `High rotation risk`: `teamRotRisk` >= 1.39. Always `🟠 CAUTION`.
- **Value/Signal**:
  - `High Val / Good Val`: High mathematical advantage based on motivation and win prob.
  - `Strong Signal`: `expertScore > 1.50` indicating an elite betting opportunity.
- **Market Signals**:
  - `Sure Bet Pattern`: Unique combination of low odds (`<2.00`), Value (`Fair<2.20`) and strong Steam (`>0.03`).
  - `Steam (+)`: Market odds are dropping for this team.
  - `(Risk: Rising Odds)`: Mathematical value is high, but the market is betting against the team. Recommendation downgraded.

## Soccer-rating Logic

Odds are used as a **dynamic market signal** to enrich the static predictions from The Analyst. It represents the "live" consensus of bookmakers and professional bettors.

1. **Market Consistency**: If model's favorite also has dropping odds (Steam), motivation and confidence are boosted.
2. **Strange Odds Anomaly**: If a market rating adjustment is significant (>30), `RotRisk` is automatically increased to account for possible hidden factors (injuries, internal rotation).

## Scraping Data

To update the Soccer-rating data (odds, steam, ratings), run:

```bash
python -m src.scraping.soccer_rating_cli
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

1. **Run Scraper**: `python -m src.scraping.soccer_rating_cli`
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

The script performs a "Data Audit" during every run. Here is how to interpret the output:

- **`[AUDIT] CL: OK`**: Data is mathematically consistent.
- **`[AUDIT] CL: INCONSISTENT (Sums > 100%)`**: The source data has rows where P(Top 8) + P(9-24) > 100%. The script uses the Anomaly Handling logic (maximum value) for these teams.
- **`[AUDIT] CL: STAGE VIOLATION`**: A team has a higher probability of reaching a later stage than an earlier one (e.g., `FINAL% > SF%`). The script applies the "Safe Stage Heuristic" to fix this.
- **`ERROR: Team 'X' not found in predicted table`**: A team name in the fixtures file doesn't match the names in the predicted table. Fix this using the `NAME_FIX` dictionary (see below).

## Customizing Team Names (NAME_FIX)

Team names often differ between lists (e.g., "Real" vs "Real Madrid"). To fix this without editing the raw CSV files, modify the `NAME_FIX` dictionary at the top of `analyze.py`:

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

Known technical shortcomings are tracked in [docs/tech-debt.md](docs/tech-debt.md).

## Development

```bash
uv sync --locked       # runtime and development dependencies
pytest                 # unit tests
ruff check .           # lint
ruff format --check .  # formatting
mypy                   # type checking (paths configured in pyproject.toml)
python .agents/sync-skills.py --check  # shared agent skills are in sync
```

The same checks run in GitHub Actions on every push to `main` and on pull requests.

## Disclaimer

This project is an analytical tool for fantasy football and research. It does not guarantee results and is not financial or betting advice. Data belongs to its respective providers (The Analyst / Opta, Soccer-rating); check their terms of use before collecting or redistributing it.

## License

[MIT](LICENSE) © 2026 visvaya
