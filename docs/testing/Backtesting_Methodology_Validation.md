---
layout: default
title: Testing Results
parent: Testing
---

# **Backtesting Methodology & Validation**

This document outlines the backtesting framework used to validate the accuracy of the MaxPreps Baseball Stats projection model. It bridges the gap between sabermetric theory and the practical realities of high school baseball, ensuring our projections are not just mathematically sound but grounded in the game itself.

## **1\. The "Time Travel" Philosophy**

To accurately measure the predictive power of our model, we cannot simply look at how well the model fits past data (hindsight bias). We must simulate the uncertainty of a new season—the "Preseason Prediction" challenge.

**The Process:**

1. **Data Isolation (The Blindfold):** When backtesting for Year X (e.g., 2025), the system strictly isolates data from Year X-1 and prior (e.g., 2024 and earlier). The model has zero knowledge of the actual Year X results during the projection phase. This simulates the exact conditions of a preseason analysis.  
2. **Projection (The Scout's Eye):** The standard `roster_prediction` logic is applied to the historical data to generate a "Projected Year X Roster." This asks: *Based on who they were last year, who should they be this year?*  
3. **Extraction (The Scoreboard):** We then extract the *actual* statistics that occurred in Year X—the ground truth.  
4. **Comparison (The Report Card):** The projected roster is compared against the actual roster to calculate error metrics.

## **2\. Running a Backtest**

The backtest is orchestrated by `run_backtest.py`.

### **Usage**

To validate the model against a specific past season:

\# Validate 2025 projections (using 2024 data)  
python run\_backtest.py \--year 2025

\# Validate 2024 projections (using 2023 data)  
python run\_backtest.py \--year 2024

### **Prerequisites**

* `aggregated_stats.csv` must contain data for both the Target Year and the Base Year (Target \- 1).  
* (Optional) Schedule/Results files for game simulation validation.

## **3\. Team Strength Scoring Methodology: "Seniority & Impact"**

The core metric for validation is the **Team Power Index Correlation**. This measures how well our projected team rankings align with the actual team strength at the end of the season.

### **Initial Findings: The "Depth Trap"**

Initially, a raw summation of projected stats (Runs Created, Pitching Scores) proved insufficient, yielding a correlation of **0.747**. This approach treated a roster of 15 average sophomores as superior to a roster of 4 elite seniors. It failed to account for roster turnover and the disproportionate impact of elite talent.

### **The Solution: Weighted Impact Score**

To correct for this, we applied a **Weighted Impact Score** that balances statistical volume with baseball intuition. This improved the 2025 correlation to **0.776**.

#### **A. The "Survivor" Confidence Weight (Roster Probability)**

High school rosters are volatile. We weight contribution based on the likelihood a player will actually be on the field and impactful.

* **Seniors (1.10x):** *The "Senior Leadership" Factor.* Seniors are physically stronger, emotionally more mature, and playing with urgency. They are the least likely to quit and most likely to carry a team.  
* **Juniors (1.00x):** *The Baseline.* Standard varsity contributors.  
* **Underclassmen (0.90x):** *The "Freshman/Sophomore" Tax.* While talented, young players are volatile. They are prone to slumps and physical development curves that are harder to predict.  
* **Generic Backfill (0.75x):** *The "Replacement Level" Penalty.* These are theoretical players added to fill roster holes. A team relying on "Generic Player 3" is not a contender. We heavily penalize this depth to ensure rankings favor teams with *real, proven* talent.

#### **B. Role Significance (Top-End Talent)**

Depth is nice, but Aces and Cleanup hitters decide championships.

* **Batting:** The top 3 projected hitters receive an additional `1.1x` to `1.2x` boost.  
* **Pitching:** The "Ace" (SP1) receives `1.5x` and SP2 receives `1.25x`. In high school, a dominant Ace can pitch 40% of the team's meaningful innings.

## **4\. Historical Results & Interpretation**

We use the Pearson correlation coefficient to grade the model.

* **\> 0.80:** Excellent predictive power.  
* **0.70 \- 0.80:** Strong predictive power (Current Target).  
* **\< 0.60:** Weak predictive power.

### **2025 Season Validation**

* **Correlation:** **0.776** (Strong)  
* **Average Rank Error:** 5.5 positions  
* **Teams within 3 spots:** 18 / 37  
* **The Baseball Story:** The model nailed the "Blue Bloods" (Rocky Mountain, Broomfield, Cherry Creek). The errors came from teams like **Grandview** and **Castle View**, who outperformed their projections. This suggests they had "breakout" players (transfers or JV call-ups) who performed at a varsity level but weren't in our 2024 dataset.

### **2024 Season Validation**

* **Correlation:** **0.656** (Moderate)  
* **The Baseball Story:** A volatile year defined by "Black Swan" events.  
  * **Northfield (+23 Rank Diff):** Massive underestimation. This is the classic "Program on the Rise" scenario—a huge influx of young talent or transfers that statistical trends couldn't see coming.  
  * **Arvada West (+20 Rank Diff):** Another massive breakout.  
  * **Interpretation:** The model establishes a **Statistical Baseline**. When a team like Northfield jumps 23 spots above projection, it's not a math error; it's a signal that *something changed* in the program (new coach? golden generation of freshmen?) that requires qualitative scouting to capture.

## **5\. Files & Outputs**

Backtest artifacts are saved to `data/output/roster_prediction/backtest/`:

* `{YEAR}_roster_prediction_backtest.csv`: The "Time Travel" roster generated by the model.  
* `{YEAR}_actual_stats.csv`: The ground truth data.  
* `team_ranking_accuracy.csv`: Side-by-side comparison of projected vs. actual team ranks.  
* `player_projection_accuracy.csv`: Detailed error metrics for individual player stats.

