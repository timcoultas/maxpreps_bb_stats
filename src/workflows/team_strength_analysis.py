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
TOP_N_BATTERS = 10      # Starting lineup + designated hitter
TOP_N_PITCHERS = 6      # Two starters, one starter/middle, two middle, one closer
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
        - Offense: Top 10 batters by RC_Score (starting lineup + DH)
        - Pitching: Top 6 pitchers by Pitching_Score (rotation + closer)
        
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
    
    # --- 0. Roster Composition Metrics ---
    # These metrics tell you about team maturity and experience depth
    # A team with 15 returning players and 40 collective varsity years is battle-tested
    # A team with 8 returning players and 12 varsity years is rebuilding
    
    # Identify "real" returning players vs generic backfill
    # SQL: WHERE Projection_Method NOT LIKE '%Generic%' AND Projection_Method NOT LIKE '%Backfill%'
    df['Is_Returning'] = ~df['Projection_Method'].str.contains('Generic|Backfill', case=False, na=False)
    
    # Calculate roster composition per team
    roster_comp = []
    for team in df['Team'].unique():
        team_df = df[df['Team'] == team]
        returning = team_df[team_df['Is_Returning']]
        
        roster_comp.append({
            'Team': team,
            'Total_Roster': len(team_df),
            'Returning_Players': len(returning),
            'Returning_Seniors': len(returning[returning['Class_Cleaned'] == 'Senior']),
            'Returning_Juniors': len(returning[returning['Class_Cleaned'] == 'Junior']),
            'Returning_Sophs': len(returning[returning['Class_Cleaned'] == 'Sophomore']),
            'Total_Varsity_Years': int(returning['Varsity_Year'].sum()),
            'Avg_Varsity_Years': round(returning['Varsity_Year'].mean(), 2) if len(returning) > 0 else 0
        })
    
    df_roster_comp = pd.DataFrame(roster_comp)
    
    # --- 1. Offensive Power Rankings (Top 10 Batters) ---
    # Filter for players with meaningful offensive contribution
    df_batters = df[df['RC_Score'] > MIN_RC_SCORE].copy()
    
    # Aggregate top 10 batters per team (starting lineup + DH)
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
            offense_scores.append({
                'Team': team,
                'Projected_Runs': 0,
                'Batters_Count': 0,
                'Top_Hitter': 'N/A',
                'Top_Hitter_RC': 0
            })
    
    offense_stats = pd.DataFrame(offense_scores)
    offense_stats = offense_stats.sort_values('Projected_Runs', ascending=False)
    
    # --- 2. Pitching Power Rankings (Top 6 Pitchers) ---
    df_pitchers = df[df['Pitching_Score'] > MIN_PITCHING_SCORE].copy()
    
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
    team_rankings = pd.merge(offense_stats, pitching_stats, on='Team', how='outer')
    team_rankings = pd.merge(team_rankings, df_roster_comp, on='Team', how='left')
    team_rankings = team_rankings.fillna(0)
    
    max_offense = team_rankings['Projected_Runs'].max()
    max_pitching = team_rankings['Pitching_dominance'].max()
    
    max_offense = 1 if max_offense == 0 else max_offense
    max_pitching = 1 if max_pitching == 0 else max_pitching

    team_rankings['Offense_Index'] = (team_rankings['Projected_Runs'] / max_offense * 100).round(1)
    team_rankings['Pitching_Index'] = (team_rankings['Pitching_dominance'] / max_pitching * 100).round(1)
    team_rankings['Total_Power_Index'] = ((team_rankings['Offense_Index'] + team_rankings['Pitching_Index']) / 2).round(1)
    
    team_rankings = team_rankings.sort_values('Total_Power_Index', ascending=False).reset_index(drop=True)
    
    # --- 4. Display & Save ---
    print(f"\n=== 2026 PROJECTED TEAM POWER RANKINGS ===")
    print(f"(Aggregation: Top {TOP_N_BATTERS} Batters, Top {TOP_N_PITCHERS} Pitchers)\n")
    
    header = f"{'Rank':<5} {'Team':<35} {'Power':<7} {'Off.':<6} {'Pit.':<6} {'Ret.':<5} {'Sr.':<4} {'Exp.':<5}"
    print(header)
    print("-" * len(header))
    
    for idx, row in team_rankings.iterrows():
        team_display = str(row['Team'])[:33]
        print(f"{idx+1:<5} {team_display:<35} {row['Total_Power_Index']:<7} {row['Offense_Index']:<6} {row['Pitching_Index']:<6} {int(row['Returning_Players']):<5} {int(row['Returning_Seniors']):<4} {int(row['Total_Varsity_Years']):<5}")

    # --- 5. Summary Statistics ---
    print(f"\n--- League Summary ---")
    print(f"Teams Analyzed: {len(team_rankings)}")
    print(f"Avg Offense Index: {team_rankings['Offense_Index'].mean():.1f}")
    print(f"Avg Pitching Index: {team_rankings['Pitching_Index'].mean():.1f}")
    print(f"Avg Total Power: {team_rankings['Total_Power_Index'].mean():.1f}")
    
    print(f"\n--- Roster Composition ---")
    print(f"Avg Returning Players: {team_rankings['Returning_Players'].mean():.1f}")
    print(f"Avg Returning Seniors: {team_rankings['Returning_Seniors'].mean():.1f}")
    print(f"Avg Collective Varsity Years: {team_rankings['Total_Varsity_Years'].mean():.1f}")
    
    exp_75 = team_rankings['Total_Varsity_Years'].quantile(0.75)
    exp_25 = team_rankings['Total_Varsity_Years'].quantile(0.25)
    
    veteran_teams = team_rankings[team_rankings['Total_Varsity_Years'] >= exp_75]
    young_teams = team_rankings[team_rankings['Total_Varsity_Years'] <= exp_25]
    
    print(f"\nVeteran Teams (75th+ %ile, {int(exp_75)}+ varsity years): {len(veteran_teams)}")
    for _, t in veteran_teams.head(5).iterrows():
        print(f"  - {t['Team'][:30]}: {int(t['Total_Varsity_Years'])} yrs ({int(t['Returning_Seniors'])} seniors)")
    
    print(f"\nYoung/Rebuilding Teams (25th- %ile, {int(exp_25)} or fewer varsity years): {len(young_teams)}")
    for _, t in young_teams.head(5).iterrows():
        print(f"  - {t['Team'][:30]}: {int(t['Total_Varsity_Years'])} yrs ({int(t['Returning_Players'])} returning)")

    # --- 6. Save Output ---
    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, 'team_strength_rankings.csv')
    
    output_cols = ['Team', 'Total_Power_Index', 'Offense_Index', 'Pitching_Index', 
                   'Projected_Runs', 'Pitching_dominance', 
                   'Batters_Count', 'Pitchers_Count',
                   'Returning_Players', 'Returning_Seniors', 'Returning_Juniors', 'Returning_Sophs',
                   'Total_Varsity_Years', 'Avg_Varsity_Years',
                   'Top_Hitter', 'Top_Hitter_RC', 'Ace_Pitcher', 'Ace_Score']
    
    team_rankings[output_cols].to_csv(save_path, index=False)
    print(f"\nDetailed analysis saved to: {save_path}")


if __name__ == "__main__":
    analyze_team_power_rankings()