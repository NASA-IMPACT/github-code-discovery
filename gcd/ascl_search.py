import requests
import pandas as pd
import os
from gcd.github_api_ql import process_github_links_from_csv
from loguru import logger

def fetch_and_process_ascl_links(token, 
                                  existing_links_path='./data/ascl_github_links.csv',
                                  json_output_path="./ascl_new_repo_readme.json",
                                  csv_output_path="./ascl_new_github_repo_readme.csv"):
    url = "https://ascl.net/code/json"
    response = requests.get(url)

    if response.status_code != 200:
        logger.error(f"Failed to fetch data. Status code: {response.status_code}")
        return

    data = response.json()

    # Extract GitHub links
    links = []
    for item in data:
        if 'site_list' in data[item] and isinstance(data[item]['site_list'], list):
            links.append(data[item]['site_list'])

    links = [link for sublist in links for link in sublist]
    github_links = set([url for url in links if "github.com" in url])

    current_df = pd.DataFrame(github_links, columns=['url'])

    try:
        source_df = pd.read_csv(existing_links_path)
    except Exception as e:
        logger.warning(f"Error reading existing links: {e}")
        source_df = pd.DataFrame(columns=['url'])

    new_links_df = current_df[~current_df['url'].isin(source_df['url'])]
    new_links_df = new_links_df.rename(columns={'url': 'GitHub Link'})

    logger.info(f"Found {len(new_links_df)} new GitHub links.")

    # Save to a temporary file for processing
    temp_path = "./temp_ascl_links.csv"
    new_links_df.to_csv(temp_path, index=False)

    # Process new GitHub links
    process_github_links_from_csv(token=token, 
                                  links_csv_path=temp_path,
                                  json_output_path=json_output_path, 
                                  csv_output_path=csv_output_path)
    
    os.remove(temp_path)
    logger.info("Temporary file removed and processing complete.")
















