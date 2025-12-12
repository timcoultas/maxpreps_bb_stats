# src/metadata.py
import re
import json

def extract_metadata(soup, file_name):
    """
    Scans the soup for the 'utag_data' Javascript variable and returns a dictionary 
    of Year, Team, and Level.

    Context:
        Baseball Context:
            This is the equivalent of the pre-game plate meeting where lineup cards are exchanged.
            Before we can track a single pitch or calculate a single stat, we must validate 
            the game's header details. This function identifies exactly which squad we are 
            scouting (Team), the quality of competition (Level), and the campaign year (Season) 
            to ensure the stats are filed into the correct history books.

        Statistical Validity:
            Establishes the independent categorical variables required for correct data stratification. 
            Accurate extraction here is critical to prevent "contamination" of sample groups—ensuring 
            Varsity stats are not commingled with JV data, and 2024 records are isolated from 2023. 
            This serves as the primary primary key generation step for the dataset.

        Technical Implementation:
            Think of this as an ETL extraction process running against a semi-structured document store. 
            The HTML page is our "raw" table. We are performing a specific lookup (scanning for a script tag) 
            to find an embedded JSON blob, similar to parsing a JSON column in Snowflake or BigQuery. 
            Once extracted, we perform data cleansing on the 'Season' field to normalize the schema 
            before loading it into our staging dictionary.

    Args:
        soup (BeautifulSoup): The parsed HTML object acting as our source document/database.
        file_name (str): The name of the source file, used for lineage tracking.

    Returns:
        dict: A dictionary containing normalized metadata fields:
            - 'Season': Raw season string.
            - 'Season_Cleaned': Normalized year (YYYY).
            - 'Team': School or Team name.
            - 'Level': Competition level (e.g., Varsity).
            - 'Source_File': Data lineage reference.
    """
    # Default values
    # This acts as our schema definition, ensuring columns exist even if null (handling NULLs gracefully)
    metadata = {
        'Season': 'Unknown',
        'Season_Cleaned': 'Unknown', # New Field
        'Team': 'Unknown',
        'Level': 'Unknown',
        'Source_File': file_name
    }

    # Similar to: SELECT * FROM html_nodes WHERE tag = 'script'
    scripts = soup.find_all('script')
    
    # iterating through the cursor of results
    for script in scripts:
        # A WHERE clause checking if the script node contains our target variable 'var utag_data'
        if script.string and 'var utag_data' in script.string:
            try:
                # 1. Extract metadata fields from MaxPreps page. 
                # Using Regex here acts like a SQL REGEXP_SUBSTR to pull the specific JSON structure out of the text block
                match = re.search(r'var utag_data\s*=\s*(\{.*?\});', script.string, re.DOTALL)
                if match:
                    # Parse the extracted string into a Python dictionary (equivalent to parsing a JSON blob into a struct)
                    data = json.loads(match.group(1))

                    # Extracting values by key, similar to accessing fields in a JSON variant column (e.g., data:year)
                    raw_season = data.get('year')
                    metadata['Season'] = raw_season
                    metadata['Team'] = data.get('schoolName')
                    metadata['Level'] = data.get('teamLevel')

                    # 2. Season Cleaning Logic
                    # This block is our transformation layer (T in ETL). We are normalizing the date format.
                    # Format is typically "23-24". We want "2024".
                    if raw_season and '-' in raw_season:
                        # Split "23-24" -> ["23", "24"] -> take "24"
                        # Logic: SPLIT_PART(season, '-', 2)
                        end_year = raw_season.split('-')[-1]
                        # Prepend "20" (Safe assumption for modern MaxPreps data)
                        # Logic: CONCAT('20', end_year)
                        metadata['Season_Cleaned'] = f"20{end_year}"
                    elif raw_season:
                         # Fallback if it's already "2024" or some other format
                         # Logic: COALESCE(formatted_date, raw_date)
                        metadata['Season_Cleaned'] = raw_season


                    # If we found it, we can stop looking (like a LIMIT 1 or breaking a cursor loop)
                    return metadata
            except Exception as e:
                # Error logging for data quality monitoring
                print(f"Warning: Metadata parse error in {file_name}: {e}")
                
    return metadata