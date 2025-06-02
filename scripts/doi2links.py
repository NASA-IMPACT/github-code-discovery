import sys
import pandas as pd
from gcd.pdf_scraper import process_dois_parallel, download_all_pdfs_from_csvs
from gcd.extract_links import extract_links_from_pdf_folder
from gcd.github_api_ql import process_github_links_from_csv
from gcd.classification_utils import run_classification_pipeline
from config import GITHUB_TOKEN

def main(csv_path: str, start_row: int = 0, end_row: int = 1000):
    process_dois_parallel(csv_path, start_row, end_row, n_jobs=-1)
    download_all_pdfs_from_csvs()
    extract_links_from_pdf_folder("./doi_results/pdfs", 
                                  output_csv="./doi_results/extracted_github_links.csv")
    process_github_links_from_csv(token=GITHUB_TOKEN, 
                                  json_output_path="./doi_results/github_repo_readme.json", 
                                  csv_output_path="./doi_results/github_repo_readme.csv")
    run_classification_pipeline(input_csv_path="./doi_results/github_repo_readme.csv", 
                                output_csv_path="./doi_results/github_repo_readme_classified.csv")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 doi2links.py ./data/[doilinks.csv] [start_row] [end_row]")
        sys.exit(1)

    input_file, start_row, end_row = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    main(input_file, start_row, end_row)

