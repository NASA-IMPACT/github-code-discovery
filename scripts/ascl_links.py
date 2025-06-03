import sys
import pandas as pd
from gcd.ascl_search import fetch_and_process_ascl_links
from gcd.classification_utils import run_classification_pipeline
from config import GITHUB_TOKEN

def main():
    fetch_and_process_ascl_links(token=GITHUB_TOKEN)
    run_classification_pipeline(input_csv_path="./ascl_new_github_repo_readme.csv", 
                                output_csv_path="./ascl_new_github_repo_readme_classified.csv")

if __name__ == "__main__":
    main()

