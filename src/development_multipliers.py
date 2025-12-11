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
    2. Identifies players who played in consecutive years (Match by NAME + TEAM).
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
        df['Season_Year'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')
        df = df.dropna(subset=['Season_Year']) # Drop rows where year couldn't be parsed
        df['Season_Year'] = df['Season_Year'].astype(int)
    else:
        print("Error: 'Season_Cleaned' column missing from input CSV.")
        return
    
    # --- Step 2: Create the "Development Curve" (Year N vs Year N+1) ---
    
    # PREPARATION: Normalize Names/Teams for matching
    # Athlete_IDs are unstable across years, so we use Name + Team as the unique identifier.
    df['Match_Name'] = df['Name'].astype(str).str.strip().str.lower()
    df['Match_Team'] = df['Team'].astype(str).str.strip().str.lower()
    
    # LOGIC:
    # We need to compare Player X in Year N (Prev) vs Player X in Year N+1 (Next).
    df_prev = df.copy()
    df_prev['Join_Year'] = df_prev['Season_Year'] + 1  # The year we are predicting FOR
    
    # Merge on Name, Team, and the Calculated Join Year
    merged = pd.merge(
        df_prev, 
        df, 
        left_on=['Match_Name', 'Match_Team', 'Join_Year'], 
        right_on=['Match_Name', 'Match_Team', 'Season_Year'],
        suffixes=('_Prev', '_Next')
    )
    
    print(f"Found {len(merged)} player-seasons with year-over-year data (Matched by Name/Team).")
    
    if len(merged) == 0:
        print("Warning: Zero matches found. Please check if 'Name' and 'Team' formats are consistent across years.")
        return

    valid_transitions = {
        'Freshman': 'Sophomore',
        'Sophomore': 'Junior',
        'Junior': 'Senior'
    }

    if 'Class_Cleaned_Prev' not in merged.columns or 'Class_Cleaned_Next' not in merged.columns:
        print("Error: 'Class_Cleaned' column missing.")
        return
    
    # --- Step 3: Calculate Multipliers ---
    
    multipliers = []

    for start_class, end_class in valid_transitions.items():
        # Get the "Cohort": 
        # 1. Started as Start_Class (e.g., Freshman)
        # 2. Ended as End_Class (e.g., Sophomore)
        # We explicitly check the Next Class to avoid data errors (e.g. someone listed as Junior -> Junior)
        cohort = merged[
            (merged['Class_Cleaned_Prev'] == start_class) & 
            (merged['Class_Cleaned_Next'] == end_class)
        ]
        
        transition_stats = {'Transition': f"{start_class}_to_{end_class}"}
        
        for col in stat_cols:
            subset = cohort.copy()
            st_type = stat_types.get(col, 'Batting') # Default to Batting if unknown
            
            # --- FILTERING LOGIC ---
            # We filter out players with small sample sizes in the previous year.
            # Rationale: Small samples (e.g., 1 AB) create noisy, unreliable multipliers (e.g. 1 Hit / 1 AB = 1.000 Avg).
            
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
            # We cannot divide by zero.
            subset = subset[subset[f'{col}_Prev'] > 0]

            # 4. Minimum Population Check
            # If we have fewer than 3 players in this cohort after filtering, the data is too scarce to trust.
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
            #    Example: A bench player going from 1 HR to 10 HR is a 10x multiplier.
            #    If we averaged that with normal players (1.1x), the result would be skewed high.
            #    The Median gives us the "typical" progression.
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