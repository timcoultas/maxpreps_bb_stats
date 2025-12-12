import pandas as pd
import numpy as np

def calculate_offensive_score(df):
    """
    Calculates a 'Runs Created' (RC) score for offensive ranking.
    RC is a superior metric to PA because it balances getting on base 
    with total bases (power).
    
    Formula: RC = ((H + BB) * TB) / (AB + BB)
    """
    # 1. Ensure required columns exist, filling with 0 if missing
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
    rc = (on_base_events * total_bases) / opportunities.replace(0, 1)
    
    # 5. Handle Edge Case: Zero stats shouldn't be NaN
    rc = rc.fillna(0)
    
    return rc

def calculate_pitching_score(df):
    """
    Calculates a 'Dominance Score' for pitching ranking.
    This balances Volume (IP) with Efficiency (K/BB/ER).
    
    Formula modeled after Fantasy Points/Game Score:
    Score = (IP * 1.5) + (K * 1.0) - (BB * 1.0) - (ER * 2.0)
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
    """
    print("Applying Advanced Ranking Models (Runs Created & Dominance Score)...")
    
    # --- Offense ---
    # Calculate raw score
    df_proj['RC_Score'] = calculate_offensive_score(df_proj)
    
    # Global Rank (Higher Score is Better)
    df_proj['Offensive_Rank'] = df_proj['RC_Score'].rank(method='min', ascending=False).astype(int)
    
    # Team Rank
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
    df_proj.loc[~df_proj['Is_Batter'], ['Offensive_Rank', 'Offensive_Rank_Team']] = 9999
    
    # If a player is NOT a pitcher, set their Pitching Rank to 9999
    df_proj.loc[~df_proj['Is_Pitcher'], ['Pitching_Rank', 'Pitching_Rank_Team']] = 9999

    return df_proj