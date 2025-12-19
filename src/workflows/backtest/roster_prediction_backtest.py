"""
roster_prediction.py

Generates projected rosters for the upcoming season.
Now uses centralized MODEL_CONFIG for all thresholds and backfill ladders.
"""

import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
try:
    from src.utils.config import STAT_SCHEMA, PATHS, MODEL_CONFIG
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []
        
    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings

except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA, PATHS, MODEL_CONFIG
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []

    from src.utils.utils import prepare_analysis_data
    from src.models.advanced_ranking import apply_advanced_rankings


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
    print(f"\n{'='*60}")
    print(f"ROSTER PROJECTION: 2026 Season")
    print(f"{'='*60}")
    
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

    # Prep History
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df_history.columns]
    for col in stat_cols:
        df_history[col] = pd.to_numeric(df_history[col], errors='coerce')
    
    df_history = prepare_analysis_data(df_history)
    df_history['Is_Elite'] = df_history['Team'].isin(ELITE_TEAMS)
    
    current_year = 2025
    projection_year = 2026
    
    df_base = df_history[df_history['Season_Year'] == current_year].copy()
    if df_base.empty: return

    # Remove graduating Seniors
    df_base = df_base[~df_base['Class_Cleaned'].isin(['Senior'])]
    
    # --- Apply Projections ---
    projections = []
    next_class_map = {'Freshman': 'Sophomore', 'Sophomore': 'Junior', 'Junior': 'Senior'}
    
    for idx, player in df_base.iterrows():
        curr_class = player['Class_Cleaned']
        curr_tenure = player['Varsity_Year']
        is_elite = player['Is_Elite']
        next_class = next_class_map.get(curr_class, 'Unknown')
        next_tenure = curr_tenure + 1
        
        if next_class == 'Unknown': continue 

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
        
        if method != "Default (1.0)" and applied_factors is not None:
            for col in stat_cols:
                if col in applied_factors.index and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    if pd.notna(multiplier):
                        # Use Constant from Config for Survivor Bias
                        proj[col] = round(player[col] * multiplier * MODEL_CONFIG['SURVIVOR_BIAS_ADJUSTMENT'], 2)
                    
                    if col == 'IP' and proj[col] > 70: 
                        proj[col] = 70.0
                    if col == 'APP' and proj[col] > 25: 
                        proj[col] = 25
        
        projections.append(proj)

    df_proj = pd.DataFrame(projections)
    
    # Assign Roles
    df_proj['Is_Pitcher'] = df_proj['IP'].fillna(0) >= 5
    df_proj['Is_Batter'] = df_proj['AB'].fillna(0) >= 10

    # --- Elite Backfill Logic ---
    if not df_generic.empty:
        filled_players = []
        teams = df_proj['Team'].unique()

        for team in teams:
            team_roster = df_proj[df_proj['Team'] == team]
            n_batters = team_roster['Is_Batter'].sum()
            n_pitchers = team_roster['Is_Pitcher'].sum()
            
            is_powerhouse = team in ELITE_TEAMS
            
            if is_powerhouse:
                # Use Elite Ladder from Config
                tier_ladder_batters = MODEL_CONFIG['ELITE_PERCENTILE_LADDER']
                tier_ladder_pitchers = MODEL_CONFIG['ELITE_PERCENTILE_LADDER']
                method_label = 'Backfill (Elite Step-Down)'
            else:
                # Use Default Ladder from Config
                tier_ladder_batters = MODEL_CONFIG['DEFAULT_PERCENTILE_LADDER']
                tier_ladder_pitchers = MODEL_CONFIG['DEFAULT_PERCENTILE_LADDER']
                method_label = 'Backfill (Standard Step-Down)'

            bat_pool = df_generic[df_generic['Role'] == 'Batter']
            pit_pool = df_generic[df_generic['Role'] == 'Pitcher']
            
            # Use Config Limits
            limit_batters = MODEL_CONFIG['MIN_ROSTER_BATTERS']
            limit_pitchers = MODEL_CONFIG['MIN_ROSTER_PITCHERS']
            
            # --- Batter Backfill ---
            if n_batters < limit_batters and not bat_pool.empty:
                needed = limit_batters - int(n_batters)
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
            if n_pitchers < limit_pitchers and not pit_pool.empty:
                needed = limit_pitchers - int(n_pitchers)
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

    df_proj = apply_advanced_rankings(df_proj)

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