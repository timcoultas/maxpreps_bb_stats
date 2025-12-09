import re
import json
import os
from bs4 import BeautifulSoup

# 1. Define the file path
file_path = 'data/raw/rocky_25.html'  # Make sure this matches your file name

#1a. get the file name 
file_name = os.path.basename(file_path)

# 2. Read the raw HTML
with open(file_path, 'r', encoding='utf-8') as f:
    html_content = f.read()

# 3. Find the script tag containing the data
# We use BeautifulSoup to narrow it down to just <script> tags first
soup = BeautifulSoup(html_content, 'lxml')
scripts = soup.find_all('script')

found_data = False

print(f"--- Processing File: {file_name} ---")

for script in scripts:
    if script.string and 'var utag_data' in script.string:
        
        pattern = r'var utag_data\s*=\s*(\{.*?\});'
        match = re.search(pattern, script.string, re.DOTALL)
        
        if match:
            try:
                data = json.loads(match.group(1))
                
                # 5. Build the Metadata Dictionary (Now with Source File)
                metadata = {
                    'Season': data.get('year'),
                    'Team': data.get('schoolName'),
                    'Level': data.get('teamLevel'),
                    'Source_File': file_name  # <--- Added this
                }
                
                print("\nSUCCESS! Metadata Extracted:")
                print(f"-----------------------------")
                print(f"FILE:   {metadata['Source_File']}")
                print(f"SEASON: {metadata['Season']}")
                print(f"TEAM:   {metadata['Team']}")
                print(f"LEVEL:  {metadata['Level']}")
                print(f"-----------------------------")
                
                found_data = True
                break 
                
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")

if not found_data:
    print("Failed to locate 'utag_data' in the file.")