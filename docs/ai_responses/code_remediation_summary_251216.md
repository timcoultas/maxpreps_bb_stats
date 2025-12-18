---
layout: default
title: Comprehensive Remediation Plan (Dec 16) # (Customize the title for each file)
parent: AI Critiques & Reports
---
Comprehensive Remediation Plan: CO High School Baseball Projection System

Date: December 16, 2025
Based On: Adversarial Reviews (Claude & Gemini)
Target Version: 1.1

1. Executive Summary

This plan outlines the specific code changes required to fix critical bugs and improve the statistical robustness of the projection system. The most urgent fixes address "invisible" mathematical errors where baseball notation (e.g., 10.1 innings) is being treated as a literal decimal, and where NaN values are silently zeroing out valid player stats.

Implementation Priority:

Critical Fixes: Stop generating incorrect numbers immediately.

Statistical Hardening: Reduce bias and volatility in projections.

Output Hygiene: Ensure exported data uses correct baseball formatting.

Phase 1: Critical Fixes (Mathematical & Data Integrity)

1.1. Fix "Decimal IP" Calculation Error

Severity: Critical
Problem: The system treats 10.1 IP as 10.1 (decimal). In baseball, .1 represents 1/3 of an inning. This causes ~2.3% error in all rate stats (ERA, K/9, etc.).
Files: src/utils/utils.py, src/models/advanced_ranking.py

Action 1: Add Helper to src/utils/utils.py
Add this function to handle the conversion strictly.

def convert_ip_to_decimal(ip_series):
    """
    Converts baseball IP notation (10.1 = 10 and 1/3) to proper decimal (10.333).
    
    Args:
        ip_series (pd.Series or float): IP values in format X.0, X.1, X.2
    
    Returns:
        pd.Series or float: IP values in proper decimal format
    """
    # If scalar, wrap in series
    is_scalar = False
    if isinstance(ip_series, (float, int)):
        ip_series = pd.Series([ip_series])
        is_scalar = True

    # FIX: Handle NaN or infinite values by filling with 0
    # This prevents the 'IntCastingNaNError' when converting to integer
    ip_series = ip_series.fillna(0).replace([np.inf, -np.inf], 0)

    # Split into integer and decimal parts
    # 10.1 -> 10 + 0.1
    innings = ip_series.astype(int)
    outs = (ip_series - innings).round(1) * 10 # 0.1 -> 1.0, 0.2 -> 2.0
    
    # Map .1 to .333 and .2 to .666
    # We use a tolerant mapping just in case of float artifacts
    decimal_outs = outs.apply(lambda x: 0.3333 if 0.8 <= x <= 1.2 else (0.6667 if 1.8 <= x <= 2.2 else 0.0))
    
    result = innings + decimal_outs
    
    if is_scalar:
        return result.iloc[0]
    return result


Action 2: Update Calculations in src/models/advanced_ranking.py
Modify calculate_pitching_score to use the converted IP AND enforce role-based scoring.

# src/models/advanced_ranking.py

# Import the new utility
from src.utils.utils import convert_ip_to_decimal

def calculate_pitching_score(df):
    df = df.copy()
    
    # [FIX] Schema validation - handle pitching specific columns
    # The projection file uses 'K' for batting strikeouts, but pitching K is 'K_P'
    req_cols = ['IP', 'K_P', 'BB_P', 'ER']
    for col in req_cols:
        if col not in df.columns:
            print(f"[Warning] Column '{col}' missing from dataframe. Imputing 0.")
            df[col] = 0

    # [FIX] Fill NaNs with 0 to prevent propagation (Same pattern as Offense)
    # Ensures a player with IP/K but missing BB doesn't get zeroed out
    cols_to_fix = ['IP', 'K_P', 'BB_P', 'ER']
    for c in cols_to_fix:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    # [NEW] Convert IP to true decimal for math
    # Note: We keep raw 'IP' for display, but use 'IP_Math' for calculation
    df['IP_Math'] = convert_ip_to_decimal(df['IP'])

    # Weighted sum aggregation using correct IP and PITCHING columns
    score = (df['IP_Math'] * 1.5) + \
            (df['K_P'] * 1.0) - \
            (df['BB_P'] * 1.0) - \
            (df['ER'] * 2.0)
            
    # [FIX] Role Masking: Force score to 0 if not a Pitcher
    # This prevents position players (who have 0 ER/BB) from getting 'neutral' scores that distort team averages
    if 'Is_Pitcher' in df.columns:
        score = np.where(df['Is_Pitcher'], score, 0.0)
        # Convert back to Series because np.where returns an array
        score = pd.Series(score, index=df.index)

    return score.fillna(0)


1.2. Prevent NaN Propagation in RC Formula

Severity: Critical
Problem: If a player has Hits but NaN for Doubles/Triples, Total Bases becomes NaN, resulting in RC = 0.
File: src/models/advanced_ranking.py

Action: Explicitly fill NaNs with 0 before vector arithmetic AND enforce role-based scoring.

# src/models/advanced_ranking.py - calculate_offensive_score()

    # ... inside calculate_offensive_score ...
    
    # [FIX] Fill NaNs with 0 to prevent propagation
    cols_to_fix = ['2B', '3B', 'HR', 'HBP', 'SF'] 
    for c in cols_to_fix:
        if c in df.columns:
            df[c] = df[c].fillna(0)

    # Calculate Total Bases (TB)
    singles = df['H'] - (df['2B'] + df['3B'] + df['HR'])
    # ... continue with formula ...
    
    # [FIX] Role Masking: Force score to 0 if not a Batter
    if 'Is_Batter' in df.columns:
        rc = np.where(df['Is_Batter'], rc, 0.0)
        rc = pd.Series(rc, index=df.index)
        
    return rc.fillna(0)


1.3. Fix Generic Profile Role Contamination

Severity: High
Problem: "Generic Batters" have pitching stats (IP, ERA) because the source sophomores were two-way players. This pollutes team pitching aggregations.
File: src/workflows/profile_generator.py

Action: Mask irrelevant columns based on role in generate_tiers().

# src/workflows/profile_generator.py - generate_tiers()

    # ... inside generate_tiers loop ...
            if not bucket.empty:
                profile = {
                    # ... existing profile setup ...
                }
                
                # Calculate Median stats
                for col in stat_cols:
                    profile[col] = round(bucket[col].median(), 2)
                
                # [FIX] Mask irrelevant stats to prevent role contamination
                # This ensures the generic_players.csv file is clean and human-readable
                if role == 'Batter':
                    # Clear ALL pitching columns
                    for p_col in ['IP', 'ERA', 'K_P', 'ER', 'BB_P', 'H_P', 'BF', 'APP']:
                        profile[p_col] = 0.0
                elif role == 'Pitcher':
                    # Clear ALL batting columns
                    for b_col in ['H', 'AB', 'HR', 'RBI', 'AVG', 'OBP', 'SLG', 'K', 'BB']:
                        profile[b_col] = 0.0

                # ... existing minimums enforcement ...


Phase 2: Statistical Hardening

2.1. Mitigate Survivor Bias (Churn Penalty)

Severity: Medium
Problem: Historical multipliers are based only on players who didn't quit. This inflates expectations for the 2026 roster (which includes future quitters).
File: src/workflows/roster_prediction.py

Action: Apply a global regression factor (0.95) to all projections.

# src/workflows/roster_prediction.py

# Add Constant at top
SURVIVOR_BIAS_ADJUSTMENT = 0.95 

# Inside predict_2026_roster loop
        # Apply Multipliers
        if method != "Default (1.0)":
            for col in stat_cols:
                if col in applied_factors and pd.notna(player[col]):
                    multiplier = applied_factors[col]
                    
                    # [FIX] Apply Churn Penalty
                    final_val = player[col] * multiplier * SURVIVOR_BIAS_ADJUSTMENT
                    proj[col] = round(final_val, 2)


2.2. Raise Replacement Level Thresholds

Severity: Medium
Problem: 10th percentile "Generic Players" are based on kids with 12 PA, creating non-viable replacement profiles.
File: src/workflows/profile_generator.py

Action: Increase thresholds to ensure generics represent "bad regulars," not "cameos."

# src/workflows/profile_generator.py

# [FIX] Increase thresholds
MIN_PA_FOR_BATTER_PROFILE = 25  # Was 10
MIN_IP_FOR_PITCHER_PROFILE = 10 # Was 3


2.3. Smooth Rare Event Multipliers

Severity: Medium
Problem: Rare stats (Triples, HRs) show wild volatility (0.5x, 0.0x) due to small denominators.
File: src/workflows/development_multipliers.py

Action: Implement Laplacian Smoothing (Add 1) for rate-based calculations.

# src/workflows/development_multipliers.py

            # ... inside the loop calculating ratios ...
            
            # [FIX] Use Laplacian Smoothing for rare events to dampen noise
            # Instead of: ratios = subset[next] / subset[prev]
            if col in ['3B', 'HR', '3B_P', 'HR_P']:
                # Add 1 to numerator and denominator to pull towards 1.0
                ratios = (subset[f'{col}_Next'] + 1) / (subset[f'{col}_Prev'] + 1)
            else:
                ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']


Phase 3: Output Hygiene

3.1. Standardize IP Output Format

Severity: Low (Cosmetic)
Problem: Output CSVs show IP: 3.02 (math artifact).
File: src/workflows/roster_prediction.py

Action: Convert math-IP back to baseball-IP for the final CSV.

# src/workflows/roster_prediction.py

def format_ip_output(val):
    """Converts 3.333 -> 3.1"""
    if pd.isna(val): return 0.0
    innings = int(val)
    decimal = val - innings
    
    # Map decimal ranges back to .1 or .2
    if 0.25 < decimal < 0.5: return innings + 0.1
    if 0.5 < decimal < 0.8: return innings + 0.2
    return float(innings)

# At the very end of predict_2026_roster(), before saving:
    if 'IP' in df_proj.columns:
        df_proj['IP'] = df_proj['IP'].apply(format_ip_output)
        
    df_proj.to_csv(output_path, index=False)


4. Verification Checklist

After applying these changes, run the pipeline (python run_pipeline.py --period history --teams all) and verify:

Zero RC Check: Look at 2026_roster_prediction.csv for Denver North players (S. Vital, D. Sanudo). RC_Score should be > 0.

IP Sanity: Check 2026_roster_prediction.csv. IP column should only contain values ending in .0, .1, or .2.

Generic Purity: Filter the roster for "Generic Batter". Their ERA and IP columns should be exactly 0.