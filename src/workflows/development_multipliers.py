import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
try:
    from src.utils.config import STAT_SCHEMA, PATHS
    from src.utils.utils import prepare_analysis_data
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA, PATHS
    from src.utils.utils import prepare_analysis_data

def generate_stat_multipliers():
    """
    Calculates Year-Over-Year (YoY) performance ratios and their VOLATILITY.
    
    This script analyzes the full historical dataset to determine how players typically 
    develop from one year to the next. It produces both a 'Multiplier' (Median improvement) 
    and a 'Volatility' score (Standard Deviation) to help gauge confidence in the projection.
    """
    
    # --- Load Data ---
    input_file = os.path.join(PATHS['processed'], 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return
        
    print(f"Loading data from {input_file}...")
    df = pd.read_csv(input_file)

    # --- 1. Dynamic Column Handling ---
    available_stats = set(df.columns)
    stat_cols = []
    stat_types = {} 

    for stat_def in STAT_SCHEMA:
        abbr = stat_def['abbreviation']
        if abbr in available_stats:
            stat_cols.append(abbr)
            stat_types[abbr] = stat_def['stat_type']

    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # --- 2. Prep ---
    df = prepare_analysis_data(df)
    
    # --- 3. Join Logic ---
    df_prev = df.copy()
    df_prev['Join_Year'] = df_prev['Season_Year'] + 1 
    
    merged = pd.merge(
        df_prev, 
        df, 
        left_on=['Match_Name', 'Match_Team', 'Join_Year'], 
        right_on=['Match_Name', 'Match_Team', 'Season_Year'],
        suffixes=('_Prev', '_Next')
    )
    
    print(f"Found {len(merged)} year-over-year player transitions.")

    # --- 4. Define Transitions ---
    transitions = [
        # Biological
        ('Class', 'Freshman', 'Sophomore'),
        ('Class', 'Sophomore', 'Junior'),
        ('Class', 'Junior', 'Senior'),
        # Experience
        ('Tenure', 1, 2),
        ('Tenure', 2, 3),
        ('Tenure', 3, 4),
        # Specific
        ('Class_Tenure', ('Freshman', 1), ('Sophomore', 2)), 
        ('Class_Tenure', ('Sophomore', 1), ('Junior', 2)),   
        ('Class_Tenure', ('Sophomore', 2), ('Junior', 3)),   
        ('Class_Tenure', ('Junior', 1), ('Senior', 2)),      
        ('Class_Tenure', ('Junior', 2), ('Senior', 3)),      
        ('Class_Tenure', ('Junior', 3), ('Senior', 4)), 
    ]
    
    multipliers = []
    
    print("\n--- Processing Cohorts ---")

    for definition in transitions:
        category = definition[0]
        start_val = definition[1]
        end_val = definition[2]
        
        # Filter Cohort
        if category == 'Class':
            cohort = merged[(merged['Class_Cleaned_Prev'] == start_val) & (merged['Class_Cleaned_Next'] == end_val)]
            trans_name = f"{start_val}_to_{end_val}"
        elif category == 'Tenure':
            cohort = merged[(merged['Varsity_Year_Prev'] == start_val) & (merged['Varsity_Year_Next'] == end_val)]
            trans_name = f"Varsity_Year{start_val}_to_Year{end_val}"
        elif category == 'Class_Tenure':
            s_cls, s_ten = start_val
            e_cls, e_ten = end_val
            cohort = merged[
                (merged['Class_Cleaned_Prev'] == s_cls) & (merged['Varsity_Year_Prev'] == s_ten) &
                (merged['Class_Cleaned_Next'] == e_cls) & (merged['Varsity_Year_Next'] == e_ten)
            ]
            trans_name = f"{s_cls}_Y{s_ten}_to_{e_cls}_Y{e_ten}"

        # Initialize stats row
        transition_stats = {
            'Transition': trans_name, 
            'Type': category, 
            'Sample_Size': len(cohort),
            'Avg_Volatility': 0.0 # Placeholder
        }
        
        volatility_scores = []

        for col in stat_cols:
            subset = cohort.copy()
            st_type = stat_types.get(col, 'Batting')
            
            # Filter for significant playing time to reduce noise
            if st_type == 'Pitching':
                if 'IP_Prev' in subset.columns: subset = subset[subset['IP_Prev'] >= 5] 
                else: continue 
            else:
                if 'PA_Prev' in subset.columns: subset = subset[subset['PA_Prev'] >= 10]
                else: continue

            subset = subset[subset[f'{col}_Prev'] > 0]

            if len(subset) < 3: 
                transition_stats[col] = 1.0 
                continue

            # Calculate Ratios
            ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']
            
            # 1. The Multiplier (Median is robust)
            transition_stats[col] = round(ratios.median(), 3)
            
            # 2. The Volatility (Standard Deviation)
            # This tells us how "correct" the bucket is. Lower is better.
            std_dev = ratios.std()
            if not np.isnan(std_dev):
                volatility_scores.append(std_dev)

        # Calculate Aggregate Volatility for this Transition type
        if volatility_scores:
            transition_stats['Avg_Volatility'] = round(sum(volatility_scores) / len(volatility_scores), 3)
        
        multipliers.append(transition_stats)

    df_multipliers = pd.DataFrame(multipliers)
    
    if not df_multipliers.empty:
        df_multipliers.set_index('Transition', inplace=True)
        
        # Save to correct output path
        output_dir = PATHS['out_development_multipliers']
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, 'development_multipliers.csv')
        df_multipliers.to_csv(output_file)
        
        print(f"\nSaved multipliers to '{output_file}'")
        
        # --- QUICK ANALYSIS REPORT ---
        print("\n=== VOLATILITY ANALYSIS (Lower is Better) ===")
        print(df_multipliers[['Type', 'Sample_Size', 'Avg_Volatility']].sort_values('Avg_Volatility').to_string())
        
    else:
        print("Warning: No valid transition data found.")

if __name__ == "__main__":
    generate_stat_multipliers()