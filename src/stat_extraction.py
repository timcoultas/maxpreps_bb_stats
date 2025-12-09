# src/stat_extraction.py
import re
from src.config import STAT_SCHEMA

def extract_player_data(soup, metadata):
    """
    Scans every row in the HTML. 
    1. Identifies players via AthleteID.
    2. Upserts them into a roster.
    3. Extracts stats based on the STAT_SCHEMA.
    
    Returns a list of dictionaries (one per player).
    """
    roster = {}
    all_rows = soup.find_all('tr')

    for row in all_rows:
        # 1. Identify Player
        link_tag = row.find('a', href=re.compile(r'athleteid='))
        
        if link_tag:
            href = link_tag.get('href', '')
            id_match = re.search(r'athleteid=([a-f0-9\-]+)', href)
            
            if id_match:
                athlete_id = id_match.group(1)
                
                # 2. Upsert (Create if new)
                if athlete_id not in roster:
                    roster[athlete_id] = {
                        # Add Metadata Context
                        **metadata,
                        # Player Identity
                        'Name': link_tag.text.strip(),
                        'Athlete_ID': athlete_id,
                        # Initialize Config Columns to None
                        **{stat['abbreviation']: None for stat in STAT_SCHEMA}
                    }
                
                # 3. Extract Stats (The Loop)
                for stat_def in STAT_SCHEMA:
                    target_class = stat_def['max_preps_class']
                    col_name = stat_def['abbreviation']
                    
                    stat_cell = row.find('td', class_=target_class)
                    if stat_cell:
                        value = stat_cell.text.strip()
                        if value:
                            roster[athlete_id][col_name] = value
                            
    return list(roster.values())