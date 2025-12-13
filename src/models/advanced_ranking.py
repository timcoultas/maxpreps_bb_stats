import pandas as pd
import numpy as np

def calculate_offensive_score(df):
    """
    Calculates a 'Runs Created' (RC) score for offensive ranking.

    Context:
        Baseball Context:
            Batting Average is dead. We don't care how often you hit the ball; we care how many 
            runs you produce. This function calculates "Runs Created" (RC), which answers the fundamental 
            question: "How many times did this player cross home plate or help a teammate cross home plate?" 
            It weighs getting on base (OBP) and hitting for power (Slugging) to find the true offensive contributors.

        Statistical Validity:
            Derived from Bill James's foundational "Runs Created" formula (Technical Version).
            Formula: $RC = \\frac{(H + BB) \\times TB}{AB + BB}$
            This metric provides a higher correlation with actual Team Runs Scored ($R^2 > .90$) 
            than Batting Average or OPS alone. It effectively converts distinct events (Walks, Doubles) 
            into a single currency: Runs.

        Technical Implementation:
            This is a Vectorized Calculation using Pandas (NumPy backend).
            1. We handle Missing Data (Imputation) by filling NaNs with 0 to prevent propagation errors.
            2. We derive intermediate columns (`Singles`, `Total Bases`) that aren't explicitly in the 
               source schema.
            3. We execute column-wise arithmetic operations, which is significantly more performant 
               than row-wise iteration (looping).

    Args:
        df (pd.DataFrame): DataFrame containing standard counting stats (H, BB, AB, 2B, 3B, HR).

    Returns:
        pd.Series: A float series representing the estimated Runs Created for each player.
    """
    # 1. Ensure required columns exist, filling with 0 if missing
    # Acts like COALESCE(col, 0)
    req_cols = ['H', 'BB', 'AB', '2B', '3B', 'HR']
    for col in req_cols:
        if col not in df.columns:
            df[col] = 0
            
    # 2. Calculate Total Bases (TB)
    # TB = 1B + 2*2B + 3*3B + 4*HR
    # Since 1B is rarely explicitly tracked, we derive it: H - (2B + 3B + HR)
    singles = df['H'] - (df['2B'] + df['3B'] + df['HR'])
    total_bases = singles + (2 * df['2B']) + (3 * df['3B']) + (4 * df['HR'])
    
    # 3. Calculate Components
    on_base_events = df['H'] + df['BB']
    opportunities = df['AB'] + df['BB']
    
    # 4. Calculate Runs Created
    # Handle division by zero for players with 0 AB/BB
    # Logic: CASE WHEN opportunities = 0 THEN 1 ELSE opportunities END
    rc = (on_base_events * total_bases) / opportunities.replace(0, 1)
    
    # 5. Handle Edge Case: Zero stats shouldn't be NaN
    rc = rc.fillna(0)
    
    return rc

def calculate_pitching_score(df):
    """
    Calculates a 'Dominance Score' for pitching ranking.

    Context:
        Baseball Context:
            We need to separate the "Inning Eaters" from the "Aces." This custom metric rewards 
            pitchers who can handle a heavy workload (IP) while actually suppressing the offense. 
            It penalizes Walks (free passes) and Earned Runs heavily. Think of it as a localized 
            version of Bill James's "Game Score," aggregated over a full season.

        Statistical Validity:
            A Weighted Composite Index.
            Formula: $Score = (1.5 \\times IP) + (1.0 \\times K) - (1.0 \\times BB) - (2.0 \\times ER)$
            - Weights are heuristic approximations of Run Value:
                - IP (Positive): Proxy for durability and trust.
                - K (Positive): Defense-Independent Pitching (DIPs) component.
                - BB/ER (Negative): Measurements of failure.

        Technical Implementation:
            Standard Linear Combination of columns.
            We use `fillna(0)` to handle cases where a player might have `IP` but `Null` Walks, 
            ensuring the arithmetic doesn't result in `NaN`.

    Args:
        df (pd.DataFrame): DataFrame containing IP, K, BB, ER.

    Returns:
        pd.Series: A float series representing the Dominance Score.
    """
    # 1. Ensure required columns exist
    req_cols = ['IP', 'K', 'BB', 'ER']
    for col in req_cols:
        if col not in df.columns:
            df[col] = 0

    # 2. Apply Weights
    # IP: Valuable. Rewards durability.
    # K:  Valuable. Rewards "stuff" and defense-independent success.
    # BB: Negative. Penalizes free passes.
    # ER: Negative. Penalizes failure to prevent scoring.
    
    score = (df['IP'] * 1.5) + \
            (df['K'] * 1.0) - \
            (df['BB'] * 1.0) - \
            (df['ER'] * 2.0)
            
    return score.fillna(0)

def apply_advanced_rankings(df_proj):
    """
    Main entry point to apply rankings to the projection DataFrame.
    Replaces the simple PA/IP ranking logic.

    Context:
        Baseball Context:
            This is the final sorting of the depth chart. After we project the stats, we need to 
            stack-rank the players to see who starts and who sits. We calculate the advanced metrics, 
            then assign a numerical rank (1, 2, 3...) both within the team and globally across the league.

        Technical Implementation:
            1. Transformation: Calls the scoring functions to append new feature columns (`RC_Score`, `Pitching_Score`).
            2. Window Function: Uses `groupby('Team')['Score'].rank()` to calculate partitioned rankings.
            3. Conditional Logic: Uses boolean indexing (`~df['Is_Batter']`) to force non-qualified players 
               to the bottom of the list (Rank 9999), effectively implementing a "Qualifying Standard" filter.
    """
    print("Applying Advanced Ranking Models (Runs Created & Dominance Score)...")
    
    # --- Offense ---
    # Calculate raw score
    df_proj['RC_Score'] = calculate_offensive_score(df_proj)
    
    # Global Rank (Higher Score is Better)
    # SQL: RANK() OVER (ORDER BY RC_Score DESC)
    df_proj['Offensive_Rank'] = df_proj['RC_Score'].rank(method='min', ascending=False).astype(int)
    
    # Team Rank
    # SQL: RANK() OVER (PARTITION BY Team ORDER BY RC_Score DESC)
    df_proj['Offensive_Rank_Team'] = df_proj.groupby('Team')['RC_Score'].rank(method='min', ascending=False).astype(int)

    # --- Pitching ---
    # Calculate raw score
    df_proj['Pitching_Score'] = calculate_pitching_score(df_proj)
    
    # Global Rank (Higher Score is Better)
    df_proj['Pitching_Rank'] = df_proj['Pitching_Score'].rank(method='min', ascending=False).astype(int)
    
    # Team Rank
    df_proj['Pitching_Rank_Team'] = df_proj.groupby('Team')['Pitching_Score'].rank(method='min', ascending=False).astype(int)

    # --- Penalties / Cleanup ---
    # Force non-batters/non-pitchers to the bottom of the list
    # Use a large number (9999) to ensure they are last
    
    # If a player is NOT a batter (e.g. strict Pitcher Only), set their Offensive Rank to 9999
    # Logic: UPDATE df SET Offensive_Rank = 9999 WHERE Is_Batter = False
    df_proj.loc[~df_proj['Is_Batter'], ['Offensive_Rank', 'Offensive_Rank_Team']] = 9999
    
    # If a player is NOT a pitcher, set their Pitching Rank to 9999
    df_proj.loc[~df_proj['Is_Pitcher'], ['Pitching_Rank', 'Pitching_Rank_Team']] = 9999

    return df_proj