from __future__ import annotations

import csv
import os
import re
import string
from glob import glob
from itertools import chain

import pandas as pd
import pymupdf
from joblib import Parallel, delayed

GITHUB_REGEX = r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"


def clean_text_for_links(text: str) -> str:
    # Flatten the text by removing newlines
    text = text.replace("\n", " ")

    # Remove all whitespace between 'https' and '.com'
    text = re.sub(
        r"https.*?\.com",
        lambda m: "".join(m.group().split()),
        text,
        flags=re.DOTALL,
    )

    # Remove one whitespace between '.com' and '/'
    text = re.sub(r"(\.com)\s+/", r"\1/", text)

    # Remove one whitespace after '.com/' (i.e., between / and user)
    text = re.sub(r"(\.com/)\s+", r"\1", text)
    return text


def extract_links_from_text(text: str) -> list[str]:
    cleaned = clean_text_for_links(text)
    raw_links = set(re.findall(GITHUB_REGEX, cleaned))
    return [link.rstrip(string.punctuation) for link in raw_links]


def extract_links_from_dataframe(
    df: pd.DataFrame, all_columns: bool = False
) -> list[str]:
    def process_row_all(row):
        links = []
        for cell in row:
            if isinstance(cell, str):
                links.extend(extract_links_from_text(cell))
        return links

    results = Parallel(n_jobs=-1)(
        delayed(process_row_all)(row) for _, row in df.iterrows()
    )
    return list(set(chain.from_iterable(results)))


# Extract text using your format and apply GitHub link extraction
def process_single_pdf(pdf_path):
    try:
        text = ""
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
        return extract_links_from_text(text)
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return []


def extract_links_from_pdf_folder(
    pdf_folder: str, output_csv: str = "extracted_github_links.csv"
):
    """
    Process all PDFs in a folder, extract GitHub links, and save them to a CSV.

    Args:
        pdf_folder (str): Path to the folder containing PDF files.
        output_csv (str): Path to the output CSV file.
    """
    all_links = []
    pdf_paths = glob(os.path.join(pdf_folder, "*.pdf"))

    for pdf_path in pdf_paths:
        links = process_single_pdf(pdf_path)
        if links:
            for link in links:
                all_links.append((os.path.basename(pdf_path), link))

    # Deduplicate and save to CSV
    unique_links = list(set(all_links))
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["PDF Filename", "GitHub Link"])
        writer.writerows(unique_links)

    print(f"Saved {len(unique_links)} links to {output_csv}")
