import pandas as pd
import os
import sys

# --- Import Config ---
try:
    from src.utils.config import PATHS
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import PATHS

# --- Configuration Constants ---
# Standardized with game_simulator.py for consistent aggregation
TOP_N_BATTERS = 9       # Starting lineup
TOP_N_PITCHERS = 5      # Rotation (4) + Closer (1)
MIN_RC_SCORE = 0.1      # Minimum RC to be considered a viable batter
MIN_PITCHING_SCORE = 0.1  # Minimum pitching score to be considered viable


def analyze_team_power_rankings():
    """
    Analyzes projected rosters to determine team-level strength indices and generates power rankings.

    Context:
        From a Baseball perspective, this is our "Pre-Season Poll." Raw stats on individual player cards 
        don't tell the whole story; we need to know which teams have the deepest lineups and the most 
        dominant rotations. This script aggregates individual talent into a team-level composite score, 
        allowing us to identify the "Juggernauts" (high offense/high pitching) vs. the "Glass Cannons" 
        (great hitting/terrible pitching).

        Statistically, we are building a Composite Index. We sum the individual 'Runs Created' (RC) 
        and 'Pitching Scores' for the top contributors on each roster. We then normalize these raw sums 
        against the league maximum to create a relative index (0-100 scale). This is similar to how 
        OPS+ or wRC+ works, but scaled to the league leader rather than the league average.

        Aggregation Strategy (Standardized with game_simulator.py):
        - Offense: Top 9 batters by RC_Score (starting lineup)
        - Pitching: Top 5 pitchers by Pitching_Score (rotation + closer)
        
        This approach reflects actual game conditions rather than full roster depth, preventing
        teams with many mediocre players from appearing stronger than teams with fewer elite players.

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
    
    # --- 1. Offensive Power Rankings (Top 9 Batters) ---
    # Filter for players with meaningful offensive contribution
    # SQL Equivalent: SELECT * FROM Roster WHERE RC_Score > 0.1
    df_batters = df[df['RC_Score'] > MIN_RC_SCORE].copy()
    
    # Aggregate top 9 batters per team (starting lineup)
    # SQL Equivalent: 
    #   SELECT Team, SUM(RC_Score), COUNT(*), FIRST(Name), FIRST(RC_Score)
    #   FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY Team ORDER BY RC_Score DESC) as rn 
    #         FROM Batters) 
    #   WHERE rn <= 9
    #   GROUP BY Team
    offense_scores = []
    for team in df['Team'].unique():
        team_batters = df_batters[df_batters['Team'] == team].nlargest(TOP_N_BATTERS, 'RC_Score')
        
        if len(team_batters) > 0:
            offense_scores.append({
                'Team': team,
                'Projected_Runs': team_batters['RC_Score'].sum(),
                'Batters_Count': len(team_batters),
                'Top_Hitter': team_batters.iloc[0]['Name'],
                'Top_Hitter_RC': team_batters.iloc[0]['RC_Score']
            })
        else:
            # Handle teams with no qualifying batters
            offense_scores.append({
                'Team': team,
                'Projected_Runs': 0,
                'Batters_Count': 0,
                'Top_Hitter': 'N/A',
                'Top_Hitter_RC': 0
            })
    
    offense_stats = pd.DataFrame(offense_scores)
    offense_stats = offense_stats.sort_values('Projected_Runs', ascending=False)
    
    # --- 2. Pitching Power Rankings (Top 5 Pitchers) ---
    # Filter for players with meaningful pitching contribution
    df_pitchers = df[df['Pitching_Score'] > MIN_PITCHING_SCORE].copy()
    
    # Aggregate top 5 pitchers per team (rotation + closer)
    pitching_scores = []
    for team in df['Team'].unique():
        team_pitchers = df_pitchers[df_pitchers['Team'] == team].nlargest(TOP_N_PITCHERS, 'Pitching_Score')
        
        if len(team_pitchers) > 0:
            pitching_scores.append({
                'Team': team,
                'Pitching_dominance': team_pitchers['Pitching_Score'].sum(),
                'Pitchers_Count': len(team_pitchers),
                'Ace_Pitcher': team_pitchers.iloc[0]['Name'],
                'Ace_Score': team_pitchers.iloc[0]['Pitching_Score']
            })
        else:
            # Handle teams with no qualifying pitchers
            pitching_scores.append({
                'Team': team,
                'Pitching_dominance': 0,
                'Pitchers_Count': 0,
                'Ace_Pitcher': 'N/A',
                'Ace_Score': 0
            })
    
    pitching_stats = pd.DataFrame(pitching_scores)
    pitching_stats = pitching_stats.sort_values('Pitching_dominance', ascending=False)
    
    # --- 3. Combined "Power Index" ---
    # Merging the two aggregated views into a single "Fact Table" for the team.
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
    print(f"\n=== 2026 PROJECTED TEAM POWER RANKINGS ===")
    print(f"(Aggregation: Top {TOP_N_BATTERS} Batters, Top {TOP_N_PITCHERS} Pitchers)\n")
    
    header = f"{'Rank':<5} {'Team':<35} {'Total':<8} {'Off.':<8} {'Pit.':<8} {'Top Hitter':<18} {'Ace':<18}"
    print(header)
    print("-" * len(header))
    
    for idx, row in team_rankings.iterrows():
        # Truncating names to fit the ASCII table width
        team_display = str(row['Team'])[:33]
        hitter_display = str(row['Top_Hitter'])[:16]
        ace_display = str(row['Ace_Pitcher'])[:16]
        
        print(f"{idx+1:<5} {team_display:<35} {row['Total_Power_Index']:<8} {row['Offense_Index']:<8} {row['Pitching_Index']:<8} {hitter_display:<18} {ace_display:<18}")

    # --- 5. Summary Statistics ---
    print(f"\n--- League Summary ---")
    print(f"Teams Analyzed: {len(team_rankings)}")
    print(f"Avg Offense Index: {team_rankings['Offense_Index'].mean():.1f}")
    print(f"Avg Pitching Index: {team_rankings['Pitching_Index'].mean():.1f}")
    print(f"Avg Total Power: {team_rankings['Total_Power_Index'].mean():.1f}")
    
    # Identify tiers
    elite_threshold = team_rankings['Total_Power_Index'].quantile(0.75)
    weak_threshold = team_rankings['Total_Power_Index'].quantile(0.25)
    
    elite_teams = team_rankings[team_rankings['Total_Power_Index'] >= elite_threshold]
    weak_teams = team_rankings[team_rankings['Total_Power_Index'] <= weak_threshold]
    
    print(f"\nElite Tier (75th+ %ile, Power >= {elite_threshold:.1f}): {len(elite_teams)} teams")
    print(f"Rebuild Tier (25th- %ile, Power <= {weak_threshold:.1f}): {len(weak_teams)} teams")

    # --- 6. Save Output ---
    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, 'team_strength_rankings.csv')
    
    output_cols = ['Team', 'Total_Power_Index', 'Offense_Index', 'Pitching_Index', 
                   'Projected_Runs', 'Pitching_dominance', 
                   'Batters_Count', 'Pitchers_Count',
                   'Top_Hitter', 'Top_Hitter_RC', 'Ace_Pitcher', 'Ace_Score']
    
    # Writing the Materialized View to disk
    team_rankings[output_cols].to_csv(save_path, index=False)
    print(f"\nDetailed analysis saved to: {save_path}")


if __name__ == "__main__":
    analyze_team_power_rankings()