import pandas as pd

def infer_missing_classes(df):
    """
    Imputes missing 'Class' values (Freshman, Sophomore, etc.) based on longitudinal data.

    Context:
        Sometimes the roster is incomplete. A player might be listed as a "Junior" in 2024, but their 
        2023 file just lists them as "Unknown" or is missing the tag entirely. We know players don't 
        age backwards or skip grades. If we know a kid is a Senior in 2025, we can safely write 
        "Junior" on his 2024 card and "Sophomore" on his 2023 card. This function fills in those 
        blanks so we can track player development accurately.

        Statistically, this performs Deterministic Imputation. Unlike mean substitution or regression 
        imputation, this logic is based on an immutable progression rule ($Class_{t} = Class_{t-1} + 1$). 
        This preserves the integrity of cohort analysis (e.g., "Sophomore Performance") by maximizing 
        the available sample size $N$ without introducing stochastic error.

        Technically, this is a Group-Based Transformation (Window Function).
        1. We partition the data by Player ID (Name).
        2. We sort by Time (Season).
        3. We identify an "Anchor Row" (a record where Class IS NOT NULL).
        4. We apply a linear offset function: $EstimatedClass = AnchorClass - (AnchorYear - CurrentYear)$.
        This is conceptually similar to a SQL `LAG()`/`LEAD()` operation or a recursive CTE used to 
        fill gaps in time-series data.

    Args:
        df (pd.DataFrame): The dataframe containing player records with potentially missing 'Class' values.

    Returns:
        pd.DataFrame: The dataframe with a new column 'Class_Cleaned' containing the imputed values.
    """
    if df.empty or 'Class' not in df.columns or 'Season_Cleaned' not in df.columns:
        return df

    # 1. Standardize Class Names to Integers for math (Freshman=1, Senior=4)
    # Mapping categorical ordinal variables to integers allows for arithmetic operations
    class_map = {
        'Freshman': 1, 
        'Sophomore': 2, 
        'Junior': 3, 
        'Senior': 4,
        'Unknown': None
    }
    # Create reverse map to convert back to string labels later
    reverse_map = {v: k for k, v in class_map.items() if v}

    # Create a temporary numeric column for calculation
    # This is our working column, similar to casting a VARCHAR to INT in SQL
    df['Class_Num'] = df['Class'].map(class_map)
    
    # Ensure Season is numeric to calculate time deltas
    df['Season_Num'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')

    # 2. Sort by Name and Year so we can see the timeline
    # ORDER BY Name, Season_Num
    df = df.sort_values(by=['Name', 'Season_Num'])

    # 3. The Inference Loop
    # We group by Name so we process one player's timeline at a time (Partitioning)
    for name, group in df.groupby('Name'):
        # Filter for rows that HAVE valid data (The Anchors)
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
            # Only fill if missing (IS NULL) and we have a valid year
            if pd.isna(row['Class_Num']) and not pd.isna(row['Season_Num']):
                diff = row['Season_Num'] - anchor_year
                expected_class = anchor_class + diff
                
                # Validity check: High School is 1-4. 
                # Discard values like "Grade 13" or "Grade 0" (Middle School)
                if 1 <= expected_class <= 4:
                    return expected_class
            return row['Class_Num']

        # Apply logic to the specific indices in the main dataframe
        # Updating the main table using the index from the group partition
        df.loc[group.index, 'Class_Num'] = group.apply(fill_row, axis=1)

    # 4. Convert back to string labels
    # Casting INT back to VARCHAR/Enum
    df['Class_Inferred'] = df['Class_Num'].map(reverse_map)
    
    # --- UPDATE START ---
    # Create Class_Cleaned initialized with the original Class data
    # COALESCE logic: Take original, if null take inferred, if null take 'Unknown'
    df['Class_Cleaned'] = df['Class'].replace('Unknown', None)
    
    # Fill Class_Cleaned where it was missing using the Inferred column
    df['Class_Cleaned'] = df['Class_Cleaned'].fillna(df['Class_Inferred'])
    
    # Restore 'Unknown' in Class_Cleaned if we truly couldn't guess
    df['Class_Cleaned'] = df['Class_Cleaned'].fillna('Unknown')
    # --- UPDATE END ---
    
    # Cleanup temporary columns (Drop intermediate tables)
    df = df.drop(columns=['Class_Num', 'Season_Num', 'Class_Inferred'])
    
    return df