import os

"""
Configuration: Statistical Schema Definition

Summary:
    Centralized configuration file acting as the Master Data Dictionary and Schema Registry for the project.

Context:
    This is the official Scorekeeping Rulebook. Just as the umpire needs to know the difference between 
    a hit and an error, our system needs to know exactly which numbers to pull from the box score. 
    This file defines the specific columns we care about—ignoring the noise—so we can build a consistent 
    scouting report for every player.

    From a statistical standpoint, this defines the Operational Definitions for all dependent variables. 
    By explicitly mapping variable names (e.g., 'H') to specific source classes (e.g., 'hits stat dw'), 
    we ensure construct validity. This prevents ambiguity where "Runs" could be interpreted as "Runs Scored" 
    vs "Runs Allowed" unless strictly defined here.

    Technically, think of this as the DDL (Data Definition Language) for our NoSQL extraction process. 
    We are mapping JSON keys (or HTML classes) to our internal Relational Column names. This dictionary 
    drives the entire downstream ETL process, acting as the config file that controls the `SELECT` statement 
    in `stat_extraction.py`.
"""

# --- 1. Centralized Path Configuration ---
# Calculate project root (3 levels up from src/utils/config.py)
# Acts as the ROOT_PATH variable in a file storage system
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

# --- 2. Statistics Configuration
# This list functions as the Master Data Dictionary. 
# It dictates the schema for the resulting Pandas DataFrames (tables).
STAT_SCHEMA = [
    # --- BATTING ---
    # Mapping source HTML class (Source System Field) to internal abbreviation (Target Column)
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

# -- This provides a group of elite teams based on state and regional championships since 2016
# See documentation
ELITE_TEAMS = [
    "Broomfield (CO)", 
    "Cherry Creek (Greenwood Village, CO)",
    "Mountain Vista (Highlands Ranch, CO)",
    "Cherokee Trail (Aurora, CO)",
    "Regis Jesuit (Aurora, CO)", 
    "Rocky Mountain (Fort Collins, CO)" 
]