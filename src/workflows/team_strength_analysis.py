import pandas as pd
import os
import sys
import argparse

# --- Import Config ---
try:
    from src.utils.config import PATHS, MODEL_CONFIG
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import PATHS, MODEL_CONFIG

def get_confidence_weight(row):
    """
    Calculates the 'Seniority/Impact' weight for a player.
    """
    if 'Data_Type' in row and row['Data_Type'] == 'Actual':
        return 1.0
        
    if 'Generic' in str(row['Name']):
        method = str(row.get('Projection_Method', ''))
        if 'Elite' in method:
            return MODEL_CONFIG['WEIGHT_GENERIC_ELITE']
        return MODEL_CONFIG['WEIGHT_GENERIC_STD']
    
    cls = str(row.get('Class_Cleaned', '')).strip().capitalize()
    
    if cls == 'Senior':
        return MODEL_CONFIG['WEIGHT_SENIOR']
    elif cls == 'Junior':
        return MODEL_CONFIG['WEIGHT_JUNIOR']
    elif cls in ['Sophomore', 'Freshman']:
        return MODEL_CONFIG['WEIGHT_UNDERCLASS']
        
    varsity_years = row.get('Varsity_Year', 0)
    if varsity_years >= 3: return MODEL_CONFIG['WEIGHT_SENIOR']
    if varsity_years == 2: return MODEL_CONFIG['WEIGHT_JUNIOR']
    return MODEL_CONFIG['WEIGHT_UNDERCLASS']


def calculate_team_strength(df_roster):
    """
    Aggregates individual player projections into a composite Team Power Index.

    Context:
        A roster of 15 average sophomores might have the same total stats as a roster of 
        4 elite seniors, but in a real game, the seniors win. They are physically stronger 
        and emotionally more mature. This function applies a "Seniority Bonus" to account 
        for the "Varsity Factor"—the intangible value of experience and leadership that 
        pure stats often miss.

        Statistically, this is a Weighted Sum Model. We apply coefficients ($w$) to the 
        raw Runs Created ($RC$) based on class year ($w_{senior}=1.1$, $w_{underclass}=0.9$). 
        This acts as a Bayesian Prior, adjusting our raw projections based on the historically 
        higher reliability of upperclassmen performance.

        Technically, this operates as a windowed aggregation:
        1. **Calculated Field:** `Weighted_RC = RC * Confidence_Weight`
        2. **Partition & Rank:** `RANK() OVER (PARTITION BY Team ORDER BY Weighted_RC DESC)`
        3. **Top-N Filter:** Keep only the top 9 batters and top 6 pitchers (the "Starting Rotation").
        4. **Aggregation:** `SUM()` the weighted values to produce the final index.
    """
    df = df_roster.copy()
    
    # Apply Confidence Weights
    df['Confidence_Weight'] = df.apply(get_confidence_weight, axis=1)
    
    if 'RC_Score' in df.columns:
        df['Weighted_RC'] = df['RC_Score'] * df['Confidence_Weight']
    
    if 'Pitching_Score' in df.columns:
        df['Weighted_Pitching'] = df['Pitching_Score'] * df['Confidence_Weight']

    team_stats = []
    
    for team in df['Team'].unique():
        team_df = df[df['Team'] == team]
        
        # --- OFFENSE AGGREGATION ---
        batters = team_df[team_df['RC_Score'] > MODEL_CONFIG['MIN_RC_SCORE']].copy()
        top_batters = batters.nlargest(MODEL_CONFIG['TOP_N_BATTERS'], 'Weighted_RC')
        
        off_raw = top_batters['RC_Score'].sum()
        
        # Weighted Sum (Rankings)
        weights_off = [1.2, 1.15, 1.1] + [1.0] * (len(top_batters) - 3)
        weights_off = weights_off[:len(top_batters)]
        off_weighted = sum(s * w for s, w in zip(top_batters['Weighted_RC'], weights_off))
        
        # --- PITCHING AGGREGATION ---
        pitchers = team_df[team_df['Pitching_Score'] > MODEL_CONFIG['MIN_PITCHING_SCORE']].copy()
        top_pitchers = pitchers.nlargest(MODEL_CONFIG['TOP_N_PITCHERS'], 'Weighted_Pitching')
        
        pit_raw = top_pitchers['Pitching_Score'].sum()
        
        # Weighted Sum (Rankings)
        weights_pit = [1.5, 1.25] + [1.0] * (len(top_pitchers) - 2)
        weights_pit = weights_pit[:len(top_pitchers)]
        pit_weighted = sum(s * w for s, w in zip(top_pitchers['Weighted_Pitching'], weights_pit))

        # --- METADATA & COMPOSITION METRICS ---
        # Identify "Returning" players (exclude Generics)
        returning_mask = ~team_df['Name'].str.contains('Generic', case=False, na=False)
        returning_df = team_df[returning_mask]
        
        # Counts by Class (Returning players only)
        ret_seniors = len(returning_df[returning_df['Class_Cleaned'] == 'Senior'])
        ret_juniors = len(returning_df[returning_df['Class_Cleaned'] == 'Junior'])
        ret_sophs = len(returning_df[returning_df['Class_Cleaned'] == 'Sophomore'])
        
        # Experience Metrics
        total_varsity = returning_df['Varsity_Year'].sum() if not returning_df.empty else 0
        avg_varsity = returning_df['Varsity_Year'].mean() if not returning_df.empty else 0.0

        # Key Player Details
        ace_name = top_pitchers.iloc[0]['Name'] if not top_pitchers.empty else "N/A"
        ace_score = top_pitchers.iloc[0]['Pitching_Score'] if not top_pitchers.empty else 0.0
        
        top_hitter = top_batters.iloc[0]['Name'] if not top_batters.empty else "N/A"
        top_hitter_rc = top_batters.iloc[0]['RC_Score'] if not top_batters.empty else 0.0

        team_stats.append({
            'Team': team,
            # Core Strength Metrics
            'Offense_Raw': off_raw,
            'Offense_Weighted': off_weighted,
            'Pitching_Raw': pit_raw,
            'Pitching_Weighted': pit_weighted,
            'Batters_Count': len(top_batters),
            'Pitchers_Count': len(top_pitchers),
            
            # Key Players
            'Ace_Pitcher': ace_name,
            'Ace_Score': ace_score,
            'Top_Hitter': top_hitter,
            'Top_Hitter_RC': top_hitter_rc,
            
            # Composition Metadata
            'Returning_Players': len(returning_df),
            'Returning_Seniors': ret_seniors,
            'Returning_Juniors': ret_juniors,
            'Returning_Sophs': ret_sophs,
            'Total_Varsity_Years': int(total_varsity),
            'Avg_Varsity_Years': round(avg_varsity, 2)
        })
        
    return pd.DataFrame(team_stats)


def analyze_team_power_rankings(input_file: str = None, year_label: str = "2026"):
    if input_file:
        input_path = input_file
    else:
        input_path = os.path.join(PATHS['out_roster_prediction'], '2026_roster_prediction.csv')

    if not os.path.exists(input_path):
        print(f"Error: Could not find input file at {input_path}")
        return

    print(f"Loading roster projections from {input_path}...")
    df = pd.read_csv(input_path)
    
    # Calculate Strength (Includes new metadata)
    team_rankings = calculate_team_strength(df)
    
    # Calculate Indices
    max_offense = team_rankings['Offense_Weighted'].max() or 1
    max_pitching = team_rankings['Pitching_Weighted'].max() or 1

    team_rankings['Offense_Index'] = (team_rankings['Offense_Weighted'] / max_offense * 100).round(1)
    team_rankings['Pitching_Index'] = (team_rankings['Pitching_Weighted'] / max_pitching * 100).round(1)
    
    team_rankings['Total_Power_Index'] = ((team_rankings['Offense_Index'] + team_rankings['Pitching_Index']) / 2).round(1)
    team_rankings = team_rankings.sort_values('Total_Power_Index', ascending=False).reset_index(drop=True)
    
    team_rankings['Rank'] = team_rankings.index + 1

    # Display Report
    print(f"\n=== {year_label} TEAM POWER RANKINGS (SENIORITY ADJUSTED) ===")
    print(f"Weights: Senior ({MODEL_CONFIG['WEIGHT_SENIOR']}x), Junior ({MODEL_CONFIG['WEIGHT_JUNIOR']}x), Underclass ({MODEL_CONFIG['WEIGHT_UNDERCLASS']}x)\n")
    
    # Expanded Header to show composition
    header = f"{'Rank':<5} {'Team':<32} {'Power':<6} {'Off':<6} {'Pit':<6} {'Ace':<18} {'Ret':<4} {'Snr':<4} {'Exp':<4}"
    print(header)
    print("-" * len(header))
    
    for idx, row in team_rankings.head(25).iterrows():
        team_display = str(row['Team'])[:30]
        ace_display = str(row['Ace_Pitcher'])[:16]
        print(f"{int(row['Rank']):<5} {team_display:<32} {row['Total_Power_Index']:<6} {row['Offense_Index']:<6} {row['Pitching_Index']:<6} {ace_display:<18} {row['Returning_Players']:<4} {row['Returning_Seniors']:<4} {row['Avg_Varsity_Years']:<4}")

    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f'{year_label}_team_strength_rankings.csv' if year_label != "2026" else 'team_strength_rankings.csv'
    save_path = os.path.join(output_dir, filename)
    
    df_order = ['Rank','Team','Total_Power_Index','Offense_Index','Pitching_Index']
    team_rankings = team_rankings[df_order]
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