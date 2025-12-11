import pandas as pd

def prepare_analysis_data(df):
    """
    Standardizes player data for analysis.
    This centralized logic ensures that 'Varsity_Year' is calculated 
    exactly the same way for both the Multiplier calculation and the Roster Prediction.
    
    Performs:
    1. Season_Year extraction (int) from Season_Cleaned
    2. Name/Team normalization (Match_Name, Match_Team)
    3. Varsity Tenure calculation (Varsity_Year)
    """
    # work on a copy to prevent SettingWithCopy warnings on the original slice
    df = df.copy()
    
    # 1. Ensure Year is Integer
    if 'Season_Cleaned' in df.columns:
        df['Season_Year'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')
        # Drop rows where year is invalid
        df = df.dropna(subset=['Season_Year'])
        df['Season_Year'] = df['Season_Year'].astype(int)
    else:
        # If we lack season info, we can't calculate tenure correctly
        raise ValueError("DataFrame missing required column: 'Season_Cleaned'")
    
    # 2. Normalize Names for Identity Tracking
    # Use strict lowercasing and stripping to ensure "Z. Perry" matches "z. perry "
    df['Match_Name'] = df['Name'].astype(str).str.strip().str.lower()
    df['Match_Team'] = df['Team'].astype(str).str.strip().str.lower()
    
    # 3. Calculate Tenure (Varsity_Year)
    # We must sort by Team -> Name -> Year to ensure the cumcount() represents chronological order
    df = df.sort_values(['Match_Team', 'Match_Name', 'Season_Year'])
    
    # Rank 1 = First year appearing in dataset (Year 1)
    df['Varsity_Year'] = df.groupby(['Match_Team', 'Match_Name']).cumcount() + 1
    
    return df