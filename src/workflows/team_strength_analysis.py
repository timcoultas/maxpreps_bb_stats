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
    Analyzes projected rosters to determine team-level strength indices and generates power rankings.

    Context:
        From a Baseball perspective, this is our "Pre-Season Poll." Raw stats on individual player cards 
        don't tell the whole story; we need to know which teams have the deepest lineups and the most 
        dominant rotations. This script aggregates individual talent into a team-level composite score, 
        allowing us to identify the "Juggerants" (high offense/high pitching) vs. the "Glass Cannons" 
        (great hitting/terrible pitching).

        Statistically, we are building a Composite Index. We sum the individual 'Runs Created' (RC) 
        and 'Pitching Scores' for every viable player on a roster. We then normalize these raw sums 
        against the league maximum to create a relative index (0-100 scale). This is similar to how 
        OPS+ or wRC+ works, but scaled to the league leader rather than the league average.

        Technically, this is a classic "Roll-Up" aggregation pipeline. We take the granular transaction 
        data (individual players), apply filters (WHERE clauses) to remove noise, perform aggregations 
        (SUM/COUNT/FIRST), and finally join the disparate datasets (Offense/Defense) into a unified 
        Reporting View.

    Returns:
        None. Generates a CSV report and prints a leaderboard to stdout.
    """
    
    input_path = os.path.join(PATHS['out_roster_prediction'], '2026_roster_prediction.csv')
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        print("Please run 'roster_prediction.py' first to generate the player-level data.")
        return

    print(f"Loading roster projections from {input_path}...")
    df = pd.read_csv(input_path)
    
    # --- 1. Offensive Power Rankings ---
    # REVIEW UPDATE: The "Utility Void" fix.
    # Instead of filtering `df[df['Is_Batter'] == True]`, we filter for anyone with positive RC.
    # SQL Equivalent: SELECT * FROM Roster WHERE RC_Score > 0.1 ORDER BY RC_Score DESC
    df_batters = df[df['RC_Score'] > 0.1].sort_values('RC_Score', ascending=False)
    
    # Aggregating player stats up to the Team level.
    # SQL Equivalent: 
    #   SELECT Team, SUM(RC_Score), COUNT(Name), FIRST(Name) 
    #   FROM Batters GROUP BY Team
    offense_stats = df_batters.groupby('Team').agg(
        Projected_Runs=('RC_Score', 'sum'),
        Batters_Count=('Name', 'count'),
        Top_Hitter=('Name', 'first'), 
        Top_Hitter_RC=('RC_Score', 'first')
    ).reset_index()
    
    offense_stats = offense_stats.sort_values('Projected_Runs', ascending=False)
    
    # --- 2. Pitching Power Rankings ---
    # REVIEW UPDATE: Same fix for pitchers. Capture anyone with positive pitching value.
    # Ensures we catch Two-Way players who might be listed primarily as batters.
    df_pitchers = df[df['Pitching_Score'] > 0.1].sort_values('Pitching_Score', ascending=False)
    
    # SQL Equivalent: GROUP BY Team (Pitching Side)
    pitching_stats = df_pitchers.groupby('Team').agg(
        Pitching_dominance=('Pitching_Score', 'sum'),
        Pitchers_Count=('Name', 'count'),
        Ace_Pitcher=('Name', 'first'),
        Ace_Score=('Pitching_Score', 'first')
    ).reset_index()
    
    pitching_stats = pitching_stats.sort_values('Pitching_dominance', ascending=False)
    
    # --- 3. Combined "Power Index" ---
    # merging the two aggregated views into a single "Fact Table" for the team.
    # SQL Equivalent: 
    #   SELECT * FROM Offense_Stats 
    #   FULL OUTER JOIN Pitching_Stats ON Offense_Stats.Team = Pitching_Stats.Team
    team_rankings = pd.merge(offense_stats, pitching_stats, on='Team', how='outer').fillna(0)
    
    # Normalization: Finding the "League Leader" to set the curve.
    # This establishes the denominator for our index calculation.
    max_offense = team_rankings['Projected_Runs'].max()
    max_pitching = team_rankings['Pitching_dominance'].max()
    
    # Safety check to avoid DivideByZero errors
    max_offense = 1 if max_offense == 0 else max_offense
    max_pitching = 1 if max_pitching == 0 else max_pitching

    # Calculating the Index (0-100 Scale).
    # Statistically: (Team_Score / Max_Score) * 100.
    # 100 = Best in League. 50 = Half as good as the best team.
    team_rankings['Offense_Index'] = (team_rankings['Projected_Runs'] / max_offense * 100).round(1)
    team_rankings['Pitching_Index'] = (team_rankings['Pitching_dominance'] / max_pitching * 100).round(1)
    
    # The Composite Score: Simple average of the two phases of the game.
    team_rankings['Total_Power_Index'] = ((team_rankings['Offense_Index'] + team_rankings['Pitching_Index']) / 2).round(1)
    
    # Final Sorting for display
    # SQL Equivalent: ORDER BY Total_Power_Index DESC
    team_rankings = team_rankings.sort_values('Total_Power_Index', ascending=False).reset_index(drop=True)
    
    # --- 4. Display & Save ---
    print("\n=== 2026 PROJECTED TEAM POWER RANKINGS (Revised Aggregation) ===\n")
    
    header = f"{'Rank':<5} {'Team':<20} {'Total':<8} {'Off. Idx':<10} {'Pit. Idx':<10} {'Top Hitter':<20} {'Ace Pitcher':<20}"
    print(header)
    print("-" * len(header))
    
    for idx, row in team_rankings.iterrows():
        # Truncating names to fit the ASCII table width
        print(f"{idx+1:<5} {row['Team']:<20} {row['Total_Power_Index']:<8} {row['Offense_Index']:<10} {row['Pitching_Index']:<10} {str(row['Top_Hitter'])[:18]:<20} {str(row['Ace_Pitcher'])[:18]:<20}")

    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, 'team_strength_rankings.csv')
    
    output_cols = ['Team', 'Total_Power_Index', 'Offense_Index', 'Pitching_Index', 
                   'Projected_Runs', 'Pitching_dominance', 
                   'Top_Hitter', 'Top_Hitter_RC', 'Ace_Pitcher', 'Ace_Score']
    
    # Writing the Materialized View to disk
    team_rankings[output_cols].to_csv(save_path, index=False)
    print(f"\nDetailed analysis saved to: {save_path}")

if __name__ == "__main__":
    analyze_team_power_rankings()