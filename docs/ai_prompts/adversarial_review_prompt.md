---
layout: default
title: Adversarial Review Prompt  # (Change title for documentation_prompt.md)
parent: AI Prompts
---

# Adversarial Review Methodology

## Purpose

This document provides a structured methodology for AI agents (Claude, GPT-4, Gemini, etc.) to perform comprehensive adversarial reviews of the Colorado High School Baseball Projection System. The goal is to identify statistical flaws, code defects, and improvement opportunities through systematic analysis.

---

## Pre-Review Setup

### Required Context

Before beginning the review, the AI agent should be provided with:

1. **Source Code Files** (in this order of priority):
   - `src/workflows/roster_prediction.py` — Core projection logic
   - `src/workflows/game_simulator.py` — Monte Carlo simulation
   - `src/models/advanced_ranking.py` — RC and Pitching Score calculations
   - `src/workflows/profile_generator.py` — Generic player profiles
   - `src/workflows/development_multipliers.py` — Aging curve calculations
   - `src/workflows/team_strength_analysis.py` — Team aggregation
   - `src/utils/config.py` — Schema and configuration
   - `src/utils/utils.py` — Utility functions

2. **Data Files** (if available):
   - `aggregated_stats.csv` — Historical player statistics
   - `development_multipliers.csv` — Calculated multipliers with volatility
   - `generic_players.csv` — Replacement level profiles
   - `2026_roster_prediction.csv` — Projected rosters
   - `team_strength_rankings.csv` — Power rankings output

3. **Documentation**:
   - `README.md` — System overview and methodology
   - Any whitepaper or design documents describing intended behavior

### Suggested Prompt Framing

```
You are a Cynical Sabermetrician, Senior Data Engineer, and Python Expert performing an adversarial review of a high school baseball projection system.

Your role is to:
1. Challenge statistical assumptions with published research
2. Identify code defects that could produce incorrect outputs
3. Suggest improvements grounded in sabermetric literature

Be skeptical. Assume nothing works correctly until proven otherwise. Cite sources for statistical claims.
```

---

## Review Framework

### Phase 1: Statistical Validity Review

The agent should systematically evaluate each statistical method against established sabermetric research.

#### 1.1 Runs Created Formula

**Questions to Ask:**
- Is the RC formula correctly implemented? (Check: `RC = (H + BB) × TB / (AB + BB)`)
- Is Total Bases calculated correctly? (`TB = 1B + 2×2B + 3×3B + 4×HR`)
- Are there edge cases that produce nonsensical results (division by zero, negative values)?
- Is basic RC appropriate for the sample sizes, or should a simpler metric (OPS) be used?

**Reference Materials:**
- James, Bill. *The Bill James Baseball Abstract* (1979)
- Tango, Tom. "wOBA" methodology at FanGraphs

**Red Flags:**
- RC values exceeding 100 for a single season (likely extrapolation error)
- RC = 0 for players with hits (formula error)
- Negative RC values (impossible with correct formula)

#### 1.2 Pitching Score Formula

**Questions to Ask:**
- What is the formula and what are the weights?
- Are the weights justified by research or arbitrary?
- Can the score go negative? If so, how is this handled downstream?
- Does the formula account for innings pitched appropriately?

**Reference Materials:**
- James, Bill. "Game Score" methodology
- Tango, Tom. FIP (Fielding Independent Pitching) formula

**Red Flags:**
- Pitching scores that don't correlate with ERA/WHIP
- Negative scores causing division errors in downstream calculations
- Weights that overvalue or undervalue specific contributions

#### 1.3 Development Multipliers (Aging Curves)

**Questions to Ask:**
- What is the sample size for each transition type?
- Is median or mean used? (Median is more robust to outliers)
- Is there survivor bias in tenure-based transitions?
- What is the volatility/standard deviation of each multiplier?
- Are multipliers applied multiplicatively or additively?

**Reference Materials:**
- Tango, Lichtman, Dolphin. *The Book* (2006), Chapter on Aging Curves
- Albert, Jim. "Bayesian Analysis of Baseball Data" (2003)

**Red Flags:**
- Multipliers > 2.0 or < 0.5 (likely noise, not signal)
- Small sample sizes (N < 30) driving key multipliers
- Tenure-based curves showing implausible patterns (e.g., Year 1→Year 2 multiplier higher than Freshman→Sophomore)

#### 1.4 Replacement Level / Generic Players

**Questions to Ask:**
- What percentile defines "replacement level"?
- Are profiles based on sufficient sample sizes?
- Do the profiles produce non-zero offensive contribution?
- Is there a distinction between elite and non-elite program backfill?

**Reference Materials:**
- Cameron, Dave. "The Beginner's Guide to Replacement Level." FanGraphs (2010)
- Tango, Tom. Replacement level in WAR calculations

**Red Flags:**
- 20th percentile players with 0 hits (cameo appearances, not replacement level)
- Generic players with impossible stat lines (e.g., PA < AB)
- All teams receiving identical replacement players regardless of program quality

#### 1.5 Monte Carlo Simulation

**Questions to Ask:**
- What distribution is used for run scoring? (Poisson vs. Negative Binomial)
- What is the dispersion parameter and how was it calibrated?
- How is home field advantage modeled?
- How are ties resolved?
- Is the simulation count (N) sufficient for stable estimates?

**Reference Materials:**
- Lindsey, G.R. "An Investigation of Strategies in Baseball." *Operations Research* (1963)
- Miller, Steven J. "A Derivation of the Pythagorean Won-Loss Formula" (2007)

**Red Flags:**
- Using Poisson when variance/mean ratio >> 1 (under-dispersed)
- Dispersion parameter of exactly 1.0 (causes division by zero in NB parameterization)
- Expected run totals > 15 or < 2 per game (unrealistic)
- Win probabilities clustered at 50% (model has no discriminating power)

#### 1.6 Index Calculations and Normalization

**Questions to Ask:**
- How are team strength indices normalized?
- Is there protection against division by zero or negative indices?
- Is dampening applied to prevent extreme projections?
- What is the baseline (league average = 1.0)?

**Reference Materials:**
- James, Bill. Pythagorean Expectation
- Log5 method for head-to-head probability

**Red Flags:**
- Indices that can go negative or to zero
- No dampening leading to 20+ run projections
- Normalization denominators that could be zero

---

### Phase 2: Code Quality Review

The agent should review code for correctness, robustness, and maintainability.

#### 2.1 Data Integrity Issues

**Check For:**
- DataFrame mutation (functions modifying input DataFrames without `.copy()`)
- Silent data loss (records dropped without logging)
- Type coercion errors (strings where numbers expected)
- Missing value handling (NaN propagation)

**Test Pattern:**
```python
# Verify no mutation
original_len = len(df)
result = some_function(df)
assert len(df) == original_len, "Input DataFrame was mutated"
```

#### 2.2 Edge Case Handling

**Check For:**
- Division by zero protection
- Empty DataFrame handling
- Missing column handling
- Negative value handling where only positive expected

**Common Patterns to Verify:**
```python
# Good: Protected division
result = numerator / denominator.replace(0, 1)

# Good: Floor on indices
index = max(calculated_index, 0.1)

# Good: Empty check
if df.empty:
    return default_value
```

#### 2.3 Algorithm Correctness

**Check For:**
- Off-by-one errors in percentile calculations
- Incorrect join keys causing record duplication or loss
- Aggregation logic (SUM vs. MEAN vs. MEDIAN)
- Sorting before rank calculations

**Validation Approach:**
- Trace a single player through the entire pipeline
- Verify intermediate values match expected calculations
- Check that output record counts match expectations

#### 2.4 Performance Issues

**Check For:**
- O(n²) loops that could be vectorized
- Repeated DataFrame filtering in loops (should use groupby)
- Unnecessary data copies
- Missing index usage for lookups

**Example Anti-Pattern:**
```python
# Bad: O(n²)
for team in teams:
    team_data = df[df['Team'] == team]  # Scans entire DataFrame each iteration

# Good: O(n)
for team, team_data in df.groupby('Team'):
    ...
```

#### 2.5 Configuration and Magic Numbers

**Check For:**
- Hardcoded values that should be configurable
- Magic numbers without explanatory comments
- Inconsistent thresholds across files

**Examples:**
```python
# Bad: Magic number
if pa > 10:

# Good: Named constant
MIN_PA_THRESHOLD = 10
if pa > MIN_PA_THRESHOLD:
```

---

### Phase 3: Documentation vs. Implementation Alignment

The agent should verify that documentation matches actual code behavior.

#### 3.1 Docstring Accuracy

**Check For:**
- Formula descriptions matching actual code
- Argument descriptions matching function signatures
- Return value descriptions matching actual returns
- Stated assumptions that aren't enforced in code

#### 3.2 README/Whitepaper Alignment

**Check For:**
- Described methodology matching implemented methodology
- Hierarchy or priority orders matching code logic
- Stated data sources matching actual inputs
- Output descriptions matching actual file contents

#### 3.3 Comment Accuracy

**Check For:**
- Comments describing what code "should" do vs. what it actually does
- Outdated comments referencing removed functionality
- TODO comments for unimplemented features

---

### Phase 4: Identify Future Opportunities

The agent should identify improvements that require additional data or research.

#### 4.1 Data-Dependent Improvements

For each opportunity, specify:
- What data would be needed
- Where that data might be obtained
- Expected impact on projection accuracy
- Implementation complexity (Low/Medium/High)

**Common Opportunities:**
- Park effects (requires field dimensions)
- Strength of schedule (requires complete league schedules)
- Pitcher matchups (requires rotation data)
- Defensive metrics (requires advanced fielding data)
- Backtesting (requires historical game results)

#### 4.2 Methodological Improvements

**Common Opportunities:**
- Bayesian regression for small samples
- Confidence intervals on projections
- Regression to the mean for extreme values
- Empirical calibration of simulation parameters

#### 4.3 Usability Improvements

**Common Opportunities:**
- Interactive visualization of projections
- Sensitivity analysis tools
- Automated data acquisition
- Pipeline monitoring and alerting

---

## Output Format

The agent should produce a structured review document with the following sections:

```markdown
# Adversarial Review: [Project Name]

**Reviewer Role:** [Agent identity/framing used]
**Review Date:** [Date]
**Files Reviewed:** [List of files examined]

## Executive Summary
[2-3 paragraph summary of findings]

## Critical Issues (Must Fix)
[Issues that produce incorrect outputs or could cause failures]

### Issue 1: [Title]
- **Location:** [File and line numbers]
- **Problem:** [Description]
- **Impact:** [What goes wrong]
- **Recommended Fix:** [Code or approach]

## Statistical Validity Concerns
[Issues with methodology that may affect accuracy]

### Concern 1: [Title]
- **Methodology:** [What the code does]
- **Problem:** [Why it may be incorrect]
- **Reference:** [Published research]
- **Recommendation:** [Suggested change]

## Code Quality Issues (Should Fix)
[Issues that don't break functionality but reduce maintainability]

## Future Opportunities
[Improvements requiring additional data or significant effort]

| Opportunity | Data Required | Impact | Priority |
|-------------|---------------|--------|----------|
| ... | ... | ... | ... |

## Appendix: Validation Checks Performed
[List of specific validations run and their results]
```

---

## Validation Checklist

The agent should confirm each item before concluding the review:

### Statistical Validation
- [ ] RC formula produces expected values for sample players
- [ ] Pitching Score formula handles edge cases (0 IP, high ER)
- [ ] Multipliers have reasonable sample sizes (N > 30)
- [ ] Generic profiles have non-zero offensive contribution
- [ ] Simulation produces realistic score distributions (mean ~6 runs)
- [ ] Win probabilities span full range (not clustered at 50%)

### Code Validation
- [ ] No DataFrame mutation in calculation functions
- [ ] Division by zero protected in all calculations
- [ ] Negative index values handled appropriately
- [ ] Pipeline logging tracks record counts at each stage
- [ ] Edge cases (empty data, missing columns) handled gracefully

### Documentation Validation
- [ ] Hierarchy/priority descriptions match code
- [ ] Formula descriptions match implementations
- [ ] Output file descriptions match actual outputs

---

## Example Findings from Previous Reviews

These are examples of issues found in past reviews of this codebase:

### Critical Issue: Negative Pitching Index Division
```python
# BEFORE (Bug)
opp_pit_factor = 1.0 / np.sqrt(opp_stats['Pit_Index'])
# If Pit_Index <= 0, this produces inf or raises error

# AFTER (Fixed)
df_strength['Pit_Index'] = df_strength['Pit_Index'].clip(lower=0.1)
```

### Statistical Concern: 20th Percentile = Zero Production
```
Finding: 20th percentile sophomore batters have median 0 hits
Impact: Teams backfilled with these profiles contribute 0 to team offense
Fix: Use 30th percentile as floor, filter for minimum PA before percentile calculation
```

### Documentation Mismatch: Hierarchy Order
```
Whitepaper stated: "Tenure → Specific → Class"
Code implemented: "Class → Specific → Tenure"
Resolution: Code was correct (Class has less survivor bias); documentation updated
```

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| December 2025 | 1.0 | Initial methodology based on first adversarial review |

---

## Contact

For questions about this methodology or the codebase, refer to the repository maintainer or open an issue on GitHub.
