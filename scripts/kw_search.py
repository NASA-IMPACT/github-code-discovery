import sys
import pandas as pd
import os
from gcd.github_api import search_repositories  
from gcd.classification_utils import run_classification_pipeline
from config import GITHUB_TOKEN

def main(keyword: str, days_back: int, output_csv_path: str):
    repos = search_repositories(keyword=keyword, days_back=days_back, GITHUB_TOKEN=GITHUB_TOKEN)
    df = pd.DataFrame(repos).drop_duplicates(subset="url")
    temp_path = "kw_temp.csv"
    df.to_csv(temp_path, index=False)
    run_classification_pipeline(input_csv_path=temp_path, 
                                output_csv_path=output_csv_path,
                                text_column="readme",
                                url_column="url")
    os.remove(temp_path)
    print(f"Saved {len(df)} unique repositories from the last {days_back} days.")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 kw_search.py <keyword> <days_back> <output_csv_path>")
        sys.exit(1)

    keyword = sys.argv[1]
    days_back = int(sys.argv[2])
    output_csv = sys.argv[3]

    main(keyword, days_back, output_csv)


