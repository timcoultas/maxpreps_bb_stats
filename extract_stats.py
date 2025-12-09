import pandas as pd
from bs4 import BeautifulSoup
import re
import os

# --- CONFIGURATION: What stats do you want? ---
# Format: { 'Your_Column_Name': 'html_class_name' }
STAT_CONFIG = {
    'Batting_Avg': 'battingaverage stat dw',
    'Earned_Runs':         'earnedruns stat dw', 
    'Appearances': 'appearances stat dw'
}

# 1. Setup
file_path = 'data/raw/rocky_25.html'
with open(file_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

# 2. Initialize Roster (The Master Records)
roster = {}

# 3. SCAN EVERY ROW IN THE DOCUMENT
# We don't care which table it is in. We only care about the Athlete ID.
all_rows = soup.find_all('tr')

print(f"Scanning {len(all_rows)} rows for data points...")

for row in all_rows:
    # A. Check if this row belongs to a player
    # We look for the link with the athleteid
    link_tag = row.find('a', href=re.compile(r'athleteid='))
    
    if link_tag:
        # Extract ID
        href = link_tag.get('href', '')
        id_match = re.search(r'athleteid=([a-f0-9\-]+)', href)
        
        if id_match:
            athlete_id = id_match.group(1)
            
            # B. Create the record if it's new
            if athlete_id not in roster:
                roster[athlete_id] = {
                    'Athlete_ID': athlete_id,
                    'Name': link_tag.text.strip(),
                    # Initialize all stats to None/Empty so columns align later
                    **{key: None for key in STAT_CONFIG}
                }
            
            # C. THE MAGIC: Hunt for the specific stats in THIS row
            for col_name, css_class in STAT_CONFIG.items():
                # Try to find the cell with this specific class
                # Note: We must handle spaces in class names for BeautifulSoup
                # 'battingaverage stat dw' -> needs to be searched carefully or split
                
                # BS4 trick: passing a function to handle multiple classes
                stat_cell = row.find('td', class_=css_class)
                
                if stat_cell:
                    value = stat_cell.text.strip()
                    # Only update if we found a value (and it's not empty)
                    if value:
                        roster[athlete_id][col_name] = value

# 4. Output the results
df = pd.DataFrame(roster.values())

# Reorder columns to put Name first
cols = ['Name', 'Athlete_ID'] + [c for c in df.columns if c not in ['Name', 'Athlete_ID']]
df = df[cols]

print(df.to_string())

# Optional: Save to CSV to verify
# df.to_csv('test_output.csv', index=False)