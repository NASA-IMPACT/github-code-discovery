import sys
import pandas as pd
from gcd.ascl_search import fetch_and_process_ascl_links
from gcd.classification_utils import run_classification_pipeline

def ascl_pipeline(token: str):
    fetch_and_process_ascl_links(token)
    run_classification_pipeline(input_csv_path="./ascl_new_github_repo_readme.csv", 
                                source_class="ASCL")

def run_ascl_pipeline(token: str):
    ascl_pipeline(token)



