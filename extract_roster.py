import pandas as pd
from bs4 import BeautifulSoup
import re
import os

# 1. Setup
file_path = 'data/raw/rocky_25.html'
file_name = os.path.basename(file_path)

with open(file_path, 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

# 2. Dictionary to store unique players
# Key = Athlete ID (GUID), Value = Dictionary of attributes
roster = {}

print(f"--- Extracting Roster from {file_name} ---")

# 3. Find all 'th' cells with class 'name' (This is where the player info lives)
player_cells = soup.find_all('th', class_='name')

for cell in player_cells:
    # A. Find the link <a> tag
    link_tag = cell.find('a')
    if not link_tag:
        continue

    # B. Extract the Link (href) to find the ID
    href = link_tag.get('href', '')
    
    # Use Regex to capture the GUID after 'athleteid='
    # Matches: 8-4-4-4-12 hex characters
    id_match = re.search(r'athleteid=([a-f0-9\-]+)', href)
    
    if id_match:
        athlete_id = id_match.group(1)
        
        # C. If we haven't seen this player yet, initialize them
        if athlete_id not in roster:
            full_name = link_tag.get('title', 'Unknown') # e.g. "Benjamin Coultas"
            display_name = link_tag.text.strip()         # e.g. "B. Coultas"
            
            # D. Find the Class Year <abbr> tag (it's usually next to the link)
            class_tag = cell.find('abbr', class_='class-year')
            class_year = class_tag.get('title') if class_tag else 'Unknown'
            
            # E. Store in our Master Dictionary
            roster[athlete_id] = {
                'Athlete_ID': athlete_id,
                'Full_Name': full_name,
                'Display_Name': display_name,
                'Class_Year': class_year
            }

# 4. Convert to DataFrame for easy viewing
df_roster = pd.DataFrame(roster.values())

print(f"Found {len(df_roster)} unique athletes.")
print("-" * 30)
print(df_roster.to_string())