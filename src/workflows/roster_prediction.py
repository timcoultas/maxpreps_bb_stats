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
# This tells the script how to pick generic players. 
# There are "elite" programs like Cherry Creek and Rocky Mountain
# These are teams that made it into the top 10 rankings 
# More than once in the last 4 years. (there are 13) 
# Only 3 made it in more than twice. 
# The ladder says: for your first generic player you get a sophomore that operates at the percentile; 
#  You next player is at the next percentile. 
# So rocky gets their first at median, their second at 20th percentile their third at 10th percentile 
# The non elite teams start at 30percentile and then drop to 10

DEFAULT_PERCENTILE_LADDER = [ 0.3, 0.1]
ELITE_PERCENTILE_LADDER = [0.5, 0.2, 0.1]

# Roster minimums for backfill logic
MIN_BATTERS = 10
MIN_PITCHERS = 6

# Survivor Bias Adjustment
# Development multipliers are calculated only from players who returned the following year,
# excluding players who quit or were cut. This creates an upward bias that we partially 
# correct with a 5% reduction to all projected stats.
SURVIVOR_BIAS_ADJUSTMENT = 0.95 

def format_ip_output(val):
    """Converts 3.333 -> 3.1 for baseball-standard IP notation."""
    if pd.isna(val): return 0.0
    innings = int(val)
    decimal = val - innings
    
    # Map decimal ranges back to .1 or .2
    if 0.25 < decimal < 0.5: return innings + 0.1
    if 0.5 < decimal < 0.8: return innings + 0.2
    return float(innings)


def load_multipliers():
    """
    Loads development multipliers, including elite and standard variants if available.
    
    Returns:
        tuple: (df_pooled, df_elite, df_standard) - DataFrames indexed by Transition.
               df_elite and df_standard may be None if files don't exist.
    """
    multipliers_dir = PATHS['out_development_multipliers']
    
    # Pooled (required, backward compatible)
    pooled_path = os.path.join(multipliers_dir, 'development_multipliers.csv')
    if not os.path.exists(pooled_path):
        print(f"Error: {pooled_path} not found. Please run development_multipliers.py first.")
        return None, None, None
    
    df_pooled = pd.read_csv(pooled_path)
    df_pooled.set_index('Transition', inplace=True)
    
    # Elite (optional)
    elite_path = os.path.join(multipliers_dir, 'elite_development_multipliers.csv')
    df_elite = None
    if os.path.exists(elite_path):
        df_elite = pd.read_csv(elite_path)
        df_elite.set_index('Transition', inplace=True)
        print("Loaded elite development multipliers.")
    
    # Standard (optional)
    standard_path = os.path.join(multipliers_dir, 'standard_development_multipliers.csv')
    df_standard = None
    if os.path.exists(standard_path):
        df_standard = pd.read_csv(standard_path)
        df_standard.set_index('Transition', inplace=True)
        print("Loaded standard development multipliers.")
    
    return df_pooled, df_elite, df_standard


def predict_2026_roster():
    """
    Generates a projected roster for the next season using hierarchical aging curves,
    with separate development multipliers for elite vs standard programs.

    Context:
        Baseball Context:
            This is the core projection engine. We take the current year's returning players 
            (excluding graduating seniors), apply statistically-derived development multipliers 
            to project their next-year performance, and fill roster gaps with synthetic "generic" 
            players representing likely JV call-ups.
            
            NEW: Elite programs (those with 2+ top-10 state finishes) now use separate multipliers
            that reflect their superior player development infrastructure: year-round training,
            structured winter practices, and summer ball with the same coaching staff.

        Statistical Validity:
            Analysis of 1,142 YoY transitions shows elite programs develop players differently,
            particularly for Junior→Senior pitching:
            - Elite K_P multiplier: 1.227 vs Standard: 1.000 (+23% more K growth)
            - Elite ER multiplier: 0.805 vs Standard: 0.883 (better run prevention)
            - Elite BB_P multiplier: 0.781 vs Standard: 1.000 (22% more walk reduction)

        Technical Implementation:
            The projection uses a Hierarchical Lookup strategy:
            1. Class (Age-Based): Freshman→Sophomore, etc. Largest sample sizes.
            2. Class_Tenure (Specific): Sophomore_Y1→Junior_Y2. Higher specificity.
            3. Tenure (Experience): Year1→Year2. Prone to survivor bias.
            
            For each lookup, the system first checks if elite/standard-specific multipliers
            exist. If not, it falls back to pooled multipliers.

    Returns:
        None. Generates '2026_roster_prediction.csv' file.
    """
    
    # --- 1. Load Data ---
    stats_path = os.path.join(PATHS['out_historical_stats'], 'aggregated_stats.csv')
    generic_path = os.path.join(PATHS['out_generic_players'], 'generic_players.csv')

    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found. Please run the ETL pipeline first.")
        return
    
    # Load multipliers (pooled + elite + standard)
    df_pooled, df_elite, df_standard = load_multipliers()
    if df_pooled is None:
        return
    
    # Log multiplier availability
    has_tiered_multipliers = df_elite is not None and df_standard is not None
    if has_tiered_multipliers:
        print("Using TIERED multipliers (elite vs standard programs).")
    else:
        print("Using POOLED multipliers (elite/standard files not found).")
        
    print("Loading data...")
    df_history = pd.read_csv(stats_path)
    
    # Load Generic profiles for backfill (if available)
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
    
    df_history = prepare_analysis_data(df_history)
    
    # Tag elite teams
    df_history['Is_Elite'] = df_history['Team'].isin(ELITE_TEAMS)
    
    initial_count = len(df_history)
    print(f"[Pipeline Log] Initial history records: {initial_count}")
    
    # --- 3. Isolate Current Year Roster ---
    df_2025 = df_history[df_history['Season_Year'] == 2025].copy()
    
    if df_2025.empty:
        max_year = df_history['Season_Year'].max()
        print(f"Warning: No 2025 data. Switching to {max_year}")
        df_2025 = df_history[df_history['Season_Year'] == max_year].copy()

    pre_filter_count = len(df_2025)
    print(f"[Pipeline Log] 2025 roster records: {pre_filter_count}")

    # Remove graduating Seniors
    df_2025 = df_2025[~df_2025['Class_Cleaned'].isin(['Senior'])]
    
    post_filter_count = len(df_2025)
    seniors_removed = pre_filter_count - post_filter_count
    print(f"[Pipeline Log] Seniors removed: {seniors_removed}")
    print(f"[Pipeline Log] Returning players: {post_filter_count}")
    
    # Count elite vs standard
    elite_returning = df_2025['Is_Elite'].sum()
    standard_returning = post_filter_count - elite_returning
    print(f"[Pipeline Log] Elite program players: {elite_returning}")
    print(f"[Pipeline Log] Standard program players: {standard_returning}")
    
    # --- 4. Apply Projections ---
    projections = []
    next_class_map = {'Freshman': 'Sophomore', 'Sophomore': 'Junior', 'Junior': 'Senior'}
    
    # Track projection methods for logging
    method_counts = {
        'Class (Age-Based) - Elite': 0, 
        'Class (Age-Based) - Standard': 0,
        'Class (Age-Based) - Pooled': 0,
        'Class_Tenure (Specific) - Elite': 0,
        'Class_Tenure (Specific) - Standard': 0,
        'Class_Tenure (Specific) - Pooled': 0,
        'Tenure (Experience-Based)': 0, 
        'Default (1.0)': 0, 
        'Skipped': 0
    }

    print("Projecting performance...")
    
    for idx, player in df_2025.iterrows():
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        is_elite = player['Is_Elite']
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown':
            method_counts['Skipped'] += 1
            continue 

        # --- HIERARCHICAL LOOKUP STRATEGY ---
        target_tenure = f"Varsity_Year{curr_tenure}_to_Year{next_tenure}"
        target_specific = f"{curr_class}_Y{curr_tenure}_to_{next_class}_Y{next_tenure}"
        target_class = f"{curr_class}_to_{next_class}"
        
        applied_factors = None
        method = "None"
        
        # Select the appropriate multiplier DataFrame based on team tier
        if has_tiered_multipliers:
            df_mult = df_elite if is_elite else df_standard
            tier_label = "Elite" if is_elite else "Standard"
        else:
            df_mult = df_pooled
            tier_label = "Pooled"
        
        # Priority 1: Class (Biological Age) - Most robust sample size
        if target_class in df_mult.index:
            applied_factors = df_mult.loc[target_class]
            method = f"Class (Age-Based) - {tier_label}"
        # Priority 2: Specific Class + Tenure
        elif target_specific in df_mult.index:
            applied_factors = df_mult.loc[target_specific]
            method = f"Class_Tenure (Specific) - {tier_label}"
        # Priority 3: Tenure Only (use pooled to maximize sample size)
        elif target_tenure in df_pooled.index:
            applied_factors = df_pooled.loc[target_tenure]
            method = "Tenure (Experience-Based)"
        else:
            method = "Default (1.0)"
        
        # Update method counts
        if method in method_counts:
            method_counts[method] += 1
        elif "Class (Age-Based)" in method:
            method_counts['Class (Age-Based) - Pooled'] += 1
        elif "Class_Tenure" in method:
            method_counts['Class_Tenure (Specific) - Pooled'] += 1

        # Clone record and update metadata
        proj = player.copy()
        proj['Season'] = 'Projected-Next'
        proj['Season_Cleaned'] = player['Season_Year'] + 1
        proj['Class_Cleaned'] = next_class
        proj['Varsity_Year'] = curr_tenure  # Keep actual experience, don't increment
        proj['Projection_Method'] = method
        
        # Apply Multipliers
        if method != "Default (1.0)":
            for col in stat_cols:
                if col in applied_factors.index and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    if pd.notna(multiplier):
                        proj[col] = round(player[col] * multiplier * SURVIVOR_BIAS_ADJUSTMENT, 2)
                    
                    # Sanity Caps to prevent extrapolation errors
                    if col == 'IP' and proj[col] > 70: 
                        proj[col] = 70.0
                    if col == 'APP' and proj[col] > 25: 
                        proj[col] = 25
        
        projections.append(proj)

    # Log projection method distribution
    print(f"\n[Pipeline Log] Projection Methods Used:")
    for method, count in method_counts.items():
        if count > 0:
            print(f"  - {method}: {count}")

    df_proj = pd.DataFrame(projections)
    
    if df_proj.empty:
        print("No projections generated.")
        return

    # --- 5. Assign Roles (Initial) ---
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
            
            is_powerhouse = team in ELITE_TEAMS
            
            if is_powerhouse:
                tier_ladder_batters = ELITE_PERCENTILE_LADDER
                tier_ladder_pitchers = ELITE_PERCENTILE_LADDER
                method_label = 'Backfill (Elite Step-Down)'
            else:
                tier_ladder_batters = DEFAULT_PERCENTILE_LADDER
                tier_ladder_pitchers = DEFAULT_PERCENTILE_LADDER
                method_label = 'Backfill (Standard Step-Down)'

            bat_pool = df_generic[df_generic['Role'] == 'Batter']
            pit_pool = df_generic[df_generic['Role'] == 'Pitcher']
            
            # Add Batters
            if n_batters < MIN_BATTERS and not bat_pool.empty:
                needed = MIN_BATTERS - int(n_batters)
                for i in range(needed):
                    if i < len(tier_ladder_batters):
                        target_tier = tier_ladder_batters[i]
                    else:
                        target_tier = tier_ladder_batters[-1]
                    
                    candidate = bat_pool[bat_pool['Percentile_Tier'] == target_tier]
                    
                    if candidate.empty:
                        candidate = bat_pool.iloc[0:1]

                    template = candidate.iloc[0].to_dict()
                    
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Batter {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = 2026
                    new_player['Is_Batter'] = True
                    new_player['Is_Pitcher'] = False
                    new_player['Projection_Method'] = method_label
                    
                    for k in ['Role', 'Percentile_Tier', 'AB_Original', 'PA_Original', 'IP_Original']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)

            # Add Pitchers
            if n_pitchers < MIN_PITCHERS and not pit_pool.empty:
                needed = MIN_PITCHERS - int(n_pitchers)
                for i in range(needed):
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
    
    # Format IP column for final output
    if 'IP' in df_proj.columns:
        df_proj['IP'] = df_proj['IP'].apply(format_ip_output)

    output_dir = PATHS['out_roster_prediction']
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    
    # Final pipeline summary
    real_players = len(df_proj[~df_proj['Name'].str.contains('Generic', na=False)])
    generic_players = len(df_proj[df_proj['Name'].str.contains('Generic', na=False)])
    print(f"\n[Pipeline Log] Final Roster Summary:")
    print(f"  - Real projected players: {real_players}")
    print(f"  - Generic backfill players: {generic_players}")
    print(f"  - Total roster size: {len(df_proj)}")
    print(f"\nSuccess! Saved to: {output_path}")


if __name__ == "__main__":
    predict_2026_roster()