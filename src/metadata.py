# src/metadata.py
import re
import json

def extract_metadata(soup, file_name):
    """
    Scans the soup for the 'utag_data' Javascript variable 
    and returns a dictionary of Year, Team, and Level.
    """
    # Default values
    metadata = {
        'Season': 'Unknown',
        'Season_Cleaned': 'Unknown', # New Field
        'Team': 'Unknown',
        'Level': 'Unknown',
        'Source_File': file_name
    }

    scripts = soup.find_all('script')
    
    for script in scripts:
        if script.string and 'var utag_data' in script.string:
            try:
                # 1. Extract metadata fields from MaxPreps page. 
                match = re.search(r'var utag_data\s*=\s*(\{.*?\});', script.string, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))

                    raw_season = data.get('year')
                    metadata['Season'] = raw_season
                    metadata['Team'] = data.get('schoolName')
                    metadata['Level'] = data.get('teamLevel')

                    # 2. Season Cleaning Logic
                    # Format is typically "23-24". We want "2024".
                    if raw_season and '-' in raw_season:
                        # Split "23-24" -> ["23", "24"] -> take "24"
                        end_year = raw_season.split('-')[-1]
                        # Prepend "20" (Safe assumption for modern MaxPreps data)
                        metadata['Season_Cleaned'] = f"20{end_year}"
                    elif raw_season:
                         # Fallback if it's already "2024" or some other format
                        metadata['Season_Cleaned'] = raw_season


                    # If we found it, we can stop looking
                    return metadata
            except Exception as e:
                print(f"Warning: Metadata parse error in {file_name}: {e}")
                
    return metadata