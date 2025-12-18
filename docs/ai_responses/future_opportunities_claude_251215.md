---
layout: default
title: Future Improvement Opportunities - Claude (Dec 15) 
parent: AI Critiques & Reports
---
# Future Improvement Opportunities

## Overview

This document outlines opportunities for improvement that were identified during the adversarial review but **cannot be implemented without additional data or external resources**. Each section describes the opportunity, the data required, and suggested implementation approaches.

---

## 1. Empirical Dispersion Parameter Calibration

### Current State
The Monte Carlo simulator uses a hardcoded dispersion parameter of 1.3 for the Negative Binomial distribution. This value is reasonable based on MLB research but has not been validated against actual high school game scores.

### Opportunity
Calibrate the dispersion parameter using empirical game-level data to improve simulation accuracy.

### Data Required
- **Game-level scores** for Colorado high school baseball games (ideally 2+ seasons)
- Format: `Date, Home_Team, Away_Team, Home_Score, Away_Score`
- Source possibilities:
  - MaxPreps game results pages
  - CHSAA (Colorado High School Activities Association) archives
  - Local newspaper sports sections

### Implementation Approach
```python
from scipy.stats import nbinom
from scipy.optimize import minimize

def fit_dispersion(actual_scores, expected_means):
    """
    Fit optimal dispersion parameter to historical game scores.
    
    Args:
        actual_scores: Array of actual runs scored
        expected_means: Array of expected runs (from team strength model)
    
    Returns:
        Optimal dispersion value
    """
    def neg_log_likelihood(dispersion):
        total_ll = 0
        for score, mean in zip(actual_scores, expected_means):
            if mean <= 0 or dispersion <= 1:
                return float('inf')
            variance = mean * dispersion
            p = mean / variance
            n = (mean ** 2) / (variance - mean)
            total_ll -= nbinom.logpmf(score, n, p)
        return total_ll
    
    result = minimize(neg_log_likelihood, x0=1.3, bounds=[(1.01, 3.0)])
    return result.x[0]
```

### Expected Impact
- More accurate win probability estimates
- Better calibrated confidence intervals for season projections
- Reduced systematic bias in blowout/shutout predictions

### References
- Lindsey, G.R. "An Investigation of Strategies in Baseball." *Operations Research* 11.4 (1963): 477-501.

---

## 2. Park Effects / Field Dimensions

### Current State
The simulator applies a flat 10% home field advantage multiplier regardless of the specific field being played on.

### Opportunity
Incorporate park factors based on field dimensions to adjust run expectations by venue.

### Data Required
- **Field dimensions** for each high school baseball field:
  - Left field line distance
  - Center field distance
  - Right field line distance
  - Fence height
  - Altitude (relevant for Colorado)
- **Historical scoring by venue** (optional but helpful for validation)

### Implementation Approach
```python
# Park factor calculation (simplified)
def calculate_park_factor(left_field, center_field, right_field, altitude_ft):
    """
    Estimate park factor based on dimensions and altitude.
    
    Returns: Multiplier where 1.0 = neutral, >1.0 = hitter-friendly
    """
    # Baseline distances (typical HS field)
    baseline_lf, baseline_cf, baseline_rf = 320, 380, 320
    
    # Distance factor (smaller = more runs)
    distance_factor = (
        (baseline_lf / left_field) * 0.3 +
        (baseline_cf / center_field) * 0.4 +
        (baseline_rf / right_field) * 0.3
    )
    
    # Altitude factor (Denver effect: ~5% increase per 1000ft above sea level)
    altitude_factor = 1.0 + (altitude_ft / 1000) * 0.05
    
    return distance_factor * altitude_factor
```

### Expected Impact
- More accurate home/away scoring differentials
- Better predictions for games at extreme venues (e.g., high altitude Fort Collins vs. sea-level opponent)
- Improved player projection for extreme home fields

### References
- Keri, Jonah, ed. *Baseball Between the Numbers*. Basic Books, 2006. Chapter on Park Effects.

---

## 3. Strength of Schedule Adjustment

### Current State
Power rankings and team strength indices do not account for opponent quality. A team with 150 projected runs against weak opponents appears equivalent to one with 150 runs against strong opponents.

### Opportunity
Implement Strength of Schedule (SOS) adjustments to normalize team ratings.

### Data Required
- **Complete league schedule** for all teams (not just Rocky Mountain)
- Format: `Team, Opponent, Date, Home/Away`
- At minimum, conference schedules for the target league

### Implementation Approach
```python
def calculate_sos_adjusted_index(team, schedule_df, strength_map):
    """
    Adjust team index based on average opponent strength.
    
    Formula: Adjusted = Raw * (League_Avg_Opponent / Team_Avg_Opponent)
    """
    team_games = schedule_df[
        (schedule_df['Home'] == team) | (schedule_df['Away'] == team)
    ]
    
    opponents = []
    for _, game in team_games.iterrows():
        opp = game['Away'] if game['Home'] == team else game['Home']
        if opp in strength_map:
            opponents.append(strength_map[opp]['Off_Index'])
    
    if not opponents:
        return strength_map[team]['Off_Index']
    
    avg_opp_strength = np.mean(opponents)
    league_avg = np.mean([v['Off_Index'] for v in strength_map.values()])
    
    adjustment = league_avg / avg_opp_strength
    return strength_map[team]['Off_Index'] * adjustment
```

### Expected Impact
- Fairer power rankings that reward teams with difficult schedules
- Better predictions for non-conference/playoff matchups
- Identification of "paper tigers" (good record against weak opponents)

---

## 4. Regression to the Mean for Extreme Projections

### Current State
Some players have extreme stat projections (e.g., 58.8 projected hits) that may be unreliable due to small sample sizes or outlier prior seasons.

### Opportunity
Apply regression toward population means based on sample reliability.

### Data Required
- **Historical variance data** by stat category (already available in multipliers)
- **League-wide averages** by class and position
- Ideally: **Multiple seasons** of data per player to estimate true talent

### Implementation Approach
```python
def regress_projection(projection, sample_size, population_mean, typical_variance):
    """
    Apply Marcel-style regression to projection.
    
    Based on Tango's Marcel the Monkey system.
    
    Args:
        projection: Raw projected value
        sample_size: Player's historical sample (e.g., PA)
        population_mean: League average for this stat
        typical_variance: Expected variance in the population
    
    Returns:
        Regressed projection
    """
    # Reliability increases with sample size
    # Rule of thumb: ~500 PA for full reliability on batting stats
    reliability = sample_size / (sample_size + 500)
    
    regressed = population_mean + reliability * (projection - population_mean)
    return regressed
```

### Expected Impact
- More conservative (and likely more accurate) projections for breakout candidates
- Reduced projection variance for low-PA players
- Better handling of "one-hit wonders"

### References
- Tango, Tom. "Marcel the Monkey Forecasting System." TangoTiger.net, 2004.
- Silver, Nate. "PECOTA." Baseball Prospectus methodology documentation.

---

## 5. Game-Level Validation / Backtesting

### Current State
The projection system has not been validated against actual game outcomes.

### Opportunity
Implement backtesting framework to measure projection accuracy.

### Data Required
- **Historical game results** for at least 1 full season
- **Historical rosters** that were used to generate predictions (to recreate past projections)
- Format: `Date, Home_Team, Away_Team, Home_Score, Away_Score, Home_Win`

### Implementation Approach
```python
def backtest_season(predictions_df, actuals_df):
    """
    Compare predicted win probabilities to actual outcomes.
    
    Metrics:
    - Brier Score: Mean squared error of probability predictions
    - Calibration: Do 70% predictions win 70% of the time?
    - Log Loss: Information-theoretic accuracy measure
    """
    merged = predictions_df.merge(actuals_df, on=['Date', 'Opponent'])
    
    # Brier Score (lower is better, 0 = perfect)
    brier = ((merged['Win_Pct'] - merged['Actual_Win']) ** 2).mean()
    
    # Calibration by bucket
    merged['Prob_Bucket'] = (merged['Win_Pct'] * 10).astype(int) / 10
    calibration = merged.groupby('Prob_Bucket').agg({
        'Win_Pct': 'mean',
        'Actual_Win': 'mean',
        'Date': 'count'
    }).rename(columns={'Date': 'N_Games'})
    
    return {
        'brier_score': brier,
        'calibration': calibration,
        'total_games': len(merged)
    }
```

### Expected Impact
- Quantified confidence in projection accuracy
- Identification of systematic biases (e.g., overconfident in favorites)
- Data-driven tuning of model parameters

---

## 6. Pitcher Matchup Adjustments

### Current State
Game simulations use aggregate team pitching strength without considering which specific pitcher will start.

### Opportunity
Model game-level outcomes based on probable starting pitcher.

### Data Required
- **Pitching rotation information** (who starts which games)
- **Opponent-specific splits** (how pitchers perform vs. specific teams/lineups)
- **Pitch count / workload data** for fatigue modeling

### Implementation Approach
```python
def simulate_game_with_starter(my_team, opponent, my_starter, opp_starter, ...):
    """
    Adjust game simulation based on starting pitchers.
    
    Use individual pitcher's Pitching_Score rather than team aggregate.
    Apply fatigue adjustment based on recent workload.
    """
    # Get individual pitcher strength instead of team aggregate
    my_pit_index = my_starter['Pitching_Score'] / league_avg_pitcher_score
    opp_pit_index = opp_starter['Pitching_Score'] / league_avg_pitcher_score
    
    # Apply fatigue if pitcher threw recently
    days_rest = calculate_days_rest(my_starter, game_date)
    fatigue_factor = min(1.0, 0.8 + days_rest * 0.05)  # Full strength at 4+ days rest
    my_pit_index *= fatigue_factor
    
    # Continue with normal simulation...
```

### Expected Impact
- More accurate game-level predictions
- Better modeling of aces vs. #4 starters
- Ability to simulate "what if" scenarios for playoff pitching decisions

---

## 7. Defensive Metrics Integration

### Current State
The system focuses on batting (RC) and pitching (Game Score variant) but does not incorporate fielding.

### Opportunity
Add defensive contribution to player and team valuations.

### Data Required
- **Fielding statistics** (currently partially available: FP, TC, PO, A, E)
- Ideally: **Position-specific data** (SS errors are different from 1B errors)
- Advanced: **Range factor** or **UZR-equivalent** (not typically available at HS level)

### Implementation Approach
```python
def calculate_defensive_score(df):
    """
    Simple defensive value based on available stats.
    
    Weights errors negatively, rewards assists/putouts for non-1B positions.
    """
    # Fielding percentage component
    fp_component = (df['FP'].fillna(0.95) - 0.95) * 10  # 0 for average, + for good
    
    # Volume component (more chances = more defensive value)
    volume_component = np.log1p(df['TC'].fillna(0)) / 3  # Diminishing returns
    
    # Error penalty (more severe for key positions)
    error_penalty = df['E'].fillna(0) * -0.5
    
    return fp_component + volume_component + error_penalty
```

### Expected Impact
- More complete player valuation
- Better differentiation of "glove-first" vs. "bat-first" players
- Improved team strength assessment for defensively-oriented squads

---

## Summary: Data Collection Priority

| Opportunity | Data Difficulty | Impact | Priority |
|-------------|-----------------|--------|----------|
| Game-Level Scores (for dispersion calibration) | Medium | High | **1** |
| Complete League Schedules (for SOS) | Low | High | **2** |
| Historical Results (for backtesting) | Medium | High | **3** |
| Field Dimensions | Medium | Medium | 4 |
| Pitching Rotation Data | High | Medium | 5 |
| Advanced Defensive Data | Very High | Low | 6 |

**Recommended Next Step:** Scrape game-level results from MaxPreps for the 2024 and 2025 seasons to enable both dispersion calibration (#1) and backtesting (#3).
