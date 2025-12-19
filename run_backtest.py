"""
run_backtest.py

Orchestrates a complete backtest of the projection system:
1. Generate 2025 projections using only 2024 data
2. Extract actual 2025 stats for comparison
3. Run game simulation against 2025 schedule
4. Compare projections to actuals

Usage:
    python run_backtest.py
    
Prerequisites:
    - aggregated_stats.csv must contain 2022-2025 data
    - rocky_mountain_schedule_2025.csv in data/input/
    - rocky_mountain_results_2025.csv in data/input/ (optional, for game comparison)
"""

import os
import sys
import subprocess

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.config import PATHS


def run_command(description: str, command: list):
    """Runs a command and prints status."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"{'='*60}")
    print(f"Running: {' '.join(command)}\n")
    
    result = subprocess.run(command, capture_output=False)
    
    if result.returncode != 0:
        print(f"ERROR: {description} failed with code {result.returncode}")
        return False
    return True


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           BACKTEST: 2025 PROJECTION VALIDATION                   ║
║                                                                  ║
║   Using 2024 data to project 2025, then comparing to actuals     ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Get the directory where this script lives
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # --- Step 1: Generate 2025 Projections from 2024 Data ---
    success = run_command(
        "Generate 2025 roster projections (from 2024 data)",
        [sys.executable, os.path.join(script_dir,'src','workflows', 'roster_prediction_backtest.py'),
         '--base-year', '2024',
         '--projection-year', '2025',
         '--output-suffix', '_backtest']
    )
    if not success:
        return
    
    # --- Step 2: Extract Actual 2025 Stats ---
    success = run_command(
        "Extract actual 2025 statistics",
        [sys.executable, os.path.join(script_dir, 'extract_actuals.py'),
         '--year', '2025']
    )
    if not success:
        return
    
    # --- Step 3: Compare Projections to Actuals ---
    backtest_dir = os.path.join(PATHS['out_roster_prediction'], 'backtest')
    projection_file = os.path.join(backtest_dir, '2025_roster_prediction_backtest.csv')
    actuals_file = os.path.join(backtest_dir, '2025_actual_stats.csv')
    
    # Check for game results file (optional)
    results_file = os.path.join(PATHS['input'], 'rocky_mountain_results_2025.csv')
    simulation_file = os.path.join(backtest_dir, 'rocky_mountain_monte_carlo_backtest.csv')
    
    compare_cmd = [
        sys.executable, os.path.join(script_dir, 'compare_projections.py'),
        '--projection-file', projection_file,
        '--actuals-file', actuals_file
    ]
    
    # Add game comparison if files exist
    if os.path.exists(results_file) and os.path.exists(simulation_file):
        compare_cmd.extend([
            '--simulation-file', simulation_file,
            '--results-file', results_file
        ])
    
    success = run_command(
        "Compare projections to actual results",
        compare_cmd
    )
    
    # --- Summary ---
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                    BACKTEST COMPLETE                             ║
╚══════════════════════════════════════════════════════════════════╝

Output files in: {backtest_dir}

  - 2025_roster_prediction_backtest.csv  (what we projected)
  - 2025_actual_stats.csv                (what actually happened)
  - player_projection_accuracy.csv       (player-level comparison)
  - team_ranking_accuracy.csv            (team-level comparison)

To add game-by-game comparison:
  1. Create rocky_mountain_schedule_2025.csv in data/input/
  2. Create rocky_mountain_results_2025.csv with columns: Date, Opponent, Result (W/L)
  3. Run the game simulator separately, then re-run this script
    """)


if __name__ == "__main__":
    main()