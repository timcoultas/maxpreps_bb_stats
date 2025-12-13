import pandas as pd

def prepare_analysis_data(df):
    """
    Standardizes player identifiers and calculates derived longitudinal metrics (Tenure).

    Context:
        This is the "Roster Scrubbing" phase. Before we can analyze development, we need to confirm 
        identity. Here is the catch: MaxPreps issues new Athlete IDs every season. Ben Coultas in 2023 
        has a completely different ID number than Ben Coultas in 2024. We standardize names to ensure 
        we are tracking the same player's career arc across multiple seasons. We also calculate years 
        played on varsity.

        Statistically, this addresses the specific data quality issue of Non-Persistent Primary Keys. 
        Since the source system's `athlete_id` is volatile (changing across temporal partitions), we 
        must construct a proxy composite key based on `Name` and `Team`. This prevents "Split-Personality Bias" 
        where a single player's history is fragmented into two unrelated records. It also handles Feature 
        Engineering by deriving `Varsity_Year` as an ordinal variable representing experience.

        Technically, this acts as a Transformation View that handles "Slowly Changing Dimensions" (SCD) 
        resolution logic. We ignore the source's Surrogate Key (`athlete_id`) because it is not durable. 
        Instead, we generate a Natural Key using string manipulation: `LOWER(TRIM(Name))`. We then calculate 
        a Window Function (`ROW_NUMBER()`) partitioned by player to generate the sequential `Varsity_Year` ID.

    Args:
        df (pd.DataFrame): Raw dataframe containing at least 'Name', 'Team', and 'Season_Cleaned'.

    Returns:
        pd.DataFrame: A transformed copy of the dataframe with normalized keys and calculated tenure.
    """
    # Create a staging copy to avoid affecting the original source table (prevents SettingWithCopy)
    # Similar to creating a TEMP TABLE in SQL
    df = df.copy()
    
    # 1. Ensure Year is Integer (Type Casting)
    if 'Season_Cleaned' in df.columns:
        # CAST(Season_Cleaned AS NUMERIC)
        df['Season_Year'] = pd.to_numeric(df['Season_Cleaned'], errors='coerce')
        
        # WHERE Season_Year IS NOT NULL
        df = df.dropna(subset=['Season_Year'])
        
        # Final CAST to Integer for join logic
        df['Season_Year'] = df['Season_Year'].astype(int)
    else:
        # Validation Constraint
        raise ValueError("DataFrame missing required column: 'Season_Cleaned'")
    
    # 2. Normalize Names for Identity Tracking (Entity Resolution)
    # SQL Equivalent: LOWER(TRIM(Name))
    # Crucial Step: This replaces the unstable 'athlete_id' as our joining mechanism
    df['Match_Name'] = df['Name'].astype(str).str.strip().str.lower()
    df['Match_Team'] = df['Team'].astype(str).str.strip().str.lower()
    
    # 3. Calculate Tenure (Varsity_Year)
    # Sort is required before applying the cumulative count, effectively functioning as the ORDER BY clause in a Window Function
    df = df.sort_values(['Match_Team', 'Match_Name', 'Season_Year'])
    
    # SQL Equivalent: ROW_NUMBER() OVER (PARTITION BY Match_Team, Match_Name ORDER BY Season_Year)
    # Calculates the sequential season count for each player
    df['Varsity_Year'] = df.groupby(['Match_Team', 'Match_Name']).cumcount() + 1
    
    return df