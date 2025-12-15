import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
# Handles imports whether running from root or src/
try:
    # Try importing ELITE_TEAMS. If it fails (old config), default to empty list.
    from src.utils.config import STAT_SCHEMA, PATHS
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []
        
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings

except ImportError:
    # Path hacking for local execution if not running as module
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA, PATHS
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []

    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings

def predict_2026_roster():
    """
    Generates a projected roster for the next season (2026) using hierarchical aging curves and dynamic backfilling.

    Context:
        Baseball Perspective: This is the "GM Mode" of the application. We are looking at our returning 
        players and asking, "How much better will they get?" We know a Freshman becoming a Sophomore 
        makes a bigger jump than a Junior becoming a Senior. We also know that rosters have holes. 
        Seniors graduate. This script fills those holes with "Generic Players" (call-ups from JV/Frosh) 
        based on the program's prestige. Elite programs reload (get average players); rebuilding programs 
        rebuild (get replacement-level players).

        Statistical Validity:
        1. Projection Logic: We use a "Hierarchical Lookup" to avoid Small Sample Size noise. We prefer 
           class-based aging curves (e.g., Freshman->Sophomore multiplier) over tenure-based ones because 
           tenure data suffers from "Survivor Bias" (only good players play as Freshmen, skewing the 
           "Year 1 to Year 2" curve).
        2. Imputation: Missing players are backfilled using percentile-based generic profiles. This maintains 
           the population distribution shape rather than filling with mean values (which reduces variance).

        Technical Implementation: 
        1. Hierarchical Lookup: This mimics a SQL `COALESCE` across multiple joined tables. 
           `COALESCE(Class_Multiplier, Specific_Multiplier, Tenure_Multiplier, 1.0)`.
        2. Dynamic Backfill: This is an Upsert/Imputation process. We identify gaps (COUNT < 9) and 
           append synthesized rows based on a configuration list (`ELITE_TEAMS`).

    Returns:
        None. Generates a CSV file.
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join(PATHS['processed'], 'history', 'aggregated_stats.csv')
    multipliers_path = os.path.join(PATHS['out_development_multipliers'], 'development_multipliers.csv')
    generic_path = os.path.join(PATHS['out_generic_players'], 'generic_players.csv')

    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found. Please run the ETL pipeline first.")
        return
    if not os.path.exists(multipliers_path):
        print(f"Error: {multipliers_path} not found. Please run the multiplier script first.")
        return
        
    print("Loading data...")
    # Loading the "Fact Table" (History) and "Dimension Tables" (Multipliers)
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
    # Schema Enforcement: Ensuring columns defined in config actually exist and are numeric
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    # Standardize names and calculate Varsity_Year (Identity Resolution)
    df_history = prepare_analysis_data(df_history)
    
    # --- 3. Isolate 2025 Roster ---
    # Filtering for the base year. SQL: WHERE Season_Year = 2025
    df_2025 = df_history[df_history['Season_Year'] == 2025].copy()
    
    # Fallback mechanism if 2025 data is missing (e.g., historical run)
    if df_2025.empty:
        max_year = df_history['Season_Year'].max()
        print(f"Warning: No 2025 data. Switching to {max_year}")
        df_2025 = df_history[df_history['Season_Year'] == max_year].copy()

    # Remove graduating Seniors
    # SQL: WHERE Class_Cleaned != 'Senior'
    df_2025 = df_2025[~df_2025['Class_Cleaned'].isin(['Senior'])]
    
    print(f"\nFound {len(df_2025)} returning players from base roster.")
    
    # --- 4. Apply Projections ---
    projections = []
    next_class_map = {'Freshman': 'Sophomore', 'Sophomore': 'Junior', 'Junior': 'Senior'}

    print("Projecting performance...")
    
    # Iterating through rows (Cursor). Vectorization is difficult here due to the complex lookup logic per player.
    for idx, player in df_2025.iterrows():
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown': continue 

        # --- HIERARCHICAL LOOKUP STRATEGY (UPDATED v2) ---
        # Prioritize Biological Age (Class) to avoid Survivor Bias
        
        target_tenure = f"Varsity_Year{curr_tenure}_to_Year{next_tenure}"
        target_specific = f"{curr_class}_Y{curr_tenure}_to_{next_class}_Y{next_tenure}"
        target_class = f"{curr_class}_to_{next_class}"
        
        applied_factors = None
        method = "None"
        
        # Priority Queue Logic (COALESCE)
        # Priority 1: Class (Biological Age) - Most robust sample size, least selection bias.
        if target_class in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_class]
            method = "Class (Age-Based)"
        # Priority 2: Specific Class + Tenure - High specificity, but lower sample size.
        elif target_specific in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_specific]
            method = "Class_Tenure (Specific)"
        # Priority 3: Tenure Only - Prone to survivor bias (only elite freshmen play Y1).
        elif target_tenure in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_tenure]
            method = "Tenure (Experience-Based)"
        else:
            method = "Default (1.0)"

        # Clone the record and update metadata
        proj = player.copy()
        proj['Season'] = 'Projected-Next'
        proj['Season_Cleaned'] = player['Season_Year'] + 1
        proj['Class_Cleaned'] = next_class
        proj['Varsity_Year'] = next_tenure
        proj['Projection_Method'] = method
        
        # Apply the Multipliers
        if method != "Default (1.0)":
            for col in stat_cols:
                if col in applied_factors and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    proj[col] = round(player[col] * multiplier, 2)
                    
                    # Sanity Caps (Business Rules)
                    # Preventing extrapolation errors (e.g., projecting 100 innings pitched).
                    if col == 'IP' and proj[col] > 70: 
                        proj[col] = 70.0
                    if col == 'APP' and proj[col] > 25: 
                        proj[col] = 25
        
        projections.append(proj)

    df_proj = pd.DataFrame(projections)
    
    if df_proj.empty:
        print("No projections generated.")
        return

    # --- 5. Assign Roles (Initial) ---
    # Boolean masking to identify role capabilities based on stats.
    df_proj['Is_Pitcher'] = df_proj['IP'].fillna(0) >= 5
    df_proj['Is_Batter'] = df_proj['AB'].fillna(0) >= 10

    # --- 6. Backfill Rosters with Tiered Generics (DYNAMIC) ---
    # Imputation Strategy for missing data (empty roster spots).
    if not df_generic.empty:
        print("\nChecking roster minimums (9 Batters, 6 Pitchers)...")
        
        filled_players = []
        teams = df_proj['Team'].unique()
        
        if not ELITE_TEAMS:
            print("Notice: ELITE_TEAMS list empty or not found in config. Using 20th %ile backfill for all.")

        for team in teams:
            team_roster = df_proj[df_proj['Team'] == team]
            n_batters = team_roster['Is_Batter'].sum()
            n_pitchers = team_roster['Is_Pitcher'].sum()
            
            # --- Powerhouse Logic ---
            # If team is in ELITE_TEAMS, they get 50th %ile (Average) replacements.
            # Otherwise, they get 20th %ile (Replacement Level) replacements.
            # Baseball Rationale: Good programs have "Next Man Up." Bad programs have holes.
            is_powerhouse = team in ELITE_TEAMS
            target_tier = 0.5 if is_powerhouse else 0.2
            method_label = 'Backfill (Elite)' if is_powerhouse else 'Backfill (Floor)'

            # Filter Pool for this specific team's needs
            # SQL: SELECT * FROM Generic WHERE Role = 'Batter' AND Percentile = target_tier
            bat_pool = df_generic[(df_generic['Role'] == 'Batter') & (df_generic['Percentile_Tier'] == target_tier)]
            pit_pool = df_generic[(df_generic['Role'] == 'Pitcher') & (df_generic['Percentile_Tier'] == target_tier)]
            
            # Fallback if specific tier missing (shouldn't happen if generic file is complete)
            if bat_pool.empty:
                 bat_pool = df_generic[df_generic['Role'] == 'Batter'].sort_values('Percentile_Tier', ascending=(not is_powerhouse))
            if pit_pool.empty:
                 pit_pool = df_generic[df_generic['Role'] == 'Pitcher'].sort_values('Percentile_Tier', ascending=(not is_powerhouse))

            # Add Batters (Imputation)
            if n_batters < 9 and not bat_pool.empty:
                needed = 9 - n_batters
                for i in range(needed):
                    template = bat_pool.iloc[i % len(bat_pool)].to_dict()
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Batter {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = True
                    new_player['Is_Pitcher'] = False
                    new_player['Projection_Method'] = method_label
                    
                    # Cleanup internal columns
                    for k in ['Role', 'Percentile_Tier']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)

            # Add Pitchers (Imputation)
            if n_pitchers < 6 and not pit_pool.empty:
                needed = 6 - n_pitchers
                for i in range(needed):
                    template = pit_pool.iloc[i % len(pit_pool)].to_dict()
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Pitcher {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = False
                    new_player['Is_Pitcher'] = True
                    new_player['Projection_Method'] = method_label
                    
                    for k in ['Role', 'Percentile_Tier']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)
                    
        if filled_players:
            print(f"Backfilling {len(filled_players)} generic player slots.")
            df_filled = pd.DataFrame(filled_players)
            df_proj = pd.concat([df_proj, df_filled], ignore_index=True)

    # --- 7. Calculate Ranks (Final) ---
    # Re-running the ranking engine on the final projected dataset
    df_proj = apply_advanced_rankings(df_proj)

    # --- 8. Save ---
    # Selecting columns for final output (Projection / View Definition)
    meta_cols_start = ['Team', 'Name',  'Season_Cleaned', 'Class_Cleaned', 'Varsity_Year', 'Projection_Method',  'Offensive_Rank_Team', 'Pitching_Rank_Team']
    meta_cols_end = [
        'Is_Batter', 'Is_Pitcher', 'Offensive_Rank',
        'Pitching_Rank', 'RC_Score', 'Pitching_Score'
    ]
    
    final_cols = [c for c in meta_cols_start if c in df_proj.columns] + \
                 [c for c in stat_cols if c in df_proj.columns] + \
                 [c for c in meta_cols_end if c in df_proj.columns]
                 
    df_proj = df_proj[final_cols]
    df_proj = df_proj.sort_values(['Team', 'Offensive_Rank_Team', 'Pitching_Rank_Team'])
    
    output_dir = PATHS['out_roster_prediction']
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    
    print(f"\nSuccess! Generated projected roster with {len(df_proj)} players.")
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    predict_2026_roster()