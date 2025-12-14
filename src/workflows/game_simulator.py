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
    Executes a Monte Carlo simulation of the entire season schedule to project win totals and game outcomes.

    Context:
        Baseball Context:
            This is the "Season Simulator." Knowing we have the best roster on paper is one thing; 
            playing 162 games (or 23 in High School) is another. This script takes the Rocky Mountain 
            schedule and "plays" every single game 1,000 times in the computer's memory. 
            It accounts for the randomness of baseball—the fact that an Ace pitcher can have a bad day, 
            or a weak lineup can string together three bloop singles. By simulating the season 
            thousands of times, we don't just predict *if* we will win; we calculate the *probability* of winning (e.g., "We win this game 82% of the time").

        Statistical Validity:
            1.  **Simulation Method (Monte Carlo):** We rely on the Law of Large Numbers. A single 
                simulation is noise; 1,000 simulations approximate the true distribution of outcomes. 
                This allows us to construct Confidence Intervals (Ceiling vs. Floor) rather than 
                single-point estimates.
            2.  **Scoring Model (Poisson Distribution):** Runs in baseball are discrete, rare events 
                that occur independently in a fixed time/opportunity window. We model scoring using 
                the Poisson distribution: $P(k; \lambda) = \frac{\lambda^k e^{-\lambda}}{k!}$, 
                where $\lambda$ is the expected runs calculated from the matchup.
            3.  **Dampening Function (Square Root):** To prevent runaway predictions (e.g., predicting 
                40 runs because one team is 3x better than average), we dampen the power indices using 
                a square root function ($\sqrt{Index}$). This reflects the concept of **Diminishing Marginal Returns** in talent disparity—having a lineup twice as good doesn't literally double your scoring 
                output in every context.

        Technical Implementation:
            This script functions as a stochastic forecasting engine.
            1.  **Data Ingestion:** Loads the Roster (Dimension Table) and Schedule (Fact Table).
            2.  **Aggregation:** Computes team-level metrics by performing a `GROUP BY Team` and summing 
                the contributions of the "Starting 9" (Batters) and "Rotation" (Pitchers).
            3.  **Lookup Creation:** Materializes a Key-Value store (`strength_map`) for O(1) retrieval 
                of opponent stats during iteration.
            4.  **Vectorized Simulation:** Uses NumPy to generate 1,000 random outcomes per game 
                simultaneously (Batch Processing), rather than looping 1,000 times per game.

    Args:
        simulations_per_game (int): The number of times to simulate each matchup (N). Default is 1000.

    Returns:
        None. Saves detailed simulation results to CSV and prints a summary to stdout.
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
    
    # 2. Build Metrics (Same as before)
    # Filter to specific roles (WHERE clause)
    df_batters = df_roster[df_roster['Is_Batter'] == True]
    df_pitchers = df_roster[df_roster['Is_Pitcher'] == True]
    
    # Get distinct list of teams (SELECT DISTINCT Team)
    team_stats = pd.DataFrame(df_roster['Team'].unique(), columns=['Team'])
    
    # --- Aggregation Logic ---
    # We aggregate based on the "Starters" only, filtering out depth pieces that won't impact a single game outcome.
    offense_scores = []
    for team in team_stats['Team']:
        # SELECT SUM(RC_Score) FROM batters WHERE Team = X ORDER BY RC_Score DESC LIMIT 9
        top_9 = df_batters[df_batters['Team'] == team].nlargest(9, 'RC_Score')
        offense_scores.append({'Team': team, 'Offense_Raw': top_9['RC_Score'].sum()})
    
    pitching_scores = []
    for team in team_stats['Team']:
        # SELECT SUM(Pitching_Score) FROM pitchers WHERE Team = X ORDER BY Pitching_Score DESC LIMIT 5
        top_staff = df_pitchers[df_pitchers['Team'] == team].nlargest(5, 'Pitching_Score')
        pitching_scores.append({'Team': team, 'Pitching_Raw': top_staff['Pitching_Score'].sum()})
        
    # Join Offense and Pitching tables
    df_strength = pd.merge(pd.DataFrame(offense_scores), pd.DataFrame(pitching_scores), on='Team')
    
    # Normalize to League Average (1.0 = Average)
    # This creates a standardized index for comparison
    avg_off = df_strength['Offense_Raw'].mean() or 1
    avg_pit = df_strength['Pitching_Raw'].mean() or 1
    
    df_strength['Off_Index'] = df_strength['Offense_Raw'] / avg_off
    df_strength['Pit_Index'] = df_strength['Pitching_Raw'] / avg_pit
    
    # Materialize the Lookup Table (Hash Map) for O(1) access inside the loop
    strength_map = df_strength.set_index('Team')[['Off_Index', 'Pit_Index']].to_dict('index')
    strength_map['Generic High School'] = {'Off_Index': 0.8, 'Pit_Index': 0.8}

    # 3. Simulation Loop
    results = []
    season_outcomes = [] # To track distribution of total wins (e.g. how often do they win 20?)
    
    # Identify Protagonist (The context for "Home" vs "Away")
    my_team_name = "Rocky Mountain (Fort Collins, CO)"
    if my_team_name not in strength_map:
        # Quick fuzzy match fallback
        for t in strength_map:
            if "Rocky Mountain" in t:
                my_team_name = t
                break
    
    # Get stats for the protagonist from our lookup table
    my_stats = strength_map.get(my_team_name, strength_map['Generic High School'])
    
    print(f"\n{'Date':<12} {'Opponent':<30} {'Win %':<8} {'Avg Score':<12} {'Confidence':<15} {'Analysis'}")
    print("-" * 120)

    # Matrix: [Games, Simulations]
    # We pre-allocate a numpy array to store the binary result (Win/Loss) of every sim for every game
    total_games = len(df_schedule)
    sim_matrix = np.zeros((total_games, simulations_per_game))

    # Iterate through the Schedule (The Cursor)
    for idx, game in df_schedule.iterrows():
        # Determine Opponent
        home, away = game.get('Home', ''), game.get('Away', '')
        opponent = away if my_team_name in home else home
        if not opponent: opponent = game.get('Opponent', 'Unknown')
        
        location = 'Home' if my_team_name in home else 'Away'
        date = game.get('Date', f"G{idx+1}")

        # Lookup Opponent Strength
        opp_stats = strength_map.get(opponent)
        if not opp_stats:
            # Fuzzy match inside loop (Data Cleaning on the fly)
            found = False
            for db_team in strength_map:
                if opponent.split('(')[0].strip() in db_team:
                    opp_stats = strength_map[db_team]
                    opponent = db_team
                    found = True
                    break
            if not found: opp_stats = strength_map['Generic High School']

        # --- CALCULATE EXPECTED RUN RATES (Lambda) ---
        LEAGUE_BASE = 6.0
        
        # Apply Dampening (Square Root) to prevent runaway scores
        # Logic: SQRT(Index) compresses outliers towards 1.0
        my_off_factor = np.sqrt(my_stats['Off_Index'])
        opp_pit_factor = 1.0 / np.sqrt(opp_stats['Pit_Index']) if opp_stats['Pit_Index'] > 0 else 1.0
        
        opp_off_factor = np.sqrt(opp_stats['Off_Index'])
        my_pit_factor = 1.0 / np.sqrt(my_stats['Pit_Index']) if my_stats['Pit_Index'] > 0 else 1.0
        
        # Lambda Calculation: Base * Offense * (1/Pitching)
        my_lambda = LEAGUE_BASE * my_off_factor * opp_pit_factor
        opp_lambda = LEAGUE_BASE * opp_off_factor * my_pit_factor
        
        if location == 'Home': my_lambda *= 1.1
        else: opp_lambda *= 1.1
            
        # --- MONTE CARLO EXECUTION ---
        # Simulate this specific game N times using Vectorized Operations
        # This is equivalent to running 1,000 INSERT statements in a batch
        my_scores = np.random.poisson(my_lambda, simulations_per_game)
        opp_scores = np.random.poisson(opp_lambda, simulations_per_game)
        
        # Determine wins (1 for win, 0 for loss)
        # Handle ties randomly for split outcomes
        wins = np.where(my_scores > opp_scores, 1, 0)
        ties = np.where(my_scores == opp_scores, 1, 0)
        # Randomly assign ties (coin flip vectorized)
        tie_breakers = np.random.binomial(1, 0.5, simulations_per_game) * ties
        wins = wins + tie_breakers
        
        # Store for season aggregation
        sim_matrix[idx] = wins
        
        # Aggregate Game Stats (Reduce/Fold)
        win_pct = wins.mean()
        avg_my_score = my_scores.mean()
        avg_opp_score = opp_scores.mean()
        
        # Confidence Label Logic (Bucketing)
        if win_pct > 0.90: conf = "Lock (W)"
        elif win_pct > 0.65: conf = "Solid (W)"
        elif win_pct < 0.10: conf = "Lock (L)"
        elif win_pct < 0.35: conf = "Solid (L)"
        else: conf = "Toss-up"
        
        # --- EXPLANATION GENERATOR ---
        # Generates a natural language explanation of the key factors driving the prediction
        reasons = []
        
        # 1. Compare Offenses
        off_diff = my_stats['Off_Index'] - opp_stats['Off_Index']
        if off_diff > 0.3: reasons.append("Elite Offense")
        elif off_diff > 0.1: reasons.append("Better Bats")
        elif off_diff < -0.3: reasons.append("Overmatched Offense")
        elif off_diff < -0.1: reasons.append("Weaker Bats")
        
        # 2. Compare Pitching
        pit_diff = my_stats['Pit_Index'] - opp_stats['Pit_Index']
        if pit_diff > 0.3: reasons.append("Dominant Pitching")
        elif pit_diff > 0.1: reasons.append("Better Arms")
        elif pit_diff < -0.3: reasons.append("Weak Pitching")
        elif pit_diff < -0.1: reasons.append("Less Depth")
        
        # 3. Location
        if location == 'Home': reasons.append("Home Field")
        
        # Construct string
        if not reasons:
            analysis = "Even Matchup"
        else:
            # If we are projected to lose, frame the reasons from opponent perspective
            if win_pct < 0.5:
                analysis = f"Opponent advantage: {', '.join(reasons).replace('Elite Offense', 'Their Offense').replace('Dominant Pitching', 'Their Pitching')}"
            else:
                analysis = f"Edge: {', '.join(reasons)}"
                
        # Truncate for display
        display_analysis = (analysis[:35] + '..') if len(analysis) > 35 else analysis
        
        print(f"{date:<12} {opponent[:28]:<30} {win_pct*100:.1f}%    {avg_my_score:.1f}-{avg_opp_score:.1f}       {conf:<15} {display_analysis}")
        
        results.append({
            'Date': date,
            'Opponent': opponent,
            'Win_Pct': win_pct,
            'Proj_Score': f"{avg_my_score:.1f}-{avg_opp_score:.1f}",
            'Confidence': conf,
            'Analysis': analysis, # Full string for CSV
            'My_Off_Idx': round(my_stats['Off_Index'], 2),
            'My_Pit_Idx': round(my_stats['Pit_Index'], 2),
            'Opp_Off_Idx': round(opp_stats['Off_Index'], 2),
            'Opp_Pit_Idx': round(opp_stats['Pit_Index'], 2)
        })

    # --- SEASON LEVEL ANALYSIS ---
    # Sum wins across columns (simulations) to get N potential season win totals
    # Essentially calculating a histogram of possible season outcomes
    season_win_totals = sim_matrix.sum(axis=0) # Array of 1000 season win totals
    
    avg_wins = season_win_totals.mean()
    p90_wins = np.percentile(season_win_totals, 90) # Optimistic (90th Percentile)
    p10_wins = np.percentile(season_win_totals, 10) # Pessimistic (10th Percentile)
    
    print("-" * 120)
    print(f"\nSEASON PROJECTION ({simulations_per_game} Sims):")
    print(f"Average Record: {avg_wins:.1f} - {total_games - avg_wins:.1f}")
    print(f"Ceiling (90th %): {int(p90_wins)} Wins")
    print(f"Floor (10th %):   {int(p10_wins)} Wins")
    
    # Save
    df_results = pd.DataFrame(results)
    output_dir = PATHS['out_team_strength']
    save_path = os.path.join(output_dir, 'rocky_mountain_monte_carlo.csv')
    df_results.to_csv(save_path, index=False)
    print(f"\nDetailed data saved to: {save_path}")

if __name__ == "__main__":
    simulate_games()