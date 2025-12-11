import pandas as pd

def infer_missing_classes(df):
    """
    Fills in 'Unknown' class years based on the progression of years.
    Logic:
      - Freshman -> Sophomore -> Junior -> Senior
      - If we know year X, we can infer X+1 and X-1.
    
    UPDATED: Now saves the result to 'Class_Cleaned' instead of overwriting 'Class'.
    """
    if df.empty or 'Class' not in df.columns or 'Season_Cleaned' not in df.columns:
        return df

    # 1. Standardize Class Names to Integers for math (Freshman=1, Senior=4)
    class_map = {
        'Freshman': 1, 
        'Sophomore': 2, 
        'Junior': 3, 
        'Senior': 4,
        'Unknown': None
    }
    reverse_map = {v: k for k, v in class_map.items() if v}

    # Create a temporary numeric column
    df['Class_Num'] = df['Class'].map(class_map)
    
    # Ensure Season is numeric
    df['Season_Num'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')

    # 2. Sort by Name and Year so we can see the timeline
    df = df.sort_values(by=['Name', 'Season_Num'])

    # 3. The Inference Loop
    # We group by Name so we process one player's timeline at a time
    for name, group in df.groupby('Name'):
        known_records = group.dropna(subset=['Class_Num', 'Season_Num'])
        
        if known_records.empty:
            continue
            
        # Take the most reliable "Anchor" point (e.g., the latest known year)
        # Ideally, we'd use all points, but one anchor is usually enough for HS ball (4 years max)
        anchor = known_records.iloc[-1] 
        anchor_year = anchor['Season_Num']
        anchor_class = anchor['Class_Num']
        
        # Calculate the expected class for every row based on the anchor
        # Formula: Expected = Anchor_Class - (Anchor_Year - Current_Year)
        
        def fill_row(row):
            if pd.isna(row['Class_Num']) and not pd.isna(row['Season_Num']):
                diff = row['Season_Num'] - anchor_year
                expected_class = anchor_class + diff
                
                # Validity check: High School is 1-4
                if 1 <= expected_class <= 4:
                    return expected_class
            return row['Class_Num']

        # Apply logic to the specific indices in the main dataframe
        df.loc[group.index, 'Class_Num'] = group.apply(fill_row, axis=1)

    # 4. Convert back to string labels
    df['Class_Inferred'] = df['Class_Num'].map(reverse_map)
    
    # --- UPDATE START ---
    # Create Class_Cleaned initialized with the original Class data
    df['Class_Cleaned'] = df['Class'].replace('Unknown', None)
    
    # Fill Class_Cleaned where it was missing using the Inferred column
    df['Class_Cleaned'] = df['Class_Cleaned'].fillna(df['Class_Inferred'])
    
    # Restore 'Unknown' in Class_Cleaned if we truly couldn't guess
    df['Class_Cleaned'] = df['Class_Cleaned'].fillna('Unknown')
    # --- UPDATE END ---
    
    # Cleanup temporary columns
    df = df.drop(columns=['Class_Num', 'Season_Num', 'Class_Inferred'])
    
    return df