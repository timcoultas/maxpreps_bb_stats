import pandas as pd
import numpy as np
import os
import sys

# --- Import Config ---
try:
    from src.utils.config import PATHS
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import PATHS

def simulate_games(simulations_per_game=1000):
    """
    Executes a Monte Carlo simulation of the season schedule using Negative Binomial distribution.
    
    UPDATES (Post-Adversarial Review V2):
    1. Reverted Dampening: Restored SQRT dampening. The previous linear attempt caused score explosions 
       (e.g., 60+ runs) when elite offenses met rebuilding (20th %ile) defenses.
    2. Distribution: Kept Negative Binomial for variance realism.
    """
    
    # 1. Load Data
    roster_path = os.path.join(PATHS['out_roster_prediction'], '2026_roster_prediction.csv')
    schedule_path = os.path.join(PATHS['input'], 'rocky_mountain_schedule.csv') 
    
    if not os.path.exists(roster_path) or not os.path.exists(schedule_path):
        print("Error: Missing input files.")
        return

    print(f"Loading data & running {simulations_per_game} simulations per game...")
    df_roster = pd.read_csv(roster_path)
    df_schedule = pd.read_csv(schedule_path)
    
    # 2. Build Metrics
    # Capture utility value (RC > 0.5)
    df_batters = df_roster[df_roster['RC_Score'] > 0.5]
    df_pitchers = df_roster[df_roster['Pitching_Score'] > 0.5]
    
    team_stats = pd.DataFrame(df_roster['Team'].unique(), columns=['Team'])
    
    # --- Aggregation Logic ---
    offense_scores = []
    for team in team_stats['Team']:
        top_9 = df_batters[df_batters['Team'] == team].nlargest(9, 'RC_Score')
        offense_scores.append({'Team': team, 'Offense_Raw': top_9['RC_Score'].sum()})
    
    pitching_scores = []
    for team in team_stats['Team']:
        top_staff = df_pitchers[df_pitchers['Team'] == team].nlargest(5, 'Pitching_Score')
        pitching_scores.append({'Team': team, 'Pitching_Raw': top_staff['Pitching_Score'].sum()})
        
    df_strength = pd.merge(pd.DataFrame(offense_scores), pd.DataFrame(pitching_scores), on='Team')
    
    # Normalize
    avg_off = df_strength['Offense_Raw'].mean() or 1
    avg_pit = df_strength['Pitching_Raw'].mean() or 1
    
    df_strength['Off_Index'] = df_strength['Offense_Raw'] / avg_off
    df_strength['Pit_Index'] = df_strength['Pitching_Raw'] / avg_pit
    
    # Base Map
    strength_map = df_strength.set_index('Team')[['Off_Index', 'Pit_Index']].to_dict('index')
    strength_map['Generic High School'] = {'Off_Index': 0.8, 'Pit_Index': 0.8}

    # Pre-compute Fuzzy Mapping
    schedule_teams = set(df_schedule['Home'].unique()).union(set(df_schedule['Away'].unique()))
    team_resolver = {}
    
    db_teams = list(strength_map.keys())
    for tm in schedule_teams:
        if pd.isna(tm): continue
        if tm in strength_map:
            team_resolver[tm] = tm
        else:
            match = 'Generic High School'
            clean_tm = tm.split('(')[0].strip()
            for db_tm in db_teams:
                if clean_tm in db_tm:
                    match = db_tm
                    break
            team_resolver[tm] = match

    # 3. Simulation Loop
    results = []
    
    my_team_name = "Rocky Mountain (Fort Collins, CO)"
    if my_team_name not in strength_map:
        for t in strength_map:
            if "Rocky Mountain" in t:
                my_team_name = t
                break
    
    my_stats = strength_map.get(my_team_name, strength_map['Generic High School'])
    
    print(f"\n{'Date':<12} {'Opponent':<30} {'Win %':<8} {'Avg Score':<12} {'Confidence':<15} {'Analysis'}")
    print("-" * 120)

    total_games = len(df_schedule)
    sim_matrix = np.zeros((total_games, simulations_per_game))

    def generate_neg_binomial(mean_val, n_sims, dispersion=1.25):
        if mean_val <= 0: return np.zeros(n_sims)
        variance = mean_val * dispersion
        p = mean_val / variance
        n = (mean_val ** 2) / (variance - mean_val)
        return np.random.negative_binomial(n, p, n_sims)

    for idx, game in df_schedule.iterrows():
        home, away = game.get('Home', ''), game.get('Away', '')
        opponent = away if my_team_name in home else home
        if not opponent: opponent = game.get('Opponent', 'Unknown')
        
        location = 'Home' if my_team_name in home else 'Away'
        date = game.get('Date', f"G{idx+1}")

        db_opponent_name = team_resolver.get(opponent, 'Generic High School')
        opp_stats = strength_map.get(db_opponent_name)

        # --- CALCULATE EXPECTED RUN RATES (Lambda) ---
        LEAGUE_BASE = 6.0
        
        # RESTORED: Sqrt Dampening
        # The 20th %ile backfill creates massive index disparities (e.g. 0.2 vs 1.0).
        # Without sqrt, this leads to 5x-10x multipliers and 60+ run projections.
        my_off_factor = np.sqrt(my_stats['Off_Index'])
        opp_pit_factor = 1.0 / np.sqrt(opp_stats['Pit_Index']) if opp_stats['Pit_Index'] > 0 else 1.0
        
        opp_off_factor = np.sqrt(opp_stats['Off_Index'])
        my_pit_factor = 1.0 / np.sqrt(my_stats['Pit_Index']) if my_stats['Pit_Index'] > 0 else 1.0
        
        my_lambda = LEAGUE_BASE * my_off_factor * opp_pit_factor
        opp_lambda = LEAGUE_BASE * opp_off_factor * my_pit_factor
        
        if location == 'Home': my_lambda *= 1.1
        else: opp_lambda *= 1.1
            
        # --- MONTE CARLO EXECUTION ---
        my_scores = generate_neg_binomial(my_lambda, simulations_per_game, dispersion=1.3)
        opp_scores = generate_neg_binomial(opp_lambda, simulations_per_game, dispersion=1.3)
        
        wins = np.where(my_scores > opp_scores, 1, 0)
        ties = np.where(my_scores == opp_scores, 1, 0)
        tie_breakers = np.random.binomial(1, 0.5, simulations_per_game) * ties
        wins = wins + tie_breakers
        
        sim_matrix[idx] = wins
        
        win_pct = wins.mean()
        avg_my_score = my_scores.mean()
        avg_opp_score = opp_scores.mean()
        
        if win_pct > 0.90: conf = "Lock (W)"
        elif win_pct > 0.65: conf = "Solid (W)"
        elif win_pct < 0.10: conf = "Lock (L)"
        elif win_pct < 0.35: conf = "Solid (L)"
        else: conf = "Toss-up"
        
        reasons = []
        # Adjusted thresholds for Sqrt scale
        off_diff = my_stats['Off_Index'] - opp_stats['Off_Index']
        if off_diff > 0.4: reasons.append("Elite Offense")
        elif off_diff > 0.15: reasons.append("Better Bats")
        elif off_diff < -0.4: reasons.append("Overmatched Offense")
        elif off_diff < -0.15: reasons.append("Weaker Bats")
        
        pit_diff = my_stats['Pit_Index'] - opp_stats['Pit_Index']
        if pit_diff > 0.4: reasons.append("Dominant Pitching")
        elif pit_diff > 0.15: reasons.append("Better Arms")
        elif pit_diff < -0.4: reasons.append("Weak Pitching")
        elif pit_diff < -0.15: reasons.append("Less Depth")
        
        if location == 'Home': reasons.append("Home Field")
        
        if not reasons: analysis = "Even Matchup"
        else:
            if win_pct < 0.5:
                analysis = f"Opponent advantage: {', '.join(reasons).replace('Elite Offense', 'Their Offense').replace('Dominant Pitching', 'Their Pitching')}"
            else:
                analysis = f"Edge: {', '.join(reasons)}"
                
        display_analysis = (analysis[:35] + '..') if len(analysis) > 35 else analysis
        
        print(f"{date:<12} {opponent[:28]:<30} {win_pct*100:.1f}%    {avg_my_score:.1f}-{avg_opp_score:.1f}       {conf:<15} {display_analysis}")
        
        results.append({
            'Date': date,
            'Opponent': opponent,
            'Win_Pct': win_pct,
            'Proj_Score': f"{avg_my_score:.1f}-{avg_opp_score:.1f}",
            'Confidence': conf,
            'Analysis': analysis,
            'My_Off_Idx': round(my_stats['Off_Index'], 2),
            'My_Pit_Idx': round(my_stats['Pit_Index'], 2),
            'Opp_Off_Idx': round(opp_stats['Off_Index'], 2),
            'Opp_Pit_Idx': round(opp_stats['Pit_Index'], 2)
        })

    season_win_totals = sim_matrix.sum(axis=0)
    
    avg_wins = season_win_totals.mean()
    p90_wins = np.percentile(season_win_totals, 90)
    p10_wins = np.percentile(season_win_totals, 10)
    
    print("-" * 120)
    print(f"\nSEASON PROJECTION ({simulations_per_game} Sims):")
    print(f"Average Record: {avg_wins:.1f} - {total_games - avg_wins:.1f}")
    print(f"Ceiling (90th %): {int(p90_wins)} Wins")
    print(f"Floor (10th %):   {int(p10_wins)} Wins")
    
    df_results = pd.DataFrame(results)
    output_dir = PATHS['out_team_strength']
    save_path = os.path.join(output_dir, 'rocky_mountain_monte_carlo.csv')
    df_results.to_csv(save_path, index=False)
    print(f"\nDetailed data saved to: {save_path}")

if __name__ == "__main__":
    simulate_games()