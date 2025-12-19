"""
run_backtest.py

Orchestrates a complete backtest of the projection system for a specific year.
1. Generate projections for {target_year} using only {base_year} data
2. Extract actual {target_year} stats for comparison
3. Compare projections to actuals

Usage:
    python run_backtest.py --year 2025  (Default)
    python run_backtest.py --year 2024
    
Prerequisites:
    - aggregated_stats.csv must contain data for the relevant years
"""

import os
import sys
import subprocess
import argparse

# Ensure we can import from src even if running from outside root
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from src.utils.config import PATHS
except ImportError:
    # Fallback if path setup failed, though the sys.path append above should catch it
    print("Warning: Could not import src.utils.config. Checking paths...")
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
    parser = argparse.ArgumentParser(description="Run projection backtest for a specific year")
    parser.add_argument('--year', type=int, default=2025, 
                        help="The target projection year to test (default: 2025)")
    args = parser.parse_args()

    target_year = args.year
    base_year = target_year - 1

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║           BACKTEST: {target_year} PROJECTION VALIDATION                   ║
║                                                                  ║
║   Using {base_year} data to project {target_year}, then comparing to actuals     ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 1. Setup Paths
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Set PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

    # Define paths to the workflow scripts
    roster_script = os.path.join(project_root, 'src', 'workflows', 'backtest', 'roster_prediction_backtest.py')
    extract_script = os.path.join(project_root, 'src', 'workflows', 'backtest', 'extract_actuals.py')
    compare_script = os.path.join(project_root, 'src', 'workflows', 'backtest', 'compare_projections.py')

    # --- Step 1: Generate Projections ---
    success = run_command(
        f"Generate {target_year} roster projections (from {base_year} data)",
        [sys.executable, roster_script,
         '--base-year', str(base_year),
         '--projection-year', str(target_year),
         '--output-suffix', '_backtest'],
        env=env
    )
    if not success:
        return
    
    # --- Step 2: Extract Actual Stats ---
    success = run_command(
        f"Extract actual {target_year} statistics",
        [sys.executable, extract_script,
         '--year', str(target_year)],
        env=env
    )
    if not success:
        return
    
    # --- Step 3: Compare Projections to Actuals ---
    backtest_dir = os.path.join(PATHS['out_roster_prediction'], 'backtest')
    projection_file = os.path.join(backtest_dir, f'{target_year}_roster_prediction_backtest.csv')
    actuals_file = os.path.join(backtest_dir, f'{target_year}_actual_stats.csv')
    
    # Check for game results file (optional)
    results_file = os.path.join(PATHS['input'], f'rocky_mountain_results_{target_year}.csv')
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

  - {target_year}_roster_prediction_backtest.csv  (Projected)
  - {target_year}_actual_stats.csv                (Actual)
  - player_projection_accuracy.csv       (Comparison)
  - team_ranking_accuracy.csv            (Comparison)
    """)


if __name__ == "__main__":
    main()