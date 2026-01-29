# UEFA Cups Fantasy Predictor & Analyzer (CL & EL)

System for predicting results, assessing motivation, and rotation risk in European competitions (Champions League and Europa League) under the new league phase format. The system is based on probabilistic forecasts from Monte Carlo simulations ("The Analyst" data).

> **Note**: This tool is specifically designed for analyzing the **final round** of the league phase, where motivation and rotation risks are most critical. For a deeper dive into the mathematical logic used, see [interpretation.md](interpretation.md).

## Key Features

- **Status Model (UEFA Art. 17 Compliance)**: Classifies clubs based on mathematical progression chances:
  - `OUT`: No chance for Top 24.
  - `LOCKED_DIRECT_RO16`: Guaranteed spot in the top eight (direct qualification).
  - `LOCKED_PLAYOFFS`: Guaranteed progression, but no chance for Top 8 (play-offs).
  - `IN_PLAY`: Fight for key positions continues.
- **Motivation Index (Mot)**: Proprietary *Pressure Vector* algorithm assessing "win pressure". Peak values occur at qualification thresholds (spots 8/9 and 24/25).
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
    - Ensure the column headers match the requirements below.

## Data Sources

The script relies on data exported from **The Analyst** (Opta):

- **CL Table**: [theanalyst.com/competition/uefa-champions-league/table](https://theanalyst.com/competition/uefa-champions-league/table) (use 'Predicted' tab)
- **CL Fixtures**: [theanalyst.com/competition/uefa-champions-league/fixtures](https://theanalyst.com/competition/uefa-champions-league/fixtures)
- **EL Table**: [theanalyst.com/competition/uefa-europa-league/table](https://theanalyst.com/competition/uefa-europa-league/table) (use 'Predicted' tab)
- **EL Fixtures**: [theanalyst.com/competition/uefa-europa-league/fixtures](https://theanalyst.com/competition/uefa-europa-league/fixtures)

## Data Interpretation Logic

The system interprets source data (*Predicted Table*) as a set of probabilities, not rigid points.

### Key Input Parameters

- **LAST 16%**: Probability of occupying places 1–8 (direct qualification).
- **KO P/O% / KPO**: Probability of occupying places 9–24 (participation in play-offs).
- **QF%**: P(quarter-final) – used as a safe *floor* for progression chances.

### Calculating P(Top 24) — "Chance of Continuing Play"

The algorithm uses a hybrid approach to maintain mathematical consistency:

1. **Disjoint Check**: If `LAST 16% + KO P/O%` is less than or equal to 100%, we assume they represent separate finishing positions (1-8 and 9-24) and **sum them**.
2. **Anomaly Handling**: If the sum exceeds 100%, the data is inconsistent. In this case, we avoid the sum and take the **maximum** value from all available progress columns (`LAST 16`, `KPO`, `QF`, etc.).
3. **Knockout Floor**: Finally, we apply a "sanity floor": `P(Top 24)` must be **≥ QF%**. This handles cases where a team's reported chance of winning/reaching late stages is higher than the reported chance of surviving the league phase.

## Report Columns Explained

| Column | Description |
| :--- | :--- |
| **Team / Opp** | Analyzed team and its opponent. |
| **Win%** | Probability of winning. |
| **EV** | *Expected Value* – expected points (3*Win% + 1*Draw%). |
| **Mot** | *Motivation Index* (0-100) – internal pressure for result. |
| **Risk** | *Rotation Risk* (1.0 - 2.3) – higher means greater risk of a backup squad. |
| **Val** | **Value Index (0-140)** – main ranking parameter. Consolidates sporting strength, team motivation, and rival's lack of motivation. |
| **OpMot / OpStatus** | Monitoring opponent's motivation and status. |
| **Recommendation** | Text recommendation (e.g., 🟢 STRONG BUY vs 🟠 CAUTION). |

## Usage & Structure

### Requirements

- Python 3.12+
- `pip install pandas numpy`

### Files & Execution

The system is consolidated into a single script supporting flags:

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

**Generated Reports:**

- `cl_recommendations.csv` — Results for Champions League.
- `el_recommendations.csv` — Results for Europa League.

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
