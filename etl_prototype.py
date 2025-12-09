import pandas as pd
from bs4 import BeautifulSoup
import os

#test comment for git

# 1. Define the path (The "Connection String")
file_path = 'data/raw/rocky_25.html'

# 2. Check if file exists (Error Handling)
if not os.path.exists(file_path):
    print(f"Error: Could not find file at {file_path}")
else:
    print(f"File found: {file_path}")

    # 3. Read the file (The "Ingestion")
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 4. Parse the HTML (The "Transformation" engine)
    soup = BeautifulSoup(html_content, 'lxml')

    # 5. Proof of Life: Print the title of the page
    page_title = soup.title.string if soup.title else "No Title Found"
    print(f"Successfully parsed page: {page_title}")
    
    # 6. Count tables (How many datasets are on this page?)
    tables = soup.find_all('table')
    print(f"Found {len(tables)} tables on this page.")