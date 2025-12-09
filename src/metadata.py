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
        'Team': 'Unknown',
        'Level': 'Unknown',
        'Source_File': file_name
    }

    scripts = soup.find_all('script')
    
    for script in scripts:
        if script.string and 'var utag_data' in script.string:
            try:
                # Regex search for the JSON block
                match = re.search(r'var utag_data\s*=\s*(\{.*?\});', script.string, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    metadata['Season'] = data.get('year')
                    metadata['Team'] = data.get('schoolName')
                    metadata['Level'] = data.get('teamLevel')
                    # If we found it, we can stop looking
                    return metadata
            except Exception as e:
                print(f"Warning: Metadata parse error in {file_name}: {e}")
                
    return metadata