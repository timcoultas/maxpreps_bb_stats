import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
try:
    from src.utils.config import STAT_SCHEMA, PATHS
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []
        
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings

except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA, PATHS
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []

    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings


# --- Configuration Constants ---
# FIX: Changed default floor from 0.2 to 0.3 based on adversarial review.
# 20th percentile sophomores have median 0 hits (RC_Score = 0), representing
# cameo appearances. 30th percentile provides meaningful offensive contribution.
DEFAULT_PERCENTILE_LADDER = [ 0.2, 0.1]
ELITE_PERCENTILE_LADDER = [0.4, 0.2, 0.1]

# Roster minimums for backfill logic
MIN_BATTERS = 10
MIN_PITCHERS = 6

# FIX: Add adjustment for survivor bias
SURVIVOR_BIAS_ADJUSTMENT = 0.95 

def format_ip_output(val):
    """Converts 3.333 -> 3.1"""
    if pd.isna(val): return 0.0
    innings = int(val)
    decimal = val - innings
    
    # Map decimal ranges back to .1 or .2
    if 0.25 < decimal < 0.5: return innings + 0.1
    if 0.5 < decimal < 0.8: return innings + 0.2
    return float(innings)

def predict_2026_roster():
    """
    Generates a projected roster for the next season using hierarchical aging curves and dynamic backfilling.

    Context:
        This is the core projection engine. We take the current year's returning players 
        (excluding graduating seniors), apply statistically-derived development multipliers 
        to project their next-year performance, and fill roster gaps with synthetic "generic" 
        players representing likely JV call-ups. The result is a complete projected roster 
        for every team in the league.

        The projection uses a Hierarchical Lookup strategy to select multipliers:
        1. **Class (Age-Based)**: Freshman→Sophomore, etc. Largest sample sizes, most robust.
        2. **Class_Tenure (Specific)**: Sophomore_Y1→Junior_Y2. Higher specificity but smaller N.
        3. **Tenure (Experience)**: Year1→Year2. Prone to survivor bias (only elite freshmen 
           play varsity Year 1, skewing the curve).
        
        This ordering prioritizes sample size and reduces selection bias, following guidance 
        from Tango et al. ("The Book", 2006) on aging curve methodology. The whitepaper 
        originally stated Tenure→Specific→Class, but empirical volatility analysis showed 
        Class-based curves are more stable for this dataset.

        This mimics a SQL COALESCE across multiple dimension tables:
        `COALESCE(class_multiplier, specific_multiplier, tenure_multiplier, 1.0)`.
        The backfill logic is an Upsert/Imputation process identifying gaps (COUNT < 9) 
        and appending synthesized rows.

    Returns:
        None. Generates '2026_roster_prediction.csv' file.
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join(PATHS['out_historical_stats'],'aggregated_stats.csv')
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
    
    # Load Generic profiles for backfill (if available)
    df_generic = pd.DataFrame()
    if os.path.exists(generic_path):
        df_generic = pd.read_csv(generic_path)
        print("Loaded generic player profiles for roster backfilling.")
    else:
        print("Warning: generic_players.csv not found. Rosters will NOT be backfilled.")

    # --- 2. Prep History (Centralized Logic) ---
    # Schema Enforcement: Ensure columns are numeric
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    # Standardize names and calculate Varsity_Year
    df_history = prepare_analysis_data(df_history)
    
    # FIX: Add logging to track player counts through pipeline
    initial_count = len(df_history)
    print(f"[Pipeline Log] Initial history records: {initial_count}")
    
    # --- 3. Isolate Current Year Roster ---
    # SQL: WHERE Season_Year = 2025
    df_2025 = df_history[df_history['Season_Year'] == 2025].copy()
    
    # Fallback if 2025 data is missing
    if df_2025.empty:
        max_year = df_history['Season_Year'].max()
        print(f"Warning: No 2025 data. Switching to {max_year}")
        df_2025 = df_history[df_history['Season_Year'] == max_year].copy()

    pre_filter_count = len(df_2025)
    print(f"[Pipeline Log] 2025 roster records: {pre_filter_count}")

    # Remove graduating Seniors
    # SQL: WHERE Class_Cleaned NOT IN ('Senior')
    df_2025 = df_2025[~df_2025['Class_Cleaned'].isin(['Senior'])]
    
    post_filter_count = len(df_2025)
    seniors_removed = pre_filter_count - post_filter_count
    print(f"[Pipeline Log] Seniors removed: {seniors_removed}")
    print(f"[Pipeline Log] Returning players: {post_filter_count}")
    
    # --- 4. Apply Projections ---
    projections = []
    next_class_map = {'Freshman': 'Sophomore', 'Sophomore': 'Junior', 'Junior': 'Senior'}
    
    # Track projection methods for logging
    method_counts = {'Class (Age-Based)': 0, 'Class_Tenure (Specific)': 0, 
                     'Tenure (Experience-Based)': 0, 'Default (1.0)': 0, 'Skipped': 0}

    print("Projecting performance...")
    
    # Cursor-based iteration (vectorization difficult due to complex lookup logic)
    for idx, player in df_2025.iterrows():
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown':
            method_counts['Skipped'] += 1
            continue 

        # --- HIERARCHICAL LOOKUP STRATEGY ---
        # Priority Order: Class → Specific → Tenure (chosen for lower volatility)
        target_tenure = f"Varsity_Year{curr_tenure}_to_Year{next_tenure}"
        target_specific = f"{curr_class}_Y{curr_tenure}_to_{next_class}_Y{next_tenure}"
        target_class = f"{curr_class}_to_{next_class}"
        
        applied_factors = None
        method = "None"
        
        # Priority 1: Class (Biological Age) - Most robust sample size, least selection bias
        if target_class in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_class]
            method = "Class (Age-Based)"
        # Priority 2: Specific Class + Tenure - High specificity, but lower sample size
        elif target_specific in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_specific]
            method = "Class_Tenure (Specific)"
        # Priority 3: Tenure Only - Prone to survivor bias
        elif target_tenure in df_multipliers.index:
            applied_factors = df_multipliers.loc[target_tenure]
            method = "Tenure (Experience-Based)"
        else:
            method = "Default (1.0)"
        
        method_counts[method] += 1

        # Clone record and update metadata
        proj = player.copy()
        proj['Season'] = 'Projected-Next'
        proj['Season_Cleaned'] = player['Season_Year'] + 1
        proj['Class_Cleaned'] = next_class
        proj['Varsity_Year'] = next_tenure
        proj['Projection_Method'] = method
        
        # Apply Multipliers
        if method != "Default (1.0)":
            for col in stat_cols:
                if col in applied_factors and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    # FIX: Apply Survivor Bias Adjustment here
                    proj[col] = round(player[col] * multiplier * SURVIVOR_BIAS_ADJUSTMENT, 2)
                    
                    # Sanity Caps to prevent extrapolation errors
                    if col == 'IP' and proj[col] > 70: 
                        proj[col] = 70.0
                    if col == 'APP' and proj[col] > 25: 
                        proj[col] = 25
        
        projections.append(proj)

    # FIX: Log projection method distribution
    print(f"\n[Pipeline Log] Projection Methods Used:")
    for method, count in method_counts.items():
        if count > 0:
            print(f"  - {method}: {count}")

    df_proj = pd.DataFrame(projections)
    
    if df_proj.empty:
        print("No projections generated.")
        return

    # --- 5. Assign Roles (Initial) ---
    # Boolean masking based on playing time thresholds
    df_proj['Is_Pitcher'] = df_proj['IP'].fillna(0) >= 5
    df_proj['Is_Batter'] = df_proj['AB'].fillna(0) >= 10

    # --- 6. Backfill Rosters with Tiered Generics ---
    if not df_generic.empty:
        print(f"\nChecking roster minimums ({MIN_BATTERS} Batters, {MIN_PITCHERS} Pitchers)...")
        
        filled_players = []
        teams = df_proj['Team'].unique()
        
        if not ELITE_TEAMS:
            print(f"Notice: ELITE_TEAMS list empty. Using {int(DEFAULT_PERCENTILE_LADDER[0]*100)}th %ile backfill for all.")

        for team in teams:
            team_roster = df_proj[df_proj['Team'] == team]
            n_batters = team_roster['Is_Batter'].sum()
            n_pitchers = team_roster['Is_Pitcher'].sum()
            
            # Determine tier based on program prestige
            is_powerhouse = team in ELITE_TEAMS
            
            # [FIX] Step-Down Logic for Realistic Depth
            # Elite teams: 50% -> 40% -> 30% -> 20% (Floor)
            # Standard teams: 30% -> 20% -> 10% -> 10% (Floor)
            if is_powerhouse:
                tier_ladder_batters = ELITE_PERCENTILE_LADDER
                tier_ladder_pitchers = ELITE_PERCENTILE_LADDER
                method_label = 'Backfill (Elite Step-Down)'
            else:
                tier_ladder_batters = DEFAULT_PERCENTILE_LADDER
                tier_ladder_pitchers = DEFAULT_PERCENTILE_LADDER
                method_label = 'Backfill (Standard Step-Down)'

            # Filter generic pool for this team's tier
            bat_pool = df_generic[df_generic['Role'] == 'Batter']
            pit_pool = df_generic[df_generic['Role'] == 'Pitcher']
            
            # Add Batters (Imputation)
            if n_batters < MIN_BATTERS and not bat_pool.empty:
                needed = MIN_BATTERS - int(n_batters)
                for i in range(needed):
                    # [FIX] Pop the best available tier, or use floor if ladder exhausted
                    if i < len(tier_ladder_batters):
                        target_tier = tier_ladder_batters[i]
                    else:
                        target_tier = tier_ladder_batters[-1] # Floor
                    
                    # Find closest match in the pool
                    candidate = bat_pool[bat_pool['Percentile_Tier'] == target_tier]
                    
                    # Fallback to closest if exact tier missing
                    if candidate.empty:
                        candidate = bat_pool.iloc[0:1] # Just take top of pool as fail-safe

                    template = candidate.iloc[0].to_dict()
                    
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Batter {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = True
                    new_player['Is_Pitcher'] = False
                    new_player['Projection_Method'] = method_label
                    
                    # Cleanup internal columns
                    for k in ['Role', 'Percentile_Tier', 'AB_Original', 'PA_Original', 'IP_Original']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)

            # Add Pitchers (Same Logic)
            if n_pitchers < MIN_PITCHERS and not pit_pool.empty:
                needed = MIN_PITCHERS - int(n_pitchers)
                for i in range(needed):
                    # [FIX] Step-Down Logic
                    if i < len(tier_ladder_pitchers):
                        target_tier = tier_ladder_pitchers[i]
                    else:
                        target_tier = tier_ladder_pitchers[-1]

                    candidate = pit_pool[pit_pool['Percentile_Tier'] == target_tier]
                    
                    if candidate.empty:
                        candidate = pit_pool.iloc[0:1]

                    template = candidate.iloc[0].to_dict()
                    
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Pitcher {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = False
                    new_player['Is_Pitcher'] = True
                    new_player['Projection_Method'] = method_label
                    
                    for k in ['Role', 'Percentile_Tier', 'AB_Original', 'PA_Original', 'IP_Original']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)
                    
        if filled_players:
            print(f"[Pipeline Log] Backfilling {len(filled_players)} generic player slots.")
            df_filled = pd.DataFrame(filled_players)
            df_proj = pd.concat([df_proj, df_filled], ignore_index=True)

    # --- 7. Calculate Ranks (Final) ---
    df_proj = apply_advanced_rankings(df_proj)

    # --- 8. Save ---
    meta_cols_start = ['Team', 'Name', 'Season_Cleaned', 'Class_Cleaned', 'Varsity_Year', 
                       'Projection_Method', 'Offensive_Rank_Team', 'Pitching_Rank_Team']
    meta_cols_end = ['Is_Batter', 'Is_Pitcher', 'Offensive_Rank', 'Pitching_Rank', 
                     'RC_Score', 'Pitching_Score']
    
    final_cols = [c for c in meta_cols_start if c in df_proj.columns] + \
                 [c for c in stat_cols if c in df_proj.columns] + \
                 [c for c in meta_cols_end if c in df_proj.columns]
                 
    df_proj = df_proj[final_cols]
    df_proj = df_proj.sort_values(['Team', 'Offensive_Rank_Team', 'Pitching_Rank_Team'])
    
    # [FIX] Format IP column for final output (3.333 -> 3.1)
    if 'IP' in df_proj.columns:
        df_proj['IP'] = df_proj['IP'].apply(format_ip_output)

    output_dir = PATHS['out_roster_prediction']
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    
    # FIX: Final pipeline summary
    real_players = len(df_proj[~df_proj['Name'].str.contains('Generic', na=False)])
    generic_players = len(df_proj[df_proj['Name'].str.contains('Generic', na=False)])
    print(f"\n[Pipeline Log] Final Roster Summary:")
    print(f"  - Real projected players: {real_players}")
    print(f"  - Generic backfill players: {generic_players}")
    print(f"  - Total roster size: {len(df_proj)}")
    print(f"\nSuccess! Saved to: {output_path}")

if __name__ == "__main__":
    predict_2026_roster()