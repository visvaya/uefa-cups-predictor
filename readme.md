# UEFA Cups Fantasy Predictor & Analyzer (CL & EL)

System for predicting results, assessing motivation, and rotation risk in European competitions (Champions League and Europa League) under the new league phase format. The system is based on probabilistic forecasts from Monte Carlo simulations ("The Analyst" data).

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

## Data Interpretation Logic

The system interprets source data (*Predicted Table*) as a set of probabilities, not rigid points.

### Key Input Parameters

- **LAST 16%**: Probability of occupying places 1–8 (direct qualification).
- **KO P/O% / KPO**: Probability of occupying places 9–24 (participation in play-offs).
- **QF%**: P(quarter-final) – used as a safe *floor* for progression chances.

### Calculating P(Top 24) — "Chance of Continuing Play"

The algorithm uses a hybrid approach to maintain mathematical consistency:

1. **Disjoint Model**: If `LAST 16% + KPO% ≤ 100%`, the chance of Top 24 is the sum of these two values.
2. **Anomaly Correction**: For inconsistent data (`sum > 100%`), the system takes a conservative estimate `max(LAST16, KPO, QF)`.
3. **Stage Hierarchy**: We guarantee that `P(Top 24) ≥ QF%`, eliminating transcription and model errors.

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
