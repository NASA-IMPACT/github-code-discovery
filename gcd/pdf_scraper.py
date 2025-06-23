from __future__ import annotations

import csv
import glob
import os
from urllib.parse import urlparse
from loguru import logger
import cloudscraper
import pandas as pd
from joblib import Parallel, delayed
from semanticscholar import SemanticScholar

BATCH_SIZE = 1000

# Initialize SemanticScholar client
sch = SemanticScholar()

def process_single_doi(doi_url: str):
    """Process a single DOI: fetch metadata and abstract from SemanticScholar."""
    doi = doi_url.replace("https://doi.org/", "").strip()
    try:
        paper = sch.get_paper(doi)
        logger.info(f"Processing {doi_url}")
        abstract = paper["abstract"]  # Original access without `.get()`
        full_text_url = paper["openAccessPdf"][
            "url"
        ]  # Original access without `.get()`
        logger.info(f"Processed: {doi_url}")
        return (doi_url, abstract, full_text_url)
    except Exception as e:
        logger.error(f"Failed: {doi_url} - {e}")
        return None


def save_batch_to_csv(batch_data, batch_number, output_folder):
    """Save a batch of data to a CSV file."""
    filename = f"batch_{batch_number}.csv"
    file_path = os.path.join(output_folder, filename)
    with open(file_path, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.writer(outfile)
        writer.writerow(["DOI", "Abstract", "FullTextURL"])
        for row in batch_data:
            if row:
                writer.writerow(row)
    logger.info(f"Saved {filename}")

def process_dois_parallel(
    input_csv,
    start_row,
    end_row,
    n_jobs=4,
    output_folder="./doi_results/links",
):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    """Process DOIs in parallel and save them in batches."""
    with open(input_csv, newline="") as infile:
        reader = csv.DictReader(infile)
        doi_urls = [row["DOI"].strip() for i, row in enumerate(reader) if start_row <= i < end_row]

    logger.info("\n--- Processing DOIs ---")
    for batch_num, i in enumerate(
        range(0, len(doi_urls), BATCH_SIZE),
        start=1,
    ):
        batch_dois = doi_urls[i : i + BATCH_SIZE]
        results = Parallel(n_jobs=n_jobs, backend="threading")(
            delayed(process_single_doi)(doi_url) for doi_url in batch_dois
        )
        save_batch_to_csv(results, batch_num, output_folder)

def download_pdf(url, output_path):
    """Download a PDF from the given URL and save it to the specified file path."""
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, stream=True)

        if response.status_code != 200:
            logger.error(f"Failed to download PDF. HTTP {response.status_code} for URL: {url}")
            return

        content_type = response.headers.get("Content-Type", "")
        if "application/pdf" not in content_type:
            logger.error(f"URL did not return a PDF: {url} (Content-Type: {content_type})")
            return

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"PDF saved as {output_path}")

    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")

def download_all_pdfs_from_csvs(
    results_folder="./doi_results/links",
    pdf_output_path="./doi_results/pdfs",
):
    """Scan all result CSVs and download PDFs from the FullTextURL column."""
    csv_files = glob.glob(os.path.join(results_folder, "batch_*.csv"))

    for csv_file in csv_files:
        logger.info(f"\nProcessing: {csv_file}")
        df = pd.read_csv(csv_file)

        for idx, row in df.iterrows():
            url = row.get("FullTextURL")
            if isinstance(url, str) and url.startswith("http"):
                # Generate a unique filename from the URL or DOI
                try:
                    parsed = urlparse(url)
                    filename = parsed.path.strip("/").replace("/", "_") + ".pdf"
                    output_file = os.path.join(pdf_output_path, filename)
                    if not os.path.exists(output_file):  # Avoid re-downloading
                        download_pdf(url, output_file)
                    else:
                        logger.info(f"PDF already exists: {output_file}")
                except Exception as e:
                    logger.error(f"Error handling URL {url}: {e}")
