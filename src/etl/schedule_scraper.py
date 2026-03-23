import os
import sys
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd
import time
#from src.utils.config import PATHS

def scrape_maxpreps_schedule(url):
    scraper =cloudscraper.create_scraper()
    response = scraper.get(url)
    
    if response.status_code != 200:
        print(f"  -> Failed: Status {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    tables = soup.find_all('table')
    
    games = []
    for table in tables:
        tbody = table.find('tbody')
        if not tbody:
            continue
            
        for row in tbody.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 3:
                date = cols[0].get_text(strip=True)
                opponent = cols[1].get_text(separator=' ', strip=True)
                time_or_result = cols[2].get_text(separator=' ', strip=True)
                
                games.append({
                    'Date': date,
                    'Opponent': opponent,
                    'Time/Result': time_or_result
                })
    return games

# 1. Load the CSV you uploaded
team_ranking_urls = os.path.join('data','input', 'team_ranking_urls.csv')
print(team_ranking_urls)
teams_df = pd.read_csv(team_ranking_urls)

all_games = []

print("Starting schedule extraction...")

# 2. Loop through every team
for index, row in teams_df.iterrows():
    team_name = row['team']
    team_rank = row['chsaa_rank']
    is_league = row['league']
    url = row['schedule_url']
    
    print(f"Fetching: {team_name}")
    schedule_data = scrape_maxpreps_schedule(url)
    
    # 3. Tag each game with the team's name so we can filter it later
    for game in schedule_data:
        game['Team'] = team_name
        game['Rank'] = team_rank
        game['League'] = is_league
        all_games.append(game)
        
    # Be polite to the Cloudflare bouncers
    time.sleep(2)

# 4. Convert the aggregated data into a master DataFrame
master_df = pd.DataFrame(all_games)

# Reorder columns so Team is first
master_df = master_df[['Team', 'Rank', 'League', 'Date', 'Opponent', 'Time/Result']]
# print(master_df)
# 5. Export
schedule_roundup_file = os.path.join('data','output','schedule_roundup', 'schedule_roundup.csv')
master_df.to_csv(schedule_roundup_file, index=False)
print("\nSuccess! Saved to schedule_roundup.csv")