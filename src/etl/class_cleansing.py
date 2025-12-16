import pandas as pd
import numpy as np

def fix_class_progression(df):
    """
    Corrects data quality issues where players fail to age correctly (e.g., Sophomore in 2024 -> Sophomore in 2025).
    
    Context:
        Some source data (like Rock Canyon 2025) lists returning players with the same class as the previous year.
        This function enforces a strict progression rule: A player's class must increase by at least 1 grade level 
        for each advancing year.
        
        Logic:
        1. Convert Class to Integer (Freshman=1, ... Senior=4).
        2. Group by Player.
        3. Sort by Year.
        4. Iterate through history:
           - If Current_Class <= Previous_Class, force Current_Class = Previous_Class + (Current_Year - Previous_Year).
    
    Args:
        df (pd.DataFrame): The dataframe containing player records with 'Class_Cleaned' and 'Season_Cleaned'.
        
    Returns:
        pd.DataFrame: The dataframe with corrected 'Class_Cleaned' values.
    """
    if df.empty:
        return df
        
    print("   -> Running Class Progression Fixer...")
    
    # 1. Map Class to Numeric
    class_map = {
        'Freshman': 1, 
        'Sophomore': 2, 
        'Junior': 3, 
        'Senior': 4,
        'Unknown': np.nan
    }
    reverse_map = {v: k for k, v in class_map.items() if pd.notna(v)}
    
    # Work on a copy to avoid SettingWithCopy warnings
    df = df.copy()
    
    # Create temp numeric columns
    df['Class_Num'] = df['Class_Cleaned'].map(class_map)
    df['Season_Num'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')
    
    # 2. Sort for chronological processing
    df = df.sort_values(by=['Name', 'Team', 'Season_Num'])
    
    # 3. Apply Correction Logic
    # We use a custom apply function on each player's history
    def correct_player_timeline(group):
        # If only 1 record, nothing to correct based on history
        if len(group) < 2:
            return group
            
        # Get valid records sorted by year
        records = group.sort_values('Season_Num')
        
        # Iterate through the timeline
        # We can't use vectorization easily because each correction depends on the previous corrected value
        last_valid_class = np.nan
        last_valid_year = np.nan
        
        updates = []
        
        for idx, row in records.iterrows():
            current_class = row['Class_Num']
            current_year = row['Season_Num']
            
            # If this is the first record, establish baseline
            if pd.isna(last_valid_year):
                if pd.notna(current_class):
                    last_valid_class = current_class
                    last_valid_year = current_year
                continue
                
            # Check for progression violation
            # Logic: If we have a history, the current class MUST be at least (Last_Class + Year_Diff)
            if pd.notna(last_valid_class) and pd.notna(current_year):
                year_diff = current_year - last_valid_year
                expected_min_class = last_valid_class + year_diff
                
                # If current data is missing OR clearly wrong (younger/same as expected), fix it
                if pd.isna(current_class) or current_class < expected_min_class:
                    # Correction!
                    # Cap at 4 (Senior) to avoid creating "Super Seniors" (Grade 13) unless they actually redshirted?
                    # For HS stats, usually better to cap at Senior.
                    new_class = min(expected_min_class, 4) 
                    
                    # Store update
                    updates.append((idx, new_class))
                    
                    # Update our running baseline
                    last_valid_class = new_class
                    last_valid_year = current_year
                else:
                    # Data is valid (or at least consistent), update baseline
                    last_valid_class = current_class
                    last_valid_year = current_year
            
            elif pd.notna(current_class):
                # We didn't have a baseline, but now we do
                last_valid_class = current_class
                last_valid_year = current_year
                
        # Apply updates to the group slice
        for idx, val in updates:
            group.at[idx, 'Class_Num'] = val
            
        return group

    # Group by Player Identity (Name + Team) to handle transfers separately (safest)
    # or just Name if we trust uniqueness. Given 'match_name' logic elsewhere, let's group by Name & Team.
    # Note: Using the original 'infer_missing_classes' logic, we might want to just group by Name if unique enough.
    # Let's stick to Name + Team to be safe against "John Smith" collisions across different schools.
    
    # Optimization: Only process groups with > 1 record
    counts = df.groupby(['Name', 'Team']).size()
    multi_year_players = counts[counts > 1].index
    
    # Filter for relevant rows to speed up apply
    mask = df.set_index(['Name', 'Team']).index.isin(multi_year_players)
    subset = df[mask].copy()
    
    if not subset.empty:
        corrected_subset = subset.groupby(['Name', 'Team'], group_keys=False).apply(correct_player_timeline)
        
        # Merge corrections back to main dataframe
        # We rely on index alignment
        df.loc[corrected_subset.index, 'Class_Num'] = corrected_subset['Class_Num']

    # 4. Map back to Strings
    # logic: if Class_Num was updated, update Class_Cleaned
    df['Class_Cleaned_Corrected'] = df['Class_Num'].map(reverse_map)
    
    # Combine: Use corrected if available, else original
    df['Class_Cleaned'] = df['Class_Cleaned_Corrected'].fillna(df['Class_Cleaned'])
    
    # Drop temp cols
    df = df.drop(columns=['Class_Num', 'Season_Num', 'Class_Cleaned_Corrected'])
    
    return df