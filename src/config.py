# src/config.py

# This is the central definition of all stats we want to capture.
# If you want to add a new stat, just add it to this list.

STAT_SCHEMA = [
    # --- BATTING ---
    {"abbreviation": "PA",   "max_preps_class": "plateappearances stat dw",        "stat_type": "Batting"},
    {"abbreviation": "AB",   "max_preps_class": "atbats stat dw",                  "stat_type": "Batting"},
    {"abbreviation": "AVG",  "max_preps_class": "battingaverage stat dw",          "stat_type": "Batting"},
    {"abbreviation": "H",    "max_preps_class": "hits stat dw",                    "stat_type": "Batting"},
    {"abbreviation": "RBI",  "max_preps_class": "rbi stat dw",                     "stat_type": "Batting"},
    {"abbreviation": "R",    "max_preps_class": "runs stat dw",                    "stat_type": "Batting"},
    {"abbreviation": "HR",   "max_preps_class": "homeruns stat dw",                "stat_type": "Batting"},
    {"abbreviation": "BB",   "max_preps_class": "baseonballs stat dw",             "stat_type": "Batting"},
    {"abbreviation": "K",    "max_preps_class": "struckout stat dw",               "stat_type": "Batting"},
    {"abbreviation": "HBP",  "max_preps_class": "hitbypitch stat dw",              "stat_type": "Batting"},
    {"abbreviation": "OBP",  "max_preps_class": "onbasepercentage stat dw",        "stat_type": "Batting"},
    {"abbreviation": "SLG",  "max_preps_class": "sluggingpercentage stat dw",      "stat_type": "Batting"},
    {"abbreviation": "OPS",  "max_preps_class": "onbaseplussluggingpercentage last stat dw", "stat_type": "Batting"},

    # --- PITCHING ---
    {"abbreviation": "APP",  "max_preps_class": "appearances stat dw",             "stat_type": "Pitching"},
    {"abbreviation": "IP",   "max_preps_class": "inningspitcheddecimal stat dw",   "stat_type": "Pitching"},
    {"abbreviation": "ERA",  "max_preps_class": "earnedrunaverage stat dw",        "stat_type": "Pitching"},
    {"abbreviation": "BF",   "max_preps_class": "battersfaced stat dw",            "stat_type": "Pitching"},
    {"abbreviation": "K_P",  "max_preps_class": "battersstruckout stat dw",        "stat_type": "Pitching"},
    {"abbreviation": "ER",   "max_preps_class": "earnedruns stat dw",              "stat_type": "Pitching"},
    {"abbreviation": "H_P",  "max_preps_class": "hitsagainst stat dw",             "stat_type": "Pitching"},
    {"abbreviation": "BB_P", "max_preps_class": "baseonballsagainst stat dw",      "stat_type": "Pitching"},
    {"abbreviation": "BAA",  "max_preps_class": "battingaveragepitcher stat dw",   "stat_type": "Pitching"}
]