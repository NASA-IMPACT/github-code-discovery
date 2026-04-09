#!/usr/bin/env python3
"""
Division Classification Script

Classifies GitHub repository READMEs into NASA research divisions using an LLM-based agent.
"""
from __future__ import annotations

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import click
import pandas as pd
from loguru import logger
from dotenv import load_dotenv

from gcd.classification_utils import (
    readme_agent,
    classify_all_readmes,
    flatten,
    NasaArea,
    SAMPLE_AVERAGE_COST,
    openai_model,
)

load_dotenv()


MODEL_OPTIONS = {
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-o4-mini": "gpt-o4-mini",
    "gpt-o3": "gpt-o3",
    "gpt-4.1": "gpt-4.1",
    "gpt-4.1-mini": "gpt-4.1-mini",
}


@click.group()
def cli():
    """NASA Division Classification CLI for GitHub repository READMEs."""
    pass


@cli.command()
@click.argument("input_csv", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output CSV path. Defaults to appending to ./data/results_cache.csv",
)
@click.option(
    "--text-column",
    "-t",
    default="readme_text",
    help="Column name containing README text (default: readme_text)",
)
@click.option(
    "--url-column",
    "-u",
    default="repo_url",
    help="Column name containing repository URLs (default: repo_url)",
)
@click.option(
    "--source",
    "-s",
    default="manual",
    help="Source label for classified entries (default: manual)",
)
@click.option(
    "--model",
    "-m",
    type=click.Choice(list(MODEL_OPTIONS.keys())),
    default="gpt-4.1-mini",
    help="OpenAI model to use (default: gpt-4.1-mini)",
)
@click.option(
    "--skip-cache-check",
    is_flag=True,
    help="Skip checking for already classified URLs in the cache",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt and proceed with classification",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Limit the number of READMEs to classify",
)
def classify(
    input_csv: str,
    output: str | None,
    text_column: str,
    url_column: str,
    source: str,
    model: str,
    skip_cache_check: bool,
    yes: bool,
    limit: int | None,
):
    """
    Classify READMEs into NASA research divisions.

    INPUT_CSV: Path to CSV file containing repository URLs and README text.
    """
    logger.info(f"Loading input CSV: {input_csv}")

    try:
        df = pd.read_csv(input_csv)
        if df.empty:
            logger.error("Input CSV is empty. Aborting.")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load input CSV: {e}")
        sys.exit(1)

    # Validate required columns
    if text_column not in df.columns:
        logger.error(f"Column '{text_column}' not found in CSV. Available: {list(df.columns)}")
        sys.exit(1)
    if url_column not in df.columns:
        logger.error(f"Column '{url_column}' not found in CSV. Available: {list(df.columns)}")
        sys.exit(1)

    logger.info(f"Loaded {len(df)} rows from {input_csv}")

    # Remove entries already in cache
    cache_path = "./data/results_cache.csv"
    if not skip_cache_check and os.path.exists(cache_path):
        cache_df = pd.read_csv(cache_path)
        if "URL" in cache_df.columns:
            before_count = len(df)
            df = df[~df[url_column].isin(cache_df["URL"])]
            removed = before_count - len(df)
            if removed > 0:
                logger.info(f"Removed {removed} entries already in cache.")

    # Apply limit if specified
    if limit is not None and limit > 0:
        df = df.head(limit)
        logger.info(f"Limited to {len(df)} entries")

    if len(df) == 0:
        logger.info("No new samples to classify. Exiting.")
        sys.exit(0)

    # Prepare data
    df[text_column] = df[text_column].fillna("")
    texts = [flatten(text) for text in df[text_column].values]
    urls = list(df[url_column].values)

    sample_count = len(texts)
    logger.info(f"Samples to classify: {sample_count}")

    # Set model
    openai_model.name = model
    logger.info(f"Using model: {model}")

    # Cost estimate
    estimated_cost = SAMPLE_AVERAGE_COST * sample_count
    logger.info(f"Estimated cost: ${estimated_cost:.4f} (${SAMPLE_AVERAGE_COST:.4f}/README)")

    # Confirmation
    if not yes:
        confirm = click.confirm("Proceed with classification?", default=True)
        if not confirm:
            logger.info("Aborted by user.")
            sys.exit(0)

    # Run classification
    logger.info("Starting classification...")
    results = asyncio.run(classify_all_readmes(readme_agent, texts, urls))

    # Build results dataframe
    results_df = pd.DataFrame(results)
    total_cost = sum(float(row.get("cost", 0)) for row in results)
    results_df.drop(["cost"], axis=1, inplace=True, errors="ignore")
    results_df["source"] = source

    # Save results
    if output:
        results_df.to_csv(output, index=False)
        logger.info(f"Saved results to {output}")
    else:
        # Append to cache
        if os.path.exists(cache_path):
            results_df.to_csv(cache_path, mode="a", index=False, header=False)
        else:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            results_df.to_csv(cache_path, index=False)
        logger.info(f"Appended results to {cache_path}")

    logger.info(f"Total classification cost: ${total_cost:.4f}")
    logger.info(f"Classification breakdown:\n{results_df['area'].value_counts().to_string()}")


@cli.command()
def divisions():
    """List all NASA research divisions used for classification."""
    click.echo("\nNASA Research Divisions:\n")
    for i, division in enumerate(NasaArea, 1):
        click.echo(f"  {i}. {division.value}")
    click.echo()


@cli.command()
@click.option(
    "--cache-path",
    default="./data/results_cache.csv",
    help="Path to results cache CSV",
)
def stats(cache_path: str):
    """Show classification statistics from the results cache."""
    if not os.path.exists(cache_path):
        logger.error(f"Cache file not found: {cache_path}")
        sys.exit(1)

    df = pd.read_csv(cache_path)

    click.echo(f"\nClassification Statistics ({cache_path}):\n")
    click.echo(f"Total classified: {len(df)}\n")

    click.echo("By Division:")
    for area, count in df["area"].value_counts().items():
        pct = (count / len(df)) * 100
        click.echo(f"  {area}: {count} ({pct:.1f}%)")

    if "source" in df.columns:
        click.echo("\nBy Source:")
        for source, count in df["source"].value_counts().items():
            click.echo(f"  {source}: {count}")
    click.echo()


if __name__ == "__main__":
    cli()
