import os
import glob
import argparse
import pandas as pd
from bs4 import BeautifulSoup
import sys
import warnings

# Suppress FutureWarning from pandas groupby operations
warnings.simplefilter(action='ignore', category=FutureWarning)

# --- ETL IMPORTS ---
from src.etl.metadata import extract_metadata
from src.etl.stat_extraction import extract_player_data
from src.etl.class_inference import infer_missing_classes
# [NEW] Import the fix script
from src.etl.class_cleansing import fix_class_progression 
from src.utils.config import STAT_SCHEMA
from src.utils.config import PATHS

# --- ANALYTICS IMPORTS ---
# We import the "Main" functions from our other scripts to chain them
try:
    from src.workflows.development_multipliers import generate_stat_multipliers
    from src.workflows.profile_generator import create_generic_profiles
    from src.workflows.roster_prediction import predict_2026_roster
    from src.workflows.team_strength_analysis import analyze_team_power_rankings
    from src.workflows.game_simulator import simulate_games
except ImportError as e:
    print(f"Warning: Could not import analytics modules. Pipeline will run ETL only.\nError: {e}")

# ==============================================================================
# 1. CORE ETL FUNCTIONS (Unchanged)
# ==============================================================================

def process_single_file(file_path):
    """Parses a single HTML file into a structured list of player records."""
    file_name = os.path.basename(file_path)
    if not os.path.exists(file_path): return []

    with open(file_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'lxml')

    meta = extract_metadata(soup, file_name)
    players = extract_player_data(soup, meta)
    return players

def save_dataframe(data_list, output_folder, file_name):
    """Validates and writes data to CSV."""
    if not data_list: return
    
    df = pd.DataFrame(data_list)
    print("   -> Running Class Inference...")
    df = infer_missing_classes(df)
    
    # [NEW] Run the Progression Fixer
    # This catches players listed as Sophomores two years in a row
    df = fix_class_progression(df)

    fixed_cols = ['Season', 'Season_Cleaned', 'Team', 'Level', 'Source_File', 'Name', 'Class', 'Class_Cleaned', 'Athlete_ID']
    schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
    
    final_cols = fixed_cols + [c for c in schema_cols if c in df.columns]
    df = df.reindex(columns=final_cols)
    
    os.makedirs(output_folder, exist_ok=True)
    out_path = os.path.join(output_folder, file_name)
    df.to_csv(out_path, index=False)
    print(f"   -> Saved: {out_path} ({len(df)} records)")

# ==============================================================================
# 2. MAIN PIPELINE
# ==============================================================================

def run_analytics_chain():
    """
    Executes the downstream modeling and prediction tasks in specific order.
    
    Context:
        Baseball Context:
            This is the Manager calling the game. Once the data is prepped (Batting Practice is over), 
            we need to execute the strategy in a specific sequence:
            1. Learn from History (Calculate Multipliers)
            2. Prepare the Reserves (Generate Generic Profiles)
            3. Set the Lineup (Predict Rosters)
            4. Check the Standings (Power Rankings)
        
        Technical Implementation:
            This is a DAG (Directed Acyclic Graph) executed sequentially.
            Step 1 -> Step 2 -> Step 3 -> Step 4.
            Failure in an upstream step (e.g., Multipliers fail to generate) will cascade 
            to downstream steps, so we execute them in dependency order.
    """
    print("\n" + "="*50)
    print("STARTING ANALYTICS CHAIN")
    print("="*50)

    # Step 1: Calculate Development Multipliers (The "Learning" Phase)
    print("\n--- Step 1: Updating Development Models ---")
    generate_stat_multipliers()

    # Step 2: Generate Generic Profiles (The "Replacement Level" Phase)
    print("\n--- Step 2: Generating Replacement Profiles ---")
    create_generic_profiles()

    # Step 3: Predict Rosters (The "Projection" Phase)
    print("\n--- Step 3: Predicting 2026 Rosters ---")
    predict_2026_roster()

    # Step 4: Analyze Strength (The "Reporting" Phase)
    print("\n--- Step 4: Analyzing Team Strength ---")
    analyze_team_power_rankings()

    #step 5: Run Game Simulator
    print("\n--- Step 5: Game Simulator ---")
    simulate_games()

def main():
    parser = argparse.ArgumentParser(description="Run Full Baseball Analytics Pipeline")
    parser.add_argument('--period', type=str, required=True, help='Target subfolder (e.g., history, 2025)')
    parser.add_argument('--teams', nargs='+', default=['all'], help='Specific teams to process')
    parser.add_argument('--skip-analysis', action='store_true', help='If set, stops after ETL and does not run projections')
    parser.add_argument('--run-analysis-only', action='store_true', help='If set, skips ETL and runs only the analytics chain')
    
    args = parser.parse_args()
    
    # Check for analysis-only mode first
    if args.run_analysis_only:
        print(f"\n--- SKIPPING ETL: Running Analytics Chain Only ({args.period}) ---")
        run_analytics_chain()
        return

    # --- PHASE 1: ETL (Extract Transform Load) ---
    print(f"\n--- PHASE 1: ETL EXECUTION ({args.period}) ---")
    
    base_raw = PATHS['raw']
    
    if 'all' in args.teams:
        # [FIX] Filter out hidden folders or templates (starting with _)
        final_team_list = [d for d in os.listdir(base_raw) 
                           if os.path.isdir(os.path.join(base_raw, d)) 
                           and not d.startswith('_') and not d.startswith('.')]
    else:
        final_team_list = args.teams

    consolidated_data = [] 

    for team in final_team_list:
        print(f"\nScanning: {team}/{args.period}...")
        raw_team_dir = os.path.join(base_raw, team, args.period)
        processed_team_dir = os.path.join(PATHS['processed'], team, args.period)
        
        search_path = os.path.join(raw_team_dir, '*.html')
        files = glob.glob(search_path)
        
        if not files:
            print(f"   Warning: No .html files found in {raw_team_dir}")
            continue

        team_data = []
        for file_path in files:
            file_results = process_single_file(file_path)
            team_data.extend(file_results)
            
        if team_data:
            save_dataframe(team_data, processed_team_dir, f"{team}_{args.period}_stats.csv")
            consolidated_data.extend(team_data)

    if consolidated_data:
        print(f"\n--- Aggregation Complete ---")
        # [FIX] Convert list of dicts to DataFrame for processing
        df_consolidated = pd.DataFrame(consolidated_data)
        
        print("   -> Running Class Inference on Consolidated Data...")
        df_consolidated = infer_missing_classes(df_consolidated)
        
        # [NEW] Run the Progression Fixer on the full dataset
        # This is the most important call, as it catches cross-year issues
        df_consolidated = fix_class_progression(df_consolidated)

        # Ensure correct column order
        fixed_cols = ['Season', 'Season_Cleaned', 'Team', 'Level', 'Source_File', 'Name', 'Class', 'Class_Cleaned', 'Athlete_ID']
        schema_cols = [stat['abbreviation'] for stat in STAT_SCHEMA]
        final_cols = fixed_cols + [c for c in schema_cols if c in df_consolidated.columns]
        df_consolidated = df_consolidated.reindex(columns=final_cols)

        # Removed sorting logic that caused volatility issues
        # if all(col in df_consolidated.columns for col in ['Team', 'Name', 'Season_Cleaned']):
        #      df_consolidated = df_consolidated.sort_values(by=['Team', 'Name', 'Season_Cleaned'])

        consolidated_dir = os.path.join(PATHS['processed'], args.period)
        save_dataframe(df_consolidated.to_dict('records'), consolidated_dir, "aggregated_stats.csv")
        
        # --- PHASE 2: ANALYTICS CHAIN ---
        # Only run if we actually processed data and user didn't skip it
        if not args.skip_analysis:
            run_analytics_chain()
        else:
            print("\nSkipping analytics chain (--skip-analysis was set).")
            
    else:
        print("\nNo data found to aggregate.")

if __name__ == "__main__":
    main()