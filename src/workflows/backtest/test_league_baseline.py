import pandas as pd
import os
import sys

# [REMOVED] from src.utils.config import PATHS  <-- This caused the error

# --- Configuration ---
# Just use the filename string. The script below will hunt for it.
STATS_FILE = 'aggregated_stats.csv'

def convert_ip_to_decimal(val):
    """
    Converts baseball innings (e.g., 3.1 = 3 and 1/3) to math decimals (3.33).
    """
    if pd.isna(val): return 0.0
    val_str = str(val)
    if '.' not in val_str: return float(val)
    
    try:
        base = float(int(float(val)))
        decimal = float(val) - base
        # .1 -> .333 (1 out)
        if 0.09 < decimal < 0.11: return base + 0.3333
        # .2 -> .666 (2 outs)
        if 0.19 < decimal < 0.21: return base + 0.6666
        return float(val)
    except ValueError:
        return 0.0

def main():
    # 1. Locate File
    # The script checks standard locations relative to where you run it
    possible_paths = [
        os.path.join('data', 'output', 'historical_stats', STATS_FILE),
        os.path.join('data', 'processed', STATS_FILE),
        STATS_FILE # Check current directory last
    ]
    
    input_path = None
    for p in possible_paths:
        if os.path.exists(p):
            input_path = p
            break
            
    if not input_path:
        print(f"ERROR: Could not find {STATS_FILE} in standard locations.")
        print(f"Checked: {possible_paths}")
        return

    print(f"Loading stats from: {input_path}")
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df)} player-season records.")

    # 2. Check for Required Columns
    if 'R' not in df.columns or 'IP' not in df.columns:
        print("ERROR: Dataset missing 'R' (Runs) or 'IP' (Innings Pitched) columns.")
        return

    # 3. Process Data
    # Convert IP to numeric first (coercing errors), then apply baseball conversion
    df['IP_Raw'] = pd.to_numeric(df['IP'], errors='coerce').fillna(0)
    df['IP_Math'] = df['IP_Raw'].apply(convert_ip_to_decimal)
    
    df['R'] = pd.to_numeric(df['R'], errors='coerce').fillna(0)

    # 4. Calculate Totals
    total_runs = df['R'].sum()
    total_math_ip = df['IP_Math'].sum()
    
    # 5. Compute Baseline
    if total_math_ip == 0:
        print("ERROR: Total IP is zero. Cannot divide.")
        return

    runs_per_inning = total_runs / total_math_ip
    runs_per_game = runs_per_inning * 7.0 # High School games are 7 innings

    # 6. Report
    print("\n" + "="*40)
    print("LEAGUE RUN ENVIRONMENT DIAGNOSTIC")
    print("="*40)
    print(f"Total Runs Scored:    {int(total_runs):,}")
    print(f"Total Innings (Math): {total_math_ip:,.1f}")
    print(f"Raw Runs/Inning:      {runs_per_inning:.3f}")
    print("-" * 40)
    print(f"CALCULATED BASELINE (R/7):  {runs_per_game:.2f}")
    print(f"CURRENT HARDCODED VALUE:    6.00")
    print("-" * 40)
    
    diff = runs_per_game - 6.0
    if abs(diff) > 0.5:
        print(f"ACTION: Significant deviation ({diff:+.2f}). Recommendation: UPDATE.")
    else:
        print(f"ACTION: Minimal deviation ({diff:+.2f}). 6.0 is likely fine.")

if __name__ == "__main__":
    main()