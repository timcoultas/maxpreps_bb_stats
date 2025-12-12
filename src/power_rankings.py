import pandas as pd
import numpy as np
import os

def generate_power_rankings():
    """
    Generates a 'First to Worst' Power Ranking for 2026 based on projected rosters.
    
    Methodology:
    1. OFFENSE: Calculate 'Team OPS' for the projected Starting 9 (Top 9 by PA).
    2. PITCHING: Calculate 'Team ERA' for the projected Rotation (Top 5 by IP).
    3. RANKING: Combine OPS and ERA using Z-Scores (Standard Deviations from League Average).
       Score = (OPS_Z_Score) - (ERA_Z_Score).
    """
    
    input_path = os.path.join('data', 'output', 'roster_prediction', '2026_roster_prediction.csv')
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    print("Loading 2026 Projections...")
    df = pd.read_csv(input_path)
    
    teams = df['Team'].unique()
    team_stats = []

    print(f"Analyzing {len(teams)} teams...")

    for team in teams:
        roster = df[df['Team'] == team]
        
        # --- 1. OFFENSIVE METRICS (Starting 9) ---
        # Sort by PA to get the starters
        batters = roster[roster['Is_Batter'] == True].sort_values('PA', ascending=False).head(9)
        
        if not batters.empty:
            # Aggregate Counting Stats
            # Note: We recalculate rate stats from totals to handle weighting correctly
            # (e.g. A guy with 100 ABs matters more than a guy with 10 ABs)
            sum_h = batters['H'].sum()
            sum_2b = batters['2B'].sum()
            sum_3b = batters['3B'].sum()
            sum_hr = batters['HR'].sum()
            sum_bb = batters['BB'].sum()
            sum_hbp = batters['HBP'].sum()
            sum_ab = batters['AB'].sum()
            sum_sf = batters['SF'].sum()
            
            # Calculate Total Bases
            # H = 1B + 2B + 3B + HR
            # 1B = H - 2B - 3B - HR
            # TB = 1*1B + 2*2B + 3*3B + 4*HR
            # Simplified: TB = H + 2B + 2*3B + 3*HR
            total_bases = sum_h + sum_2b + (2 * sum_3b) + (3 * sum_hr)
            
            # OBP = (H + BB + HBP) / (AB + BB + HBP + SF)
            numerator_obp = sum_h + sum_bb + sum_hbp
            denominator_obp = sum_ab + sum_bb + sum_hbp + sum_sf
            
            team_obp = numerator_obp / denominator_obp if denominator_obp > 0 else 0
            team_slg = total_bases / sum_ab if sum_ab > 0 else 0
            team_ops = team_obp + team_slg
            
            proj_runs = batters['R'].sum()
        else:
            team_ops = 0
            proj_runs = 0

        # --- 2. PITCHING METRICS (Rotation Top 5) ---
        # Sort by IP to get the main arms
        pitchers = roster[roster['Is_Pitcher'] == True].sort_values('IP', ascending=False).head(5)
        
        if not pitchers.empty:
            sum_er = pitchers['ER'].sum()
            sum_ip = pitchers['IP'].sum()
            
            # ERA = (ER * 7) / IP  (High School games are 7 innings)
            team_era = (sum_er * 7) / sum_ip if sum_ip > 0 else 99.0
            
            # Cap ERA at 15 for sanity in rankings (in case of weird outliers)
            if team_era > 15: team_era = 15.0
            
        else:
            team_era = 15.0 # Penalty for no pitchers

        team_stats.append({
            'Team': team,
            'Projected_OPS': round(team_ops, 3),
            'Projected_ERA': round(team_era, 2),
            'Top9_Runs': int(proj_runs)
        })

    # Create DataFrame
    rank_df = pd.DataFrame(team_stats)
    
    # --- 3. WIZARDRY (Z-Score Ranking) ---
    # Normalize stats to compare apples to oranges (OPS vs ERA)
    
    # OPS Z-Score (Higher is Better)
    ops_mean = rank_df['Projected_OPS'].mean()
    ops_std = rank_df['Projected_OPS'].std()
    rank_df['OPS_Z'] = (rank_df['Projected_OPS'] - ops_mean) / ops_std
    
    # ERA Z-Score (Lower is Better, so we invert or subtract later)
    era_mean = rank_df['Projected_ERA'].mean()
    era_std = rank_df['Projected_ERA'].std()
    rank_df['ERA_Z'] = (rank_df['Projected_ERA'] - era_mean) / era_std
    
    # POWER SCORE
    # Score = (Offense Strength) - (Pitching Weakness)
    # A negative ERA Z-score means low ERA (Good). Subtracting a negative adds to the score.
    rank_df['Power_Score'] = rank_df['OPS_Z'] - rank_df['ERA_Z']
    
    # Sort
    rank_df = rank_df.sort_values('Power_Score', ascending=False)
    
    # Add 1-N Rank
    rank_df.reset_index(drop=True, inplace=True)
    rank_df.index += 1
    rank_df.index.name = 'Rank'
    rank_df = rank_df.reset_index()

    # --- 4. Save ---
    output_dir = os.path.join('data', 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, '2026_power_rankings.csv')
    
    # Clean output columns
    final_cols = ['Rank', 'Team', 'Power_Score', 'Projected_OPS', 'Projected_ERA', 'Top9_Runs']
    rank_df[final_cols].to_csv(output_path, index=False)
    
    print(f"\nSuccess! Power Rankings generated for {len(rank_df)} teams.")
    print(f"Saved to: {output_path}")
    print("\n--- Top 10 Projected Teams for 2026 ---")
    print(rank_df[final_cols].head(20).to_string(index=False))

if __name__ == "__main__":
    generate_power_rankings()