import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
# Handles imports whether running from root or src/
try:
    from src.utils.config import STAT_SCHEMA
    from src.utils.config import PATHS
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings
except ImportError:
    # Path hacking for local execution if not running as module
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA
    from src.utils.config import PATHS
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings

def predict_2026_roster():
    """
    Generates a projected roster for the next season (2026) by applying development multipliers 
    to returning players and backfilling gaps with generic replacement-level players.

    Context:
        Baseball Context:
            This is the GM's "War Room" session. The season is over, the Seniors have turned in 
            their jerseys, and we need to answer the big question: "Can we win next year?" 
            We take every returning player, add a year of muscle and experience (applying the 
            Multipliers we calculated), and put them on the depth chart. If we don't have 
            enough players (e.g., we only have 2 returning pitchers), we simulate "calling up" 
            players from the JV squad (Generic Profiles) to ensure we can field a legal team.

        Statistical Validity:
            1. Projection Method: Deterministic extrapolation based on historical cohort analysis. 
               Formula: $Stat_{t+1} = Stat_{t} \times Multiplier_{Transition}$.
            2. Imputation Strategy: Uses "Tiered Replacement Level" imputation for missing roster spots. 
               Instead of filling with zeros or means, we fill with specific quantiles (50th, 40th... 
               10th percentile) to simulate the diminishing returns of digging deeper into the 
               depth chart (the 3rd string catcher is likely worse than the starter).
            3. Ranking: Generates ordinal rankings (1 to N) within teams and globally to allow 
               for relative comparison.

        Technical Implementation:
            This is the Inference Engine / Application Layer.
            1. Data Loading: Ingests the Feature Store (History) and Model Coefficients (Multipliers).
            2. Filtering: Conceptually executes `DELETE FROM roster WHERE Class = 'Senior'`.
            3. Transformation: Iterates through rows, performs a Key-Value Lookup for the correct 
               multiplier (Coefficient), and computes the projected values.
            4. Backfilling: Checks row counts (`COUNT(*)`) per team. If below threshold, performs 
               a `UNION ALL` with records from the Generic Profiles reference table.
            5. Ranking: Calculates `RANK() OVER (PARTITION BY Team ORDER BY Stat)` for depth charts.
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join(PATHS['processed'], 'history', 'aggregated_stats.csv')
    multipliers_path = os.path.join(PATHS['output'], 'development_multipliers', 'development_multipliers.csv')
    generic_path = os.path.join(PATHS['output'], 'generic_players', 'generic_players.csv')

    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found. Please run the ETL pipeline first.")
        return
    if not os.path.exists(multipliers_path):
        print(f"Error: {multipliers_path} not found. Please run the multiplier script first.")
        return
        
    print("Loading data...")
    # Loading the "Fact Table" (History) and "Lookup Tables" (Multipliers, Generics)
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
    
    # Standardize names and calculate Varsity_Year (Identity Resolution)
    df_history = prepare_analysis_data(df_history)
    
    # --- 3. Isolate 2025 Roster ---
    # Filtering for the current state (t=0)
    df_2025 = df_history[df_history['Season_Year'] == 2025].copy()
    
    if df_2025.empty:
        max_year = df_history['Season_Year'].max()
        print(f"Warning: No 2025 data. Switching to {max_year}")
        df_2025 = df_history[df_history['Season_Year'] == max_year].copy()

    # Remove graduating Seniors
    # Logic: DELETE FROM df WHERE Class = 'Senior'
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

        # Hierarchical Lookup Logic (Coalesce)
        # 1. Try Specific (Class + Tenure): "Sophomore Year 2 -> Junior Year 3"
        # 2. Try Generic (Class only): "Sophomore -> Junior"
        # 3. Default: No change
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
                # Check if we have a multiplier for this specific stat
                if col in applied_factors and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    # The Projection Formula: New = Old * Multiplier
                    proj[col] = round(player[col] * multiplier, 2)
                    
                    # Sanity Caps (Business Rules / Guardrails)
                    # Preventing the model from predicting impossible values
                    if col == 'IP' and proj[col] > 70: proj[col] = 70.0
                    if col == 'APP' and proj[col] > 25: proj[col] = 25
        
        projections.append(proj)

    df_proj = pd.DataFrame(projections)
    
    if df_proj.empty:
        print("No projections generated.")
        return

    # --- 5. Assign Roles (Initial) ---
    # Logic: CASE WHEN IP >= 6 THEN True ELSE False
    df_proj['Is_Pitcher'] = df_proj['IP'].fillna(0) >= 6
    df_proj['Is_Batter'] = df_proj['AB'].fillna(0) >= 15

    # --- 6. Backfill Rosters with Tiered Generics ---
    # This logic fills "Sparse Vectors" (Rosters with missing positions)
    if not df_generic.empty:
        print("\nChecking roster minimums (9 Batters, 6 Pitchers)...")
        
        # Prepare Tiered Generics
        # Sort by Percentile DESCENDING (50th %ile first, then 40th...)
        # Logic: We want to give teams the "best available" replacement first (Best Available Player strategy)
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
            # Partition by Team
            team_roster = df_proj[df_proj['Team'] == team]
            n_batters = team_roster['Is_Batter'].sum()
            n_pitchers = team_roster['Is_Pitcher'].sum()
            
            # Add Batters (Imputation)
            if n_batters < 9 and not gen_batters.empty:
                needed = 9 - n_batters
                for i in range(needed):
                    # Cycle through tiers: i=0 -> 50th, i=1 -> 40th, etc.
                    # This ensures we don't just fill with 50th percentile clones; we simulate depth drop-off
                    template_idx = i % len(gen_batters)
                    template = gen_batters.iloc[template_idx].to_dict()
                    
                    new_player = template.copy()
                    new_player['Team'] = team
                    # Distinct Name creation
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

            # Add Pitchers (Imputation)
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
            # UNION ALL to combine Real Projections with Generic Backfills
            df_proj = pd.concat([df_proj, df_filled], ignore_index=True)

    # --- 7. Calculate Ranks (Final) ---
    df_proj = apply_advanced_rankings(df_proj)

    # --- 8. Save ---
    
   # Construct Column Order: Meta -> Stats -> Flags/Ranks (at far right)
    meta_cols_start = ['Team', 'Name',  'Season_Cleaned', 'Class_Cleaned', 'Varsity_Year', 'Projection_Method',  'Offensive_Rank_Team', 'Pitching_Rank_Team']
    meta_cols_end = [
        'Is_Batter', 'Is_Pitcher', 'Offensive_Rank',
        'Pitching_Rank', 'RC_Score', 'Pitching_Score'
    ]
    
    final_cols = [c for c in meta_cols_start if c in df_proj.columns] + \
                 [c for c in stat_cols if c in df_proj.columns] + \
                 [c for c in meta_cols_end if c in df_proj.columns]
                 
    df_proj = df_proj[final_cols]
    
    # Sort: Team -> Offensive Rank (Team) -> Pitching Rank (Team)
    df_proj = df_proj.sort_values(['Team', 'Offensive_Rank_Team', 'Pitching_Rank_Team'])
    
    output_dir = os.path.join(PATHS['output'], 'roster_prediction')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    
    print(f"\nSuccess! Generated projected roster with {len(df_proj)} players.")
    print(f"Saved to: {output_path}")
    
    # Preview
    if not df_proj.empty:
        print("\n--- Top 5 Projected Hitters (by Team Rank) ---")
        preview_cols = ['Team', 'Offensive_Rank_Team', 'Name', 'PA']
        print(df_proj[preview_cols].head().to_string(index=False))

if __name__ == "__main__":
    predict_2026_roster()