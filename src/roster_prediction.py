import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
# Handles imports whether running from root or src/
try:
    from src.config import STAT_SCHEMA
    from src.utils import prepare_analysis_data
except ImportError:
    try:
        from config import STAT_SCHEMA
        from utils import prepare_analysis_data
    except ImportError:
        print("Error: Could not import config or utils. Please ensure src/config.py and src/utils.py exist.")
        sys.exit(1)

def predict_2026_roster():
    """
    1. Loads historical data.
    2. Standardizes it (Varsity Tenure, Match Keys) using utils.py.
    3. Forecasts 2026 stats using the 'Class_Tenure' multipliers.
    4. Assigns Offensive and Pitching Ranks.
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    multipliers_path = os.path.join('data', 'development_multipliers', 'development_multipliers.csv')
    
    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found. Please run the ETL pipeline first.")
        return
    if not os.path.exists(multipliers_path):
        print(f"Error: {multipliers_path} not found. Please run the multiplier script first.")
        return
        
    print("Loading data...")
    df_history = pd.read_csv(stats_path)
    df_multipliers = pd.read_csv(multipliers_path)
    
    # Set index for fast lookup: Transition -> Row
    df_multipliers.set_index('Transition', inplace=True)
    
    # --- 2. Prep History & Calculate Tenure (Centralized Logic) ---
    
    # Numeric conversion based on Schema (stats only)
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    # Use the utility to add Season_Year, Match_Names, and Varsity_Year
    # This ensures "Varsity Year" is calculated exactly the same way as in development_multipliers.py
    df_history = prepare_analysis_data(df_history)
    
    # --- 3. Isolate the 2025 Roster (The Base for Projection) ---
    # We only want players who played in 2025. 
    # Note: Ensure your data contains 2025. If testing with 2024 data, adjust this filter.
    df_2025 = df_history[df_history['Season_Year'] == 2025].copy()
    
    if df_2025.empty:
        print("Warning: No 2025 data found. Checking for most recent year...")
        max_year = df_history['Season_Year'].max()
        print(f"Switching base year to {max_year}")
        df_2025 = df_history[df_history['Season_Year'] == max_year].copy()

    # Remove graduating Seniors
    # We remove anyone who was a Senior in the base year.
    df_2025 = df_2025[~df_2025['Class_Cleaned'].isin(['Senior'])]
    
    print(f"\nFound {len(df_2025)} returning players from base roster.")
    
    # --- 4. Apply Projections ---
    projections = []
    
    # Class progression map
    next_class_map = {
        'Freshman': 'Sophomore',
        'Sophomore': 'Junior',
        'Junior': 'Senior'
    }

    print("Projecting next season performance...")
    
    for idx, player in df_2025.iterrows():
        # Current State
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        
        # Future State
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown':
            continue # Skip if we can't determine next class

        # --- KEY STRATEGY: Hierarchical Lookup ---
        # 1. Try Specific Slice: "Freshman_Y1_to_Sophomore_Y2" (Class + Tenure)
        # 2. Fallback Slice: "Freshman_to_Sophomore" (Standard Class progression)
        
        target_transition = f"{curr_class}_Y{curr_tenure}_to_{next_class}_Y{next_tenure}"
        fallback_transition = f"{curr_class}_to_{next_class}"
        
        applied_factors = None
        method = "None"
        
        if target_transition in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_transition]
            method = "Class_Tenure"
        elif fallback_transition in df_multipliers.index:
            applied_factors = df_multipliers.loc[fallback_transition]
            method = "Class_Fallback"
        else:
            # If no data exists (e.g., Rare combo), assume no growth (1.0)
            method = "Default (1.0)"

        # Create Projected Record
        proj = player.copy()
        proj['Season'] = 'Projected-Next'
        proj['Season_Cleaned'] = player['Season_Year'] + 1
        proj['Season_Year'] = player['Season_Year'] + 1
        proj['Class'] = next_class
        proj['Class_Cleaned'] = next_class
        proj['Varsity_Year'] = next_tenure
        proj['Projection_Method'] = method
        
        # Apply Multipliers
        if method != "Default (1.0)":
            for col in stat_cols:
                # Only apply multiplier if the stat exists in multipliers AND the player has the stat
                if col in applied_factors and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    
                    # Apply logic
                    projected_val = player[col] * multiplier
                    proj[col] = round(projected_val, 2)
                    
                    # --- SANITY CAPS ---
                    # Logic Check: Innings Pitched shouldn't exceed reasonable HS max (~70)
                    if col == 'IP' and proj[col] > 70:
                        proj[col] = 70.0
                        
                    # Logic Check: Games Played (APP) shouldn't exceed season length (~25)
                    if col == 'APP' and proj[col] > 25:
                        proj[col] = 25
        
        projections.append(proj)

    # Convert to DataFrame
    df_proj = pd.DataFrame(projections)
    
    if df_proj.empty:
        print("No projections generated.")
        return

    # --- 5. Generate Ranks ---
    # We rank strictly within the 2026 Projected Population
    
    # Offensive Rank: Based on Plate Appearances (PA) Descending
    # If PA is NaN, fill with 0 for ranking purposes
    df_proj['PA_Filled'] = df_proj['PA'].fillna(0)
    df_proj['Offensive_Rank'] = df_proj['PA_Filled'].rank(method='min', ascending=False).astype(int)
    
    # Pitching Rank: Based on Innings Pitched (IP) Descending
    df_proj['IP_Filled'] = df_proj['IP'].fillna(0)
    df_proj['Pitching_Rank'] = df_proj['IP_Filled'].rank(method='min', ascending=False).astype(int)
    
    # Drop helper columns
    df_proj.drop(columns=['PA_Filled', 'IP_Filled'], inplace=True)

    # --- 6. Save Results ---
    # Select clean columns for output order
    cols_order = [
        'Offensive_Rank', 'Pitching_Rank',
        'Name', 'Team', 'Season_Cleaned', 'Class_Cleaned', 'Varsity_Year', 'Projection_Method'
    ] + stat_cols
    
    # Filter only columns that exist
    final_cols = [c for c in cols_order if c in df_proj.columns]
    df_proj = df_proj[final_cols]
    
    # Sort by Offensive Rank by default
    df_proj = df_proj.sort_values('Offensive_Rank')
    
    # --- UPDATED OUTPUT PATH ---
    output_dir = os.path.join('data', 'output', 'roster_prediction')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    
    print(f"\nSuccess! Generated projected roster with {len(df_proj)} players.")
    print(f"Saved to: {output_path}")
    
    # Preview Top 5 Hitters
    if not df_proj.empty:
        print("\n--- Top 5 Projected Hitters (by PA) ---")
        print(df_proj[['Offensive_Rank', 'Name', 'Class_Cleaned', 'Varsity_Year', 'PA', 'H', 'HR', 'Projection_Method']].head().to_string(index=False))

    # Preview Top 5 Pitchers
    if not df_proj.empty:
        print("\n--- Top 5 Projected Pitchers (by IP) ---")
        pitchers = df_proj.sort_values('Pitching_Rank').head()
        print(pitchers[['Pitching_Rank', 'Name', 'Class_Cleaned', 'Varsity_Year', 'IP', 'ERA', 'K_P']].to_string(index=False))

if __name__ == "__main__":
    predict_2026_roster()