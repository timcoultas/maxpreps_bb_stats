---
layout: default
title: Adversarial Review - Colorado High School Baseball Projection System - Claude (Dec 16) 
parent: AI Critiques & Reports
---
# Adversarial Review - Colorado High School Baseball Projection System

**Reviewer Role:** Cynical Sabermetrician, Senior Data Engineer, Python Expert  
**Review Date:** December 16, 2025  
**Files Reviewed:** aggregated_stats.csv, development_multipliers.csv, generic_players.csv, 2026_roster_prediction.csv, team_strength_rankings.csv, and 8 source code modules

---

## Executive Summary

This adversarial review examined the Colorado High School Baseball Projection System against established sabermetric research and software engineering best practices. The system demonstrates solid foundational design with appropriate use of Bill James' Runs Created formula, Negative Binomial distribution for game simulation (validated by a variance/mean ratio of 13.4), and a hierarchical multiplier lookup strategy that correctly prioritizes sample size over specificity.

However, the review identified two **critical issues** that produce incorrect outputs for specific players and teams: (1) NaN propagation in Runs Created calculations causing 4 players with significant hitting stats to receive RC_Score = 0, and (2) generic player profile contamination where 'Batter' templates incorrectly include pitching statistics, creating unexpected impacts on team strength aggregations.

Additionally, the review identified statistical concerns around rare-event multipliers (3B, 2B_P, 3B_P) that likely represent noise rather than development signal, and survivor bias in freshman-to-sophomore transitions showing a 2.25x hits multiplier. The codebase demonstrates good separation of concerns and documentation/implementation alignment following recent fixes from a prior review.

---

## Critical Issues (Must Fix)

### Issue 1: NaN Propagation in Runs Created Calculation

**Location:** `src/models/advanced_ranking.py:calculate_offensive_score()`, lines 45-55

**Problem:** When a player has hits (H > 0) but NaN values in any extra-base hit column (2B, 3B, or HR), the Total Bases calculation produces NaN, which propagates through the RC formula. The `fillna(0)` at the end converts this to RC_Score = 0, incorrectly representing these players as having zero offensive value.

**Impact:** 4 players in the 2026 roster projection have RC_Score = 0 despite having 8-36 projected hits:

| Player | Team | H | 2B | 3B | HR | RC_Score |
|--------|------|---|----|----|-----|----------|
| S. Vital | Denver North | 28.8 | 2.0 | 0.5 | **NaN** | 0.0 ❌ |
| D. Sanudo | Denver North | 36.0 | 4.0 | **NaN** | **NaN** | 0.0 ❌ |
| R. Avalos | Denver North | 20.4 | 2.0 | **NaN** | 2.0 | 0.0 ❌ |
| R. Martinez | Denver North | 8.4 | 1.0 | **NaN** | **NaN** | 0.0 ❌ |

**Recommended Fix:**

```python
# In calculate_offensive_score(), add fillna(0) BEFORE TB calculation:
df['2B'] = df['2B'].fillna(0)
df['3B'] = df['3B'].fillna(0)
df['HR'] = df['HR'].fillna(0)
singles = df['H'] - (df['2B'] + df['3B'] + df['HR'])
```

---

### Issue 2: Generic Batter Profile Contamination with Pitching Stats

**Location:** `src/workflows/profile_generator.py:generate_tiers()` and `generic_players.csv`

**Problem:** Generic 'Batter' profiles include pitching statistics (IP, K, ER, ERA) because the source sophomore population includes two-way players. When these generic batters are used for roster backfill, they carry unexpected pitching values that can contribute to (or detract from) team pitching strength calculations.

**Impact:** 72 players have negative Pitching_Score in the projection, including many Generic Batters:

- Generic Batter (50th %ile) has IP=10.1, ER=11.5, resulting in Pitching_Score = -2.85
- Elite teams receiving 50th percentile batters get penalized on pitching strength
- Floor teams receiving 30th percentile batters get a pitching boost (IP=11.1, ERA=3.71)

**Recommended Fix:**

```python
# In generate_tiers(), clear irrelevant stats by role:
if role == 'Batter':
    for col in ['IP', 'ERA', 'BF', 'K_P', 'ER', 'H_P', 'BB_P', 'APP']:
        profile[col] = 0  # Clear pitching stats for batters
elif role == 'Pitcher':
    for col in ['PA', 'AB', 'H', 'BB', '2B', '3B', 'HR']:
        profile[col] = 0  # Clear batting stats for pitchers
```

---

## Statistical Validity Concerns

### Concern 1: Rare Event Multiplier Noise (3B, 2B_P, 3B_P)

**Methodology:** Development multipliers are calculated as `median(Year_N+1_stat / Year_N_stat)` for players with the stat > 0 in Year_N.

**Problem:** Triples (3B) are rare events in high school baseball. The observed multipliers show unrealistic patterns:

- Freshman→Sophomore: 0.50x (triples cut in half?)
- Sophomore→Junior: 1.00x (no change)
- Junior→Senior: 0.50x (triples cut in half again?)
- Freshman_Y1→Sophomore_Y2: 0.25x (75% reduction?)

These patterns likely represent small-sample noise where players with 1-2 triples in Year N have 0-1 in Year N+1 due to randomness, not development regression.

**Reference:** Tango, Lichtman, Dolphin. "The Book" (2006): Rare events require larger samples to distinguish signal from noise.

**Recommendation:** Apply Bayesian shrinkage toward 1.0 for rare-event stats, or use a minimum sample threshold (e.g., N > 50 instances of the specific stat) before trusting the multiplier.

---

### Concern 2: Freshman Survivor Bias in Hits Multiplier

**Methodology:** The Freshman_Y1→Sophomore_Y2 transition shows a 2.25x multiplier for Hits.

**Problem:** This likely reflects survivor bias: only the most elite freshmen earn varsity playing time in Year 1. These players are not representative of typical freshmen and are already on accelerated development trajectories.

**Evidence:** Sample size is reasonable (N=121), but the population is inherently biased toward elite talent.

**Recommendation:** Cap multipliers at 1.5x maximum, or apply regression toward the Class-only multiplier (Freshman→Sophomore = 2.07x). Consider weighting by inverse volatility.

---

### Concern 3: Negative Pitching Scores in Downstream Calculations

**Finding:** 72 players have Pitching_Score < 0, ranging from -0.03 to -7.72

**Current Handling:** The code correctly applies `clip(lower=0.1)` to Pit_Index in team aggregation, preventing division-by-zero errors.

**Remaining Risk:** Negative pitching scores still reduce team Pitching_dominance totals when aggregating all qualifying pitchers. A team with 5 good pitchers and 2 bad ones will have lower Pitching_dominance than one with 5 good pitchers only.

---

## Code Quality Issues (Should Fix)

### Documentation Mismatch: Team Aggregation Logic

**README states:** "Sum top 9 batters (starting lineup) per team"

**Code implements:** Sum of ALL players with RC_Score > 0.1

Validation shows Rocky Mountain has 152.8 total RC from all batters, matching team_strength output, not 148.7 from top 9.

**Recommendation:** Update README or implement Top-N selection. Current approach (all qualified) is defensible for power rankings but differs from stated methodology.

---

### Unused Volatility Metrics

Development multipliers include Avg_Volatility (standard deviation of ratios) but this metric is not used in downstream projections.

**Opportunity:** Weight projections by inverse volatility, or add confidence intervals to player projections based on multiplier reliability.

---

### High Generic Roster Dependency

31.5% of the projected roster (193 of 613 players) are generic backfill. Some teams rely heavily on generics:

- Cherokee Trail: 13 generic players
- Highlands Ranch: 12 generic players
- Prairie View: 12 generic players

This is a data limitation, not a code issue, but should be noted in output interpretation.

---

## Validation Checks Passed

1. **RC Formula:** No negative values, no values > 100, correlation with raw stats is positive
2. **Pitching-ERA Correlation:** -0.50 (expected negative, within normal range)
3. **Sample Sizes:** All multiplier transitions have N ≥ 40
4. **Generic Players:** All tiers have non-zero offensive contribution (RC 0.55 to 4.02)
5. **NB Distribution:** Variance/Mean ratio = 13.4, validating use of Negative Binomial
6. **Index Protection:** No zero or negative indices in team strength output
7. **Hierarchy Implementation:** 100% of real players use Class (Age-Based) projection
8. **Elite Backfill:** All elite teams receive 50th percentile, others receive 30th
9. **Roster Minimums:** All teams have ≥9 batters and ≥6 pitchers

---

## Future Opportunities

| Opportunity | Data Required | Impact | Priority |
|-------------|---------------|--------|----------|
| Backtesting Framework | Historical game results | High | **1** |
| Dispersion Calibration | Game-level scores | High | **2** |
| Strength of Schedule | Complete league schedules | High | **3** |
| Confidence Intervals | Volatility metrics (available) | Medium | **4** |
| Park Effects | Field dimensions, altitude | Medium | **5** |
| Pitcher Matchups | Rotation data | Medium | **6** |

---

## Appendix: Validation Checks Performed

### Statistical Validation

- [x] RC formula produces expected values for sample players
- [x] Pitching Score formula handles edge cases (correlation with ERA = -0.50)
- [x] Multipliers have reasonable sample sizes (N ≥ 40 for all transitions)
- [x] Generic profiles have non-zero offensive contribution
- [x] Simulation distribution validated (Var/Mean = 13.4 >> 1)
- [x] Team strength indices span full range (9.8 to 100.0)

### Code Validation

- [x] Division by zero protected via clip(lower=0.1)
- [x] Negative index values handled appropriately
- [x] Pipeline logging tracks record counts at each stage
- [ ] **FAILED:** NaN propagation in RC calculation for 4 players

### Documentation Validation

- [x] Hierarchy/priority descriptions match code (Class → Specific → Tenure)
- [ ] **PARTIAL:** Team aggregation described as "Top 9" but uses all qualified
- [x] Output file descriptions match actual outputs

---

## Conclusion

The Colorado High School Baseball Projection System demonstrates thoughtful application of sabermetric principles and solid software engineering. The two critical issues identified (NaN propagation and generic profile contamination) are straightforward to fix with targeted code changes. The statistical concerns around rare-event multipliers are common challenges in small-sample sports analytics and can be addressed with Bayesian techniques when time permits.

Following implementation of the two critical fixes, the system should produce reliable projections for the 2026 season with appropriate caveats about uncertainty in individual player development.

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| December 16, 2025 | 1.0 | Initial adversarial review |
