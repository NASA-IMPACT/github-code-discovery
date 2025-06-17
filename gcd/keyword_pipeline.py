import sys
import pandas as pd
import os
from gcd.github_api import search_repositories  
from gcd.github_api_ql import search_repositories_graphql
from gcd.classification_utils import run_classification_pipeline
from loguru import logger

def keyword_pipeline(keyword: str, days_back: int, token: str):
        
    #repos = search_repositories(keyword=keyword, days_back=days_back, GITHUB_TOKEN=token) # REST API Implementation
    repos = search_repositories_graphql(keyword=keyword, days_back=days_back, GITHUB_TOKEN=token) # GraphQL Implementation
    df = pd.DataFrame(repos).drop_duplicates(subset="url")
    temp_path = "kw_temp.csv"
    df.to_csv(temp_path, index=False)
    run_classification_pipeline(input_csv_path=temp_path, 
                                text_column="readme",
                                url_column="url",
                                source_class="Keyword: " + keyword)
    os.remove(temp_path)
    logger.info(f"Saved {len(df)} unique repositories from the last {days_back} days.")

def run_keyword_pipeline(keyword: str, days_back: int, token: str):
    keyword_pipeline(keyword, days_back, token)




