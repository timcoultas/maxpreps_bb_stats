import os           # Operating System: Interaction with file system/folders
import glob         # File Pattern Matching: Finds files like *.html
import argparse     # Argument Parser: Handles command line inputs (--teams, --period)
import pandas as pd # Data Manipulation: Manages the data tables/CSVs
from bs4 import BeautifulSoup               # HTML Parser: Reads the raw web pages
from src.metadata import extract_metadata   # Custom Tool: Extracts header info (Team/Year)
from src.stat_extraction import extract_player_data # Custom Tool: Extracts roster & stats
from src.config import STAT_SCHEMA          # Configuration: The list of stats to target


# ==============================================================================
#MaxPreps Baseball ETL Pipeline
#------------------------------
#This script processes HTML files exported from MaxPreps and converts them 
#into structured CSV datasets for analysis.
#
#Usage:
#    python main_etl.py --period <PERIOD> --teams <TEAMS>
#
#Arguments:
#    --period : (Required) The subfolder name to target (e.g., 'history', '2025', '2026').
#               This allows you to separate historical data from active seasons.
#               
#    --teams  : (Optional) A list of specific team folder names to process.
#               Default is 'all', which scans the 'data/raw' directory for every folder.
#
#Examples:
#    1. Process ALL teams for the 2025 season:
#       $ python main_etl.py --period 2025 --teams all
#
#    2. Process specific history for just Rocky Mountain:
#       $ python main_etl.py --period history --teams rocky_mountain
#
#    3. Process two specific teams for 2026:
#       $ python main_etl.py --period 2026 --teams rocky_mountain fossil_ridge
#
#Output:
#    - Individual team CSVs are saved to: data/processed/<team>/<period>/
#    - An aggregated "master" CSV is saved to: data/processed/<period>/aggregated_stats.csv
# ==============================================================================

# ==============================================================================
# 1. CORE FUNCTIONS
# ==============================================================================

def process_single_file(file_path):
    """
    Parses a single HTML file.
    Opens the file, extracts metadata (context) and player stats (rows),
    and returns a clean list of data dictionaries.
    """
    file_name = os.path.basename(file_path)
    
    # Safety check: Does the file exist?
    if not os.path.exists(file_path):
        return []

    # Open the file and parse with BeautifulSoup
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    # 1. Get the context (Year, Team)
    meta = extract_metadata(soup, file_name)
    
    # 2. Get the players and their stats
    players = extract_player_data(soup, meta)
    
    return players

def save_dataframe(data_list, output_folder, file_name):
    """
    Takes a raw list of dictionary data, organizes the columns based on the
    schema, and saves the result to a CSV file.
    """
    if not data_list:
        return
    
    # Convert list of dicts to DataFrame
    df = pd.DataFrame(data_list)
    
    # --- Column Organization ---
    # Define fixed columns that should always appear on the left
    fixed_cols = ['Season', 'Team', 'Level', 'Source_File', 'Name', 'Display_Name', 'Class_Year', 'Athlete_ID']
    
    # Get stat columns from Config to ensure consistency
    schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
    
    # Combine and reorder (only including columns that exist in the data)
    final_cols = fixed_cols + [c for c in schema_cols if c in df.columns]
    df = df.reindex(columns=final_cols)
    
    # Create the directory if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Save to CSV
    out_path = os.path.join(output_folder, file_name)
    df.to_csv(out_path, index=False)
    print(f"   -> Saved: {out_path} ({len(df)} records)")


# ==============================================================================
# 2. MAIN EXECUTION
# ==============================================================================

def main():
    # --- A. ARGUMENT SETUP ---
    # Allows the user to run the script with specific flags
    # Example: python main_etl.py --period 2025 --teams rocky_mountain
    
    parser = argparse.ArgumentParser(description="Run ETL for MaxPreps Baseball Stats")
    
    # Argument 1: Period (Required)
    parser.add_argument('--period', type=str, required=True, 
                        help='The subfolder to target (e.g., history, 2025, 2026)')
    
    # Argument 2: Teams (Optional, default='all')
    parser.add_argument('--teams', nargs='+', default=['all'], 
                        help='List of team folders to process. Use "all" for every folder.')
    
    args = parser.parse_args()
    target_period = args.period
    target_teams = args.teams
    
    base_raw = os.path.join('data', 'raw')
    
    
    # --- B. DETERMINE SCOPE ---
    
    # If user selected "all", scan the directory for all available folders
    if 'all' in target_teams:
        all_subdirs = [d for d in os.listdir(base_raw) if os.path.isdir(os.path.join(base_raw, d))]
        final_team_list = all_subdirs
        print(f"--- MODE: Processing ALL {len(final_team_list)} teams for period '{target_period}' ---")
    else:
        # Otherwise, use the specific list provided
        final_team_list = target_teams
        print(f"--- MODE: Processing specific teams: {final_team_list} for period '{target_period}' ---")


    # --- C. PROCESSING LOOP ---
    
    # Master list to hold data from all teams for the final aggregation
    consolidated_data = [] 

    for team in final_team_list:
        print(f"\nScanning: {team}/{target_period}...")
        
        # 1. Define input and output paths
        raw_team_dir = os.path.join(base_raw, team, target_period)
        processed_team_dir = os.path.join('data', 'processed', team, target_period)
        
        # 2. Find HTML files
        search_path = os.path.join(raw_team_dir, '*.html')
        files = glob.glob(search_path)
        
        if not files:
            print(f"   Warning: No .html files found in {raw_team_dir}")
            continue

        # 3. Process files for this team
        team_data = []
        for file_path in files:
            file_results = process_single_file(file_path)
            team_data.extend(file_results)
            
        # 4. Save Team-Level CSV
        if team_data:
            out_filename = f"{team}_{target_period}_stats.csv"
            save_dataframe(team_data, processed_team_dir, out_filename)
            
            # Add to master list
            consolidated_data.extend(team_data)


    # --- D. AGGREGATION ---
    
    if consolidated_data:
        print(f"\n--- Aggregation Complete ---")
        
        # Save the consolidated "All Teams" file in the period folder
        consolidated_dir = os.path.join('data', 'processed', target_period)
        save_dataframe(consolidated_data, consolidated_dir, "aggregated_stats.csv")
        
        print("Done. Just keep truckin'.")
    else:
        print("\nNo data found to aggregate.")

if __name__ == "__main__":
    main()