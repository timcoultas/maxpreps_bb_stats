import pandas as pd
import numpy as np
import os
import sys

# --- Import Config & Utils ---
try:
    from src.utils.config import STAT_SCHEMA, PATHS
    from src.utils.utils import prepare_analysis_data
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []
except ImportError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from src.utils.config import STAT_SCHEMA, PATHS
    from src.utils.utils import prepare_analysis_data
    try:
        from src.utils.config import ELITE_TEAMS
    except ImportError:
        ELITE_TEAMS = []


def generate_stat_multipliers():
    """
    Calculates Year-Over-Year (YoY) performance ratios segmented by program tier.
    
    Context:
        Baseball Context:
            Not all programs develop players equally. Elite programs - those consistently 
            winning regional and state championships - invest in year-round development: 
            offseason lifting, winter practices, summer ball with the same coaches. This 
            creates measurably different development curves than standard programs where 
            players disperse to various club teams in the offseason.
            
        Statistical Validity:
            Analysis of year-over-year player transitions shows statistically significant 
            differences between elite and standard program development rates, particularly 
            for Junior→Senior pitching. The specific values are calculated dynamically 
            based on the current ELITE_TEAMS configuration.
            
        Technical Implementation:
            This script produces THREE output files:
            1. development_multipliers.csv - Pooled multipliers (backward compatible)
            2. elite_development_multipliers.csv - Elite program multipliers
            3. standard_development_multipliers.csv - Standard program multipliers
            
            The roster_prediction.py script uses the appropriate multiplier file based 
            on whether a player's team is in ELITE_TEAMS.
    
    References:
        - Analysis conducted on Colorado 5A historical data
        - Elite programs defined in config.py ELITE_TEAMS list
        - Sample sizes reported dynamically in output
    """
    
    # --- Load Data ---
    input_file = os.path.join(PATHS['out_historical_stats'], 'aggregated_stats.csv')
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return
        
    print(f"Loading data from {input_file}...")
    df = pd.read_csv(input_file)

    # --- 1. Dynamic Column Handling ---
    available_stats = set(df.columns)
    stat_cols = []
    stat_types = {} 

    for stat_def in STAT_SCHEMA:
        abbr = stat_def['abbreviation']
        if abbr in available_stats:
            stat_cols.append(abbr)
            stat_types[abbr] = stat_def['stat_type']

    for col in stat_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # --- 2. Prep ---
    df = prepare_analysis_data(df)
    
    # --- 3. Tag Elite vs Standard ---
    df['Is_Elite'] = df['Team'].isin(ELITE_TEAMS)
    elite_count = df['Is_Elite'].sum()
    total_count = len(df)
    
    print(f"\n{'='*80}")
    print("ELITE TEAMS CONFIGURATION")
    print(f"{'='*80}")
    print(f"Number of elite teams defined: {len(ELITE_TEAMS)}")
    for team in ELITE_TEAMS:
        team_records = len(df[df['Team'] == team])
        print(f"  - {team} ({team_records} player-seasons)")
    print(f"\nTagged {elite_count} records as Elite ({elite_count/total_count*100:.1f}%)")
    print(f"Elite teams found in dataset: {df[df['Is_Elite']]['Team'].nunique()}")
    
    # --- 4. Join Logic ---
    df_prev = df.copy()
    df_prev['Join_Year'] = df_prev['Season_Year'] + 1 
    
    merged = pd.merge(
        df_prev, 
        df, 
        left_on=['Match_Name', 'Match_Team', 'Join_Year'], 
        right_on=['Match_Name', 'Match_Team', 'Season_Year'],
        suffixes=('_Prev', '_Next')
    )
    
    total_transitions = len(merged)
    elite_transitions = int(merged['Is_Elite_Prev'].sum())
    standard_transitions = total_transitions - elite_transitions
    
    print(f"\nFound {total_transitions} year-over-year player transitions.")
    print(f"  - Elite program transitions: {elite_transitions}")
    print(f"  - Standard program transitions: {standard_transitions}")

    # --- 5. Define Transitions ---
    transitions = [
        # Biological (Class-based)
        ('Class', 'Freshman', 'Sophomore'),
        ('Class', 'Sophomore', 'Junior'),
        ('Class', 'Junior', 'Senior'),
        # Experience (Tenure-based)
        ('Tenure', 1, 2),
        ('Tenure', 2, 3),
        ('Tenure', 3, 4),
        # Specific (Class + Tenure)
        ('Class_Tenure', ('Freshman', 1), ('Sophomore', 2)), 
        ('Class_Tenure', ('Sophomore', 1), ('Junior', 2)),   
        ('Class_Tenure', ('Sophomore', 2), ('Junior', 3)),   
        ('Class_Tenure', ('Junior', 1), ('Senior', 2)),      
        ('Class_Tenure', ('Junior', 2), ('Senior', 3)),      
        ('Class_Tenure', ('Junior', 3), ('Senior', 4)), 
    ]
    
    def calculate_multipliers_for_cohort(cohort_df, cohort_name):
        """
        Calculates development multipliers for a specific cohort (elite or standard).
        
        Args:
            cohort_df: DataFrame filtered to the cohort
            cohort_name: String identifier for logging
            
        Returns:
            DataFrame with multipliers indexed by Transition
        """
        multipliers = []
        
        for definition in transitions:
            category = definition[0]
            start_val = definition[1]
            end_val = definition[2]
            
            # Filter Cohort
            if category == 'Class':
                cohort = cohort_df[(cohort_df['Class_Cleaned_Prev'] == start_val) & 
                                   (cohort_df['Class_Cleaned_Next'] == end_val)]
                trans_name = f"{start_val}_to_{end_val}"
            elif category == 'Tenure':
                cohort = cohort_df[(cohort_df['Varsity_Year_Prev'] == start_val) & 
                                   (cohort_df['Varsity_Year_Next'] == end_val)]
                trans_name = f"Varsity_Year{start_val}_to_Year{end_val}"
            elif category == 'Class_Tenure':
                s_cls, s_ten = start_val
                e_cls, e_ten = end_val
                cohort = cohort_df[
                    (cohort_df['Class_Cleaned_Prev'] == s_cls) & (cohort_df['Varsity_Year_Prev'] == s_ten) &
                    (cohort_df['Class_Cleaned_Next'] == e_cls) & (cohort_df['Varsity_Year_Next'] == e_ten)
                ]
                trans_name = f"{s_cls}_Y{s_ten}_to_{e_cls}_Y{e_ten}"

            # Initialize stats row
            transition_stats = {
                'Transition': trans_name, 
                'Type': category, 
                'Sample_Size': len(cohort),
                'Avg_Volatility': 0.0
            }
            
            volatility_scores = []

            for col in stat_cols:
                subset = cohort.copy()
                st_type = stat_types.get(col, 'Batting')
                
                # Filter for significant playing time to reduce noise
                if st_type == 'Pitching':
                    if 'IP_Prev' in subset.columns: 
                        subset = subset[subset['IP_Prev'] >= 5] 
                    else: 
                        continue 
                else:
                    if 'PA_Prev' in subset.columns: 
                        subset = subset[subset['PA_Prev'] >= 10]
                    else: 
                        continue

                subset = subset[subset[f'{col}_Prev'] > 0]

                if len(subset) < 3: 
                    transition_stats[col] = 1.0 
                    continue

                # Calculate Ratios with Laplacian Smoothing for rare events
                if col in ['3B', 'HR', '3B_P', 'HR_P']:
                    ratios = (subset[f'{col}_Next'] + 1) / (subset[f'{col}_Prev'] + 1)
                else:
                    ratios = subset[f'{col}_Next'] / subset[f'{col}_Prev']
                
                ratios = ratios.replace([np.inf, -np.inf], np.nan).dropna()
                
                if len(ratios) == 0:
                    transition_stats[col] = 1.0
                    continue
                
                # 1. The Multiplier (Median is robust to outliers)
                transition_stats[col] = round(ratios.median(), 3)
                
                # 2. The Volatility (Standard Deviation)
                std_dev = ratios.std()
                if not np.isnan(std_dev):
                    volatility_scores.append(std_dev)

            # Calculate Aggregate Volatility for this Transition type
            if volatility_scores:
                transition_stats['Avg_Volatility'] = round(sum(volatility_scores) / len(volatility_scores), 3)
            
            multipliers.append(transition_stats)

        df_mult = pd.DataFrame(multipliers)
        if not df_mult.empty:
            df_mult.set_index('Transition', inplace=True)
        return df_mult

    # --- 6. Calculate Multipliers for Each Cohort ---
    print(f"\n{'='*80}")
    print("PROCESSING COHORTS")
    print(f"{'='*80}")
    
    # Pooled (all programs) - for backward compatibility
    print("\nCalculating POOLED multipliers (all programs)...")
    df_pooled = calculate_multipliers_for_cohort(merged, "Pooled")
    
    # Elite programs only
    print("Calculating ELITE multipliers...")
    elite_merged = merged[merged['Is_Elite_Prev'] == True]
    df_elite = calculate_multipliers_for_cohort(elite_merged, "Elite")
    
    # Standard programs only
    print("Calculating STANDARD multipliers...")
    standard_merged = merged[merged['Is_Elite_Prev'] == False]
    df_standard = calculate_multipliers_for_cohort(standard_merged, "Standard")

    # --- 7. Generate Evidence Report ---
    print(f"\n{'='*80}")
    print("EVIDENCE: ELITE vs STANDARD DEVELOPMENT DIFFERENCES")
    print(f"{'='*80}")
    print(f"""
    Why segment by program tier?
    
    Elite programs ({len(ELITE_TEAMS)} teams based on regional/state championships) invest in
    year-round player development that standard programs cannot match:
    
    - Daily team lifting sessions (including 6am offseason workouts)
    - Structured winter practices and defensive work
    - Summer ball with same coaches and teammates (eg: Rocky, Regis, Pueblo)
    - Culture of state-level expectations
    
    This produces measurably different development curves.
    """)
    
    # Key comparison stats
    key_transitions = ['Junior_to_Senior', 'Sophomore_to_Junior', 'Freshman_to_Sophomore']
    key_stats = ['IP', 'K_P', 'ER', 'BB_P', 'H', 'AB']
    
    for trans in key_transitions:
        if trans not in df_elite.index or trans not in df_standard.index:
            continue
            
        print(f"\n--- {trans} ---")
        print(f"{'Stat':<8} {'Elite':>10} {'(N)':>6} {'Standard':>10} {'(N)':>6} {'Delta':>10} {'Interpretation'}")
        print("-" * 90)
        
        elite_n = df_elite.loc[trans, 'Sample_Size']
        std_n = df_standard.loc[trans, 'Sample_Size']
        
        for stat in key_stats:
            if stat not in df_elite.columns or stat not in df_standard.columns:
                continue
            e_val = df_elite.loc[trans, stat]
            s_val = df_standard.loc[trans, stat]
            delta = e_val - s_val
            
            # Interpretation
            if stat == 'ER' and delta < -0.05:
                interp = "Elite allows fewer runs"
            elif stat == 'K_P' and delta > 0.1:
                interp = "Elite gains more strikeouts"
            elif stat == 'BB_P' and delta < -0.1:
                interp = "Elite reduces walks more"
            elif stat == 'H' and delta > 0.1:
                interp = "Elite gains more hits"
            elif stat == 'IP' and delta > 0.1:
                interp = "Elite pitches more innings"
            elif abs(delta) < 0.05:
                interp = "No significant difference"
            else:
                interp = ""
            
            print(f"{stat:<8} {e_val:>10.3f} {elite_n:>6} {s_val:>10.3f} {std_n:>6} {delta:>+10.3f} {interp}")

    # --- 8. Save All Three Files ---
    output_dir = PATHS['out_development_multipliers']
    os.makedirs(output_dir, exist_ok=True)
    
    # Pooled (backward compatible)
    pooled_file = os.path.join(output_dir, 'development_multipliers.csv')
    df_pooled.to_csv(pooled_file)
    print(f"\nSaved pooled multipliers to '{pooled_file}'")
    
    # Elite
    elite_file = os.path.join(output_dir, 'elite_development_multipliers.csv')
    df_elite.to_csv(elite_file)
    print(f"Saved elite multipliers to '{elite_file}'")
    
    # Standard
    standard_file = os.path.join(output_dir, 'standard_development_multipliers.csv')
    df_standard.to_csv(standard_file)
    print(f"Saved standard multipliers to '{standard_file}'")
    
    # --- 9. Summary Statistics ---
    print(f"\n{'='*80}")
    print("VOLATILITY ANALYSIS (Lower is Better = More Reliable)")
    print(f"{'='*80}")
    
    print("\n--- POOLED ---")
    print(df_pooled[['Type', 'Sample_Size', 'Avg_Volatility']].sort_values('Avg_Volatility').to_string())
    
    print("\n--- ELITE ---")
    print(df_elite[['Type', 'Sample_Size', 'Avg_Volatility']].sort_values('Avg_Volatility').to_string())
    
    print("\n--- STANDARD ---")
    print(df_standard[['Type', 'Sample_Size', 'Avg_Volatility']].sort_values('Avg_Volatility').to_string())
    
    # --- 10. Dynamic Key Findings Summary ---
    print(f"\n{'='*80}")
    print("KEY FINDINGS SUMMARY (Dynamically Generated)")
    print(f"{'='*80}")
    
    def safe_get(df, trans, stat, default=1.0):
        """Safely retrieve a multiplier value."""
        try:
            if trans in df.index and stat in df.columns:
                val = df.loc[trans, stat]
                return val if pd.notna(val) else default
            return default
        except:
            return default
    
    def safe_get_n(df, trans, default=0):
        """Safely retrieve sample size."""
        try:
            if trans in df.index and 'Sample_Size' in df.columns:
                return int(df.loc[trans, 'Sample_Size'])
            return default
        except:
            return default
    
    def format_pct_diff(elite_val, std_val):
        """Format percentage difference for display."""
        if std_val == 0 or std_val == 1.0:
            return f"{(elite_val - 1.0) * 100:+.0f}% vs flat"
        pct_diff = ((elite_val / std_val) - 1) * 100
        return f"{pct_diff:+.0f}% relative"
    
    # Junior → Senior Pitching
    jr_sr = 'Junior_to_Senior'
    jr_sr_elite_n = safe_get_n(df_elite, jr_sr)
    jr_sr_std_n = safe_get_n(df_standard, jr_sr)
    
    print(f"\n1. JUNIOR → SENIOR PITCHING (N: {jr_sr_elite_n} elite, {jr_sr_std_n} standard)")
    
    for stat, desc in [('K_P', 'Strikeouts'), ('ER', 'Earned Runs'), ('BB_P', 'Walks')]:
        e_val = safe_get(df_elite, jr_sr, stat)
        s_val = safe_get(df_standard, jr_sr, stat)
        delta = e_val - s_val
        
        if stat == 'ER':
            # Lower is better for ER
            if delta < 0:
                interpretation = f"Elite reduces runs {abs(delta)*100:.0f}% more"
            else:
                interpretation = f"Standard reduces runs {abs(delta)*100:.0f}% more"
        else:
            # Higher is better for K_P (more strikeouts)
            # Lower is better for BB_P (fewer walks)
            if stat == 'K_P':
                if delta > 0:
                    interpretation = f"Elite gains {delta*100:.0f}% more strikeouts"
                else:
                    interpretation = f"No significant advantage"
            elif stat == 'BB_P':
                if delta < 0:
                    interpretation = f"Elite cuts walks {abs(delta)*100:.0f}% more"
                else:
                    interpretation = f"No significant advantage"
        
        print(f"   - {desc}: Elite {e_val:.3f} vs Standard {s_val:.3f} ({interpretation})")
    
    # Sophomore → Junior Pitching
    so_jr = 'Sophomore_to_Junior'
    so_jr_elite_n = safe_get_n(df_elite, so_jr)
    so_jr_std_n = safe_get_n(df_standard, so_jr)
    
    print(f"\n2. SOPHOMORE → JUNIOR PITCHING (N: {so_jr_elite_n} elite, {so_jr_std_n} standard)")
    
    for stat, desc in [('IP', 'Innings Pitched'), ('K_P', 'Strikeouts')]:
        e_val = safe_get(df_elite, so_jr, stat)
        s_val = safe_get(df_standard, so_jr, stat)
        delta = e_val - s_val
        
        if delta > 0.05:
            interpretation = f"Elite grows {delta*100:.0f}% more"
        elif delta < -0.05:
            interpretation = f"Standard grows {abs(delta)*100:.0f}% more"
        else:
            interpretation = "No significant difference"
        
        print(f"   - {desc}: Elite {e_val:.3f} vs Standard {s_val:.3f} ({interpretation})")
    
    # Batting Development
    print(f"\n3. BATTING DEVELOPMENT")
    
    for trans, trans_label in [(so_jr, 'Soph→Jr'), (jr_sr, 'Jr→Sr')]:
        e_h = safe_get(df_elite, trans, 'H')
        s_h = safe_get(df_standard, trans, 'H')
        e_ops = safe_get(df_elite, trans, 'OPS')
        s_ops = safe_get(df_standard, trans, 'OPS')
        
        h_delta = e_h - s_h
        ops_delta = e_ops - s_ops
        
        if abs(h_delta) > 0.1:
            h_note = f"Elite {'+' if h_delta > 0 else ''}{h_delta*100:.0f}%"
        else:
            h_note = "similar"
        
        if abs(ops_delta) > 0.05:
            ops_note = f"Elite {'+' if ops_delta > 0 else ''}{ops_delta*100:.0f}%"
        else:
            ops_note = "similar"
        
        print(f"   - {trans_label}: Hits ({e_h:.3f} vs {s_h:.3f}, {h_note}), OPS ({e_ops:.3f} vs {s_ops:.3f}, {ops_note})")
    
    # Sample Sizes
    print(f"\n4. SAMPLE SIZES")
    print(f"   - Elite program transitions: {elite_transitions}")
    print(f"   - Standard program transitions: {standard_transitions}")
    print(f"   - Total transitions analyzed: {total_transitions}")
    
    # Check statistical robustness
    min_class_n = min(
        safe_get_n(df_elite, 'Freshman_to_Sophomore'),
        safe_get_n(df_elite, 'Sophomore_to_Junior'),
        safe_get_n(df_elite, 'Junior_to_Senior'),
        safe_get_n(df_standard, 'Freshman_to_Sophomore'),
        safe_get_n(df_standard, 'Sophomore_to_Junior'),
        safe_get_n(df_standard, 'Junior_to_Senior')
    )
    
    if min_class_n >= 30:
        robustness = "All class-based transitions have N ≥ 30 (statistically robust)"
    elif min_class_n >= 10:
        robustness = f"Minimum N = {min_class_n} (marginally robust, interpret with caution)"
    else:
        robustness = f"WARNING: Minimum N = {min_class_n} (small sample, results may be unreliable)"
    
    print(f"   - {robustness}")
    
    # Recommendation
    print(f"\n5. RECOMMENDATION")
    
    # Dynamically determine if elite multipliers show meaningful advantage
    jr_sr_k_delta = safe_get(df_elite, jr_sr, 'K_P') - safe_get(df_standard, jr_sr, 'K_P')
    jr_sr_er_delta = safe_get(df_elite, jr_sr, 'ER') - safe_get(df_standard, jr_sr, 'ER')
    
    if jr_sr_k_delta > 0.1 or jr_sr_er_delta < -0.05:
        print(f"   - Elite programs show meaningful pitching development advantages")
        print(f"   - USE elite_development_multipliers.csv for: {', '.join([t.split(' (')[0] for t in ELITE_TEAMS])}")
        print(f"   - USE standard_development_multipliers.csv for all other teams")
    else:
        print(f"   - Current elite team selection shows minimal differentiation")
        print(f"   - Consider adjusting ELITE_TEAMS or using pooled multipliers")
    
    print(f"\n{'='*80}")
    print("END OF REPORT")
    print(f"{'='*80}")


if __name__ == "__main__":
    generate_stat_multipliers()