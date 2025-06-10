#!/usr/bin/env python3
"""
Multi-Repository Code Search CLI

A command-line interface for searching code across multiple GitHub repositories
using semantic embeddings and weighted scoring.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
import pandas as pd
from loguru import logger
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Core Components
from gcd.embeddings import Embedder
from gcd.scorer import WeightedAverageSelectiveScorer
from gcd.search import LocalCloneBasedGitHubCodeSearcher, MultiRepoCodeSearcher
from gcd.vectorizer import RepoFinder

from config import GITHUB_ACCESS_TOKEN
github_access_token = GITHUB_ACCESS_TOKEN
if not github_access_token:
    logger.error("Error: GITHUB_ACCESS_TOKEN environment variable not set")

@click.command()
@click.argument("query", required=True)
@click.option(
    "--github-access-token",
    default=github_access_token,
    help="GitHub access token for API requests (default: env GITHUB_ACCESS_TOKEN)",
)
@click.option(
    "--top-k",
    "-k",
    default=25,
    type=int,
    help="Final number of code elements to return (default: 25)",
)
@click.option(
    "--top-cr",
    default=15,
    type=int,
    help="Number of code elements per repo to consider (default: 15)",
)
@click.option(
    "--top-fr",
    default=25,
    type=int,
    help="Max files to scan per repo (default: 25)",
)
@click.option(
    "--top-r",
    "-r",
    default=10,
    type=int,
    help="Number of top repos to search within (default: 10)",
)
@click.option(
    "--data-file",
    "-d",
    default="data/repositories_with_embeddings.csv",
    type=click.Path(exists=True),
    help="Path to repositories CSV file",
)
@click.option(
    "--cache-dir",
    "-c",
    default="tmp/cloned_repos",
    help="Directory for caching cloned repositories (default: tmp/cloned_repos)",
)
@click.option(
    "--threshold",
    "-t",
    default=0.5,
    type=float,
    help="Scoring threshold (default: 0.5)",
)
@click.option(
    "--debug/--no-debug",
    default=False,
    help="Enable debug output",
)
@click.option(
    "--output-format",
    "-f",
    type=click.Choice(["pretty", "json", "csv"]),
    default="pretty",
    help="Output format (default: pretty)",
)
@click.option(
    "--output-file",
    "-o",
    type=click.Path(),
    help="Save results to file (format determined by extension)",
)
@click.option(
    "--embedding-model",
    default="all-MiniLM-L6-v2",
    help="Embedding model to use (default: all-MiniLM-L6-v2)",
)
@click.option(
    "--embedding-max-seq-length",
    default=512,
    type=int,
    help="Maximum sequence length for embeddings (default: 512)",
)
@click.option(
    "--weight-name",
    default=0.35,
    type=float,
    help="Weight for name scoring (default: 0.35)",
)
@click.option(
    "--weight-code",
    default=0.2,
    type=float,
    help="Weight for code scoring (default: 0.2)",
)
@click.option(
    "--weight-docstring",
    default=0.35,
    type=float,
    help="Weight for docstring scoring (default: 0.35)",
)
@click.option(
    "--weight-signature",
    default=0.05,
    type=float,
    help="Weight for signature scoring (default: 0.05)",
)
@click.option(
    "--weight-filepath",
    default=0.05,
    type=float,
    help="Weight for file path scoring (default: 0.05)",
)
def search_code(
    query,
    github_access_token,
    top_k,
    top_cr,
    top_fr,
    top_r,
    data_file,
    cache_dir,
    threshold,
    debug,
    output_format,
    output_file,
    embedding_model,
    embedding_max_seq_length,
    weight_name,
    weight_code,
    weight_docstring,
    weight_signature,
    weight_filepath,
):
    """
    Search for code across multiple GitHub repositories using semantic embeddings.

    QUERY: The search query to find relevant code (e.g., "detect oil rigs")
    """

    # Validate GitHub token
    if not github_access_token:
        click.echo(
            "Error: GITHUB_ACCESS_TOKEN environment variable not set!", err=True
        )
        sys.exit(1)

    # Validate weights sum to 1.0 (approximately)
    total_weight = (
        weight_name
        + weight_code
        + weight_docstring
        + weight_signature
        + weight_filepath
    )
    if abs(total_weight - 1.0) > 0.01:
        click.echo(f"Warning: Weights sum to {total_weight:.3f}, not 1.0", err=True)

    if debug:
        click.echo(f"Initializing embedder with model: {embedding_model}")

    try:
        # Initialize embedder
        embedder = Embedder(
            embedding_model,
            model_max_seq_length=embedding_max_seq_length,
            debug=debug,
        )

        # Create scorer with custom weights
        scorer = WeightedAverageSelectiveScorer(
            embedder=embedder,
            debug=debug,
            threshold=threshold,
            weights={
                "name": weight_name,
                "code": weight_code,
                "docstring": weight_docstring,
                "signature": weight_signature,
                "file_path": weight_filepath,
            },
        )

        if debug:
            click.echo(f"Loading repository data from: {data_file}")

        # Load repository data
        data = pd.read_csv(data_file)

        # Initialize searcher
        searcher = LocalCloneBasedGitHubCodeSearcher(
            github_access_token,
            scorer=scorer,
            debug=debug,
            cache_dir=cache_dir,
        )

        # Initialize repository finder
        repo_finder = RepoFinder(embedder=embedder, data=data, debug=debug)

        # Initialize multi-repo code searcher
        code_searcher = MultiRepoCodeSearcher(
            repo_finder=repo_finder,
            scorer=scorer,
            searcher=searcher,
        )

        if debug:
            click.echo("Starting search with parameters:")
            click.echo(f"  Query: {query}")
            click.echo(f"  Top K results: {top_k}")
            click.echo(f"  Top code elements per repo: {top_cr}")
            click.echo(f"  Top files per repo: {top_fr}")
            click.echo(f"  Top repositories: {top_r}")

        # Perform the search
        with click.progressbar(length=1, label="Searching repositories") as bar:
            results = code_searcher.search_code(
                query=query,
                top_k=top_k,
                top_cr=top_cr,
                top_fr=top_fr,
                top_r=top_r,
            )
            bar.update(1)

        # Output results
        if len(results) == 0:
            click.echo("No results found for your query.")
            return

        click.echo(f"\nSearch complete. Found {len(results)} results.")

        results_serializable = [r.model_dump() for r in results]
        # determine output format
        searcher.print_results(results, show_code=True)
        if output_file:
            output_file = Path(output_file)
            if output_file.suffix == ".json":
                output_format = "json"
            elif output_file.suffix == ".csv":
                output_format = "csv"
            else:
                output_format = "pretty"

        if output_format == "json":
            import json

            if output_file:
                with open(output_file, "w") as f:
                    json.dump(results_serializable, f, indent=4)
                click.echo(f"Results saved to {output_file}")
            else:
                click.echo(json.dumps(results_serializable, indent=4))
        elif output_format == "csv":
            if output_file:
                pd.DataFrame(results_serializable).to_csv(output_file, index=False)
                click.echo(f"Results saved to {output_file}")
            else:
                click.echo(pd.DataFrame(results_serializable).to_csv(index=False))

    except Exception as e:
        click.echo(f"Error during search: {str(e)}", err=True)
        if debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@click.group()
def cli():
    """Multi-Repository Code Search CLI Tool"""
    pass


@cli.command()
def validate_setup():
    """Validate that all required components are properly configured."""
    click.echo("Validating setup...")

    # Check GitHub token
    github_token = os.getenv("GITHUB_ACCESS_TOKEN")
    if github_token:
        click.echo("✓ GitHub token found")
    else:
        click.echo("✗ GitHub token not found (set GITHUB_ACCESS_TOKEN)")

    # Check data file
    data_file = "data/repositories_with_embeddings.csv"
    if os.path.exists(data_file):
        click.echo("✓ Repository data file found")
    else:
        click.echo(f"✗ Repository data file not found: {data_file}")

    # Check if we can import required modules
    try:
        from gcd.embeddings import Embedder

        click.echo("✓ GCD embeddings module available")
    except ImportError:
        click.echo("✗ GCD embeddings module not found")

    try:
        from gcd.search import MultiRepoCodeSearcher

        click.echo("✓ GCD search module available")
    except ImportError:
        click.echo("✗ GCD search module not found")


cli.add_command(search_code)

if __name__ == "__main__":
    cli()
