import sys
import os

# This forces Python to look two folders up (your root project folder)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import cloudscraper
from bs4 import BeautifulSoup
import pprint

# Import your existing extraction function
from src.etl.stat_extraction import extract_player_data

def test_print_page_scraper():
    # The specific Rocky print URL you provided
    url = "https://www.maxpreps.com/print/team_stats.aspx?admin=0&bygame=0&league=0&print=1&schoolid=1f979532-8a7a-4067-ad3b-1470f47eb80f&ssid=1278779e-84df-4e60-8d03-db0024535aa6"
    
    # Mocking up the metadata that your main loop would normally inject
    metadata = {
        "Team": "Rocky Mountain",
        "Rank": "Test Rank",
        "League": True
    }

    print("Initializing cloudscraper...")
    scraper = cloudscraper.create_scraper()
    
    print("Fetching the Print Page HTML...")
    response = scraper.get(url)

    # Check if cloudscraper successfully bypassed the protection
    if response.status_code == 200:
        print("Success! HTTP 200 OK received. Parsing HTML...\n")
        
        # Pass the raw HTML string into BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Run your custom extraction logic
        player_stats = extract_player_data(soup, metadata)
        
        print(f"Extraction Complete: Found {len(player_stats)} player records.")
        print("-" * 50)
        
        # Preview the first 3 records to ensure the columns map correctly
        print("Previewing the first 3 players:")
        pprint.pprint(player_stats, sort_dicts=False)
        
    else:
        print(f"Failed to fetch the page. Status Code: {response.status_code}")
        print("MaxPreps/Cloudflare blocked the request.")

if __name__ == "__main__":
    test_print_page_scraper()