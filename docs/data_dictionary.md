# Data Dictionary

## Key Outputs

### Team Power Rankings

**Purpose:** Team-level power rankings aggregating individual player performance into composite indices. This shows the relative strenght of teams as well as provides information about returning players and experience level. 

**Location:** `data/output/team_strength/team_strength_rankings.csv`

| Column | Data Type | Description | Calculation |
|--------|-----------|-------------|-------------|
| **Team** | String | Full team name with location | Direct from roster |
| **Total_Power_Index** | Float | Composite team strength (0-100 scale) | `(Offense_Index + Pitching_Index) / 2` |
| **Offense_Index** | Float | Relative offensive strength (0-100) | `(Projected_Runs / max_Projected_Runs) × 100` |
| **Pitching_Index** | Float | Relative pitching strength (0-100) | `(Pitching_dominance / max_Pitching_dominance) × 100` |
| **Projected_Runs** | Float | Sum of RC_Score for top 10 batters | `SUM(TOP 10 RC_Score)` |
| **Pitching_dominance** | Float | Sum of Pitching_Score for top 6 pitchers | `SUM(TOP 6 Pitching_Score)` |
| **Batters_Count** | Integer | Number of qualified batters (RC > 0.1) in top 10 | Count |
| **Pitchers_Count** | Integer | Number of qualified pitchers (Score > 0.1) in top 6 | Count |
| **Returning_Players** | Integer | Real players (not generic backfill) | `COUNT WHERE Projection_Method NOT LIKE '%Generic%'` |
| **Returning_Seniors** | Integer | Returning players projected as Seniors | Count |
| **Returning_Juniors** | Integer | Returning players projected as Juniors | Count |
| **Returning_Sophs** | Integer | Returning players projected as Sophomores | Count |
| **Total_Varsity_Years** | Integer | Sum of Varsity_Year for all returning players | `SUM(Varsity_Year) WHERE Is_Returning = True` |
| **Avg_Varsity_Years** | Float | Average experience level | `AVG(Varsity_Year) WHERE Is_Returning = True` |
| **Top_Hitter** | String | Name of team's best batter | Player with highest RC_Score |
| **Top_Hitter_RC** | Float | RC_Score of top hitter | Max RC_Score for team |
| **Ace_Pitcher** | String | Name of team's best pitcher | Player with highest Pitching_Score |
| **Ace_Score** | Float | Pitching_Score of ace | Max Pitching_Score for team |

**Index Interpretation:**
- 100.0 = League leader (best team)
- 50.0 = Half as strong as league leader
- <30 = Significantly weaker program

---

### Season Game by Game Simulation

**Purpose:** Provides Game-by-game season simulation results for Rocky Mountain's schedule. Shows win probability, projected scores, confidence of the projection, and a sort narrative describing the outcome. 

**Location:** `data/output/team_strength/rocky_mountain_monte_carlo.csv`

| Column | Data Type | Description |
|--------|-----------|-------------|
| **Date** | String | Game date |
| **Opponent** | String | Opposing team name |
| **Win_Pct** | Float | Win probability (0.0-1.0) based on 1,000 simulations |
| **Proj_Score** | String | Average projected score (e.g., "6.2-5.1") |
| **Confidence** | String | Game classification: "Lock (W)", "Solid (W)", "Toss-up", "Solid (L)", "Lock (L)" |
| **Analysis** | String | Narrative explanation of matchup factors |
| **My_Off_Idx** | Float | Rocky Mountain's Offense Index |
| **My_Pit_Idx** | Float | Rocky Mountain's Pitching Index |
| **Opp_Off_Idx** | Float | Opponent's Offense Index |
| **Opp_Pit_Idx** | Float | Opponent's Pitching Index |

**Confidence Labels:**

| Label | Win_Pct Range | Interpretation |
|-------|---------------|----------------|
| Lock (W) | >90% | Very likely win |
| Solid (W) | 65-90% | Favorable matchup |
| Toss-up | 35-65% | Could go either way |
| Solid (L) | 10-35% | Unfavorable matchup |
| Lock (L) | <10% | Very likely loss |

**Simulation Parameters:**
- 1,000 iterations per game
- Negative Binomial distribution with dispersion = 1.3
- Home field advantage = 10% scoring boost
- Average Runs per Game in HS baseball = 6.0 per game

---

### 2026 Roster Projection

**Purpose:** Complete projected roster for every team with individual player statistics and rankings. This carries non-senior varsity players forward onto the 2026 roster, applies an improvement mulitiplier to them based on historical trends, and fills in empty roster spots with generic players also based on historical data. 

**Location:** `data/output/roster_prediction/2026_roster_prediction.csv`

| Column | Data Type | Description | Source/Calculation |
|--------|-----------|-------------|-------------------|
| **Team** | String | Full team name with location (e.g., "Rocky Mountain (Fort Collins, CO)") | ETL: metadata.py |
| **Name** | String | Player name or generic player identifier | ETL: stat_extraction.py / profile_generator.py |
| **Season_Cleaned** | Integer | Projected season year (e.g., 2026) | Calculated: base year + 1 |
| **Class_Cleaned** | String | Projected grade level (Freshman, Sophomore, Junior, Senior) | Calculated: next_class_map lookup |
| **Varsity_Year** | Integer | Number of varsity seasons player is entering (1-4) | Calculated: cumcount() + 1, then +1 for projection |
| **Projection_Method** | String | Method used to project stats | One of: "Class (Age-Based)", "Class_Tenure (Specific)", "Tenure (Experience-Based)", "Default (1.0)", "Backfill (Elite Step-Down)", "Backfill (Standard Step-Down)", "Generic Baseline" |
| **Offensive_Rank_Team** | Integer | Within-team batting rank (1 = best batter on team) | RANK() OVER (PARTITION BY Team ORDER BY RC_Score DESC) |
| **Pitching_Rank_Team** | Integer | Within-team pitching rank (1 = best pitcher on team) | RANK() OVER (PARTITION BY Team ORDER BY Pitching_Score DESC) |

**Batting Statistics:**

| Column | Data Type | Description | Unit |
|--------|-----------|-------------|------|
| **PA** | Float | Plate Appearances | Count |
| **AB** | Float | At Bats | Count |
| **AVG** | Float | Batting Average | Ratio (0.000-1.000) |
| **H** | Float | Hits | Count |
| **2B** | Float | Doubles | Count |
| **3B** | Float | Triples | Count |
| **HR** | Float | Home Runs | Count |
| **RBI** | Float | Runs Batted In | Count |
| **R** | Float | Runs Scored | Count |
| **SF** | Float | Sacrifice Flies | Count |
| **BB** | Float | Walks (Base on Balls) | Count |
| **K** | Float | Strikeouts | Count |
| **HBP** | Float | Hit By Pitch | Count |
| **OBP** | Float | On-Base Percentage | Ratio |
| **SLG** | Float | Slugging Percentage | Ratio |
| **OPS** | Float | On-Base Plus Slugging | Ratio |
| **SB** | Float | Stolen Bases | Count |

**Pitching Statistics:**

| Column | Data Type | Description | Unit |
|--------|-----------|-------------|------|
| **APP** | Float | Appearances | Count |
| **IP** | Float | Innings Pitched (baseball notation: X.1 = X⅓, X.2 = X⅔) | Innings |
| **ERA** | Float | Earned Run Average | Runs per 9 innings |
| **BF** | Float | Batters Faced | Count |
| **K_P** | Float | Strikeouts (Pitching) | Count |
| **ER** | Float | Earned Runs | Count |
| **H_P** | Float | Hits Against | Count |
| **2B_P** | Float | Doubles Against | Count |
| **3B_P** | Float | Triples Against | Count |
| **HR_P** | Float | Home Runs Against | Count |
| **BB_P** | Float | Walks Against | Count |
| **BAA** | Float | Batting Average Against | Ratio |

**Fielding Statistics:**

| Column | Data Type | Description | Unit |
|--------|-----------|-------------|------|
| **FP** | Float | Fielding Percentage | Ratio |
| **TC** | Float | Total Chances | Count |
| **PO** | Float | Putouts | Count |
| **A** | Float | Assists | Count |
| **E** | Float | Errors | Count |
| **DP** | Float | Double Plays | Count |

**Derived/Calculated Fields:**

| Column | Data Type | Description | Calculation |
|--------|-----------|-------------|-------------|
| **Is_Batter** | Boolean | Qualifies as batter (AB ≥ 10) | `df['AB'].fillna(0) >= 10` |
| **Is_Pitcher** | Boolean | Qualifies as pitcher (IP ≥ 5) | `df['IP'].fillna(0) >= 5` |
| **Offensive_Rank** | Integer | League-wide batting rank | RANK() OVER (ORDER BY RC_Score DESC) |
| **Pitching_Rank** | Integer | League-wide pitching rank | RANK() OVER (ORDER BY Pitching_Score DESC) |
| **RC_Score** | Float | Runs Created offensive value | `(H + BB) × TB / (AB + BB)` where TB = 1B + 2×2B + 3×3B + 4×HR |
| **Pitching_Score** | Float | Pitching Dominance Score | `(IP_decimal × 1.5) + (K_P × 1.0) - (BB_P × 1.0) - (ER × 2.0)` |

**Special Values:**
- `9999` in Offensive_Rank/Pitching_Rank: Player doesn't qualify for that role
- "Generic Batter/Pitcher" in Name: Synthetic backfill player

---

### Historical Rosters

**Purpose:** Historical player statistics across all teams and seasons, serving as the source data for projections. This is an aggregate of all historical MaxPreps data that was collected (currently 37 teams for four years 2022- 2025). It provides all of the same statistics columns as the Roster Projection data, but based on actuals pulled from MaxPreps. . 

**Location:** `data/output/historical_stats/aggregated_stats.csv`

| Column | Data Type | Description | Source |
|--------|-----------|-------------|--------|
| **Season** | String | Raw season identifier (e.g., "23-24") | metadata.py: utag_data.year |
| **Season_Cleaned** | String/Int | Normalized year (e.g., "2024") | metadata.py: parsed from Season |
| **Team** | String | School name with location | metadata.py: utag_data.schoolName |
| **Level** | String | Competition level (typically "Varsity") | metadata.py: utag_data.teamLevel |
| **Source_File** | String | Original HTML filename for data lineage | ETL: filename |
| **Name** | String | Player display name | stat_extraction.py: link text |
| **Class** | String | Original class year from MaxPreps | stat_extraction.py: abbr.class-year |
| **Class_Cleaned** | String | Inferred/corrected class year | class_inference.py + class_cleansing.py |
| **Athlete_ID** | String (UUID) | MaxPreps unique player identifier (per season) | stat_extraction.py: href athleteid parameter |

**Statistics Columns:** Same as roster prediction (PA through DP) but representing actual historical values, not projections.

**Data Quality Notes:**
- `Class = 'Unknown'`: MaxPreps didn't provide class information; inference attempted
- `Class_Cleaned` may differ from `Class` if corrected by progression fixer
- Athlete_ID changes between seasons; Name-based matching used for longitudinal tracking

---

## Supporting Files

### Development Mulitipliers

**Purpose:** Year-over-year performance ratios used to project player development. These mulitpliers are derived from historical performance. For example, across all Juniors becoming Seniors, what was the median change in ERA? That multiplier is then applied to that age transition. 

**Location:** `data/output/development_multipliers/development_multipliers.csv`

| Column | Data Type | Description |
|--------|-----------|-------------|
| **Transition** | String (Index) | Transition identifier (e.g., "Sophomore_to_Junior", "Freshman_Y1_to_Sophomore_Y2") |
| **Type** | String | Category: "Class", "Tenure", or "Class_Tenure" |
| **Sample_Size** | Integer | Number of players in cohort (N) |
| **Avg_Volatility** | Float | Average standard deviation across all stat multipliers (lower = more reliable) |
| **[Stat Columns]** | Float | Median YoY ratio for each statistic |

**Transition Types Explained:**

| Type | Example | Description | Reliability |
|------|---------|-------------|-------------|
| Class | Sophomore_to_Junior | All players making this class transition | **Highest N, most stable** |
| Tenure | Varsity_Year1_to_Year2 | Players by varsity experience | Prone to survivor bias |
| Class_Tenure | Sophomore_Y1_to_Junior_Y2 | Specific combination | Highest specificity, smaller N |

**Multiplier Interpretation:**
- `1.0` = No change expected
- `>1.0` = Expected improvement (e.g., 1.2 = 20% increase)
- `<1.0` = Expected decline
- `0.0` or extreme values = Small sample noise (use with caution)

**Special Handling:**
- Triples (3B), Home Runs (HR), and pitching equivalents use Laplacian smoothing to reduce noise
- Multipliers are capped/floored when applied to prevent extreme projections

---

### Generic Players

**Purpose:** Synthetic "replacement level" player profiles that are used for roster backfilling.

**Location:** `data/output/generic_players/generic_players.csv`

| Column | Data Type | Description |
|--------|-----------|-------------|
| **Name** | String | Descriptive identifier (e.g., "Generic Sophomore Batter (30th %ile)") |
| **Role** | String | "Batter" or "Pitcher" |
| **Class_Cleaned** | String | Always "Sophomore" (typical call-up class) |
| **Varsity_Year** | Integer | Always 1 (first-year varsity) |
| **Projection_Method** | String | "Generic Baseline" |
| **Percentile_Tier** | Float | Statistical percentile (0.1, 0.2, 0.3, 0.4, 0.5) |
| **[Stat Columns]** | Float | Median values for that percentile bucket |
| **AB_Original / PA_Original / IP_Original** | Float | Original values before minimum enforcement |

**Percentile Tier Usage:**

| Tier | Description | Used For |
|------|-------------|----------|
| 0.5 (50th) | Median sophomore | Elite teams' first backfill slot |
| 0.4 (40th) | Above-average starter | |
| 0.3 (30th) | Replacement level | Standard teams' first backfill slot |
| 0.2 (20th) | Below-average regular | Elite teams' second slot |
| 0.1 (10th) | Marginal player | Floor for all teams |

**Role-Based Masking:**
- Batter profiles have all pitching columns zeroed
- Pitcher profiles have all batting columns zeroed

---

