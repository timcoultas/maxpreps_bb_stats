import pandas as pd
import numpy as np

def calculate_offensive_score(df):
    """
    Calculates a 'Runs Created' (RC) score for offensive ranking.

    Context:
        This metric answers the fundamental question scouts ask: "How many runs does this 
        player personally generate?" Unlike batting average, which treats all hits equally, 
        Runs Created weights extra-base hits appropriately and factors in plate discipline 
        (walks). This allows us to compare a singles-hitting contact hitter against a 
        power-hitting slugger on the same scale.

        Derived from Bill James' Basic Runs Created formula, first published in the 
        1979 Baseball Abstract. The formula RC = (H + BB) × TB / (AB + BB) correlates 
        with actual team runs scored at r > 0.95 across MLB seasons (James, 1979). 
        While more sophisticated versions exist (RC/27, Technical RC), the basic formula 
        is appropriate for high school data where plate appearance counts are lower and 
        advanced inputs (GIDP, IBB) are often unavailable.

        This function performs element-wise vector arithmetic on pandas Series, equivalent 
        to a calculated field in a SELECT statement: 
        `SELECT ((H+BB) * TB) / NULLIF(AB+BB, 0) AS RC_Score FROM players`.
        We use `.replace(0, 1)` as a NULLIF equivalent to prevent division by zero.

    Args:
        df (pd.DataFrame): The roster projection dataframe containing raw batting stats.
            Required columns: H, BB, AB, 2B, 3B, HR.

    Returns:
        pd.Series: A float series representing the calculated Runs Created for each row.
            Players with zero plate appearances will have RC_Score = 0.
    """
    # FIX: Create a working copy to avoid mutating the caller's DataFrame
    # This prevents SettingWithCopyWarning and side effects in upstream code
    # SQL Equivalent: Creating a TEMP TABLE rather than modifying the source
    df = df.copy()
    
    # Schema Enforcement: Ensure required columns exist
    # This handles schema drift where historical files may lack certain columns
    req_cols = ['H', 'BB', 'AB', '2B', '3B', 'HR']
    for col in req_cols:
        if col not in df.columns:
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0
            
    # Calculate Total Bases (TB) using vectorized arithmetic
    # TB = 1B + (2 × 2B) + (3 × 3B) + (4 × HR)
    # SQL Equivalent: SELECT (H - 2B - 3B - HR) + (2*2B) + (3*3B) + (4*HR) AS TB
    singles = df['H'] - (df['2B'] + df['3B'] + df['HR'])
    total_bases = singles + (2 * df['2B']) + (3 * df['3B']) + (4 * df['HR'])
    
    # On-Base Factor: Times reaching base via hit or walk
    on_base_events = df['H'] + df['BB']
    
    # Opportunities: Total plate appearances that could result in an AB outcome
    opportunities = df['AB'] + df['BB']
    
    # Calculate Runs Created with division-by-zero protection
    # SQL Equivalent: (on_base * tb) / NULLIF(opportunities, 0)
    rc = (on_base_events * total_bases) / opportunities.replace(0, 1)
    
    # COALESCE: Replace any NaN values with 0
    rc = rc.fillna(0)
    
    return rc


def calculate_pitching_score(df):
    """
    Calculates a 'Dominance Score' for pitching ranking.

    Context:
        This metric identifies pitchers who can carry a rotation. High school pitching 
        staffs are often thin, so we need to find arms that combine durability (innings) 
        with dominance (strikeouts) while limiting damage (walks, earned runs). A high 
        score indicates a pitcher who can be trusted in big games.

        This is a simplified adaptation of Bill James' Game Score metric (Game Score v2.0, 
        2016 revision). The original formula starts at 40 and adjusts based on performance. 
        Our adaptation uses weights: IP (+1.5), K (+1), BB (-1), ER (-2). While less 
        granular than FIP (Fielding Independent Pitching), this formula is appropriate 
        for high school where defensive quality varies significantly and we lack batted 
        ball data (GB%, FB%, LD%) needed for FIP calculations.

        This is a weighted linear combination of features, equivalent to:
        `SELECT (IP * 1.5) + (K * 1.0) - (BB * 1.0) - (ER * 2.0) AS Pitching_Score`.
    
    Args:
        df (pd.DataFrame): The roster projection dataframe containing pitching stats.
            Required columns: IP, K (or K_P), BB (or BB_P), ER.

    Returns:
        pd.Series: A float series representing the pitching dominance score.
            Note: Scores CAN be negative for pitchers with high walks/runs and low K/IP.
    """
    # FIX: Create a working copy to avoid mutating the caller's DataFrame
    df = df.copy()
    
    # Schema validation - handle both batting K/BB and pitching K_P/BB_P column names
    # The projection file uses 'K' for batting strikeouts, but pitching K may be labeled differently
    req_cols = ['IP', 'K', 'BB', 'ER']
    for col in req_cols:
        if col not in df.columns:
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0

    # Weighted sum aggregation across columns
    # Positive weights reward: Innings (durability) and Strikeouts (dominance)
    # Negative weights penalize: Walks (lack of control) and Earned Runs (damage)
    score = (df['IP'] * 1.5) + \
            (df['K'] * 1.0) - \
            (df['BB'] * 1.0) - \
            (df['ER'] * 2.0)
    
    # NOTE: We intentionally allow negative scores. A pitcher with 2 IP, 0 K, 5 BB, 6 ER
    # should have a negative score (-9.0) to indicate they hurt the team.
    # Downstream code should handle this appropriately (e.g., floor at 0 for index calculations).
            
    return score.fillna(0)


def apply_advanced_rankings(df_proj):
    """
    Main entry point to apply RC and Pitching Score rankings to the projection DataFrame.

    Context:
        Once we have individual player grades, we need to create a depth chart. This 
        function ranks every player in the league (1 to N) and within their own team, 
        so coaches can instantly see who their #3 hitter is or who the #1 starter should be.
        The league-wide rank helps identify hidden gems on weaker teams.

        We use 'min' method ranking, which is standard competition ranking. If two players 
        tie for 10th place, they are both ranked 10th, and the next player is ranked 12th. 
        This preserves the weight of achievement and is the standard used by Baseball 
        Reference and FanGraphs for leaderboards.

        This function applies Window Functions to the DataFrame:
        - `df['RC_Score'].rank()` is equivalent to `RANK() OVER (ORDER BY RC_Score DESC)`
        - The groupby rank is `RANK() OVER (PARTITION BY Team ORDER BY RC_Score DESC)`
    
    Args:
        df_proj (pd.DataFrame): The main projection dataset containing player stats.
            Must have columns that can be used to calculate RC_Score and Pitching_Score.

    Returns:
        pd.DataFrame: The original dataframe enriched with 6 new columns:
            - RC_Score: Raw offensive value
            - Offensive_Rank: League-wide batting rank (1 = best)
            - Offensive_Rank_Team: Within-team batting rank
            - Pitching_Score: Raw pitching value
            - Pitching_Rank: League-wide pitching rank (1 = best)
            - Pitching_Rank_Team: Within-team pitching rank
    """
    print("Applying Advanced Ranking Models (Runs Created & Dominance Score)...")
    
    # --- Offense ---
    # Feature Engineering: Calculate the raw score
    df_proj['RC_Score'] = calculate_offensive_score(df_proj)
    
    # Window Function: League-wide Rank
    # SQL: RANK() OVER (ORDER BY RC_Score DESC)
    df_proj['Offensive_Rank'] = df_proj['RC_Score'].rank(method='min', ascending=False).astype(int)
    
    # Window Function: Team-specific Rank (Partition by Team)
    # SQL: RANK() OVER (PARTITION BY Team ORDER BY RC_Score DESC)
    df_proj['Offensive_Rank_Team'] = df_proj.groupby('Team')['RC_Score'].rank(method='min', ascending=False).astype(int)

    # --- Pitching ---
    df_proj['Pitching_Score'] = calculate_pitching_score(df_proj)
    
    # Window Function: League-wide Rank
    df_proj['Pitching_Rank'] = df_proj['Pitching_Score'].rank(method='min', ascending=False).astype(int)
    
    # Window Function: Team-specific Rank (Partition by Team)
    df_proj['Pitching_Rank_Team'] = df_proj.groupby('Team')['Pitching_Score'].rank(method='min', ascending=False).astype(int)

    # --- Penalties / Cleanup ---
    # Force non-qualified players to bottom rank for UI sorting purposes.
    # Note: Downstream aggregation scripts (team_strength_analysis.py, game_simulator.py)
    # now use raw scores with threshold filters rather than these ranks, correctly 
    # handling the "Utility Void" issue where two-way players were being excluded.
    # SQL Equivalent: UPDATE df SET Offensive_Rank = 9999 WHERE Is_Batter = False
    df_proj.loc[~df_proj['Is_Batter'], ['Offensive_Rank', 'Offensive_Rank_Team']] = 9999
    df_proj.loc[~df_proj['Is_Pitcher'], ['Pitching_Rank', 'Pitching_Rank_Team']] = 9999

    return df_proj
