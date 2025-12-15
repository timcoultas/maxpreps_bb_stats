import pandas as pd
import numpy as np

def calculate_offensive_score(df):
    """
    Calculates a 'Runs Created' (RC) score for offensive ranking.

    Context:
        Baseball Perspective: This is the "Moneyball" metric. We move beyond batting average because 
        a single is not equal to a home run. We want to know: "How many runs is this player personally 
        responsible for manufacturing?" It rewards getting on base and driving the ball for power, 
        stripping away the context of teammates (like RBIs do).

        Statistical Validity: Derived from Bill James' basic Runs Created formula: 
        RC = (On-Base Factor * Slugging Factor) / Opportunities.
        Specifically: TB x (H + BB) / (AB + BB). This correlates to actual team runs scored at r > .95.

        Technical Implementation: This is a computed column (Feature Engineering). We are performing 
        element-wise vector arithmetic on pandas Series. It's equivalent to a calculated field in a 
        SELECT statement: `SELECT ((H+BB) * TB) / (AB+BB) AS RC_Score`.

    Args:
        df (pd.DataFrame): The roster projection dataframe containing raw stats.

    Returns:
        pd.Series: A float series representing the calculated Runs Created for each row.
    """
    # 1. Ensure required columns exist, filling with 0 if missing
    # Data Validation / Schema Enforcement
    req_cols = ['H', 'BB', 'AB', '2B', '3B', 'HR']
    for col in req_cols:
        if col not in df.columns:
            # REVIEW UPDATE: Log warning if critical column is missing entirely
            # Handling Schema Drift
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0
            
    # 2. Calculate Total Bases (TB)
    # Vectorized arithmetic (Columnar operation)
    singles = df['H'] - (df['2B'] + df['3B'] + df['HR'])
    total_bases = singles + (2 * df['2B']) + (3 * df['3B']) + (4 * df['HR'])
    
    # 3. Calculate Components
    on_base_events = df['H'] + df['BB']
    opportunities = df['AB'] + df['BB']
    
    # 4. Calculate Runs Created
    # Handling Division by Zero using .replace(0, 1) to prevent NaN explosion
    # SQL Equivalent: NULLIF(AB + BB, 0)
    rc = (on_base_events * total_bases) / opportunities.replace(0, 1)
    
    # 5. Handle Edge Case: Zero stats shouldn't be NaN
    # SQL Equivalent: COALESCE(rc, 0)
    rc = rc.fillna(0)
    
    return rc

def calculate_pitching_score(df):
    """
    Calculates a 'Dominance Score' for pitching ranking.

    Context:
        Baseball Perspective: We are looking for "Ace Potential." This simple formula rewards the 
        two things a pitcher controls most: Innings (durability) and Strikeouts (dominance), while 
        punishing walks and earned runs. It is roughly based on the "Game Score" concept, designed 
        to separate the staff aces from the inning-eaters.

        Statistical Validity: A simplified version of Bill James' Game Score v2.0. 
        Formula weights: IP (+1.5), K (+1), BB (-1), ER (-2).
        While less complex than FIP (Fielding Independent Pitching), it effectively ranks value 
        in a high school context where defense is variable.

        Technical Implementation: Another computed column. We use weighted linear combination 
        of features.
    
    Args:
        df (pd.DataFrame): The roster projection dataframe.

    Returns:
        pd.Series: A float series representing the pitching dominance score.
    """
    req_cols = ['IP', 'K', 'BB', 'ER']
    # Schema validation loop
    for col in req_cols:
        if col not in df.columns:
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0

    # Weighted Sum aggregation across columns
    score = (df['IP'] * 1.5) + \
            (df['K'] * 1.0) - \
            (df['BB'] * 1.0) - \
            (df['ER'] * 2.0)
            
    return score.fillna(0)

def apply_advanced_rankings(df_proj):
    """
    Main entry point to apply rankings to the projection DataFrame.

    Context:
        Baseball Perspective: Once we have the raw "grades" (RC and Dominance Score), we need to 
        stack the board. This function ranks every player in the league from 1 to N. It also 
        ranks them within their own team, so we instantly know who the #3 hitter is or who the 
        #1 starter is.

        Statistical Validity: We use 'min' method ranking. If two players tie for 10th, they are 
        both ranked 10th, and the next player is 12th. This is standard competition ranking 
        to preserve the weight of the achievement.

        Technical Implementation: This acts as a Window Function.
        `df['RC_Score'].rank()` is equivalent to `RANK() OVER (ORDER BY RC_Score DESC)`.
        The groupby rank is `RANK() OVER (PARTITION BY Team ORDER BY RC_Score DESC)`.
    
    Args:
        df_proj (pd.DataFrame): The main projection dataset.

    Returns:
        pd.DataFrame: The original dataframe enriched with 6 new ranking columns.
    """
    print("Applying Advanced Ranking Models (Runs Created & Dominance Score)...")
    
    # --- Offense ---
    # Feature Engineering: adding the raw score
    df_proj['RC_Score'] = calculate_offensive_score(df_proj)
    
    # Window Function: League-wide Rank
    df_proj['Offensive_Rank'] = df_proj['RC_Score'].rank(method='min', ascending=False).astype(int)
    
    # Window Function: Team-specific Rank (Partition by Team)
    df_proj['Offensive_Rank_Team'] = df_proj.groupby('Team')['RC_Score'].rank(method='min', ascending=False).astype(int)

    # --- Pitching ---
    df_proj['Pitching_Score'] = calculate_pitching_score(df_proj)
    
    # Window Function: League-wide Rank
    df_proj['Pitching_Rank'] = df_proj['Pitching_Score'].rank(method='min', ascending=False).astype(int)
    
    # Window Function: Team-specific Rank (Partition by Team)
    df_proj['Pitching_Rank_Team'] = df_proj.groupby('Team')['Pitching_Score'].rank(method='min', ascending=False).astype(int)

    # --- Penalties / Cleanup ---
    # REVIEW: We still force non-qualified players to bottom rank for sorting UI purposes, 
    # but the downstream aggregation scripts now ignore these ranks and use raw scores, 
    # correctly handling the "Utility Void" issue identified in review.
    # SQL Equivalent: UPDATE df SET Offensive_Rank = 9999 WHERE Is_Batter = False
    df_proj.loc[~df_proj['Is_Batter'], ['Offensive_Rank', 'Offensive_Rank_Team']] = 9999
    df_proj.loc[~df_proj['Is_Pitcher'], ['Pitching_Rank', 'Pitching_Rank_Team']] = 9999

    return df_proj