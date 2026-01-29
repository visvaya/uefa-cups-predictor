# Data from The Analyst ("Predicted" table) — Logic Interpretation

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

**Interpretation:** In some rows, LAST 16% and KO P/0% do not behave as disjoint probabilities of occupying places 1–8 vs 9–24. The cause of inconsistency is unknown (could be a model error from The Analyst, different column definition, or simulation artifact). In these rows, we treat the data as inconsistent and fall back to heuristics. If, after verification with a screenshot / double-entry, LAST16+KO > 100 still occurs, we treat it as source inconsistency (The Analyst).

**Technical Solution:**

- If `LAST16 + KO ≤ 100`: `Top24 = LAST16 + KO`
- If `LAST16 + KO > 100` (anomaly): **we do not use the sum**, but take a conservative floor `Top24 = max(LAST16, KO, QF, SF, FINAL, WINNER)`. Then we cap the result to `[0, 100]`. This is an **cautious floor-estimate**, not "anomaly ⇒ 100%".

**Note:** This is NOT a mathematical lower bound for P(Top 24), but a **capped floor estimate** ensuring consistency with the stage hierarchy (`WINNER ⊂ FINAL ⊂ SF ⊂ QF ⊂ TOP 24`).

The actual lower bound for inconsistent rows is `max(LAST16, KO)`, but for practical purposes (fantasy), we use the capped estimate = 100%.

- **Safe Stage Heuristic**: Even if data is inconsistent, the system ensures that `P(Top 24)` is at least equal to `QF%` (since you cannot reach the quarter-final without being in the Top 24).

## 5) P(Top 24) Calculation Logic

The system estimates the chance of continuing play using the following logic:

1. **Disjoint Check**: If `LAST 16% + KO P/O%` is less than or equal to 100%, we assume they represent separate finishing positions (1-8 and 9-24) and **sum them**.
2. **Anomaly Handling**: If the sum exceeds 100%, the data is inconsistent. In this case, we avoid the sum and take the **maximum** value from all available progress columns (`LAST 16`, `KPO`, `QF`, etc.).
3. **Knockout Floor**: Finally, we apply a "sanity floor": `P(Top 24)` must be **≥ QF%**. This handles cases where a team's reported chance of winning/reaching late stages is higher than the reported chance of surviving the league phase.

---

## UEFA League Phase Rules — Context

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
