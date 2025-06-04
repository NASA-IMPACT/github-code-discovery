import sys
import pandas as pd
import os
from gcd.github_api import search_repositories  
from gcd.classification_utils import run_classification_pipeline

def keyword_pipeline(keyword: str, days_back: int, output_csv_path: str, token: str):
    output_dir = os.path.dirname(output_csv_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    repos = search_repositories(keyword=keyword, days_back=days_back, GITHUB_TOKEN=token)
    df = pd.DataFrame(repos).drop_duplicates(subset="url")
    temp_path = "kw_temp.csv"
    df.to_csv(temp_path, index=False)
    run_classification_pipeline(input_csv_path=temp_path, 
                                output_csv_path=output_csv_path,
                                text_column="readme",
                                url_column="url")
    os.remove(temp_path)
    print(f"Saved {len(df)} unique repositories from the last {days_back} days.")

def run_keyword_pipeline(keyword: str, days_back: int, output_csv_path: str, token: str):
    keyword_pipeline(keyword, days_back, output_csv_path, token)




