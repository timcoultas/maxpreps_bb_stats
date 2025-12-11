import pandas as pd
import numpy as np
import os
import sys

# --- Import Config ---
# We try importing from src.config first (standard structure), 
# then fallback to local config (flat structure).
try:
    from src.config import STAT_SCHEMA
except ImportError:
    try:
        from config import STAT_SCHEMA
    except ImportError:
        print("Error: Could not import STAT_SCHEMA from config.py. Please ensure the file exists.")
        sys.exit(1)

def generate_stat_multipliers():
    """
    1. Loads aggregated history.
    2. Identifies players who played in consecutive years.
    3. Calculates year-over-year performance multipliers.
    4. Uses config.py to determine stat types and apply appropriate filters.
    """
    
    # --- Load Data ---
    input_file = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        input_file = 'aggregated_stats.csv'
        
    print(f"Loading data from {input_file}...")
    try:
        df = pd.read_csv(input_file)
    except FileNotFoundError:
        print("Error: Could not find aggregated_stats.csv. Please run the ETL pipeline first.")
        return

    # --- 1. Dynamic Column Handling using Config ---
    # We only process stats that are defined in our schema AND exist in the CSV.
    available_stats = set(df.columns)
    stat_cols = []
    stat_types = {} # Map abbreviation -> stat_type (Batting, Pitching, etc.)

    for stat_def in STAT_SCHEMA:
        abbr = stat_def['abbreviation']
        if abbr in available_stats:
            stat_cols.append(abbr)
            stat_types[abbr] = stat_def['stat_type']

    print(f"Processing {len(stat_cols)} stats defined in config...")

    # Convert numeric columns to float, coercing errors
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Ensure Year is int for math
    if 'Season_Cleaned' in df.columns:
        df['Season_Year'] = df['Season_Cleaned'].astype(int)
    else:
        print("Error: 'Season_Cleaned' column missing from input CSV.")
        return

    # --- Step 2: Create the "Development Curve" (Year N vs Year N+1) ---
    
    # LOGIC:
    # We need to compare Player X in 2023 vs Player X in 2024.
    # We perform a "Self-Join" where the Left side is the Previous Year 
    # and the Right side is the Current Year.
    
    df_prev = df.copy()
    df_prev['Join_Year'] = df_prev['Season_Year'] + 1  # This calculates the year we want to match AGAINST
    
    merged = pd.merge(
        df_prev, 
        df, 
        left_on=['Athlete_ID', 'Join_Year'], 
        right_on=['Athlete_ID', 'Season_Year'],
        suffixes=('_Prev', '_Next')
    )
    
    print(f"Found {len(merged)} player-seasons with year-over-year data.")

    valid_transitions = {
        'Freshman': 'Sophomore',
        'Sophomore': 'Junior',
        'Junior': 'Senior'
    }

    if 'Class_Cleaned_Prev' in merged.columns:
        merged = merged[merged['Class_Cleaned_Prev'].isin(valid_transitions.keys())]
    else:
        print("Error: 'Class_Cleaned' column missing.")
        return
    
    # --- Step 3: Calculate Multipliers ---
    
    multipliers = []

    for start_class, end_class in valid_transitions.items():
        # Get the "Cohort": All players making this specific transition (e.g., Freshman to Sophomore)
        cohort = merged[merged['Class_Cleaned_Prev'] == start_class]
        transition_stats = {'Transition': f"{start_class}_to_{end_class}"}
        
        for col in stat_cols:
            subset = cohort.copy()
            st_type = stat_types.get(col, 'Batting') # Default to Batting if unknown
            
            # --- FILTERING LOGIC ---
            # We filter out players with small sample sizes in the previous year.
            # Rationale: A player with 1 At-Bat who gets 1 Hit has a 1.000 average.
            # If they play full time next year and hit .300, the multiplier would be 0.3x.
            # Small samples create noisy, unreliable multipliers.
            
            # 1. Pitching Stats: Filter by Innings Pitched (IP)
            if st_type == 'Pitching':
                if 'IP_Prev' in subset.columns:
                    subset = subset[subset['IP_Prev'] >= 5] # Minimum 5 innings
                else:
                    continue 

            # 2. Batting/Running/Fielding Stats: Filter by Plate Appearances (PA)
            else:
                if 'PA_Prev' in subset.columns:
                    subset = subset[subset['PA_Prev'] >= 10] # Minimum 10 PAs
                else:
                    continue

            # 3. Valid Denominator Check
            # We cannot divide by zero. If a player had 0 stats last year, we can't calculate a growth multiplier.
            subset = subset[subset[f'{col}_Prev'] > 0]

            # 4. Minimum Population Check
            # If we have fewer than 3 players in this cohort after filtering, 
            # the data is too scarce to trust. Default to 1.0 (no change).
            if len(subset) < 3:
                transition_stats[col] = 1.0 
                continue

            # --- CALCULATION LOGIC ---
            # 1. Calculate the Ratio for every individual player.
            #    Formula: Next_Year_Stat / Prev_Year_Stat
            ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']
            
            # 2. Aggregation: MEDIAN vs MEAN
            #    We use the MEDIAN (the middle value).
            #    Why? Averages are sensitive to outliers. 
            #    Example: 
            #       Player A: 1 HR -> 2 HR (2.0x)
            #       Player B: 2 HR -> 4 HR (2.0x)
            #       Player C: 1 HR -> 15 HR (15.0x) -- The "Breakout" star
            #    Average = (2+2+15)/3 = 6.3x multiplier. (Too high for a normal projection)
            #    Median = 2.0x multiplier. (A safer, more realistic expectation)
            median_growth = ratios.median()
            
            transition_stats[col] = round(median_growth, 3)
            
        multipliers.append(transition_stats)

    df_multipliers = pd.DataFrame(multipliers)
    
    if not df_multipliers.empty:
        df_multipliers.set_index('Transition', inplace=True)
        
        # Display preview
        preview_cols = [c for c in ['PA', 'H', 'HR', 'ERA', 'IP'] if c in df_multipliers.columns]
        print("\nCalculated Development Multipliers (Median):")
        print(df_multipliers[preview_cols].to_string() if preview_cols else df_multipliers.head())
        
        # --- Save to specified directory ---
        output_dir = os.path.join('data', 'development_multipliers')
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, 'development_multipliers.csv')
        df_multipliers.to_csv(output_file)
        print(f"Saved multipliers to '{output_file}'")
    else:
        print("Warning: No valid transition data found.")

if __name__ == "__main__":
    generate_stat_multipliers()