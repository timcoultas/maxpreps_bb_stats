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
    3. Calculates multipliers for:
       a) Standard Class Progressions (Freshman -> Sophomore, etc.)
       b) Varsity Tenure Progressions (Year 1 -> Year 2, etc.)
    4. Outputs a combined multipliers CSV.
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
    available_stats = set(df.columns)
    stat_cols = []
    stat_types = {} 

    for stat_def in STAT_SCHEMA:
        abbr = stat_def['abbreviation']
        if abbr in available_stats:
            stat_cols.append(abbr)
            stat_types[abbr] = stat_def['stat_type']

    print(f"Processing {len(stat_cols)} stats defined in config...")

    # Convert numeric columns
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Ensure Year is int
    if 'Season_Cleaned' in df.columns:
        df['Season_Year'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')
        df = df.dropna(subset=['Season_Year']) 
        df['Season_Year'] = df['Season_Year'].astype(int)
    else:
        print("Error: 'Season_Cleaned' column missing.")
        return
    
    # --- PREPARATION ---
    # Normalize Names/Teams for matching
    df['Match_Name'] = df['Name'].astype(str).str.strip().str.lower()
    df['Match_Team'] = df['Team'].astype(str).str.strip().str.lower()
    
    # --- CALCULATE VARSITY TENURE (Year 1, Year 2, etc.) ---
    # We sort by Player and Year, then count the cumulative occurrence.
    # Rank 1 = First year appearing in dataset (Year 1)
    # Rank 2 = Second year appearing in dataset (Year 2)
    df = df.sort_values(['Match_Team', 'Match_Name', 'Season_Year'])
    df['Varsity_Year'] = df.groupby(['Match_Team', 'Match_Name']).cumcount() + 1
    
    # --- JOIN LOGIC (Self-Join Year N vs Year N+1) ---
    df_prev = df.copy()
    df_prev['Join_Year'] = df_prev['Season_Year'] + 1 
    
    merged = pd.merge(
        df_prev, 
        df, 
        left_on=['Match_Name', 'Match_Team', 'Join_Year'], 
        right_on=['Match_Name', 'Match_Team', 'Season_Year'],
        suffixes=('_Prev', '_Next')
    )
    
    print(f"Found {len(merged)} player-seasons with year-over-year data.")
    
    if len(merged) == 0:
        print("Warning: Zero matches found.")
        return

    # --- DEFINE TRANSITIONS ---
    # We now have two types of transitions we want to calculate.
    
    # 1. Class Transitions (Freshman -> Sophomore)
    class_transitions = [
        ('Class', 'Freshman', 'Sophomore'),
        ('Class', 'Sophomore', 'Junior'),
        ('Class', 'Junior', 'Senior')
    ]
    
    # 2. Tenure Transitions (Year 1 -> Year 2)
    tenure_transitions = [
        ('Tenure', 1, 2),
        ('Tenure', 2, 3),
        ('Tenure', 3, 4)
    ]
    
    all_transitions = class_transitions + tenure_transitions
    
    multipliers = []

    for category, start_val, end_val in all_transitions:
        
        # Filter the cohort based on the category (Class vs Tenure)
        if category == 'Class':
            cohort = merged[
                (merged['Class_Cleaned_Prev'] == start_val) & 
                (merged['Class_Cleaned_Next'] == end_val)
            ]
            trans_name = f"{start_val}_to_{end_val}"
        else: # Tenure
            cohort = merged[
                (merged['Varsity_Year_Prev'] == start_val) & 
                (merged['Varsity_Year_Next'] == end_val)
            ]
            trans_name = f"Varsity_Year{start_val}_to_Year{end_val}"

        # --- DEBUG VIEW (Specific Requests) ---
        if (category == 'Class' and start_val == 'Junior' and end_val == 'Senior'):
             print(f"\n--- DEBUG: {trans_name} (n={len(cohort)}) ---")
             # (Existing debug logic omitted for brevity unless needed, but keeping simple print)

        transition_stats = {'Transition': trans_name, 'Type': category}
        
        for col in stat_cols:
            subset = cohort.copy()
            st_type = stat_types.get(col, 'Batting')
            
            # --- FILTERING LOGIC ---
            if st_type == 'Pitching':
                if 'IP_Prev' in subset.columns:
                    subset = subset[subset['IP_Prev'] >= 5] 
                else: continue 
            else:
                if 'PA_Prev' in subset.columns:
                    subset = subset[subset['PA_Prev'] >= 10]
                else: continue

            # Valid Denominator
            subset = subset[subset[f'{col}_Prev'] > 0]

            # Minimum Population
            if len(subset) < 3:
                transition_stats[col] = 1.0 
                continue

            # --- CALCULATION (Median) ---
            ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']
            transition_stats[col] = round(ratios.median(), 3)
            
        multipliers.append(transition_stats)

    df_multipliers = pd.DataFrame(multipliers)
    
    if not df_multipliers.empty:
        df_multipliers.set_index('Transition', inplace=True)
        
        # Display preview
        preview_cols = [c for c in ['PA', 'H', 'HR', 'ERA', 'IP'] if c in df_multipliers.columns]
        print("\nCalculated Development Multipliers (Median):")
        print(df_multipliers[preview_cols].to_string() if preview_cols else df_multipliers.head())
        
        # --- Save ---
        output_dir = os.path.join('data', 'development_multipliers')
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, 'development_multipliers.csv')
        df_multipliers.to_csv(output_file)
        print(f"Saved multipliers to '{output_file}'")
    else:
        print("Warning: No valid transition data found.")

if __name__ == "__main__":
    generate_stat_multipliers()