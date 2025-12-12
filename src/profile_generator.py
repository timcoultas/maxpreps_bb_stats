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
    Generates synthetic "Replacement Level" player profiles based on historical data.

    Context:
        Baseball Context:
            This is the "Farm System" simulator. Every season, Seniors graduate and leave 
            holes in the roster. We need to fill those spots with call-ups from JV. 
            Since we don't know the specific names of every incoming Sophomore yet, 
            we create "Generic Players" to stand in for them. This allows us to answer: 
            "Even if we only get average talent coming up from JV, how strong will our team be?"

        Statistical Validity:
            Constructs a **Reference Distribution** for new entrants (Sophomores). 
            Instead of assuming every new player is "Average" (Mean), we model the 
            variance of talent by calculating **Quantiles** (10th, 20th... 50th percentiles). 
            This allows for sensitivity analysis—we can model a "Rebuilding Year" (using 
            20th percentile replacement players) vs a "Strong Class" (50th percentile).

        Technical Implementation:
            This acts as a Stratified Aggregation job.
            1. Filter: Select only `Sophomores` from history (The target population).
            2. Window Function: Calculate `PERCENT_RANK()` over the primary sorting metric 
               (PA for Batters, IP for Pitchers).
            3. Binning: Group records into decile buckets (0-10%, 10-20%, etc.).
            4. Aggregate: Calculate the Median stat line for each bucket to create 
               the representative "Generic" record.

    Output:
        Saves 'data/reference/generic_players.csv' containing tiered stat lines 
        for both Batters and Pitchers.
    """
    
    # 1. Load History
    input_file = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print("Loading historical data to calculate tiered generic baselines...")
    df = pd.read_csv(input_file)
    
    # Clean numeric columns (Schema Enforcement)
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df.columns]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 2. Filter for Sophomores
    # WHERE Class = 'Sophomore'
    sophs = df[df['Class_Cleaned'] == 'Sophomore'].copy()
    if sophs.empty:
        print("Error: No sophomores found in history.")
        return

    profiles = []
    
    # Tiers to generate (Percentiles)
    # We focus on the bottom half (10th-50th) because "Backfill" players are typically 
    # not the superstars; they are the depth pieces.
    target_quantiles = [0.1, 0.2, 0.3, 0.4, 0.5]

    # --- HELPER: Generate Tiered Stats ---
    def generate_tiers(df_subset, role, metric_col):
        """
        Calculates the median stats for specific percentile tiers.
        """
        # Calculate Percentile Ranks for the sorting metric (PA or IP)
        # SQL Equivalent: PERCENT_RANK() OVER (ORDER BY metric_col)
        df_subset = df_subset.copy()
        df_subset['pct_rank'] = df_subset[metric_col].rank(pct=True, method='min')
        
        generated = []
        
        for q in target_quantiles:
            # Define Bucket: (q - 0.1) < rank <= q
            # e.g., for 0.1, we want 0.0 to 0.1. For 0.2, we want 0.1 to 0.2.
            lower_bound = round(q - 0.1, 1)
            upper_bound = q
            
            # Filter for players in this percentile bucket
            # WHERE pct_rank > lower AND pct_rank <= upper
            bucket = df_subset[
                (df_subset['pct_rank'] > lower_bound) & 
                (df_subset['pct_rank'] <= upper_bound)
            ]
            
            # Handling sparse data buckets
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
                
                # Calculate Median stats for this bucket (The "Representative" stat line)
                for col in stat_cols:
                    profile[col] = round(bucket[col].median(), 2)
                
                # Enforce minimums for the defining stat to ensure they qualify for the role
                # A "Generic Batter" must have at least some At-Bats, even if the median was 0
                if role == 'Batter' and profile.get('AB', 0) < 10:
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