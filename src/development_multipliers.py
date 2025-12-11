import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
try:
    from src.config import STAT_SCHEMA
    from src.utils import prepare_analysis_data
except ImportError:
    try:
        from config import STAT_SCHEMA
        from utils import prepare_analysis_data
    except ImportError:
        print("Error: Could not import config or utils. Please ensure src/config.py and src/utils.py exist.")
        sys.exit(1)

def generate_stat_multipliers():
    """
    1. Loads aggregated history.
    2. Identifies players who played in consecutive years.
    3. Calculates multipliers for Class, Tenure, and Combined transitions.
    """
    
    # --- Load Data ---
    input_file = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return
        
    print(f"Loading data from {input_file}...")
    df = pd.read_csv(input_file)

    # --- 1. Dynamic Column Handling using Config ---
    available_stats = set(df.columns)
    stat_cols = []
    stat_types = {} 

    for stat_def in STAT_SCHEMA:
        abbr = stat_def['abbreviation']
        if abbr in available_stats:
            stat_cols.append(abbr)
            stat_types[abbr] = stat_def['stat_type']

    # Convert numeric columns
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # --- 2. Centralized Data Prep (Utils) ---
    # Calculates Season_Year, Match Keys, and Varsity_Year
    df = prepare_analysis_data(df)
    
    # --- 3. Join Logic (Self-Join Year N vs Year N+1) ---
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

    # --- 4. Define Transitions ---
    
    # Class Transitions
    class_transitions = [
        ('Class', 'Freshman', 'Sophomore'),
        ('Class', 'Sophomore', 'Junior'),
        ('Class', 'Junior', 'Senior')
    ]
    
    # Tenure Transitions
    tenure_transitions = [
        ('Tenure', 1, 2),
        ('Tenure', 2, 3),
        ('Tenure', 3, 4)
    ]

    # Combined Class + Tenure Transitions
    combined_transitions = [
        ('Class_Tenure', ('Freshman', 1), ('Sophomore', 2)), 
        ('Class_Tenure', ('Sophomore', 1), ('Junior', 2)),   
        ('Class_Tenure', ('Sophomore', 2), ('Junior', 3)),   
        ('Class_Tenure', ('Junior', 1), ('Senior', 2)),      
        ('Class_Tenure', ('Junior', 2), ('Senior', 3)),      
        ('Class_Tenure', ('Junior', 3), ('Senior', 4)),      
    ]
    
    all_transitions = class_transitions + tenure_transitions + combined_transitions
    
    multipliers = []
    
    print("\n--- Processing Cohorts ---")

    for definition in all_transitions:
        category = definition[0]
        start_val = definition[1]
        end_val = definition[2]
        
        # Filter Logic based on Category
        if category == 'Class':
            cohort = merged[
                (merged['Class_Cleaned_Prev'] == start_val) & 
                (merged['Class_Cleaned_Next'] == end_val)
            ]
            trans_name = f"{start_val}_to_{end_val}"
            
        elif category == 'Tenure':
            cohort = merged[
                (merged['Varsity_Year_Prev'] == start_val) & 
                (merged['Varsity_Year_Next'] == end_val)
            ]
            trans_name = f"Varsity_Year{start_val}_to_Year{end_val}"
            
        elif category == 'Class_Tenure':
            s_cls, s_ten = start_val
            e_cls, e_ten = end_val
            cohort = merged[
                (merged['Class_Cleaned_Prev'] == s_cls) & 
                (merged['Varsity_Year_Prev'] == s_ten) &
                (merged['Class_Cleaned_Next'] == e_cls) & 
                (merged['Varsity_Year_Next'] == e_ten)
            ]
            trans_name = f"{s_cls}_Y{s_ten}_to_{e_cls}_Y{e_ten}"

        transition_stats = {'Transition': trans_name, 'Type': category, 'Sample_Size': len(cohort)}
        
        for col in stat_cols:
            subset = cohort.copy()
            st_type = stat_types.get(col, 'Batting')
            
            # Filtering Logic
            if st_type == 'Pitching':
                if 'IP_Prev' in subset.columns:
                    subset = subset[subset['IP_Prev'] >= 5] 
                else: continue 
            else:
                if 'PA_Prev' in subset.columns:
                    subset = subset[subset['PA_Prev'] >= 10]
                else: continue

            subset = subset[subset[f'{col}_Prev'] > 0]

            if len(subset) < 3:
                transition_stats[col] = 1.0 
                continue

            ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']
            transition_stats[col] = round(ratios.median(), 3)
            
        multipliers.append(transition_stats)

    df_multipliers = pd.DataFrame(multipliers)
    
    if not df_multipliers.empty:
        df_multipliers.set_index('Transition', inplace=True)
        
        # Save
        output_dir = os.path.join('data', 'development_multipliers')
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, 'development_multipliers.csv')
        df_multipliers.to_csv(output_file)
        print(f"\nSaved multipliers to '{output_file}'")
    else:
        print("Warning: No valid transition data found.")

if __name__ == "__main__":
    generate_stat_multipliers()