"""
extract_actuals.py

Extracts actual stats for a given year from aggregated_stats.csv and formats them
for comparison against projections. Adds the same ranking columns (RC_Score, 
Pitching_Score, team/league ranks) so we have apples-to-apples comparison.

Usage:
    python extract_actuals.py --year 2025
    
Output:
    data/output/backtest/2025_actual_stats.csv
"""

import pandas as pd
import numpy as np
import os
import sys
import argparse

# --- Import Config & Utils ---
try:
    from src.utils.config import STAT_SCHEMA, PATHS
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from src.utils.config import STAT_SCHEMA, PATHS
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings


def extract_actual_stats(year: int):
    """
    Extracts actual statistics for a given year and applies the same
    ranking calculations used in projections.
    
    Args:
        year: The season year to extract (e.g., 2025)
        
    Returns:
        DataFrame with actual stats and rankings
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join(PATHS['out_historical_stats'], 'aggregated_stats.csv')
    
    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found.")
        return None
    
    print(f"Loading historical data from {stats_path}...")
    df_history = pd.read_csv(stats_path)
    
    # --- 2. Prep Data ---
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    df_history = prepare_analysis_data(df_history)
    
    # --- 3. Filter for Target Year ---
    df_year = df_history[df_history['Season_Year'] == year].copy()
    
    if df_year.empty:
        print(f"Error: No data found for year {year}")
        return None
    
    print(f"Found {len(df_year)} player records for {year}")
    print(f"Teams represented: {df_year['Team'].nunique()}")
    
    # --- 4. Assign Roles ---
    df_year['Is_Pitcher'] = df_year['IP'].fillna(0) >= 5
    df_year['Is_Batter'] = df_year['AB'].fillna(0) >= 10
    
    # --- 5. Apply Rankings (same as projections) ---
    df_year = apply_advanced_rankings(df_year)
    
    # --- 6. Format Output ---
    # Add a marker column to distinguish from projections
    df_year['Data_Type'] = 'Actual'
    df_year['Season_Cleaned'] = year
    
    # Select columns to match projection output format
    meta_cols_start = ['Team', 'Name', 'Season_Cleaned', 'Class_Cleaned', 'Varsity_Year', 
                       'Data_Type', 'Offensive_Rank_Team', 'Pitching_Rank_Team']
    meta_cols_end = ['Is_Batter', 'Is_Pitcher', 'Offensive_Rank', 'Pitching_Rank', 
                     'RC_Score', 'Pitching_Score']
    
    final_cols = [c for c in meta_cols_start if c in df_year.columns] + \
                 [c for c in stat_cols if c in df_year.columns] + \
                 [c for c in meta_cols_end if c in df_year.columns]
    
    df_year = df_year[[c for c in final_cols if c in df_year.columns]]
    df_year = df_year.sort_values(['Team', 'Offensive_Rank_Team', 'Pitching_Rank_Team'])
    
    # --- 7. Save ---
    output_dir = os.path.join(PATHS['out_roster_prediction'], 'backtest')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{year}_actual_stats.csv')
    
    df_year.to_csv(output_path, index=False)
    
    print(f"\n[Extract Complete]")
    print(f"  - Players: {len(df_year)}")
    print(f"  - Batters (AB >= 10): {df_year['Is_Batter'].sum()}")
    print(f"  - Pitchers (IP >= 5): {df_year['Is_Pitcher'].sum()}")
    print(f"  - Saved to: {output_path}")
    
    return df_year


def main():
    parser = argparse.ArgumentParser(description="Extract actual stats for a given year")
    parser.add_argument('--year', type=int, default=2025, help='Year to extract (default: 2025)')
    
    args = parser.parse_args()
    
    extract_actual_stats(args.year)


if __name__ == "__main__":
    main()