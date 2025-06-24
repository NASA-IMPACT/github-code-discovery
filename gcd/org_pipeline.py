import sys
import pandas as pd
from gcd.github_api_ql import fetch_and_process_org_links
from gcd.classification_utils import run_classification_pipeline

def org_pipeline(input_csv_path: str, token: str):
    fetch_and_process_org_links(input_csv_path, token)
    run_classification_pipeline(input_csv_path = "./org_list_temp.csv", 
                                source_class="ORG")

def run_org_pipeline(input_csv_path: str, token: str):
    org_pipeline(input_csv_path, token)



