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
    Calculates 5 tiers of generic profiles (10th-50th percentile) for Batters and Pitchers.
    Saves to data/reference/generic_players.csv.
    """
    
    # 1. Load History
    input_file = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print("Loading historical data to calculate tiered generic baselines...")
    df = pd.read_csv(input_file)
    
    # Clean numeric columns
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df.columns]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 2. Filter for Sophomores
    sophs = df[df['Class_Cleaned'] == 'Sophomore'].copy()
    if sophs.empty:
        print("Error: No sophomores found in history.")
        return

    profiles = []
    
    # Tiers to generate (Percentiles)
    target_quantiles = [0.1, 0.2, 0.3, 0.4, 0.5]

    # --- HELPER: Generate Tiered Stats ---
    def generate_tiers(df_subset, role, metric_col):
        # Calculate Percentile Ranks for the sorting metric (PA or IP)
        # method='min' ensures that tied values don't jump brackets unexpectedly
        df_subset = df_subset.copy()
        df_subset['pct_rank'] = df_subset[metric_col].rank(pct=True, method='min')
        
        generated = []
        
        for q in target_quantiles:
            # Define Bucket: (q - 0.1) < rank <= q
            # e.g., for 0.1, we want 0.0 to 0.1. For 0.2, we want 0.1 to 0.2.
            lower_bound = round(q - 0.1, 1)
            upper_bound = q
            
            # Filter for players in this percentile bucket
            bucket = df_subset[
                (df_subset['pct_rank'] > lower_bound) & 
                (df_subset['pct_rank'] <= upper_bound)
            ]
            
            if bucket.empty:
                # Fallback: expand search slightly if bucket is empty due to small sample
                bucket = df_subset[
                    (df_subset['pct_rank'] > lower_bound - 0.05) & 
                    (df_subset['pct_rank'] <= upper_bound + 0.05)
                ]

            if not bucket.empty:
                profile = {
                    'Name': f"Generic Sophomore {role} ({int(q*100)}th %ile)",
                    'Role': role,
                    'Class_Cleaned': 'Sophomore',
                    'Varsity_Year': 1,
                    'Projection_Method': 'Generic Baseline',
                    'Percentile_Tier': q
                }
                
                # Calculate Median stats for this bucket
                for col in stat_cols:
                    profile[col] = round(bucket[col].median(), 2)
                
                # Enforce minimums for the defining stat to ensure they qualify for the role
                if role == 'Batter' and profile.get('AB', 0) < 10:
                     # Even the 10th percentile batter needs to look like a batter
                     profile['AB'] = max(profile.get('AB', 0), 10.0)
                
                if role == 'Pitcher' and profile.get('IP', 0) < 5:
                     profile['IP'] = max(profile.get('IP', 0), 5.0)

                generated.append(profile)
        return generated

    # --- 1. Batters (Based on PA) ---
    # Filter for valid batters first (PA > 0) to establish a ranking baseline
    active_batters = sophs[sophs['PA'] > 0]
    print(f"Generating Batter profiles from {len(active_batters)} records...")
    profiles.extend(generate_tiers(active_batters, 'Batter', 'PA'))

    # --- 2. Pitchers (Based on IP) ---
    active_pitchers = sophs[sophs['IP'] > 0]
    print(f"Generating Pitcher profiles from {len(active_pitchers)} records...")
    profiles.extend(generate_tiers(active_pitchers, 'Pitcher', 'IP'))

    # 3. Save
    df_profiles = pd.DataFrame(profiles)
    
    # Sort for readability
    df_profiles = df_profiles.sort_values(['Role', 'Percentile_Tier'])
    
    output_dir = os.path.join('data', 'reference')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'generic_players.csv')
    
    df_profiles.to_csv(output_path, index=False)
    print(f"Success. Saved {len(df_profiles)} generic profiles to: {output_path}")
    print(df_profiles[['Name', 'PA', 'H', 'IP', 'ERA']].to_string(index=False))

if __name__ == "__main__":
    create_generic_profiles()