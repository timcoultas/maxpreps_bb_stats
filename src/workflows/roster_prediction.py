"""
roster_prediction.py

Generates projected rosters for the upcoming season.
Features "Elite Backfill" logic to prevent underestimating powerhouse programs.

v1.3 Updates:
- Added regression-to-mean for high-volume underclassmen (fixes Jacobus-type over-projections)
- Added hard caps on counting stats as safety net
- Configurable thresholds in PROJECTION_LIMITS
"""

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
DEFAULT_PERCENTILE_LADDER = [0.3, 0.1]
ELITE_PERCENTILE_LADDER = [0.5, 0.2, 0.1]  # Elite teams draw from deeper talent pools

MIN_BATTERS = 10
MIN_PITCHERS = 6

SURVIVOR_BIAS_ADJUSTMENT = 0.95

# --- NEW: Projection Limits & Regression Configuration ---
PROJECTION_LIMITS = {
    # High-volume thresholds - players above these in base year get regression applied
    'HIGH_VOLUME_PA_THRESHOLD': 80,   # PA above this triggers regression for underclassmen
    'HIGH_VOLUME_IP_THRESHOLD': 30,   # IP above this triggers regression for underclassmen
    
    # Regression strength - how much to pull toward 1.0 (0 = no regression, 1 = full regression to 1.0)
    'REGRESSION_STRENGTH': 0.5,       # 50% regression toward 1.0 for high-volume players
    
    # Hard caps on projected counting stats (safety net for data errors)
    'MAX_HITS': 75,
    'MAX_PA': 200,
    'MAX_AB': 180,
    'MAX_RBI': 60,
    'MAX_R': 60,
    'MAX_HR': 15,
    'MAX_2B': 25,
    'MAX_3B': 10,
    'MAX_BB': 50,
    'MAX_K': 70,
    'MAX_SB': 40,
    
    # Pitching caps
    'MAX_IP': 70,      # Already existed
    'MAX_APP': 25,     # Already existed
    'MAX_K_P': 100,
    'MAX_BB_P': 40,
    'MAX_ER': 50,
    'MAX_H_P': 80,
}


def calculate_regressed_multiplier(base_multiplier, base_year_volume, threshold, regression_strength=0.5):
    """
    Applies regression toward 1.0 for players who exceeded volume thresholds in the base year.
    
    Context:
        The Jacobus Problem: A freshman who already played 111 PA and hit .396 doesn't need
        a 2.25x multiplier on hits - he's already performing at a high level. Applying the
        standard Freshman→Sophomore multiplier (derived from players with 30 PA) would
        project him for 167 hits, which is impossible.
        
        This function dampens the multiplier based on how much the player exceeded the
        "typical" volume threshold. The more games they already played, the less room
        for the standard development curve to apply.
    
    Statistical Basis:
        This implements a simplified version of Marcel-style regression (Tango, 2004).
        The key insight: reliability increases with sample size. A player with 100+ PA
        has already demonstrated their true talent level; we don't need to assume they'll
        follow the same development curve as a 20 PA cameo player.
    
    Args:
        base_multiplier (float): The original multiplier from development_multipliers.csv
        base_year_volume (float): Player's PA (for batters) or IP (for pitchers) in base year
        threshold (float): Volume above which regression kicks in
        regression_strength (float): How much to pull toward 1.0 (0-1 scale)
    
    Returns:
        float: Adjusted multiplier, regressed toward 1.0 for high-volume players
    
    Example:
        - base_multiplier = 2.25 (Freshman→Sophomore Hits)
        - base_year_volume = 111 PA (Jacobus)
        - threshold = 80 PA
        - regression_strength = 0.5
        
        excess_ratio = (111 - 80) / 80 = 0.39
        regression_factor = min(0.39, 1.0) * 0.5 = 0.19
        regressed = 2.25 + (1.0 - 2.25) * 0.19 = 2.25 - 0.24 = 2.01
        
        Still shows growth, but dampened from 2.25x to 2.01x
    """
    if base_year_volume <= threshold:
        # Below threshold - no regression needed
        return base_multiplier
    
    # Calculate how much they exceeded the threshold (as a ratio)
    excess_ratio = (base_year_volume - threshold) / threshold
    
    # Cap the excess ratio at 1.0 (100% over threshold = maximum regression)
    excess_ratio = min(excess_ratio, 1.0)
    
    # Calculate regression factor
    regression_factor = excess_ratio * regression_strength
    
    # Pull the multiplier toward 1.0
    regressed_multiplier = base_multiplier + (1.0 - base_multiplier) * regression_factor
    
    return regressed_multiplier


def apply_stat_caps(proj, stat_cols):
    """
    Applies hard caps to projected counting stats as a safety net.
    
    Context:
        Even after regression, some projections might be unrealistic due to:
        - Data entry errors in source data
        - Edge cases the regression doesn't catch
        - Multiplier noise for rare events
        
        These caps represent the upper bound of what's achievable in a high school season.
        They're set generously - a player hitting these caps is having an all-time great year.
    
    Args:
        proj (dict): The projection dictionary for a single player
        stat_cols (list): List of stat column names
    
    Returns:
        dict: The projection with caps applied
        bool: True if any cap was applied (for logging)
    """
    caps_applied = []
    
    cap_map = {
        'H': PROJECTION_LIMITS['MAX_HITS'],
        'PA': PROJECTION_LIMITS['MAX_PA'],
        'AB': PROJECTION_LIMITS['MAX_AB'],
        'RBI': PROJECTION_LIMITS['MAX_RBI'],
        'R': PROJECTION_LIMITS['MAX_R'],
        'HR': PROJECTION_LIMITS['MAX_HR'],
        '2B': PROJECTION_LIMITS['MAX_2B'],
        '3B': PROJECTION_LIMITS['MAX_3B'],
        'BB': PROJECTION_LIMITS['MAX_BB'],
        'K': PROJECTION_LIMITS['MAX_K'],
        'SB': PROJECTION_LIMITS['MAX_SB'],
        'IP': PROJECTION_LIMITS['MAX_IP'],
        'APP': PROJECTION_LIMITS['MAX_APP'],
        'K_P': PROJECTION_LIMITS['MAX_K_P'],
        'BB_P': PROJECTION_LIMITS['MAX_BB_P'],
        'ER': PROJECTION_LIMITS['MAX_ER'],
        'H_P': PROJECTION_LIMITS['MAX_H_P'],
    }
    
    for col, cap in cap_map.items():
        if col in proj and pd.notna(proj[col]) and proj[col] > cap:
            caps_applied.append(f"{col}: {proj[col]:.1f} → {cap}")
            proj[col] = cap
    
    return proj, caps_applied


def format_ip_output(val):
    if pd.isna(val): return 0.0
    innings = int(val)
    decimal = val - innings
    
    if 0.25 < decimal < 0.5: return innings + 0.1
    if 0.5 < decimal < 0.8: return innings + 0.2
    return float(innings)


def load_multipliers():
    multipliers_dir = PATHS['out_development_multipliers']
    
    pooled_path = os.path.join(multipliers_dir, 'development_multipliers.csv')
    if not os.path.exists(pooled_path):
        print(f"Error: {pooled_path} not found.")
        return None, None, None
    
    df_pooled = pd.read_csv(pooled_path)
    df_pooled.set_index('Transition', inplace=True)
    
    elite_path = os.path.join(multipliers_dir, 'elite_development_multipliers.csv')
    df_elite = None
    if os.path.exists(elite_path):
        df_elite = pd.read_csv(elite_path)
        df_elite.set_index('Transition', inplace=True)
    
    standard_path = os.path.join(multipliers_dir, 'standard_development_multipliers.csv')
    df_standard = None
    if os.path.exists(standard_path):
        df_standard = pd.read_csv(standard_path)
        df_standard.set_index('Transition', inplace=True)
    
    return df_pooled, df_elite, df_standard


def predict_2026_roster():
    """
    Orchestrates the end-to-end roster generation process for the upcoming season.
    
    v1.3 Changes:
        - Added regression for high-volume underclassmen before applying multipliers
        - Added hard caps on counting stats after projection
        - Logs when regression/caps are applied for transparency
    """

    print(f"\n{'='*60}")
    print(f"ROSTER PROJECTION: 2026 Season")
    print(f"{'='*60}")
    
    # --- 1. Load Data ---
    stats_path = os.path.join(PATHS['out_historical_stats'], 'aggregated_stats.csv')
    generic_path = os.path.join(PATHS['out_generic_players'], 'generic_players.csv')

    if not os.path.exists(stats_path):
        print(f"Error: {stats_path} not found.")
        return
    
    df_pooled, df_elite, df_standard = load_multipliers()
    if df_pooled is None:
        return
    
    has_tiered_multipliers = df_elite is not None and df_standard is not None
    
    print(f"Loading data...")
    df_history = pd.read_csv(stats_path)
    
    df_generic = pd.DataFrame()
    if os.path.exists(generic_path):
        df_generic = pd.read_csv(generic_path)

    # --- 2. Prep History ---
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    df_history = prepare_analysis_data(df_history)
    df_history['Is_Elite'] = df_history['Team'].isin(ELITE_TEAMS)
    
    # --- 3. Isolate Base Year (2025) ---
    current_year = 2025
    projection_year = 2026
    
    df_base = df_history[df_history['Season_Year'] == current_year].copy()
    
    if df_base.empty:
        print(f"Error: No data found for base year {current_year}")
        return

    # Remove graduating Seniors
    df_base = df_base[~df_base['Class_Cleaned'].isin(['Senior'])]
    
    # --- 4. Apply Projections ---
    projections = []
    next_class_map = {'Freshman': 'Sophomore', 'Sophomore': 'Junior', 'Junior': 'Senior'}
    
    # Track regression and cap applications for logging
    regression_applied_count = 0
    caps_applied_count = 0
    regression_log = []
    caps_log = []
    
    for idx, player in df_base.iterrows():
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        is_elite = player['Is_Elite']
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown':
            continue 

        target_tenure = f"Varsity_Year{curr_tenure}_to_Year{next_tenure}"
        target_specific = f"{curr_class}_Y{curr_tenure}_to_{next_class}_Y{next_tenure}"
        target_class = f"{curr_class}_to_{next_class}"
        
        applied_factors = None
        method = "None"
        
        if has_tiered_multipliers:
            df_mult = df_elite if is_elite else df_standard
            tier_label = "Elite" if is_elite else "Standard"
        else:
            df_mult = df_pooled
            tier_label = "Pooled"
        
        if target_class in df_mult.index:
            applied_factors = df_mult.loc[target_class]
            method = f"Class (Age-Based) - {tier_label}"
        elif target_specific in df_mult.index:
            applied_factors = df_mult.loc[target_specific]
            method = f"Class_Tenure (Specific) - {tier_label}"
        elif target_tenure in df_pooled.index:
            applied_factors = df_pooled.loc[target_tenure]
            method = "Tenure (Experience-Based)"
        else:
            method = "Default (1.0)"
        
        proj = player.copy()
        proj['Season'] = f'Projected-{projection_year}'
        proj['Season_Cleaned'] = projection_year
        proj['Class_Cleaned'] = next_class
        proj['Varsity_Year'] = curr_tenure
        proj['Projection_Method'] = method
        
        # --- NEW: Determine if regression should be applied ---
        # Regression applies to underclassmen (Fr→So, So→Jr) with high base-year volume
        apply_regression = False
        base_pa = player.get('PA', 0) or 0
        base_ip = player.get('IP', 0) or 0
        
        if curr_class in ['Freshman', 'Sophomore']:
            if base_pa > PROJECTION_LIMITS['HIGH_VOLUME_PA_THRESHOLD']:
                apply_regression = True
            elif base_ip > PROJECTION_LIMITS['HIGH_VOLUME_IP_THRESHOLD']:
                apply_regression = True
        
        player_regression_applied = False
        
        if method != "Default (1.0)" and applied_factors is not None:
            for col in stat_cols:
                if col in applied_factors.index and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    if pd.notna(multiplier):
                        # --- NEW: Apply regression if needed ---
                        if apply_regression and multiplier > 1.0:
                            # Determine volume metric based on stat type
                            if col in ['IP', 'K_P', 'BB_P', 'ER', 'H_P', 'APP', '2B_P', '3B_P', 'HR_P']:
                                volume = base_ip
                                threshold = PROJECTION_LIMITS['HIGH_VOLUME_IP_THRESHOLD']
                            else:
                                volume = base_pa
                                threshold = PROJECTION_LIMITS['HIGH_VOLUME_PA_THRESHOLD']
                            
                            original_multiplier = multiplier
                            multiplier = calculate_regressed_multiplier(
                                multiplier, 
                                volume, 
                                threshold,
                                PROJECTION_LIMITS['REGRESSION_STRENGTH']
                            )
                            
                            if multiplier != original_multiplier:
                                player_regression_applied = True
                        
                        proj[col] = round(player[col] * multiplier * SURVIVOR_BIAS_ADJUSTMENT, 2)
        
        if player_regression_applied:
            regression_applied_count += 1
            regression_log.append(f"  - {player['Name']} ({player['Team'][:20]}): {curr_class}→{next_class}, PA={base_pa:.0f}, IP={base_ip:.1f}")
        
        # --- NEW: Apply hard caps ---
        proj_dict = proj.to_dict() if hasattr(proj, 'to_dict') else dict(proj)
        proj_dict, caps_applied = apply_stat_caps(proj_dict, stat_cols)
        
        if caps_applied:
            caps_applied_count += 1
            caps_log.append(f"  - {player['Name']} ({player['Team'][:20]}): {', '.join(caps_applied)}")
        
        # Convert back to series if needed
        proj = pd.Series(proj_dict)
        
        projections.append(proj)

    df_proj = pd.DataFrame(projections)
    
    # --- Log regression and cap applications ---
    if regression_applied_count > 0:
        print(f"\n[Regression Applied] {regression_applied_count} high-volume underclassmen regressed toward mean:")
        for log_entry in regression_log[:10]:  # Show first 10
            print(log_entry)
        if len(regression_log) > 10:
            print(f"  ... and {len(regression_log) - 10} more")
    
    if caps_applied_count > 0:
        print(f"\n[Caps Applied] {caps_applied_count} players had stats capped:")
        for log_entry in caps_log[:10]:  # Show first 10
            print(log_entry)
        if len(caps_log) > 10:
            print(f"  ... and {len(caps_log) - 10} more")
    
    # --- 5. Assign Roles ---
    df_proj['Is_Pitcher'] = df_proj['IP'].fillna(0) >= 5
    df_proj['Is_Batter'] = df_proj['AB'].fillna(0) >= 10

    # --- 6. Elite Backfill Logic ---
    if not df_generic.empty:
        filled_players = []
        teams = df_proj['Team'].unique()

        for team in teams:
            team_roster = df_proj[df_proj['Team'] == team]
            n_batters = team_roster['Is_Batter'].sum()
            n_pitchers = team_roster['Is_Pitcher'].sum()
            
            is_powerhouse = team in ELITE_TEAMS
            
            if is_powerhouse:
                # Elite teams get better replacement players (higher percentiles)
                tier_ladder_batters = ELITE_PERCENTILE_LADDER
                tier_ladder_pitchers = ELITE_PERCENTILE_LADDER
                method_label = 'Backfill (Elite Step-Down)'
            else:
                tier_ladder_batters = DEFAULT_PERCENTILE_LADDER
                tier_ladder_pitchers = DEFAULT_PERCENTILE_LADDER
                method_label = 'Backfill (Standard Step-Down)'

            bat_pool = df_generic[df_generic['Role'] == 'Batter']
            pit_pool = df_generic[df_generic['Role'] == 'Pitcher']
            
            # --- Batter Backfill ---
            if n_batters < MIN_BATTERS and not bat_pool.empty:
                needed = MIN_BATTERS - int(n_batters)
                for i in range(needed):
                    target_tier = tier_ladder_batters[min(i, len(tier_ladder_batters)-1)]
                    candidate = bat_pool[bat_pool['Percentile_Tier'] == target_tier]
                    if candidate.empty:
                        candidate = bat_pool.iloc[0:1]

                    template = candidate.iloc[0].to_dict()
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Batter {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = projection_year
                    new_player['Is_Batter'] = True
                    new_player['Is_Pitcher'] = False
                    new_player['Projection_Method'] = method_label

                    for k in ['Role', 'Percentile_Tier', 'AB_Original', 'PA_Original', 'IP_Original']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)

            # --- Pitcher Backfill ---
            if n_pitchers < MIN_PITCHERS and not pit_pool.empty:
                needed = MIN_PITCHERS - int(n_pitchers)
                for i in range(needed):
                    target_tier = tier_ladder_pitchers[min(i, len(tier_ladder_pitchers)-1)]
                    candidate = pit_pool[pit_pool['Percentile_Tier'] == target_tier]
                    if candidate.empty:
                        candidate = pit_pool.iloc[0:1]

                    template = candidate.iloc[0].to_dict()
                    new_player = template.copy()
                    new_player['Team'] = team
                    pct_label = int(template.get('Percentile_Tier', 0) * 100)
                    new_player['Name'] = f"Generic Pitcher {i+1} ({pct_label}th)"
                    new_player['Season_Cleaned'] = projection_year
                    new_player['Is_Batter'] = False
                    new_player['Is_Pitcher'] = True
                    new_player['Projection_Method'] = method_label

                    for k in ['Role', 'Percentile_Tier', 'AB_Original', 'PA_Original', 'IP_Original']:
                        new_player.pop(k, None)
                    filled_players.append(new_player)
                    
        if filled_players:
            df_filled = pd.DataFrame(filled_players)
            df_proj = pd.concat([df_proj, df_filled], ignore_index=True)

    # --- 7. Calculate Ranks ---
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
    
    if 'IP' in df_proj.columns:
        df_proj['IP'] = df_proj['IP'].apply(format_ip_output)

    output_dir = PATHS['out_roster_prediction']
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{projection_year}_roster_prediction.csv')
    
    df_proj.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    
    return df_proj

if __name__ == "__main__":
    predict_2026_roster()