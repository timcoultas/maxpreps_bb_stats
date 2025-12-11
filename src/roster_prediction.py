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
    1. Loads historical data & generic profiles.
    2. Forecasts 2026 stats for returning players.
    3. Backfills rosters with Tiered Generic Sophomores if teams are short ( <9 Batters, <6 Pitchers).
       - Uses "Best Available" generic strategy (50th %ile -> 10th %ile).
    4. Assigns Roles and Ranks (Global & Team).
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    multipliers_path = os.path.join('data', 'development_multipliers', 'development_multipliers.csv')
    generic_path = os.path.join('data', 'reference', 'generic_players.csv')

    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found. Please run the ETL pipeline first.")
        return
    if not os.path.exists(multipliers_path):
        print(f"Error: {multipliers_path} not found. Please run the multiplier script first.")
        return
        
    print("Loading data...")
    df_history = pd.read_csv(stats_path)
    df_multipliers = pd.read_csv(multipliers_path)
    df_multipliers.set_index('Transition', inplace=True)
    
    # Load Generics (if available)
    df_generic = pd.DataFrame()
    if os.path.exists(generic_path):
        df_generic = pd.read_csv(generic_path)
        print("Loaded generic player profiles for roster backfilling.")
    else:
        print("Warning: generic_players.csv not found. Rosters will NOT be backfilled.")

    # --- 2. Prep History (Centralized Logic) ---
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    # Standardize names and calculate Varsity_Year
    df_history = prepare_analysis_data(df_history)
    
    # --- 3. Isolate 2025 Roster ---
    df_2025 = df_history[df_history['Season_Year'] == 2025].copy()
    
    if df_2025.empty:
        max_year = df_history['Season_Year'].max()
        print(f"Warning: No 2025 data. Switching to {max_year}")
        df_2025 = df_history[df_history['Season_Year'] == max_year].copy()

    # Remove graduating Seniors
    df_2025 = df_2025[~df_2025['Class_Cleaned'].isin(['Senior'])]
    
    print(f"\nFound {len(df_2025)} returning players from base roster.")
    
    # --- 4. Apply Projections ---
    projections = []
    next_class_map = {'Freshman': 'Sophomore', 'Sophomore': 'Junior', 'Junior': 'Senior'}

    print("Projecting performance...")
    
    for idx, player in df_2025.iterrows():
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown': continue 

        # Hierarchical Lookup
        target = f"{curr_class}_Y{curr_tenure}_to_{next_class}_Y{next_tenure}"
        fallback = f"{curr_class}_to_{next_class}"
        
        applied_factors = None
        method = "None"
        
        if target in df_multipliers.index:
            applied_factors = df_multipliers.loc[target]
            method = "Class_Tenure"
        elif fallback in df_multipliers.index:
            applied_factors = df_multipliers.loc[fallback]
            method = "Class_Fallback"
        else:
            method = "Default (1.0)"

        proj = player.copy()
        proj['Season'] = 'Projected-Next'
        proj['Season_Cleaned'] = player['Season_Year'] + 1
        proj['Class_Cleaned'] = next_class
        proj['Varsity_Year'] = next_tenure
        proj['Projection_Method'] = method
        
        if method != "Default (1.0)":
            for col in stat_cols:
                if col in applied_factors and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    proj[col] = round(player[col] * multiplier, 2)
                    
                    # Sanity Caps
                    if col == 'IP' and proj[col] > 70: proj[col] = 70.0
                    if col == 'APP' and proj[col] > 25: proj[col] = 25
        
        projections.append(proj)

    df_proj = pd.DataFrame(projections)
    
    if df_proj.empty:
        print("No projections generated.")
        return

    # --- 5. Assign Roles (Initial) ---
    df_proj['Is_Pitcher'] = df_proj['IP'].fillna(0) >= 6
    df_proj['Is_Batter'] = df_proj['AB'].fillna(0) >= 15

    # --- 6. Backfill Rosters with Tiered Generics ---
    if not df_generic.empty:
        print("\nChecking roster minimums (9 Batters, 6 Pitchers)...")
        
        # Prepare Tiered Generics
        # Sort by Percentile DESCENDING (50th %ile first, then 40th...)
        # We want to give teams the "best available" replacement first.
        if 'Percentile_Tier' in df_generic.columns:
            gen_batters = df_generic[df_generic['Role'] == 'Batter'].sort_values('Percentile_Tier', ascending=False)
            gen_pitchers = df_generic[df_generic['Role'] == 'Pitcher'].sort_values('Percentile_Tier', ascending=False)
        else:
            # Fallback for old generic file format
            gen_batters = df_generic[df_generic['Role'] == 'Batter']
            gen_pitchers = df_generic[df_generic['Role'] == 'Pitcher']

        filled_players = []
        teams = df_proj['Team'].unique()
        
        for team in teams:
            team_roster = df_proj[df_proj['Team'] == team]
            n_batters = team_roster['Is_Batter'].sum()
            n_pitchers = team_roster['Is_Pitcher'].sum()
            
            # Add Batters
            if n_batters < 9 and not gen_batters.empty:
                needed = 9 - n_batters
                for i in range(needed):
                    # Cycle through tiers: i=0 -> 50th, i=1 -> 40th, etc.
                    template_idx = i % len(gen_batters)
                    template = gen_batters.iloc[template_idx].to_dict()
                    
                    new_player = template.copy()
                    new_player['Team'] = team
                    # Distinct Name
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Batter {i+1} ({pct_label}th)"
                    
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = True
                    new_player['Is_Pitcher'] = False
                    new_player['Projection_Method'] = 'Roster Backfill'
                    
                    # Clean metadata keys
                    for k in ['Role', 'Percentile_Tier']:
                        new_player.pop(k, None)
                        
                    filled_players.append(new_player)

            # Add Pitchers
            if n_pitchers < 6 and not gen_pitchers.empty:
                needed = 6 - n_pitchers
                for i in range(needed):
                    template_idx = i % len(gen_pitchers)
                    template = gen_pitchers.iloc[template_idx].to_dict()
                    
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Pitcher {i+1} ({pct_label}th)"
                    
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = False
                    new_player['Is_Pitcher'] = True
                    new_player['Projection_Method'] = 'Roster Backfill'
                    
                    for k in ['Role', 'Percentile_Tier']:
                        new_player.pop(k, None)
                        
                    filled_players.append(new_player)
                    
        if filled_players:
            print(f"Backfilling {len(filled_players)} generic player slots.")
            df_filled = pd.DataFrame(filled_players)
            df_proj = pd.concat([df_proj, df_filled], ignore_index=True)

    # --- 7. Calculate Ranks (Final) ---
    df_proj['PA_Filled'] = df_proj['PA'].fillna(0)
    df_proj['IP_Filled'] = df_proj['IP'].fillna(0)

    # Global Ranks
    df_proj['Offensive_Rank'] = df_proj['PA_Filled'].rank(method='min', ascending=False).astype(int)
    df_proj['Pitching_Rank'] = df_proj['IP_Filled'].rank(method='min', ascending=False).astype(int)

    # Team Ranks
    df_proj['Offensive_Rank_Team'] = df_proj.groupby('Team')['PA_Filled'].rank(method='min', ascending=False).astype(int)
    df_proj['Pitching_Rank_Team'] = df_proj.groupby('Team')['IP_Filled'].rank(method='min', ascending=False).astype(int)
    
    # Penalties
    df_proj.loc[~df_proj['Is_Batter'], ['Offensive_Rank', 'Offensive_Rank_Team']] = 9999
    df_proj.loc[~df_proj['Is_Pitcher'], ['Pitching_Rank', 'Pitching_Rank_Team']] = 9999

    # Clean up
    df_proj.drop(columns=['PA_Filled', 'IP_Filled', 'Role'], inplace=True, errors='ignore')

    # --- 8. Save ---
    cols_order = [
        'Offensive_Rank', 'Offensive_Rank_Team', 
        'Pitching_Rank', 'Pitching_Rank_Team',
        'Is_Batter', 'Is_Pitcher',
        'Name', 'Team', 'Season_Cleaned', 'Class_Cleaned', 'Varsity_Year', 'Projection_Method'
    ] + stat_cols
    
    final_cols = [c for c in cols_order if c in df_proj.columns]
    df_proj = df_proj[final_cols].sort_values('Offensive_Rank')
    
    output_dir = os.path.join('data', 'output', 'roster_prediction')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    
    print(f"\nSuccess! Generated projected roster with {len(df_proj)} players.")
    print(f"Saved to: {output_path}")
    
    # Preview
    if not df_proj.empty:
        print("\n--- Top 5 Projected Hitters (by PA) ---")
        print(df_proj[['Offensive_Rank', 'Offensive_Rank_Team', 'Name', 'Team', 'PA']].head().to_string(index=False))

if __name__ == "__main__":
    predict_2026_roster()