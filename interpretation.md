# Data from The Analyst ("Predicted" table) – Logic Interpretation

## 1) Data Nature

These are **probabilistic forecasts** based on simulations (Monte Carlo), not a mathematical table or simple classification:

- `XPOS`, `XPTS` are the predicted average final position and predicted points (expected points).
- Percentage columns represent the **probability of reaching a given stage**.

## 2) Key Column Definitions (League Phase)

| Column | Meaning |
| --- | --- |
| **LEAGUE%** | P(1st place in the league phase) |
| **LAST 16%** | P(positions 1-8) = direct qualification to the round of 16 |
| **KO P/0% / KPO** | P(positions 9-24) = participation in the knockout phase play-offs |
| **QF%** | P(quarter-final) via any path |

### Mathematical Relationships

- **P(Top 24)** = `LAST 16%` + `KO P/0% / KPO`
  - Relationship is theoretically correct assuming disjoint positions (Top 8 vs 9–24).
  - **Note:** In practice, downloaded data often violates this property (`LAST 16 + KO > 100`), requiring corrections.
- **P(Elimination)** = 100% − P(Top 24)
  - This is the "**implied OUT%**" and makes mathematical sense only if `LAST 16 + KO ≤ 100`.
  - In inconsistent rows (e.g., sum > 100), simple difference would lead to illogical negative values.
- **QF% vs LAST 16%**: no fixed relationship (depends on team strength).

## 3) Logical Verification

```text
Liverpool:   91.97 + 8.03  = 100.00% → P(Elim) ≈ 0%
København:  2.28 + 15.38  = 17.66%  → P(Elim) ≈ 82%
```

### LAST 16% Semantics Test as P(Top 8)

```text
Nottm Forest: LAST 16% = 0.01%, QF% = 39.05%
```

→ QF% > LAST 16% is a **strong hint/argument** that `LAST 16%` refers to the chance of reaching the Top 8 specifically, and not to reaching the Round of 16 via any path (which would have to be ≥ QF%). Although data can be inconsistent, this logic test (assuming QF ⊂ Round of 16) remains the most consistent interpretation model.

## 4) Data Anomalies (Sums > 100%)

**Examples from CL:**

```text
Leverkusen:   93.73 + 38.92 = 132.65%
Galatasaray:  99.86 + 32.57 = 132.43%
```

**Examples from EL:**

```text
Fenerbahce:   100.00 + 61.17 = 161.17%
Lille:        98.91 + 49.85  = 148.76%
```

**Interpretation (checked 2026-11-17 on the January 2026 CL and EL tables):** the column sums explain these rows. `KO P/0%` sums to exactly 1600 % over the table (16 play-off places), and `LAST 16%` sums to exactly 800 % (8 direct places) over the rows where `LAST 16% + KO P/0% = 100`. So in those rows `LAST 16%` is P(top 8), every other row has no top-8 chance, and in those other rows `LAST 16%` is the chance of reaching the last 16 through the play-off (Leverkusen 38.92 / 93.73 ≈ 0.42, Fenerbahce 61.17 / 100). The Analyst did not define the columns in writing; its current predictions page (checked 2026-11-17) shows separate "Top 8", "9–24" and "L16" columns instead.

**Technical Solution:**

- A row is **direct** when `LAST16 + KO` is 100 (within 0.01 for rounding) or `QF > LAST16`.
- When the table's sums match that layout (`Σ KO ≈ 1600` and `Σ LAST16 of the direct rows ≈ 800`, within 0.5 percentage points): `P(top 8) = LAST16` in direct rows and 0 elsewhere, and `Top24 = P(top 8) + KO`. The integrity report says so.
- Otherwise the meaning of `LAST 16%` cannot be told from the table, and the earlier approximation stays: `P(top 8) = LAST16`; `Top24 = LAST16 + KO` when that is at most 100.01, else the largest progress value (`max(LAST16, KO, QF, SF, FINAL, WINNER)`, a cautious floor estimate). The integrity report warns when such a table has sums above 100.
- **Safe Stage Heuristic**: in both cases `P(Top 24)` is at least `QF%` (you cannot reach the quarter-final without being in the Top 24) and is capped to `[0, 100]`.

## 5) P(Top 24) Calculation Logic

The system estimates the chance of continuing play using the following logic:

1. **Layout Check**: When the column sums show the January 2026 layout (see section 4), `P(Top 24) = P(top 8) + KO P/0%`, with `P(top 8)` taken from `LAST 16%` in direct rows only.
2. **Approximation**: Otherwise `LAST 16% + KO P/0%` is summed when it is at most 100.01% (rounding), and the **maximum** progress value is taken when it is larger.
3. **Knockout Floor**: Finally, we apply a "sanity floor": `P(Top 24)` must be **≥ QF%**. This handles cases where a team's reported chance of winning/reaching late stages is higher than the reported chance of surviving the league phase.

---

## UEFA League Phase Rules – Context

### 1) Format

The league phase is a single table for **36 teams**. Each plays 8 matches (CL/EL).

### 2) Status after League Phase

| Position | Status | Consequence |
| --- | --- | --- |
| **1-8** | Direct qualification to Rd of 16 | Bye in February, certain March play |
| **9-24** | Qualification to Play-offs | Additional two-legged tie in February |
| **25-36** | Eliminated from competition | Players no longer score points |

### 3) Motivation

| Fighting for... | Why it matters? |
| --- | --- |
| **Top 8** | Avoiding risky play-offs |
| **Top 16** | Seeding in play-offs (9–16 seeded vs 17–24 unseeded) |
| **Top 24** | Survival in the tournament |

### 4) Rotation Risk

In standard mode (the CL/EL reports; SR-only mode has no rotation risk), the analyzer turns each team's status and motivation into a rotation risk (`teamRotRisk`, 1.0 to 2.3; at 1.39 or above the row becomes CAUTION, except for an eliminated (OUT) team, which is always AVOID). A LOCKED team is CAUTION by its status whatever its rotation risk; the seeding fight (16/17) raises a locked play-off team's motivation, so its shown risk can be below 1.39. When the soccer-rating market adjustment for a match is strange (|AO| above 30), both teams' rotation risk is multiplied by `STRANGE_ODDS_ROTATION_FACTOR` (1.10, in `src/analyzer/config.py`) and capped at 2.3, because such an adjustment often reflects hidden squad news and does not say which side it concerns. The raised risk also lowers the team's value index. The factor is a conservative choice, not a calibrated one: the model has not been fitted to match outcomes.
