import sys
import pandas as pd
from gcd.pdf_scraper import process_dois_parallel, download_all_pdfs_from_csvs
from gcd.extract_links import extract_links_from_pdf_folder
from gcd.github_api_ql import process_github_links_from_csv
from gcd.classification_utils import run_classification_pipeline
import os

def doi_pipeline(token: str, csv_path: str, start_row: int = 0, end_row: int = 1000):
    process_dois_parallel(csv_path, start_row, end_row, n_jobs=-1)
    download_all_pdfs_from_csvs()
    extract_links_from_pdf_folder("./doi_results/pdfs", 
                                  output_csv="./doi_results/extracted_github_links.csv")
    process_github_links_from_csv(token=token, 
                                  json_output_path="./doi_results/github_repo_readme.json", 
                                  csv_output_path="./doi_results/github_repo_readme.csv")
    run_classification_pipeline(input_csv_path="./doi_results/github_repo_readme.csv", 
                                source_class="DOI")
    
    # Uncomment to save all the results
    os.remove("./doi_results/extracted_github_links.csv")
    os.remove("./doi_results/github_repo_readme.json")
    os.remove("./doi_results/github_repo_readme.csv")

def run_doi_pipeline(token: str, csv_path: str, start_row: int = 0, end_row: int = 1000):
    doi_pipeline(token, csv_path, start_row, end_row)

