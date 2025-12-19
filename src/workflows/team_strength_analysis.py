import pandas as pd
import os
import sys
import argparse

# --- Import Config ---
try:
    from src.utils.config import PATHS
except ImportError:
    # Fallback if running directly from src/workflows
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import PATHS

# --- Configuration Constants ---
TOP_N_BATTERS = 9       
TOP_N_PITCHERS = 4      
MIN_RC_SCORE = 0.1      
MIN_PITCHING_SCORE = 0.1 


def analyze_team_power_rankings(input_file: str = None, year_label: str = "2026"):
    """
    Analyzes projected rosters to determine team-level strength indices and generates power rankings.
    
    UPDATED METHODOLOGY (Seniority & Probability Weighted):
    Applies weights based on Class Year to reflect the "Senior Leadership" factor common in HS sports.
    """
    
    # 1. Determine Input Path
    if input_file:
        input_path = input_file
    else:
        input_path = os.path.join(PATHS['out_roster_prediction'], '2026_roster_prediction.csv')

    if not os.path.exists(input_path):
        print(f"Error: Could not find input file at {input_path}")
        return

    print(f"Loading roster projections from {input_path}...")
    df = pd.read_csv(input_path)
    
    # --- 0. Roster Composition Metrics ---
    if 'Projection_Method' in df.columns:
        df['Is_Returning'] = ~df['Projection_Method'].str.contains('Generic|Backfill', case=False, na=False)
    else:
        df['Is_Returning'] = True 
    
    # --- SENIORITY WEIGHTING LOGIC ---
    def get_confidence_weight(row):
        # 1. Actuals Data: Always 1.0 (It happened)
        if 'Data_Type' in row and row['Data_Type'] == 'Actual':
            return 1.0
            
        # 2. Generic Players Logic
        if 'Generic' in str(row['Name']):
            # NEW: If it's an Elite Backfill (indicated by method), don't penalize as harshly
            # They are likely varsity ready.
            method = str(row.get('Projection_Method', ''))
            if 'Elite' in method:
                return 1.00 # Treat as standard varsity player
            return 0.75  # Standard generic penalty
        
        # 3. Class-Based Weights (The "How many Seniors?" Factor)
        cls = str(row.get('Class_Cleaned', '')).strip().capitalize()
        
        if cls == 'Senior':
            return 1.10  # Leadership/Physical Maturity Bonus
        elif cls == 'Junior':
            return 1.00  # Baseline
        elif cls in ['Sophomore', 'Freshman']:
            return 0.90  # Development Volatility Penalty
            
        # 4. Fallback based on Experience if Class is missing
        varsity_years = row.get('Varsity_Year', 0)
        if varsity_years >= 3: return 1.10
        if varsity_years == 2: return 1.00
        return 0.90

    df['Confidence_Weight'] = df.apply(get_confidence_weight, axis=1)

    # --- 1. Offensive Power Rankings (Weighted) ---
    df_batters = df[df['RC_Score'] > MIN_RC_SCORE].copy()
    df_batters['Weighted_RC'] = df_batters['RC_Score'] * df_batters['Confidence_Weight']
    
    offense_scores = []
    for team in df['Team'].unique():
        team_batters = df_batters[df_batters['Team'] == team].nlargest(TOP_N_BATTERS, 'Weighted_RC')
        
        if len(team_batters) > 0:
            # Lineup Weight: Top 3 hitters matter disproportionately
            weights = [1.2, 1.15, 1.1] + [1.0] * (len(team_batters) - 3)
            weights = weights[:len(team_batters)]
            
            # FIXED: Summing the Weighted_RC instead of raw RC_Score
            weighted_sum = sum(s * w for s, w in zip(team_batters['Weighted_RC'], weights))
            
            offense_scores.append({
                'Team': team,
                'Projected_Runs': weighted_sum,
                'Batters_Count': len(team_batters),
                'Top_Hitter': team_batters.iloc[0]['Name'],
                'Top_Hitter_RC': team_batters.iloc[0]['RC_Score']
            })
        else:
            offense_scores.append({'Team': team, 'Projected_Runs': 0, 'Batters_Count': 0, 'Top_Hitter': 'N/A', 'Top_Hitter_RC': 0})
    
    offense_stats = pd.DataFrame(offense_scores)
    
    # --- 2. Pitching Power Rankings (Ace-Weighted) ---
    df_pitchers = df[df['Pitching_Score'] > MIN_PITCHING_SCORE].copy()
    df_pitchers['Weighted_Pitching'] = df_pitchers['Pitching_Score'] * df_pitchers['Confidence_Weight']
    
    pitching_scores = []
    for team in df['Team'].unique():
        team_pitchers = df_pitchers[df_pitchers['Team'] == team].nlargest(TOP_N_PITCHERS, 'Weighted_Pitching')
        
        if len(team_pitchers) > 0:
            # Pitching Weight: Aces matter disproportionately
            weights = [1.5, 1.25] + [1.0] * (len(team_pitchers) - 2)
            weights = weights[:len(team_pitchers)]
            
            # FIXED: Summing the Weighted_Pitching instead of raw Pitching_Score
            weighted_sum = sum(s * w for s, w in zip(team_pitchers['Weighted_Pitching'], weights))
            
            pitching_scores.append({
                'Team': team,
                'Pitching_dominance': weighted_sum,
                'Pitchers_Count': len(team_pitchers),
                'Ace_Pitcher': team_pitchers.iloc[0]['Name'],
                'Ace_Score': team_pitchers.iloc[0]['Pitching_Score']
            })
        else:
            pitching_scores.append({'Team': team, 'Pitching_dominance': 0, 'Pitchers_Count': 0, 'Ace_Pitcher': 'N/A', 'Ace_Score': 0})
    
    pitching_stats = pd.DataFrame(pitching_scores)
    
    # --- 3. Combined "Power Index" ---
    team_rankings = pd.merge(offense_stats, pitching_stats, on='Team', how='outer').fillna(0)
    
    max_offense = team_rankings['Projected_Runs'].max() or 1
    max_pitching = team_rankings['Pitching_dominance'].max() or 1

    team_rankings['Offense_Index'] = (team_rankings['Projected_Runs'] / max_offense * 100).round(1)
    team_rankings['Pitching_Index'] = (team_rankings['Pitching_dominance'] / max_pitching * 100).round(1)
    
    team_rankings['Total_Power_Index'] = ((team_rankings['Offense_Index'] + team_rankings['Pitching_Index']) / 2).round(1)
    team_rankings = team_rankings.sort_values('Total_Power_Index', ascending=False).reset_index(drop=True)
    
    # --- 4. Display & Save ---
    print(f"\n=== {year_label} TEAM POWER RANKINGS (SENIORITY ADJUSTED) ===")
    print(f"Weights: Senior (1.1x), Junior (1.0x), Underclass (0.9x), Generic (0.75x [Elite: 1.0x])\n")
    
    header = f"{'Rank':<5} {'Team':<35} {'Power':<7} {'Off.':<6} {'Pit.':<6} {'Ace':<20}"
    print(header)
    print("-" * len(header))
    
    for idx, row in team_rankings.head(25).iterrows():
        team_display = str(row['Team'])[:33]
        ace_display = str(row['Ace_Pitcher'])[:18]
        print(f"{idx+1:<5} {team_display:<35} {row['Total_Power_Index']:<7} {row['Offense_Index']:<6} {row['Pitching_Index']:<6} {ace_display:<20}")

    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f'{year_label}_team_strength_rankings.csv' if year_label != "2026" else 'team_strength_rankings.csv'
    save_path = os.path.join(output_dir, filename)
    
    team_rankings.to_csv(save_path, index=False)
    print(f"\nSaved weighted rankings to: {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze team strength from roster projections")
    parser.add_argument('--input-file', type=str, default=None, help='Path to roster prediction CSV')
    parser.add_argument('--year', type=str, default="2026", help='Label for the year')
    args = parser.parse_args()
    analyze_team_power_rankings(args.input_file, args.year)


if __name__ == "__main__":
    main()