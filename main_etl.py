import os           # Operating System: Interaction with file system/folders
import glob         # File Pattern Matching: Finds files like *.html
import argparse     # Argument Parser: Handles command line inputs (--teams, --period)
import pandas as pd # Data Manipulation: Manages the data tables/CSVs
from bs4 import BeautifulSoup               # HTML Parser: Reads the raw web pages
from src.etl.metadata import extract_metadata   # Custom Tool: Extracts header info (Team/Year)
from src.etl.stat_extraction import extract_player_data # Custom Tool: Extracts roster & stats
from src.utils.config import STAT_SCHEMA          # Configuration: The list of stats to target
from src.etl.class_inference import infer_missing_classes # <--- function to clean up player class data where missing

# ==============================================================================
# MaxPreps Baseball ETL Pipeline
# ------------------------------
# Context:
#   Baseball Context:
#       This is the General Manager of our operation. It sets the scouting schedule,
#       tells the scouts (parsers) which stadiums (folders) to visit, and ensures
#       every report filed ends up in the correct filing cabinet. Without this
#       orchestrator, we just have a pile of loose papers on a desk.
#
#   Statistical Validity:
#       Ensures the integrity of the sample population. By enforcing strict
#       directory traversal and consistent schema application, this script guarantees
#       that the resulting dataset is a complete census of the targeted period,
#       minimizing selection bias caused by missing files or dropped teams.
#
#   Technical Implementation:
#       This is the main Execution Engine/Orchestrator. It functions similarly to
#       an Airflow DAG or a Master Stored Procedure. It handles Parameterization
#       (via CLI args), Partition Discovery (traversing file paths), and the
#       execution of the Extract-Transform-Load (ETL) cycle for each target.
#
# Usage:
#    python main_etl.py --period <PERIOD> --teams <TEAMS>
#
# Arguments:
#    --period : (Required) The subfolder name to target (e.g., 'history', '2025', '2026').
#               This allows you to separate historical data from active seasons.
#               
#    --teams  : (Optional) A list of specific team folder names to process.
#               Default is 'all', which scans the 'data/raw' directory for every folder.
# ==============================================================================

# ==============================================================================
# 1. CORE FUNCTIONS
# ==============================================================================

def process_single_file(file_path):
    """
    Parses a single HTML file into a structured list of player records.

    Context:
        Baseball Context:
            This is the equivalent of a scout sitting down with a single game's
            scorecard. They read the header to see who played (Metadata) and then
            go line-by-line through the box score to record every hit and strikeout
            (Player Data) for that specific contest.

        Statistical Validity:
            Represents the Unit of Observation extraction. This step converts semi-structured
            web data into structured observations (rows). It ensures that every player
            on the page is captured, preserving the N-count for later analysis.

        Technical Implementation:
            The "Extract" phase for a single document. We open a file stream, parse the
            DOM (Document Object Model) using BeautifulSoup—acting as a NoSQL document
            reader—and flatten the hierarchical HTML structure into a list of dictionaries
            (Key-Value pairs) ready for tabular ingestion.

    Args:
        file_path (str): Full path to the raw HTML file.

    Returns:
        list: A list of dictionaries, where each dictionary is one player's stat line.
    """
    file_name = os.path.basename(file_path)
    
    # Safety check: Does the file exist?
    if not os.path.exists(file_path):
        return []

    # Open the file and parse with BeautifulSoup
    # Think of this as opening a cursor to a raw text file
    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    # 1. Get the context (Year, Team)
    # Extracting "Header" level data to append to every row (Denormalization)
    meta = extract_metadata(soup, file_name)
    
    # 2. Get the players and their stats
    # Extracting "Line Item" level data
    players = extract_player_data(soup, meta)
    
    return players

def save_dataframe(data_list, output_folder, file_name):
    """
    Validates, structures, and writes the data to a CSV file.

    Context:
        Baseball Context:
            This is the filing system. Once the scouts hand in their notes, we don't
            just toss them in a drawer. We type them up into the official league
            format, make sure no crucial info (like graduation year) is missing,
            and file them into the team's permanent folder.

        Statistical Validity:
            Enforces Schema Consistency. Before saving, this function ensures that
            every column defined in our experimental design (STAT_SCHEMA) is present,
            even if empty. This prevents "jagged arrays" where different teams have
            different columns, which would break downstream aggregate analysis.

        Technical Implementation:
            The "Load" phase. It converts our staging list (List of Dicts) into an
            in-memory columnar store (Pandas DataFrame). It performs final Schema
            Validation (reindex) to ensure column order matches the DDL (Data Definition
            Language) defined in Config, and then writes to disk (CSV).

    Args:
        data_list (list): Raw list of dictionaries from the extraction phase.
        output_folder (str): Target directory path.
        file_name (str): Target filename.
    """
    if not data_list:
        return
    
    # Convert list of dicts to DataFrame (NoSQL -> Relational Table conversion)
    df = pd.DataFrame(data_list)
    
    # Before saving, try to fill in missing class years
    # Data Imputation: Handling NULL values in critical grouping columns using logic
    print("   -> Running Class Inference...")
    df = infer_missing_classes(df)


    # --- Column Organization ---
    # Define fixed columns that should always appear on the left (Primary Keys & Metadata)
    # UPDATED: Added 'Class_Cleaned' to this list
    fixed_cols = ['Season', 'Season_Cleaned',  'Team', 'Level', 'Source_File', 'Name', 'Class', 'Class_Cleaned', 'Athlete_ID']
    
    # Get stat columns from Config to ensure consistency (Schema Enforcement)
    schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
    
    # Combine and reorder (only including columns that exist in the data)
    # Equivalent to: SELECT fixed_cols, schema_cols FROM table
    final_cols = fixed_cols + [c for c in schema_cols if c in df.columns]
    df = df.reindex(columns=final_cols)
    
    # Create the directory if it doesn't exist (ensure partition path exists)
    os.makedirs(output_folder, exist_ok=True)
    
    # Save to CSV
    out_path = os.path.join(output_folder, file_name)
    df.to_csv(out_path, index=False)
    print(f"   -> Saved: {out_path} ({len(df)} records)")


# ==============================================================================
# 2. MAIN EXECUTION
# ==============================================================================

def main():
    """
    Main execution loop.
    1. Parses arguments to determine scope.
    2. Iterates through team folders (Partitions).
    3. Processes files (Extract/Transform).
    4. Aggregates results into a master file (Union All).
    """
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
    # Dynamic Partition Discovery: listing subdirectories to build the job queue
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
    # Acts as a temporary staging table in memory for a UNION ALL operation
    consolidated_data = [] 

    for team in final_team_list:
        print(f"\nScanning: {team}/{target_period}...")
        
        # 1. Define input and output paths
        raw_team_dir = os.path.join(base_raw, team, target_period)
        processed_team_dir = os.path.join('data', 'processed', team, target_period)
        
        # 2. Find HTML files
        # Glob acts like a wildcard file search: ls *.html
        search_path = os.path.join(raw_team_dir, '*.html')
        files = glob.glob(search_path)
        
        if not files:
            print(f"   Warning: No .html files found in {raw_team_dir}")
            continue

        # 3. Process files for this team
        team_data = []
        for file_path in files:
            # Execute the Extract function for each file
            file_results = process_single_file(file_path)
            # Append results to the team-level list (List.extend is cheaper than DataFrame.append)
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
        # This creates the "Master Table" for the given period
        consolidated_dir = os.path.join('data', 'processed', target_period)
        save_dataframe(consolidated_data, consolidated_dir, "aggregated_stats.csv")
        
        print("Done. Keep on truckin'.")
    else:
        print("\nNo data found to aggregate.")

if __name__ == "__main__":
    main()