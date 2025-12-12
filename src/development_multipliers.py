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
    Calculates Year-Over-Year (YoY) performance ratios for various player cohorts.

    Context:
        Baseball Context:
            This is the "Scouting Department" quantifying player development. We all know 
            that a Senior is generally stronger and faster than a Freshman. But by how much? 
            Does a player improve more from their 1st to 2nd year on Varsity, or simply by 
            getting older? This script answers the question: "If a kid hits .300 as a 
            Sophomore, what should we expect him to hit as a Junior?"

            The values derived in this script are used to predict the performance of a player in 
            a future year. 

        Statistical Validity:
            1. Design: Paired Longitudinal Study. We only analyze subjects (players) who 
               appear in two consecutive time periods ($t$ and $t+1$).
            2. Survivorship Bias: The model inherently selects for players who "survived" 
               to play another year. This is a feature, not a bug—we want to project 
               performance for *returning* players, so our training data should consist 
               of players who successfully returned.
            3. Estimator: Uses the **Median of Ratios** rather than the Ratio of Averages. 
               This is robust to outliers (e.g., a player going from 1 HR to 15 HRs) that 
               would skew a Mean calculation.

        Technical Implementation:
            This script performs a Self-Join on the historical dataset.
            1. We alias the table as `Previous_Year` and `Next_Year`.
            2. We join on `Player_ID` and `Year = Year + 1` (conceptually similar to a 
               SQL `LAG()` window function, but materialized as a join).
            3. We partition the data into Cohorts (e.g., Freshman->Sophomore) and 
               calculate aggregate statistics for each group.

        Integration & Output:
            1. Output Artifact: 'data/development_multipliers/development_multipliers.csv'
               - Index: 'Transition' key (e.g., 'Freshman_to_Sophomore', 'Varsity_Year1_to_Year2').
               - Columns: Floating point multipliers for each stat (e.g., 'HR': 1.50 means a 50% increase).
            
            2. Downstream Usage:
               - Consumer: `roster_prediction.py`
               - Logic: This file serves as the "Lookup Table" for the projection engine. When predicting 
                 next year's stats, the system identifies the player's transition path (e.g., Soph->Junior) 
                 and multiplies their current stats by the factors found in this CSV.
                 Formula: $ProjectedStat = CurrentStat * Multiplier_{Transition}$
    """
    
    # --- Load Data ---
    input_file = os.path.join('data', 'processed', 'history', 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return
        
    print(f"Loading data from {input_file}...")
    df = pd.read_csv(input_file)

    # --- 1. Dynamic Column Handling using Config ---
    # We dynamically build our query columns based on the config schema.
    # This ensures that if we add "Stolen Bases" to config.py later, it automatically gets calculated here.
    available_stats = set(df.columns)
    stat_cols = []
    stat_types = {} 

    for stat_def in STAT_SCHEMA:
        abbr = stat_def['abbreviation']
        if abbr in available_stats:
            stat_cols.append(abbr)
            stat_types[abbr] = stat_def['stat_type']

    # Convert numeric columns (Data Casting)
    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # --- 2. Centralized Data Prep (Utils) ---
    # Applies the exact same "Identity Resolution" logic as the rest of the pipeline.
    # Essential to ensure the Join Keys (Name, Team) match perfectly.
    df = prepare_analysis_data(df)
    
    # --- 3. Join Logic (Self-Join Year N vs Year N+1) ---
    # We create a copy of the dataframe to act as the "Previous Year" table.
    # We increment the year by 1 so we can join [Year 2023] to [Year 2024].
    df_prev = df.copy()
    df_prev['Join_Year'] = df_prev['Season_Year'] + 1 
    
    # SQL Equivalent:
    # SELECT * FROM df AS Prev
    # INNER JOIN df AS Next 
    #   ON Prev.Name = Next.Name 
    #   AND Prev.Team = Next.Team 
    #   AND Prev.Join_Year = Next.Season_Year
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
    # These act as the "GROUP BY" clauses for our analysis.
    
    # Simple biological aging (Freshman -> Sophomore)
    class_transitions = [
        ('Class', 'Freshman', 'Sophomore'),
        ('Class', 'Sophomore', 'Junior'),
        ('Class', 'Junior', 'Senior')
    ]
    
    # Experience-based aging (1st Year Varsity -> 2nd Year Varsity)
    tenure_transitions = [
        ('Tenure', 1, 2),
        ('Tenure', 2, 3),
        ('Tenure', 3, 4)
    ]

    # The "Specific" lookup: A Sophomore with 1 year experience becoming a Junior with 2 years.
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
        
        # Filter Logic based on Category (The WHERE clause for this partition)
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
        
        # Calculate multipliers for every stat column in the schema
        for col in stat_cols:
            subset = cohort.copy()
            st_type = stat_types.get(col, 'Batting')
            
            # Filtering Logic: Enforcing Minimum Thresholds
            # We filter out "cups of coffee" (insignificant playing time) to avoid noise.
            # A kid with 1 AB hitting 1.000 (1/1) shouldn't skew the projection for a starter.
            if st_type == 'Pitching':
                if 'IP_Prev' in subset.columns:
                    subset = subset[subset['IP_Prev'] >= 5] 
                else: continue 
            else:
                if 'PA_Prev' in subset.columns:
                    subset = subset[subset['PA_Prev'] >= 10]
                else: continue

            # Avoid Division by Zero errors
            subset = subset[subset[f'{col}_Prev'] > 0]

            # Minimum Sample Size Check
            # If we don't have at least 3 players in history making this jump, we assume no change (1.0).
            if len(subset) < 3:
                transition_stats[col] = 1.0 
                continue

            # THE CORE CALCULATION:
            # Multiplier = Stat_Year_2 / Stat_Year_1
            ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']
            
            # We use Median instead of Mean. 
            # Mean is sensitive to outliers (someone improving 500%). 
            # Median gives us the "Typical" improvement.
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