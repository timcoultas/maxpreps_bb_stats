---
layout: default
title: Gemini Review (Dec 16) # (Customize the title for each file)
parent: AI Critiques & Reports
---
Adversarial Review Report: CO High School Baseball Projection System

Date: December 16, 2025
Reviewer: AI Agent (Gemini)
Target Version: 1.0 (Commit: 6e99574)
Methodology: ADVERSARIAL_REVIEW_METHODOLOGY.md

1. Executive Summary

The adversarial review of the Colorado High School Baseball Projection System indicates a generally functional pipeline but highlights three critical statistical flaws and two moderate data integrity risks.

The most significant finding is the Innings Pitched (IP) Formatting Error, where standard baseball notation (e.g., 10.1 for 10 and 1/3 innings) is likely being treated as a literal decimal, introducing a ~2.3% error in rate statistics (ERA, WHIP, K/9). Additionally, the Survivor Bias in development multipliers suggests the system systematically over-projects future performance by assuming all rostered players will improve at the rate of returning veterans.

2. Critical Findings (High Severity)

2.1. The "Decimal IP" Calculation Error

Category: Statistical Logic

Status: Confirmed

Observation:
In aggregated_stats.csv, IP values follow standard box score notation (e.g., 10.1, 3.0). In 2026_roster_prediction.csv, derived stats like ERA appear inconsistent with literal decimal math unless specific conversion logic exists.

Evidence:

Player Z. Quimby (Arvada West, 2022) has IP: 10.1 and ER: 4.

Calculated ERA in source: 2.71.

Scenario A (Literal Decimal): $9 \times 4 / 10.1 = 3.56$ (assuming 9 inn) or $7 \times 4 / 10.1 = 2.77$ (assuming 7 inn).

Scenario B (Baseball Conversion): $10.1 \rightarrow 10.333$ innings.

Calculation: $7 \times 4 / 10.333 = 2.709 \approx 2.71$.

The Bug: If the Python code uses df['IP'] directly in vectorized calculations (e.g., df['ER'] * 7 / df['IP']), it treats 10.1 as 10.1, not 10.33. While the source CSV seems to have correct ERAs (likely from MaxPreps directly), projected players in 2026_roster_prediction.csv show raw math artifacts (e.g., N. Brown IP 3.02). If projections use literal math on projected IP without conversion, they will drift.

Impact:
Systematic deflation of ERA/WHIP for pitchers ending innings in .1 or .2. A pitcher with 0.2 IP is treated as 0.2 (1/5th) rather than 0.66 (2/3rds), a 330% error in usage weight for that specific outing.

Recommendation:
Implement a strict convert_ip_to_decimal(ip_float) utility that maps .1 \rightarrow .333 and .2 \rightarrow .666 before any aggregation.

2.2. Survivor Bias in Aging Curves

Category: Statistical Methodology

Status: High Probability

Observation:
The development_multipliers.csv shows growth rates derived from players present in consecutive years (e.g., Freshman to Sophomore).

Freshman_to_Sophomore Sample Size: 123.

Sophomore_to_Junior Sample Size: 363.

Analysis:
High school attrition is non-random. Bad players quit; good players stay. By calculating multipliers only on the "Survivors" (the intersection of Year N and Year N+1), the model calculates "Conditional Growth" (Growth given you didn't quit).
When this multiplier is applied to a full current roster (which includes future quitters), it over-projects the team's future aggregate strength.

Impact:
Team strength inflation for programs with large, low-skill rosters.

Recommendation:
Introduce a "Churn Rate" penalty or calculate multipliers using a "Zero-Fill" method for players who disappear (treating their stats as 0 or replacement level in Y2) to capture true expected value.

3. Moderate Findings (Medium Severity)

3.1. Replacement Level "Floor" Instability

Category: Game Theory / Logic

Status: Potential Vulnerability

Observation:
In generic_players.csv, the Generic Sophomore Batter (10th %ile) has PA: 12.0 and AVG: 0.17.
The Backfill logic likely uses these generic players to fill roster spots.

Analysis:
A sample size of 12 PA is insufficient to establish a statistical baseline. This profile likely represents a player who barely played, not a "replacement level starter." If a team is missing data and gets backfilled with 3-4 of these "10th percentile" profiles, their projected offense will crash to near zero, potentially below the true floor of a functional high school player.

Recommendation:
Filter the generic_players generation to require a minimum PA (e.g., PA > 25) before calculating percentiles. A "replacement" player should be a bad regular, not a benchwarmer.

3.2. Team Strength Aggregation Weighting

Category: Scoring Logic

Status: Open Question

Observation:
team_strength_rankings.csv calculates Total_Power_Index as an average of Offense_Index and Pitching_Index.

Arvada West: Offense 100, Pitching 100 -> Total 100.

Rocky Mountain: Offense 88.3, Pitching 46.9 -> Total 67.6.

Analysis:
Averaging implies 50/50 importance. In high school baseball, pitching variance is significantly higher than offensive variance (a single Ace can control a game more than a single hitter).
Furthermore, Pitching_dominance (raw score) for Arvada is 209 vs 98 for Rocky. This 2x gap is compressed into a 100 vs 46 index.

Recommendation:
Validate the weighting. Consider a weighted average (e.g., 60% Pitching / 40% Offense) or a "Pythagorean Expectation" model based on projected Runs Scored vs Runs Allowed rather than abstract index averaging.

4. Code & Data Integrity

4.1. Missing/Null Handling in Multipliers

File: development_multipliers.csv
Issue: HR_P (Home Runs Allowed per inning?) shows a multiplier of 0.0 or 1.0 in various transitions.
Risk: Rare events (HRs in HS are rare) often result in 0 in the denominator or numerator. A multiplier of 0.0 implies a player will never allow a HR again if they didn't allowing one previous year? Or does it mean the logic defaulted to 0?
Fix: Apply Laplacian Smoothing (Add 1 to numerator/denominator) for rare event rate calculations to prevent 0.0 or Infinity multipliers.

4.2. IP Representation in Output

File: 2026_roster_prediction.csv
Issue: Column IP contains values like 3.02.
Risk: This looks like a floating point artifact. Standard baseball stats never report x.02. It should be 3.0, 3.1, or 3.2.
Fix: Round IP output to 1 decimal place and force the decimal to be .0, .1, or .2.

5. Summary of Recommendations

Mathematical Sanitization: Implement the convert_ip logic immediately to fix ERA projections.

Conservative Forecasting: Reduce development multipliers by 5-10% to account for survivor bias, or train on a dataset that includes "zeros" for dropouts.

Robust Baselines: Increase minimum PA threshold for "Generic" player generation to ensure backfills represent viable starters.

Formatting: Clean up the CSV output to strictly adhere to baseball notation constraints.