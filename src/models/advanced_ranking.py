import pandas as pd
import numpy as np

def calculate_offensive_score(df):
    """
    Calculates a 'Runs Created' (RC) score for offensive ranking.
    
    UPDATES:
    1. Added safety checks for critical columns.
    """
    # 1. Ensure required columns exist, filling with 0 if missing
    req_cols = ['H', 'BB', 'AB', '2B', '3B', 'HR']
    for col in req_cols:
        if col not in df.columns:
            # REVIEW UPDATE: Log warning if critical column is missing entirely
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0
            
    # 2. Calculate Total Bases (TB)
    singles = df['H'] - (df['2B'] + df['3B'] + df['HR'])
    total_bases = singles + (2 * df['2B']) + (3 * df['3B']) + (4 * df['HR'])
    
    # 3. Calculate Components
    on_base_events = df['H'] + df['BB']
    opportunities = df['AB'] + df['BB']
    
    # 4. Calculate Runs Created
    rc = (on_base_events * total_bases) / opportunities.replace(0, 1)
    
    # 5. Handle Edge Case: Zero stats shouldn't be NaN
    rc = rc.fillna(0)
    
    return rc

def calculate_pitching_score(df):
    """
    Calculates a 'Dominance Score' for pitching ranking.
    """
    req_cols = ['IP', 'K', 'BB', 'ER']
    for col in req_cols:
        if col not in df.columns:
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0

    score = (df['IP'] * 1.5) + \
            (df['K'] * 1.0) - \
            (df['BB'] * 1.0) - \
            (df['ER'] * 2.0)
            
    return score.fillna(0)

def apply_advanced_rankings(df_proj):
    """
    Main entry point to apply rankings to the projection DataFrame.
    """
    print("Applying Advanced Ranking Models (Runs Created & Dominance Score)...")
    
    # --- Offense ---
    df_proj['RC_Score'] = calculate_offensive_score(df_proj)
    df_proj['Offensive_Rank'] = df_proj['RC_Score'].rank(method='min', ascending=False).astype(int)
    df_proj['Offensive_Rank_Team'] = df_proj.groupby('Team')['RC_Score'].rank(method='min', ascending=False).astype(int)

    # --- Pitching ---
    df_proj['Pitching_Score'] = calculate_pitching_score(df_proj)
    df_proj['Pitching_Rank'] = df_proj['Pitching_Score'].rank(method='min', ascending=False).astype(int)
    df_proj['Pitching_Rank_Team'] = df_proj.groupby('Team')['Pitching_Score'].rank(method='min', ascending=False).astype(int)

    # --- Penalties / Cleanup ---
    # REVIEW: We still force non-qualified players to bottom rank for sorting, 
    # but the aggregation scripts now ignore these ranks and use raw scores, solving the "Void".
    df_proj.loc[~df_proj['Is_Batter'], ['Offensive_Rank', 'Offensive_Rank_Team']] = 9999
    df_proj.loc[~df_proj['Is_Pitcher'], ['Pitching_Rank', 'Pitching_Rank_Team']] = 9999

    return df_proj