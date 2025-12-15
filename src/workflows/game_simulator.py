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


# --- Configuration Constants ---
LEAGUE_BASE_RUNS = 6.0          # Average runs per game in high school baseball
HOME_FIELD_ADVANTAGE = 1.10     # 10% boost for home team (derived from MLB studies)
DEFAULT_DISPERSION = 1.3        # Negative binomial dispersion parameter
MIN_INDEX_FLOOR = 0.1           # FIX: Minimum index value to prevent division issues

# Thresholds for including players in team aggregations
MIN_RC_SCORE = 0.5              # Minimum RC to be considered a viable batter
MIN_PITCHING_SCORE = 0.5        # Minimum pitching score to be considered viable


def simulate_games(simulations_per_game=1000):
    """
    Executes a Monte Carlo simulation of the season schedule using Negative Binomial distribution.

    Context:
        This is the "crystal ball" of the projection system. We simulate every scheduled 
        game 1,000 times to generate probability distributions for wins, losses, and 
        expected scores. This moves beyond deterministic "Team A is better than Team B" 
        to probabilistic "Team A wins 65% of the time, but has a 10% chance of being upset."
        The output helps set realistic expectations for floor and ceiling outcomes.

        We use the Negative Binomial distribution rather than Poisson because baseball 
        scoring exhibits "over-dispersion"—runs come in bunches during big innings rather 
        than arriving independently. Empirical analysis of this dataset shows a 
        variance/mean ratio of ~13.4 at the season level, far exceeding the Poisson 
        assumption of Var=Mean. The Negative Binomial's extra dispersion parameter allows 
        us to model this clumpiness. See Lindsey (1963) "An Investigation of Strategies 
        in Baseball" for foundational work on baseball scoring distributions.

        The square root dampening on indices derives from Pythagorean Expectation principles 
        (Bill James, 1980). While Pythagorean uses exponent ~1.83 for run-to-win conversion, 
        we apply sqrt (exponent 0.5) to the offensive/pitching indices to compress extreme 
        values and prevent unrealistic run projections (e.g., 24 runs vs. weak pitching).

        Technically, this is a batch simulation process:
        1. ETL: Aggregate player stats into team-level metrics (GROUP BY Team)
        2. Iterate: Loop through schedule (cursor-based, N is small)
        3. Vectorize: Within each game, use NumPy arrays for 1,000 parallel simulations

    Args:
        simulations_per_game (int): Number of Monte Carlo iterations per matchup. 
            Default 1,000 provides stable estimates; increase for tighter confidence intervals.

    Returns:
        None. Writes results to 'rocky_mountain_monte_carlo.csv'.
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
    
    # 2. Build Team Strength Metrics
    # Filter for replacement-level viability using score thresholds
    # SQL: WHERE RC_Score > 0.5
    df_batters = df_roster[df_roster['RC_Score'] > MIN_RC_SCORE]
    df_pitchers = df_roster[df_roster['Pitching_Score'] > MIN_PITCHING_SCORE]
    
    team_stats = pd.DataFrame(df_roster['Team'].unique(), columns=['Team'])
    
    # --- Offensive Aggregation ---
    # Sum top 9 batters (starting lineup) per team
    # SQL: SELECT Team, SUM(RC_Score) FROM (SELECT TOP 9 ... ORDER BY RC_Score DESC) GROUP BY Team
    offense_scores = []
    for team in team_stats['Team']:
        top_9 = df_batters[df_batters['Team'] == team].nlargest(9, 'RC_Score')
        offense_scores.append({'Team': team, 'Offense_Raw': top_9['RC_Score'].sum()})
    
    # --- Pitching Aggregation ---
    # Sum top 5 pitchers (rotation + closer) per team
    pitching_scores = []
    for team in team_stats['Team']:
        top_staff = df_pitchers[df_pitchers['Team'] == team].nlargest(5, 'Pitching_Score')
        pitching_scores.append({'Team': team, 'Pitching_Raw': top_staff['Pitching_Score'].sum()})
        
    # Join offense and pitching into team strength fact table
    df_strength = pd.merge(pd.DataFrame(offense_scores), pd.DataFrame(pitching_scores), on='Team')
    
    # Normalize to league average (1.0 = average)
    avg_off = df_strength['Offense_Raw'].mean() or 1
    avg_pit = df_strength['Pitching_Raw'].mean() or 1
    
    df_strength['Off_Index'] = df_strength['Offense_Raw'] / avg_off
    df_strength['Pit_Index'] = df_strength['Pitching_Raw'] / avg_pit
    
    # FIX: Apply floor to prevent division by zero or negative index issues
    # Some teams may have negative total Pitching_Score if all pitchers are bad
    df_strength['Off_Index'] = df_strength['Off_Index'].clip(lower=MIN_INDEX_FLOOR)
    df_strength['Pit_Index'] = df_strength['Pit_Index'].clip(lower=MIN_INDEX_FLOOR)
    
    # Convert to dictionary for O(1) lookups during simulation loop
    strength_map = df_strength.set_index('Team')[['Off_Index', 'Pit_Index']].to_dict('index')
    strength_map['Generic High School'] = {'Off_Index': 0.8, 'Pit_Index': 0.8}

    # Pre-compute Fuzzy Mapping for schedule team names
    # Handles data quality issues where schedule names don't exactly match roster names
    schedule_teams = set(df_schedule['Home'].unique()).union(set(df_schedule['Away'].unique()))
    team_resolver = {}
    
    db_teams = list(strength_map.keys())
    for tm in schedule_teams:
        if pd.isna(tm): 
            continue
        if tm in strength_map:
            team_resolver[tm] = tm
        else:
            match = 'Generic High School'
            clean_tm = tm.split('(')[0].strip()
            # Fuzzy match using substring (LIKE '%clean_tm%')
            for db_tm in db_teams:
                if clean_tm in db_tm:
                    match = db_tm
                    break
            team_resolver[tm] = match

    # 3. Simulation Loop
    results = []
    
    # Identify focal team for reporting
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

    def generate_neg_binomial(mean_val, n_sims, dispersion=DEFAULT_DISPERSION):
        """
        Generates random score outcomes based on a Negative Binomial distribution.

        Context:
            This is the stochastic engine. In baseball, runs don't arrive independently—
            a hit increases the probability of another run in the same inning. This 
            "clumpiness" requires a distribution with fatter tails than Poisson. The 
            Negative Binomial allows us to model both the expected runs (mean) and the 
            variance inflation (dispersion).

            Derived from the standard Negative Binomial parameterization where:
            - Variance = Mean × Dispersion
            - We solve for n (failures) and p (success probability) required by NumPy:
              p = Mean / Variance
              n = Mean² / (Variance - Mean)

        Args:
            mean_val (float): Expected runs (lambda) for this team in this game.
            n_sims (int): Number of simulations to generate.
            dispersion (float): Variance inflation factor. Default 1.3 based on 
                empirical baseball scoring patterns.

        Returns:
            np.ndarray: Array of n_sims integer score outcomes.
        """
        if mean_val <= 0: 
            return np.zeros(n_sims)
        
        # FIX: Enforce minimum dispersion to prevent division by zero
        dispersion = max(dispersion, 1.01)
        
        variance = mean_val * dispersion
        p = mean_val / variance
        n = (mean_val ** 2) / (variance - mean_val)
        
        return np.random.negative_binomial(n, p, n_sims)

    # Iterate through schedule
    for idx, game in df_schedule.iterrows():
        home, away = game.get('Home', ''), game.get('Away', '')
        opponent = away if my_team_name in home else home
        if not opponent: 
            opponent = game.get('Opponent', 'Unknown')
        
        location = 'Home' if my_team_name in home else 'Away'
        date = game.get('Date', f"G{idx+1}")

        db_opponent_name = team_resolver.get(opponent, 'Generic High School')
        opp_stats = strength_map.get(db_opponent_name, strength_map['Generic High School'])

        # --- Calculate Expected Run Rates (Lambda) ---
        # Apply sqrt dampening to compress extreme values
        # Formula: λ = Base × √(Off_Index) × (1/√(Pit_Index))
        my_off_factor = np.sqrt(my_stats['Off_Index'])
        # FIX: opp_stats guaranteed to have Pit_Index >= MIN_INDEX_FLOOR due to clip above
        opp_pit_factor = 1.0 / np.sqrt(opp_stats['Pit_Index'])
        
        opp_off_factor = np.sqrt(opp_stats['Off_Index'])
        my_pit_factor = 1.0 / np.sqrt(my_stats['Pit_Index'])
        
        my_lambda = LEAGUE_BASE_RUNS * my_off_factor * opp_pit_factor
        opp_lambda = LEAGUE_BASE_RUNS * opp_off_factor * my_pit_factor
        
        # Apply Home Field Advantage
        if location == 'Home': 
            my_lambda *= HOME_FIELD_ADVANTAGE
        else: 
            opp_lambda *= HOME_FIELD_ADVANTAGE
            
        # --- Monte Carlo Execution ---
        my_scores = generate_neg_binomial(my_lambda, simulations_per_game)
        opp_scores = generate_neg_binomial(opp_lambda, simulations_per_game)
        
        # Vectorized win determination
        wins = np.where(my_scores > opp_scores, 1, 0)
        ties = np.where(my_scores == opp_scores, 1, 0)
        
        # Handle ties with coin flip (baseball has no ties in regulation)
        tie_breakers = np.random.binomial(1, 0.5, simulations_per_game) * ties
        wins = wins + tie_breakers
        
        sim_matrix[idx] = wins
        
        # Aggregate results
        win_pct = wins.mean()
        avg_my_score = my_scores.mean()
        avg_opp_score = opp_scores.mean()
        
        # Determine confidence label
        if win_pct > 0.90: conf = "Lock (W)"
        elif win_pct > 0.65: conf = "Solid (W)"
        elif win_pct < 0.10: conf = "Lock (L)"
        elif win_pct < 0.35: conf = "Solid (L)"
        else: conf = "Toss-up"
        
        # Generate analysis narrative
        reasons = []
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
        
        if not reasons: 
            analysis = "Even Matchup"
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

    # Season Summary
    season_win_totals = sim_matrix.sum(axis=0)
    
    avg_wins = season_win_totals.mean()
    p90_wins = np.percentile(season_win_totals, 90)
    p10_wins = np.percentile(season_win_totals, 10)
    
    print("-" * 120)
    print(f"\nSEASON PROJECTION ({simulations_per_game} Sims):")
    print(f"Average Record: {avg_wins:.1f} - {total_games - avg_wins:.1f}")
    print(f"Ceiling (90th %): {int(p90_wins)} Wins")
    print(f"Floor (10th %):   {int(p10_wins)} Wins")
    
    # Save results
    df_results = pd.DataFrame(results)
    output_dir = PATHS['out_team_strength']
    os.makedirs(output_dir, exist_ok=True)
    save_path = os.path.join(output_dir, 'rocky_mountain_monte_carlo.csv')
    df_results.to_csv(save_path, index=False)
    print(f"\nDetailed data saved to: {save_path}")


if __name__ == "__main__":
    simulate_games()
