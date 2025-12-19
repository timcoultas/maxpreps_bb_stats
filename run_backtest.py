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

# Ensure we can import from src even if running from outside root
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from src.utils.config import PATHS
except ImportError:
    # Fallback if path setup failed, though the sys.path append above should catch it
    print("Warning: Could not import src.utils.config. Checking paths...")
    # Attempt to define PATHS manually for the script to function if import fails
    # This is a fallback to allow the script to at least print errors
    PATHS = {
        'out_roster_prediction': os.path.join(current_dir, 'data', 'output', 'roster_prediction'),
        'input': os.path.join(current_dir, 'data', 'input')
    }


def run_command(description: str, command: list, env: dict = None):
    """Runs a command and prints status."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"{'='*60}")
    print(f"Running: {' '.join(command)}\n")
    
    # Run with the modified environment (containing PYTHONPATH)
    result = subprocess.run(command, capture_output=False, env=env)
    
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
    
    # 1. Setup Paths
    # The script is likely at the project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # We need to set PYTHONPATH for subprocesses so they can resolve 'from src.utils...'
    # This creates a copy of the current environment and adds the project root to it
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

    # Define paths to the workflow scripts (UPDATED to src/workflows/backtest/)
    roster_script = os.path.join(project_root, 'src', 'workflows', 'backtest', 'roster_prediction_backtest.py')
    extract_script = os.path.join(project_root, 'src', 'workflows', 'backtest', 'extract_actuals.py')
    compare_script = os.path.join(project_root, 'src', 'workflows', 'backtest', 'compare_projections.py')

    # --- Step 1: Generate 2025 Projections from 2024 Data ---
    success = run_command(
        "Generate 2025 roster projections (from 2024 data)",
        [sys.executable, roster_script,
         '--base-year', '2024',
         '--projection-year', '2025',
         '--output-suffix', '_backtest'],
        env=env
    )
    if not success:
        return
    
    # --- Step 2: Extract Actual 2025 Stats ---
    success = run_command(
        "Extract actual 2025 statistics",
        [sys.executable, extract_script,
         '--year', '2025'],
        env=env
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
        sys.executable, compare_script,
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
        compare_cmd,
        env=env
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