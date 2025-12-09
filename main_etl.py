import os
import pandas as pd
from bs4 import BeautifulSoup
from src.metadata import extract_metadata
from src.stat_extraction import extract_player_data
from src.config import STAT_SCHEMA

def process_file(file_path):
    file_name = os.path.basename(file_path)
    print(f"--- Processing: {file_name} ---")
    
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []

    # 1. Load Soup (The Raw Material)
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    # 2. Get Context (The Header)
    meta = extract_metadata(soup, file_name)
    print(f"   Context: {meta['Team']} ({meta['Season']})")

    # 3. Get Data (The Content)
    players = extract_player_data(soup, meta)
    print(f"   Extracted {len(players)} players.")
    
    return players

def main():
    # --- INPUTS ---
    # Later, we can change this to look at a whole folder
    target_file = 'data/raw/rocky_25.html'
    
    # --- EXECUTION ---
    all_data = process_file(target_file)
    
    # --- OUTPUT ---
    if all_data:
        df = pd.DataFrame(all_data)
        
        # Organize Columns
        fixed_cols = ['Season', 'Team', 'Level', 'Source_File', 'Name', 'Class_Year', 'Athlete_ID']
        schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
        final_cols = fixed_cols + [c for c in schema_cols if c in df.columns]
        
        df = df[final_cols]
        
        # Save
        os.makedirs('data/processed', exist_ok=True)
        out_name = f"data/processed/final_stats.csv"
        df.to_csv(out_name, index=False)
        
        print("\nSUCCESS!")
        print(df.to_csv())
        print(f"Saved to {out_name}")

if __name__ == "__main__":
    main()