"""
compare_projections.py

Compares projected stats/rankings against actual results to validate model accuracy.
Includes Seniority-based weighting.

Usage:
    python compare_projections.py --projection-file 2025_roster_prediction_backtest.csv \
                                   --actuals-file 2025_actual_stats.csv \
                                   --simulation-file rocky_mountain_monte_carlo_backtest.csv \
                                   --results-file rocky_mountain_results_2025.csv

Output:
    Console report + CSV files in data/output/backtest/
"""

import pandas as pd
import numpy as np
import os
import sys
import argparse

# --- Import Config ---
try:
    from src.utils.config import PATHS
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from src.utils.config import PATHS

# --- Constants ---
TOP_N_BATTERS = 9
TOP_N_PITCHERS = 4
MIN_RC_SCORE = 0.1
MIN_PITCHING_SCORE = 0.1

def calculate_weighted_team_strength(df, label):
    """
    Calculates team strength using the Weighted Impact methodology.
    Matches the Seniority Bonus logic in team_strength_analysis.py.
    """
    
    # --- SENIORITY WEIGHTING LOGIC ---
    def get_confidence_weight(row):
        # 1. Actuals Data: Always 1.0 (It happened)
        if label == 'Actual':
            return 1.0
            
        # 2. Generic Players: Harsh Penalty (Replacement Level)
        if 'Generic' in str(row['Name']): 
            return 0.75  
        
        # 3. Class-Based Weights (The "How many Seniors?" Factor)
        cls = str(row.get('Class_Cleaned', '')).strip().capitalize()
        
        if cls == 'Senior':
            return 1.10  # Leadership/Physical Maturity Bonus
        elif cls == 'Junior':
            return 1.00  # Baseline
        elif cls in ['Sophomore', 'Freshman']:
            return 0.90  # Development Volatility Penalty
            
        # 4. Fallback based on Experience
        varsity_years = row.get('Varsity_Year', 0)
        if varsity_years >= 3: return 1.10
        if varsity_years == 2: return 1.00
        return 0.90

    df = df.copy()
    df['Confidence_Weight'] = df.apply(get_confidence_weight, axis=1)

    # Aggregation Helper
    teams = []
    
    for team in df['Team'].unique():
        team_df = df[df['Team'] == team]
        
        # --- Offense ---
        batters = team_df[team_df['RC_Score'] > MIN_RC_SCORE].copy()
        batters['Weighted_RC'] = batters['RC_Score'] * batters['Confidence_Weight']
        
        top_batters = batters.nlargest(TOP_N_BATTERS, 'Weighted_RC')
        
        off_score = 0
        if len(top_batters) > 0:
            weights = [1.2, 1.15, 1.1] + [1.0] * (len(top_batters) - 3)
            weights = weights[:len(top_batters)]
            # FIXED: Summing the Weighted_RC instead of raw RC_Score
            off_score = sum(s * w for s, w in zip(top_batters['Weighted_RC'], weights))
            
        # --- Pitching ---
        pitchers = team_df[team_df['Pitching_Score'] > MIN_PITCHING_SCORE].copy()
        pitchers['Weighted_Pitching'] = pitchers['Pitching_Score'] * pitchers['Confidence_Weight']
        
        top_pitchers = pitchers.nlargest(TOP_N_PITCHERS, 'Weighted_Pitching')
        
        pit_score = 0
        if len(top_pitchers) > 0:
            weights = [1.5, 1.25] + [1.0] * (len(top_pitchers) - 2)
            weights = weights[:len(top_pitchers)]
            # FIXED: Summing the Weighted_Pitching instead of raw Pitching_Score
            pit_score = sum(s * w for s, w in zip(top_pitchers['Weighted_Pitching'], weights))
            
        teams.append({
            'Team': team,
            f'Offense_{label}': off_score,
            f'Pitching_{label}': pit_score,
            f'Total_{label}': off_score + pit_score
        })
        
    return pd.DataFrame(teams)


def compare_player_projections(df_proj: pd.DataFrame, df_actual: pd.DataFrame) -> pd.DataFrame:
    """
    Compares projected player stats against actual stats.
    """
    print("\n" + "="*70)
    print("PLAYER PROJECTION ACCURACY")
    print("="*70)
    
    df_proj_real = df_proj[~df_proj['Name'].str.contains('Generic', na=False)].copy()
    
    comparison = pd.merge(
        df_proj_real,
        df_actual,
        on=['Name', 'Team'],
        suffixes=('_Proj', '_Actual'),
        how='inner'
    )
    
    print(f"\nMatched {len(comparison)} players between projection and actuals")
    
    batting_stats = ['H', 'AB', 'HR', 'RBI', 'AVG', 'OPS', 'RC_Score']
    pitching_stats = ['IP', 'K_P', 'ERA', 'BB_P', 'ER', 'Pitching_Score']
    
    results = []
    
    print("\n--- BATTING PROJECTIONS ---")
    print(f"{'Stat':<12} {'Avg Proj':<12} {'Avg Actual':<12} {'Avg Error':<12} {'Error %':<10}")
    print("-" * 58)
    
    for stat in batting_stats:
        proj_col = f"{stat}_Proj" if f"{stat}_Proj" in comparison.columns else stat
        actual_col = f"{stat}_Actual" if f"{stat}_Actual" in comparison.columns else None
        
        if actual_col and actual_col in comparison.columns and proj_col in comparison.columns:
            batters = comparison[comparison['Is_Batter_Actual'] == True]
            
            if len(batters) > 0:
                avg_proj = batters[proj_col].mean()
                avg_actual = batters[actual_col].mean()
                avg_error = (batters[proj_col] - batters[actual_col]).abs().mean()
                error_pct = (avg_error / avg_actual * 100) if avg_actual != 0 else 0
                
                print(f"{stat:<12} {avg_proj:<12.2f} {avg_actual:<12.2f} {avg_error:<12.2f} {error_pct:<10.1f}%")
                
                results.append({
                    'Category': 'Batting',
                    'Stat': stat,
                    'Avg_Projected': avg_proj,
                    'Avg_Actual': avg_actual,
                    'Avg_Abs_Error': avg_error,
                    'Error_Pct': error_pct,
                    'N': len(batters)
                })
    
    print("\n--- PITCHING PROJECTIONS ---")
    print(f"{'Stat':<12} {'Avg Proj':<12} {'Avg Actual':<12} {'Avg Error':<12} {'Error %':<10}")
    print("-" * 58)
    
    for stat in pitching_stats:
        proj_col = f"{stat}_Proj" if f"{stat}_Proj" in comparison.columns else stat
        actual_col = f"{stat}_Actual" if f"{stat}_Actual" in comparison.columns else None
        
        if actual_col and actual_col in comparison.columns and proj_col in comparison.columns:
            pitchers = comparison[comparison['Is_Pitcher_Actual'] == True]
            
            if len(pitchers) > 0:
                avg_proj = pitchers[proj_col].mean()
                avg_actual = pitchers[actual_col].mean()
                avg_error = (pitchers[proj_col] - pitchers[actual_col]).abs().mean()
                error_pct = (avg_error / avg_actual * 100) if avg_actual != 0 else 0
                
                print(f"{stat:<12} {avg_proj:<12.2f} {avg_actual:<12.2f} {avg_error:<12.2f} {error_pct:<10.1f}%")
                
                results.append({
                    'Category': 'Pitching',
                    'Stat': stat,
                    'Avg_Projected': avg_proj,
                    'Avg_Actual': avg_actual,
                    'Avg_Abs_Error': avg_error,
                    'Error_Pct': error_pct,
                    'N': len(pitchers)
                })
    
    print("\n--- TOP PROJECTED BATTERS vs ACTUAL ---")
    if 'RC_Score_Proj' in comparison.columns and 'RC_Score_Actual' in comparison.columns:
        top_batters = comparison.nlargest(15, 'RC_Score_Proj')[
            ['Name', 'Team', 'RC_Score_Proj', 'RC_Score_Actual']
        ].copy()
        top_batters['Error'] = top_batters['RC_Score_Proj'] - top_batters['RC_Score_Actual']
        top_batters['Error_Pct'] = (top_batters['Error'] / top_batters['RC_Score_Actual'] * 100).round(1)
        print(top_batters.to_string(index=False))
    
    return pd.DataFrame(results)


def compare_team_rankings(df_proj: pd.DataFrame, df_actual: pd.DataFrame) -> pd.DataFrame:
    """
    Compares projected team power rankings against actual team strength.
    """
    print("\n" + "="*70)
    print("TEAM RANKING ACCURACY (SENIORITY ADJUSTED)")
    print("="*70)
    
    proj_teams = calculate_weighted_team_strength(df_proj, 'Proj')
    actual_teams = calculate_weighted_team_strength(df_actual, 'Actual')
    
    comparison = pd.merge(proj_teams, actual_teams, on='Team', how='outer').fillna(0)
    
    comparison['Rank_Proj'] = comparison['Total_Proj'].rank(ascending=False).astype(int)
    comparison['Rank_Actual'] = comparison['Total_Actual'].rank(ascending=False).astype(int)
    comparison['Rank_Diff'] = comparison['Rank_Proj'] - comparison['Rank_Actual']
    
    comparison = comparison.sort_values('Rank_Actual')
    
    print(f"\n{'Team':<40} {'Proj Rank':<12} {'Actual Rank':<12} {'Diff':<8}")
    print("-" * 72)
    
    for _, row in comparison.head(20).iterrows():
        team_short = str(row['Team'])[:38]
        diff_str = f"+{int(row['Rank_Diff'])}" if row['Rank_Diff'] > 0 else str(int(row['Rank_Diff']))
        print(f"{team_short:<40} {int(row['Rank_Proj']):<12} {int(row['Rank_Actual']):<12} {diff_str:<8}")
    
    avg_rank_error = comparison['Rank_Diff'].abs().mean()
    correlation = comparison['Total_Proj'].corr(comparison['Total_Actual'])
    
    print(f"\n--- SUMMARY ---")
    print(f"Average rank error: {avg_rank_error:.1f} positions")
    print(f"Correlation (Projected vs Actual strength): {correlation:.3f}")
    print(f"Teams within 3 positions: {(comparison['Rank_Diff'].abs() <= 3).sum()} / {len(comparison)}")
    
    return comparison


def compare_game_predictions(df_sim: pd.DataFrame, df_results: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "="*70)
    print("GAME PREDICTION ACCURACY")
    print("="*70)
    
    comparison = pd.merge(df_sim, df_results, on=['Date', 'Opponent'], how='inner')
    
    if len(comparison) == 0:
        print("No matching games found.")
        return pd.DataFrame()
    
    print(f"\nMatched {len(comparison)} games")
    
    comparison['Actual_Win'] = (comparison['Result'] == 'W').astype(int)
    
    print(f"\n{'Date':<12} {'Opponent':<25} {'Win Prob':<10} {'Confidence':<15} {'Result':<8} {'Correct?'}")
    print("-" * 85)
    
    correct = 0
    for _, row in comparison.iterrows():
        predicted_win = row['Win_Pct'] > 0.5
        actual_win = row['Actual_Win'] == 1
        is_correct = predicted_win == actual_win
        if is_correct: correct += 1
        
        correct_str = "✓" if is_correct else "✗"
        result_str = "W" if actual_win else "L"
        
        print(f"{row['Date']:<12} {str(row['Opponent'])[:23]:<25} {row['Win_Pct']*100:>6.1f}%   {row['Confidence']:<15} {result_str:<8} {correct_str}")
    
    accuracy = correct / len(comparison) * 100
    print(f"\n--- SUMMARY ---")
    print(f"Overall accuracy: {correct}/{len(comparison)} ({accuracy:.1f}%)")
    
    brier = ((comparison['Win_Pct'] - comparison['Actual_Win']) ** 2).mean()
    print(f"Brier Score: {brier:.3f}")
    
    return comparison


def main():
    parser = argparse.ArgumentParser(description="Compare projections against actual results")
    parser.add_argument('--projection-file', type=str, required=True, help='Path to projection CSV')
    parser.add_argument('--actuals-file', type=str, required=True, help='Path to actual stats CSV')
    parser.add_argument('--simulation-file', type=str, default=None, help='Path to Monte Carlo CSV')
    parser.add_argument('--results-file', type=str, default=None, help='Path to game results CSV')
    
    args = parser.parse_args()
    
    print("Loading projection data...")
    df_proj = pd.read_csv(args.projection_file)
    
    print("Loading actual stats...")
    df_actual = pd.read_csv(args.actuals_file)
    
    player_results = compare_player_projections(df_proj, df_actual)
    team_results = compare_team_rankings(df_proj, df_actual)
    
    if args.simulation_file and args.results_file:
        print("\nLoading simulation and results...")
        df_sim = pd.read_csv(args.simulation_file)
        df_results = pd.read_csv(args.results_file)
        compare_game_predictions(df_sim, df_results)
    
    output_dir = os.path.join(PATHS['out_roster_prediction'], 'backtest')
    os.makedirs(output_dir, exist_ok=True)
    
    player_results.to_csv(os.path.join(output_dir, 'player_projection_accuracy.csv'), index=False)
    team_results.to_csv(os.path.join(output_dir, 'team_ranking_accuracy.csv'), index=False)
    
    print(f"\n" + "="*70)
    print("COMPARISON COMPLETE")
    print(f"Results saved to: {output_dir}")
    print("="*70)


if __name__ == "__main__":
    main()