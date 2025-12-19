# backtest_config.py
"""
Backtest Configuration

This file contains settings for running the projection system in "backtest mode" —
using 2024 data to project 2025, then comparing against actual 2025 results.

Usage:
    Set BACKTEST_MODE = True to run projections for 2025 validation
    Set BACKTEST_MODE = False for normal 2026 projections
"""

# --- Backtest Toggle ---
BACKTEST_MODE = True  # Set to False for normal 2026 projections

# --- Year Configuration ---
if BACKTEST_MODE:
    BASE_YEAR = 2024           # Filter historical data up to this year
    PROJECTION_YEAR = 2025     # The year we're projecting INTO
    SCHEDULE_FILE = "rocky_mountain_schedule_2025.csv"
    OUTPUT_SUFFIX = "_backtest_2025"
else:
    BASE_YEAR = 2025           # Normal mode: use all data through 2025
    PROJECTION_YEAR = 2026     # Project into 2026
    SCHEDULE_FILE = "rocky_mountain_schedule.csv"
    OUTPUT_SUFFIX = ""

# --- Output File Names ---
ROSTER_OUTPUT = f"{PROJECTION_YEAR}_roster_prediction{OUTPUT_SUFFIX}.csv"
TEAM_STRENGTH_OUTPUT = f"team_strength_rankings{OUTPUT_SUFFIX}.csv"
SIMULATION_OUTPUT = f"rocky_mountain_monte_carlo{OUTPUT_SUFFIX}.csv"
ACTUALS_OUTPUT = f"{PROJECTION_YEAR}_actual_stats.csv"
COMPARISON_OUTPUT = f"{PROJECTION_YEAR}_projection_vs_actual.csv"