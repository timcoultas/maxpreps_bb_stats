import pandas as pd
import numpy as np
import os
import sys

# --- Import Config ---
try:
    from src.config import STAT_SCHEMA
except ImportError:
    try:
        from config import STAT_SCHEMA
    except ImportError:
        print("Error: Could not import STAT_SCHEMA.")
        sys.exit(1)

def create_generic_profiles():
    """
    Calculates the 'Median Sophomore' stats for Batters and Pitchers 
    based on historical data. Saves to data/reference/generic_players.csv.
    """
    
    # 1. Load History
    input_file = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print("Loading historical data to calculate generic baselines...")
    df = pd.read_csv(input_file)
    
    # Clean numeric columns
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df.columns]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 2. Filter for Sophomores (The "Generic" baseline)
    # We use Sophomores as the replacement level player.
    sophs = df[df['Class_Cleaned'] == 'Sophomore'].copy()
    
    if sophs.empty:
        print("Error: No sophomores found in history.")
        return

    profiles = []

    # --- Profile 1: Generic Batter ---
    # Defined as Sophomores with significant Plate Appearances
    batters = sophs[sophs['PA'] >= 10]
    if not batters.empty:
        generic_batter = {
            'Name': 'Generic Sophomore Batter',
            'Role': 'Batter',
            'Class_Cleaned': 'Sophomore',
            'Varsity_Year': 1, # Assume new to varsity
            'Projection_Method': 'Generic Baseline'
        }
        # Calculate median for every stat
        for col in stat_cols:
            generic_batter[col] = round(batters[col].median(), 2)
        
        # Ensure they qualify as a batter logic
        if generic_batter.get('AB', 0) < 15:
            generic_batter['AB'] = 15.0
            
        profiles.append(generic_batter)
    
    # --- Profile 2: Generic Pitcher ---
    # Defined as Sophomores with significant Innings Pitched
    pitchers = sophs[sophs['IP'] >= 5]
    if not pitchers.empty:
        generic_pitcher = {
            'Name': 'Generic Sophomore Pitcher',
            'Role': 'Pitcher',
            'Class_Cleaned': 'Sophomore',
            'Varsity_Year': 1,
            'Projection_Method': 'Generic Baseline'
        }
        # Calculate median
        for col in stat_cols:
            generic_pitcher[col] = round(pitchers[col].median(), 2)

        # Ensure they qualify as a pitcher logic
        if generic_pitcher.get('IP', 0) < 6:
            generic_pitcher['IP'] = 6.0

        profiles.append(generic_pitcher)

    # 3. Save
    df_profiles = pd.DataFrame(profiles)
    
    output_dir = os.path.join('data', 'reference')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'generic_players.csv')
    
    df_profiles.to_csv(output_path, index=False)
    print(f"Success. Saved generic profiles to: {output_path}")
    print(df_profiles[['Name', 'Role', 'PA', 'H', 'IP', 'ERA']].to_string(index=False))

if __name__ == "__main__":
    create_generic_profiles()