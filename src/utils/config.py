import os

"""
Configuration: Statistical Schema Definition

Summary:
    Centralized configuration file acting as the Master Data Dictionary and Schema Registry.
    Now includes Modeling & Simulation constants to prevent configuration sprawl.
"""

# --- 1. Centralized Path Configuration ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
INPUT_DIR = os.path.join(DATA_DIR, "input")

PATHS = {
    # Inputs
    "raw": os.path.join(DATA_DIR, "raw"),
    "processed": os.path.join(DATA_DIR, "processed"), 
    "input": INPUT_DIR,
    
    # Outputs
    "out_team_strength": os.path.join(OUTPUT_DIR, "team_strength"), 
    "out_development_multipliers": os.path.join(OUTPUT_DIR, "development_multipliers"), 
    "out_generic_players": os.path.join(OUTPUT_DIR, "generic_players"), 
    "out_roster_prediction": os.path.join(OUTPUT_DIR, "roster_prediction"),
    "out_historical_stats": os.path.join(OUTPUT_DIR, "historical_stats")
}

# --- 2. Statistics Configuration ---
STAT_SCHEMA = [
    # --- BATTING ---
    {"abbreviation": "PA",   "max_preps_class": "plateappearances stat dw",        "stat_type": "Batting", "description": "Plate Appearances"},
    {"abbreviation": "AB",   "max_preps_class": "atbats stat dw",                  "stat_type": "Batting", "description": "At Bats"},
    {"abbreviation": "AVG",  "max_preps_class": "battingaverage stat dw",          "stat_type": "Batting", "description": "Batting Average"},
    {"abbreviation": "H",    "max_preps_class": "hits stat dw",                    "stat_type": "Batting", "description": "Hits"},
    {"abbreviation": "2B",    "max_preps_class": "doubles stat dw",                "stat_type": "Batting", "description": "Doubles"},
    {"abbreviation": "3B",    "max_preps_class": "triples stat dw",                "stat_type": "Batting", "description": "Triples"},
    {"abbreviation": "HR",   "max_preps_class": "homeruns stat dw",                "stat_type": "Batting", "description": "Home Runs"},
    {"abbreviation": "RBI",  "max_preps_class": "rbi stat dw",                     "stat_type": "Batting", "description": "Runs Batted In"},
    {"abbreviation": "R",    "max_preps_class": "runs stat dw",                    "stat_type": "Batting", "description": "Runs Scored"},
    {"abbreviation": "SF",    "max_preps_class": "sacrificefly stat dw",            "stat_type": "Batting", "description": "Sacrifice Flies"},
    {"abbreviation": "BB",   "max_preps_class": "baseonballs stat dw",             "stat_type": "Batting", "description": "Walks"},
    {"abbreviation": "K",    "max_preps_class": "struckout stat dw",               "stat_type": "Batting", "description": "Strikeouts"},
    {"abbreviation": "HBP",  "max_preps_class": "hitbypitch stat dw",              "stat_type": "Batting", "description": "Hit by Pitch"},
    {"abbreviation": "OBP",  "max_preps_class": "onbasepercentage stat dw",        "stat_type": "Batting", "description": "On Base Percentage"},
    {"abbreviation": "SLG",  "max_preps_class": "sluggingpercentage stat dw",      "stat_type": "Batting", "description": "Slugging Percentage"},
    {"abbreviation": "OPS",  "max_preps_class": "onbaseplussluggingpercentage last stat dw", "stat_type": "Batting", "description": "On Base Plus Slugging"},

    # --- PITCHING ---
    {"abbreviation": "APP",  "max_preps_class": "appearances stat dw",             "stat_type": "Pitching", "description": "Appearances"},
    {"abbreviation": "IP",   "max_preps_class": "inningspitcheddecimal stat dw",   "stat_type": "Pitching","description": "Innings Pitched"},
    {"abbreviation": "ERA",  "max_preps_class": "earnedrunaverage stat dw",        "stat_type": "Pitching","description": "Earned Run Average"},
    {"abbreviation": "BF",   "max_preps_class": "battersfaced stat dw",            "stat_type": "Pitching","description": "Batters Faced"},
    {"abbreviation": "K_P",  "max_preps_class": "battersstruckout stat dw",        "stat_type": "Pitching","description": "Strikeouts"},
    {"abbreviation": "ER",   "max_preps_class": "earnedruns stat dw",              "stat_type": "Pitching","description": "Earned Runs"},
    {"abbreviation": "H_P",  "max_preps_class": "hitsagainst stat dw",             "stat_type": "Pitching","description": "Hits Against"},
    {"abbreviation": "2B_P",  "max_preps_class": "doublesagainst stat dw",         "stat_type": "Pitching" ,"description": "Doubles Against"},
    {"abbreviation": "3B_P",  "max_preps_class": "triplesagainst stat dw",         "stat_type": "Pitching" ,"description": "Triples Against"},
    {"abbreviation": "HR_P",  "max_preps_class": "homerunsagainst stat dw",        "stat_type": "Pitching" ,"description": "Home Runs Against"},
    {"abbreviation": "BB_P", "max_preps_class": "baseonballsagainst stat dw",      "stat_type": "Pitching" ,"description": "Walks Against"},
    {"abbreviation": "BAA",  "max_preps_class": "battingaveragepitcher stat dw",   "stat_type": "Pitching" ,"description": "Batting Average Against"}, 

    # --- Base Running ---
    {"abbreviation": "SB",  "max_preps_class": "stolenbase stat dw",   "stat_type": "Baserunning" ,"description": "Stolen Bases"}, 

    # --- Fielding --- 
    {"abbreviation": "FP",  "max_preps_class": "fieldingpercentage stat dw",   "stat_type": "Fielding" ,"description": "Fielding Percentage"}, 
    {"abbreviation": "TC",  "max_preps_class": "totalchances stat dw",   "stat_type": "Fielding" ,"description": "Total Chances"}, 
    {"abbreviation": "PO",  "max_preps_class": "putouts stat dw",   "stat_type": "Fielding" ,"description": "Putouts"}, 
    {"abbreviation": "A",  "max_preps_class": "assists stat dw",   "stat_type": "Fielding" ,"description": "Assists"}, 
    {"abbreviation": "E",  "max_preps_class": "errors stat dw",   "stat_type": "Fielding","description": "Errors"}, 
    {"abbreviation": "DP",  "max_preps_class": "doubleplays stat dw",   "stat_type": "Fielding" ,"description": "Double Plays"}
]

# --- 3. Modeling & Simulation Configuration ---
ELITE_TEAMS = [
    "Broomfield (CO)", 
    "Cherry Creek (Greenwood Village, CO)",
    "Mountain Vista (Highlands Ranch, CO)",
    "Cherokee Trail (Aurora, CO)",
    "Regis Jesuit (Aurora, CO)", 
    "Rocky Mountain (Fort Collins, CO)" 
]

MODEL_CONFIG = {
    # Ranking Logic (Team Strength)
    'TOP_N_BATTERS': 9,
    'TOP_N_PITCHERS': 5,
    'MIN_RC_SCORE': 0.1,       # Minimum score to be considered a viable batter
    'MIN_PITCHING_SCORE': 0.1, # Minimum score to be considered a viable pitcher
    
    # Confidence Weights (Age/Experience)
    'WEIGHT_SENIOR': 1.10,
    'WEIGHT_JUNIOR': 1.00,
    'WEIGHT_UNDERCLASS': 0.90,
    'WEIGHT_GENERIC_ELITE': 0.90,
    'WEIGHT_GENERIC_STD': 0.75,
    
    # Simulation Logic (Monte Carlo)
    'LEAGUE_BASE_RUNS': 6.0,          # Conservative baseline
    'HOME_FIELD_ADVANTAGE': 1.10,
    'DEFAULT_DISPERSION': 1.3,
    'MIN_INDEX_FLOOR': 0.30,          # Prevents runaway multipliers against weak teams
    
    # Roster Prediction (Backfill)
    'DEFAULT_PERCENTILE_LADDER': [0.3, 0.1],
    'ELITE_PERCENTILE_LADDER': [0.5, 0.2, 0.1],
    'MIN_ROSTER_BATTERS': 10,
    'MIN_ROSTER_PITCHERS': 6,
    'SURVIVOR_BIAS_ADJUSTMENT': 0.95
}