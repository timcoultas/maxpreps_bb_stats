import pandas as pd
import os
import sys

# --- Import Config ---
try:
    from src.utils.config import PATHS
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import PATHS

def analyze_team_power_rankings():
    """
    Analyzes the projected rosters to determine team-level strength.
    
    Methodology:
    1. Offense: We sum the 'RC_Score' (Runs Created) for batters. 
       Since RC is an estimate of absolute runs contributed, summing it gives 
       a theoretical "Total Team Runs" projection.
       
    2. Pitching: We sum the 'Pitching_Score' (Dominance Score) for pitchers.
       Since this metric rewards both volume (IP) and quality (K/ER), a higher
       sum indicates a deeper, more dominant staff.
    """
    
    # Path to the output of the roster prediction script
    input_path = os.path.join(PATHS['out_roster_prediction'], '2026_roster_prediction.csv')
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        print("Please run 'roster_prediction.py' first to generate the player-level data.")
        return

    print(f"Loading roster projections from {input_path}...")
    df = pd.read_csv(input_path)
    
    # --- 1. Offensive Power Rankings ---
    # Filter to Batters only and explicit sort for "Top Hitter" identification
    df_batters = df[df['Is_Batter'] == True].sort_values('RC_Score', ascending=False)
    
    # Group by Team and aggregate
    offense_stats = df_batters.groupby('Team').agg(
        Projected_Runs=('RC_Score', 'sum'),
        Batters_Count=('Name', 'count'),
        Top_Hitter=('Name', 'first'), 
        Top_Hitter_RC=('RC_Score', 'first')
    ).reset_index()
    
    offense_stats = offense_stats.sort_values('Projected_Runs', ascending=False)
    
    # --- 2. Pitching Power Rankings ---
    # Filter to Pitchers only and explicit sort for "Ace" identification
    df_pitchers = df[df['Is_Pitcher'] == True].sort_values('Pitching_Score', ascending=False)
    
    pitching_stats = df_pitchers.groupby('Team').agg(
        Pitching_dominance=('Pitching_Score', 'sum'),
        Pitchers_Count=('Name', 'count'),
        Ace_Pitcher=('Name', 'first'),
        Ace_Score=('Pitching_Score', 'first')
    ).reset_index()
    
    pitching_stats = pitching_stats.sort_values('Pitching_dominance', ascending=False)
    
    # --- 3. Combined "Power Index" ---
    # Merge the two
    team_rankings = pd.merge(offense_stats, pitching_stats, on='Team', how='outer').fillna(0)
    
    # Create normalized scores (0-100 scale) for easier comparison
    # Score = (Value / Max_Value) * 100
    max_offense = team_rankings['Projected_Runs'].max()
    max_pitching = team_rankings['Pitching_dominance'].max()
    
    # Handle edge case if max is 0
    max_offense = 1 if max_offense == 0 else max_offense
    max_pitching = 1 if max_pitching == 0 else max_pitching

    team_rankings['Offense_Index'] = (team_rankings['Projected_Runs'] / max_offense * 100).round(1)
    team_rankings['Pitching_Index'] = (team_rankings['Pitching_dominance'] / max_pitching * 100).round(1)
    
    # Total Power Index (Simple Average of the two indices)
    team_rankings['Total_Power_Index'] = ((team_rankings['Offense_Index'] + team_rankings['Pitching_Index']) / 2).round(1)
    
    team_rankings = team_rankings.sort_values('Total_Power_Index', ascending=False).reset_index(drop=True)
    
    # --- 4. Display & Save ---
    print("\n=== 2026 PROJECTED TEAM POWER RANKINGS ===\n")
    
    # Format: Rank | Team | Total | Offense | Pitching | Top Hitter | Ace
    header = f"{'Rank':<5} {'Team':<20} {'Total':<8} {'Off. Idx':<10} {'Pit. Idx':<10} {'Top Hitter':<20} {'Ace Pitcher':<20}"
    print(header)
    print("-" * len(header))
    
    for idx, row in team_rankings.iterrows():
        print(f"{idx+1:<5} {row['Team']:<20} {row['Total_Power_Index']:<8} {row['Offense_Index']:<10} {row['Pitching_Index']:<10} {str(row['Top_Hitter'])[:18]:<20} {str(row['Ace_Pitcher'])[:18]:<20}")

    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, 'team_strength_rankings.csv')
    
    # Clean up output columns
    output_cols = ['Team', 'Total_Power_Index', 'Offense_Index', 'Pitching_Index', 
                   'Projected_Runs', 'Pitching_dominance', 
                   'Top_Hitter', 'Top_Hitter_RC', 'Ace_Pitcher', 'Ace_Score']
    
    team_rankings[output_cols].to_csv(save_path, index=False)
    print(f"\nDetailed analysis saved to: {save_path}")

if __name__ == "__main__":
    analyze_team_power_rankings()