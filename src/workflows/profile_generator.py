import pandas as pd
import numpy as np
import os
import sys

# --- Import Config ---
try:
    from src.utils.config import STAT_SCHEMA
    from src.utils.config import PATHS
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA
    from src.utils.config import PATHS

# --- Configuration Constants ---
# FIX: Changed from 0.2 to 0.3 based on adversarial review finding that 20th percentile
# sophomores have 0 hits (RC_Score = 0), which represents cameo appearances rather than
# true "replacement level" players who could theoretically start.
DEFAULT_FLOOR_PERCENTILE = 0.3
DEFAULT_ELITE_PERCENTILE = 0.5

# Minimum playing time thresholds to qualify as a "real" player profile
# Players below these thresholds are filtered out before percentile calculation
MIN_PA_FOR_BATTER_PROFILE = 10
MIN_IP_FOR_PITCHER_PROFILE = 3


def create_generic_profiles():
    """
    Generates synthetic "Replacement Level" player profiles based on historical sophomore data.

    Context:
        Every season, seniors graduate and leave holes in the roster. We need to model 
        incoming talent (typically sophomores moving up from JV) to project team strength 
        even when we don't know specific names. This function creates statistical profiles 
        representing different talent tiers, allowing sensitivity analysis: "What if our 
        call-ups are average (50th percentile) vs. below-average (30th percentile)?"

        This constructs a Reference Distribution for new varsity entrants. Instead of 
        assuming every incoming player is "average" (mean imputation, which artificially 
        reduces variance), we calculate quantile-based profiles. This approach is similar 
        to the "Replacement Level" concept in WAR calculations (Tango, Lichtman, Dolphin, 
        "The Book", 2006), where replacement level represents the talent available freely 
        on the waiver wire—roughly the 20th-30th percentile of MLB players.

        This acts as a Stratified Aggregation job:
        1. Filter: `SELECT * FROM history WHERE Class = 'Sophomore'`
        2. Window: `PERCENT_RANK() OVER (ORDER BY PA)` to rank by playing time
        3. Bin: Group into decile buckets (0-10%, 10-20%, etc.)
        4. Aggregate: `SELECT MEDIAN(stat) FROM bucket GROUP BY percentile_tier`

    Output:
        Saves 'generic_players.csv' containing tiered stat lines for Batters and Pitchers.
    """
    
    # 1. Load History
    input_file = os.path.join(PATHS['processed'], 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print("Loading historical data to calculate tiered generic baselines...")
    df = pd.read_csv(input_file)
    
    # Schema Enforcement: Ensure numeric columns are properly typed
    # SQL Equivalent: CAST(column AS NUMERIC)
    stat_cols = [s['abbreviation'] for s in STAT_SCHEMA if s['abbreviation'] in df.columns]
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 2. Filter for Sophomores (the typical "call-up" class)
    # SQL: WHERE Class_Cleaned = 'Sophomore'
    sophs = df[df['Class_Cleaned'] == 'Sophomore'].copy()
    if sophs.empty:
        print("Error: No sophomores found in history.")
        return

    profiles = []
    
    # Tiers to generate - focusing on bottom half since backfill players are depth pieces
    # FIX: Start at 0.1 but use 0.3 as default floor (see roster_prediction.py)
    target_quantiles = [0.1, 0.2, 0.3, 0.4, 0.5]

    def generate_tiers(df_subset, role, metric_col):
        """
        Calculates the median stats for specific percentile tiers.
        
        Context:
            We're building representative "player cards" for each talent tier. The median
            is used rather than mean to be robust against outliers (e.g., a sophomore who
            had one monster game but otherwise limited playing time).
        
        Args:
            df_subset: Filtered DataFrame of sophomores with the relevant stats
            role: 'Batter' or 'Pitcher'
            metric_col: Column to use for percentile ranking ('PA' or 'IP')
            
        Returns:
            List of profile dictionaries, one per quantile tier
        """
        # FIX: Filter for minimum playing time BEFORE calculating percentiles
        # This ensures we're ranking "real" players, not single-AB cameos
        # SQL: WHERE PA >= 10 (for batters) or WHERE IP >= 3 (for pitchers)
        if role == 'Batter':
            df_subset = df_subset[df_subset[metric_col] >= MIN_PA_FOR_BATTER_PROFILE].copy()
        else:
            df_subset = df_subset[df_subset[metric_col] >= MIN_IP_FOR_PITCHER_PROFILE].copy()
        
        if df_subset.empty:
            print(f"  Warning: No qualifying {role}s found after minimum threshold filter.")
            return []
        
        # Calculate Percentile Ranks for the sorting metric
        # SQL Equivalent: PERCENT_RANK() OVER (ORDER BY metric_col)
        df_subset['pct_rank'] = df_subset[metric_col].rank(pct=True, method='min')
        
        generated = []
        
        for q in target_quantiles:
            # Define Bucket boundaries
            # For 0.3, we want players ranked between 0.2 and 0.3 (the 20th-30th percentile)
            lower_bound = round(q - 0.1, 1)
            upper_bound = q
            
            # Filter for players in this percentile bucket
            # SQL: WHERE pct_rank > 0.2 AND pct_rank <= 0.3
            bucket = df_subset[
                (df_subset['pct_rank'] > lower_bound) & 
                (df_subset['pct_rank'] <= upper_bound)
            ]
            
            # Fallback: Expand search if bucket is empty due to small sample
            if bucket.empty:
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
                # SQL: SELECT MEDIAN(col) FROM bucket
                for col in stat_cols:
                    profile[col] = round(bucket[col].median(), 2)
                
                # FIX: Store original values before applying minimums
                # This maintains data integrity for any downstream rate calculations
                if role == 'Batter':
                    profile['AB_Original'] = profile.get('AB', 0)
                    profile['PA_Original'] = profile.get('PA', 0)
                else:
                    profile['IP_Original'] = profile.get('IP', 0)
                
                # Enforce minimums to ensure players qualify for Is_Batter/Is_Pitcher flags
                # Note: This is for roster_prediction.py thresholds (AB >= 10, IP >= 5)
                if role == 'Batter' and profile.get('AB', 0) < 10:
                     profile['AB'] = max(profile.get('AB', 0), 10.0)
                
                if role == 'Pitcher' and profile.get('IP', 0) < 5:
                     profile['IP'] = max(profile.get('IP', 0), 5.0)

                generated.append(profile)
                
        return generated

    # --- Generate Batter Profiles (Based on PA) ---
    # Filter for batters with at least 1 PA to establish a ranking baseline
    active_batters = sophs[sophs['PA'] > 0]
    print(f"Generating Batter profiles from {len(active_batters)} records...")
    profiles.extend(generate_tiers(active_batters, 'Batter', 'PA'))

    # --- Generate Pitcher Profiles (Based on IP) ---
    active_pitchers = sophs[sophs['IP'] > 0]
    print(f"Generating Pitcher profiles from {len(active_pitchers)} records...")
    profiles.extend(generate_tiers(active_pitchers, 'Pitcher', 'IP'))

    # 3. Save
    df_profiles = pd.DataFrame(profiles)
    
    # Sort for readability: Batters first, then by percentile tier
    df_profiles = df_profiles.sort_values(['Role', 'Percentile_Tier'])
    
    output_dir = PATHS['out_generic_players']
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'generic_players.csv')
    
    df_profiles.to_csv(output_path, index=False)
    print(f"Success. Saved {len(df_profiles)} generic profiles to: {output_path}")
    
    # Display summary for verification
    print("\n--- Generated Profiles Summary ---")
    print(df_profiles[['Name', 'PA', 'H', 'AB', 'IP', 'ERA']].to_string(index=False))

if __name__ == "__main__":
    create_generic_profiles()
