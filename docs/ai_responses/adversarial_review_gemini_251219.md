---
layout: default
title: Adversarial Review - Gemini (Dec 19) 
parent: AI Critiques & Reports
---
# Adversarial Review & Remediation Report

**Project:** MaxPreps Baseball Projection System

**Date:** December 19, 2025

**Review Type:** Codebase & Statistical Methodology Analysis

---

## 1. Executive Summary

An adversarial review was conducted to challenge the "V1.1" state of the projection system. The review acted as a "Cynical Sabermetrician," systematically identifying logic errors, statistical overfitting, and code defects.

**Key Outcome:** The review identified **critical architectural divergences** where the "Power Rankings" and "Game Simulator" utilized contradictory mathematical logic. It also flagged **"double-counting" of elite bias**, where powerhouse teams received overlapping artificial boosts.

Following remediation, the system now features a **Unified Logic Core**, centralized configuration, and a stabilized simulation engine that balances empirical data with realistic game constraints.

---

## 2. Findings & Resolution Matrix

| Severity | Finding | Description | Status | Resolution |
| --- | --- | --- | --- | --- |
| **Critical** | **Logic Divergence** | Rankings used "Top 9 Weighted" stats; Simulator used "Top 10 Unweighted." Users saw one metric, but the engine predicted with another. | **FIXED** | Created `calculate_team_strength()` as the "Single Source of Truth" for both modules. |
| **Critical** | **Double-Counting Bias** | Elite teams received 3 boosts: Aging Curves + Better Backfill + **Manual Stat Bumps**. This artificially inflated floors. | **FIXED** | **Removed manual stat bumps.** Logic now relies solely on statistical percentile ladders to model depth. |
| **High** | **Simulator Explosion** | Hardcoded baseline (6.0 runs) + Low Floors (0.1) caused weak teams to yield infinite multipliers (e.g., 32-run games). | **TUNED** | Adjusted floors from 0.1 → 0.30 to cap maximum multipliers at ~1.8x. Retained conservative 6.0 baseline. |
| **Medium** | **Uncalibrated Weights** | Weights (1.10 for Seniors) appeared arbitrary ("Magic Numbers"). | **CLOSED** | **Validated.** Backtesting documentation proved these specific weights improved correlation from 0.74 to 0.77. |
| **Code** | **Config Sprawl** | Constants (`TOP_N`, `LEAGUE_BASE`) defined in 3 different files. | **FIXED** | Centralized all "tuning knobs" into `src/utils/config.py`. |

---

## 3. Detailed Remediation Steps

### A. Architectural Unification (The "Single Source of Truth")

We refactored `src/workflows/team_strength_analysis.py` to export a standardized calculation engine.

* **Before:** Simulator re-calculated strength independently, often ignoring seniority weights defined elsewhere.
* **After:** Simulator imports `calculate_team_strength()`. If the definition of a "good team" changes in the rankings, the simulation engine automatically adapts.

### B. Removal of "Thumb on the Scale"

We audited `src/workflows/roster_prediction.py` and removed manual overrides (specifically lines 233-235 and 257-259).

* **Change:** Elite generic players no longer receive manual stat overwrites (e.g., `if hits < 5: hits = 8`).
* **Impact:** Program strength is now modeled organically through **Percentile Ladders** (Elite teams draft from the 50th percentile pool; others from the 30th).

### C. Simulation Tuning (The "Goldilocks" Fix)

We performed a diagnostic on the run environment and adjusted `src/workflows/game_simulator.py`.

1. **Discovery:** The actual history showed a run environment of **8.01 runs/game**.
2. **The Trap:** Plugging 8.01 into the model broke the "Mercy Rule" reality, creating 32-3 scores against weak pitching due to aggressive multipliers.
3. **The Fix:**
* **Baseline:** Kept conservative `6.0` (Simulates "Competitive Context").
* **Floor:** Raised from `0.1` → `0.30`.
* **Result:** Prevented mathematical explosions. Weak teams are punished, but games stay within baseball reality (e.g., 10-2, not 35-0).



### D. Configuration Consolidation

We created a `MODEL_CONFIG` dictionary in `src/utils/config.py`.

* **Centralized:** `TOP_N_BATTERS`, `WEIGHT_SENIOR`, `LEAGUE_BASE_RUNS`, and `MIN_INDEX_FLOOR`.
* **Benefit:** Future tuning requires editing only **one file**, ensuring consistency across the pipeline.

---

## 4. Final Validation State

* **Statistical Integrity:** The "Seniority Boost" (1.10x) is statistically validated by 2025 backtesting results (Correlation 0.776).
* **Code Quality:** No magic numbers remain in workflow files. All constants are named and centralized.
* **Simulation Reality:** The simulator produces "Lock/Solid/Toss-up" confidence ratings that align with the user-facing Power Rankings.

**Status:** The codebase is now considered **Stable (V1.2)** and ready for production deployment.