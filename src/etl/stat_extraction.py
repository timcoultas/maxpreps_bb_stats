# src/stat_extraction.py

import re
from src.utils.config import STAT_SCHEMA

def extract_player_data(soup, metadata):
    """
    Parses HTML rows to create a unique list of players and their associated statistics.

    Context:
        Baseball Context:
            This is reading the information on the MaxPreps Player Stats for the season. 
            We aren't scoring a single Tuesday afternoon game ; we are ingesting the season-long totals. 
            This is the "stat sheet" that tells us a player hit .450 with 5 HRs over 
            the entire Spring campaign.

        Statistical Validity:
            Establishes the Unit of Observation (The Player-Season). 
            1. Uniqueness: Uses `AthleteID` as the primary key to ensure one record per 
               player per season.
            2. Aggregation Level: These are pre-calculated sums (Totals) provided by the 
               MaxPreps, not event-level data. We are transcribing the reported population 
               parameters for that specific season/team cohort.
            3. Completeness: Initializes all schema fields to Null to distinguish between 
               "Zero performance" (0 hits) and "Data not tracked" (Null).

        Technical Implementation:
            This functions as a "Screen Scraper" or parsing engine. 
            1. It iterates through the DOM nodes (`tr` tags) acting as a cursor.
            2. It uses an "Upsert" pattern (Update if exists, Insert if new) based on a 
               Unique Constraint (`athleteid`).
            3. It performs an Inner Join logic in Python: matching HTML `class` attributes 
               to our `STAT_SCHEMA` configuration to map raw text to structured columns.

    Args:
        soup (BeautifulSoup): The parsed HTML object representing the season stats page.
        metadata (dict): The header info (Season, Team) to attach to every player record (Foreign Keys).

    Returns:
        list: A list of dictionaries, where each dictionary is a normalized player-season record.
    """
    roster = {}
    
    # Acts like: SELECT * FROM html_table_rows
    all_rows = soup.find_all('tr')

    for row in all_rows:
        # 1. Identify Player
        # We look for the anchor tag that contains the unique ID, acting as our Primary Key lookup
        link_tag = row.find('a', href=re.compile(r'athleteid='))
        
        if link_tag:
            href = link_tag.get('href', '')
            # Regex extraction to grab the UUID from the query string
            # Logic: REGEXP_SUBSTR(href, 'athleteid=([a-f0-9\-]+)')
            id_match = re.search(r'athleteid=([a-f0-9\-]+)', href)
            
            if id_match:
                athlete_id = id_match.group(1)
                
                # 2. Upsert Pattern (Create if new)
                # If this ID is not in our dictionary (Hash Map), initialize the record
                if athlete_id not in roster:
                    
                    ### [START NEW CODE] --------------------------------------
                    # Extraction: Pulling descriptive attributes from DOM properties
                    full_name = link_tag.get('title', link_tag.text.strip()) 
                    
                    # Look for the <abbr> tag that sits right next to the link
                    # This is finding a sibling node in the DOM tree
                    class_tag = link_tag.find_next('abbr', class_='class-year')
                    class_year = class_tag.get('title', 'Unknown') if class_tag else 'Unknown'
                    ### [END NEW CODE] ----------------------------------------

                    roster[athlete_id] = {
                        # Add Metadata Context (Denormalization: adding header info to line items)
                        **metadata,
                        
                        # Player Identity
                        ### [MODIFIED LINE] Changed 'Name' to use full_name
                        'Full_Name': full_name, 
                        
                        ### [NEW LINES] Added Display_Name and Class_Year
                        'Name': link_tag.text.strip(),
                        'Class': class_year,
                        
                        'Athlete_ID': athlete_id,
                        # Initialize Config Columns to None (Schema Enforcement)
                        # ensuring every record has the same shape
                        **{stat['abbreviation']: None for stat in STAT_SCHEMA}
                    }
                
                # 3. Extract Stats (The Loop)
                # Iterating through our Schema Definition (Column Mapping)
                for stat_def in STAT_SCHEMA:
                    target_class = stat_def['max_preps_class']
                    col_name = stat_def['abbreviation']
                    
                    # Finding the specific cell (td) that matches the mapped class name
                    # Logic: SELECT value FROM row WHERE class = target_class
                    stat_cell = row.find('td', class_=target_class)
                    if stat_cell:
                        value = stat_cell.text.strip()
                        if value:
                            # Update the record in memory
                            roster[athlete_id][col_name] = value
                            
    # Return the values of the hash map as a list of records
    return list(roster.values())