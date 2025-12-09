import os
import glob  ### [NEW IMPORT] Needed to find files in a folder
import pandas as pd
from bs4 import BeautifulSoup
from src.metadata import extract_metadata
from src.stat_extraction import extract_player_data
from src.config import STAT_SCHEMA

def process_file(file_path):
    # (This function stays exactly the same as you wrote it!)
    file_name = os.path.basename(file_path)
    print(f"--- Processing: {file_name} ---")
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []

    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    meta = extract_metadata(soup, file_name)
    # Optional: Print less detail if processing 50 files
    print(f"   Context: {meta['Team']} ({meta['Season']})")

    players = extract_player_data(soup, meta)
    print(f"   Extracted {len(players)} players.")
    
    return players

def main():
    # --- INPUTS ---
    ### [MODIFIED] Point to the DIRECTORY, not a specific file
    data_directory = 'data/raw/rocky_mountain/'
    
    # Use glob to find ALL html files in that folder
    # os.path.join ensures it works on Mac or Windows
    search_path = os.path.join(data_directory, '*.html')
    files_to_process = glob.glob(search_path)
    
    print(f"Found {len(files_to_process)} files in {data_directory}")

    # --- EXECUTION ---
    master_data = [] # The empty bucket
    
    for file_path in files_to_process:
        # Run the ETL on one file
        file_data = process_file(file_path)
        
        # Add ("extend") this file's data to our master list
        master_data.extend(file_data)
    
    # --- OUTPUT ---
    if master_data:
        df = pd.DataFrame(master_data)
        
        # Organize Columns
        # [NOTE] Ensure 'Class_Year' matches whatever you called it in extraction.py
        fixed_cols = ['Season', 'Team', 'Level', 'Source_File', 'Name', 'Class', 'Athlete_ID']
        schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
        final_cols = fixed_cols + [c for c in schema_cols if c in df.columns]
        
        df = df[final_cols]
        
        # Save
        os.makedirs('data/processed', exist_ok=True)
        out_name = f"data/processed/final_stats.csv"
        df.to_csv(out_name, index=False)
        
        print("\nSUCCESS!")
        print(f"Total Records Processed: {len(df)}")
        print(f"Saved to {out_name}")
    else:
        print("No data found in any files!")

if __name__ == "__main__":
    main()