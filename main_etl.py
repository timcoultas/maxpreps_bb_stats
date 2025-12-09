import os
import glob
import pandas as pd
from bs4 import BeautifulSoup
from src.metadata import extract_metadata
from src.stat_extraction import extract_player_data
from src.config import STAT_SCHEMA

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Change this folder name to target a different team's data
# Example: 'rocky_mountain' or 'fossil_ridge'
TEAM_FOLDER = 'rocky_mountain'

def process_file(file_path):
    file_name = os.path.basename(file_path)
    # print(f"--- Processing: {file_name} ---") # Optional: reduce noise
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    meta = extract_metadata(soup, file_name)
    print(f"   Context: {meta['Team']} ({meta['Season']})")

    players = extract_player_data(soup, meta)
    # print(f"   Extracted {len(players)} players.") # Optional: reduce noise
    
    return players

def main():
    # --- 1. SETUP PATHS ---
    # Construct the full paths based on the TEAM_FOLDER variable
    raw_dir = os.path.join('data', 'raw', TEAM_FOLDER)
    processed_dir = os.path.join('data', 'processed', TEAM_FOLDER)
    
    print(f"Targeting Raw Directory: {raw_dir}")

    # Use glob to find ALL html files in that specific team folder
    search_path = os.path.join(raw_dir, '*.html')
    files_to_process = glob.glob(search_path)
    
    if not files_to_process:
        print(f"CRITICAL: No .html files found in {raw_dir}")
        return

    print(f"Found {len(files_to_process)} files to process.")

    # --- 2. EXECUTION ---
    master_data = []
    
    for file_path in files_to_process:
        file_data = process_file(file_path)
        master_data.extend(file_data)
    
    # --- 3. OUTPUT ---
    if master_data:
        df = pd.DataFrame(master_data)
        
        # Organize Columns
        fixed_cols = ['Season', 'Team', 'Level', 'Source_File', 'Name', 'Class', 'Athlete_ID']
        schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
        final_cols = fixed_cols + [c for c in schema_cols if c in df.columns]
        
        df = df[final_cols]
        
        # Dynamic Output Directory
        # This creates 'data/processed/rocky_mountain' if it doesn't exist
        os.makedirs(processed_dir, exist_ok=True)
        
        # Save the file inside that specific folder
        out_name = os.path.join(processed_dir, 'final_stats.csv')
        
        df.to_csv(out_name, index=False)
        
        print("\nSUCCESS!")
        print(f"Total Records: {len(df)}")
        print(f"Saved to: {out_name}")
    else:
        print("No data extracted.")

if __name__ == "__main__":
    main()