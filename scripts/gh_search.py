from __future__ import annotations

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import click
from gcd.doi_pipeline import run_doi_pipeline
from gcd.ascl_pipeline import run_ascl_pipeline
from gcd.keyword_pipeline import run_keyword_pipeline
from config import GITHUB_ACCESS_TOKEN

@click.group()
def cli():
    """Unified CLI to search GitHub for NASA-related repositories"""
    pass

@cli.command()
@click.argument("csv_path", type=click.Path(exists=True))
@click.argument("start_row", type=int)
@click.argument("end_row", type=int)
def dois(csv_path, start_row, end_row):
    """Run pipeline with a list of DOIs"""
    run_doi_pipeline(GITHUB_ACCESS_TOKEN,csv_path, start_row, end_row)

@cli.command()
def ascl():
    """Run pipeline for ASCL dataset"""
    run_ascl_pipeline(GITHUB_ACCESS_TOKEN)

@cli.command()
@click.argument("keyword", type=str)
@click.argument("days_back", type=int)
@click.argument("output_csv_path", type=click.Path())
def keywords(keyword, days_back, output_csv_path):
    """Run keyword-based GitHub search pipeline"""
    run_keyword_pipeline(keyword, days_back, output_csv_path, GITHUB_ACCESS_TOKEN)

if __name__ == "__main__":
    cli()


