from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from gcd.embeddings import EmbeddingScorer
from gcd.search import GitHubCodeSearcher

from config import GITHUB_ACCESS_TOKEN
github_token = GITHUB_ACCESS_TOKEN
if not github_token:
    logger.error("Error: GITHUB_ACCESS_TOKEN environment variable not set")

def main():
    parser = argparse.ArgumentParser(
        description="Search GitHub repositories for Python functions and classes",
    )
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("query", help="Search query for functions/classes")
    parser.add_argument(
        "--max-files",
        type=int,
        default=50,
        help="Maximum number of files to analyze",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum number of results to return",
    )
    parser.add_argument(
        "--output",
        help="Output file to save results (JSON format)",
    )
    parser.add_argument(
        "--no-code",
        action="store_true",
        help="Don't show code in console output",
    )

    args = parser.parse_args()

    try:
        scorer = EmbeddingScorer(
            "sentence-transformers/all-MiniLM-L6-v2",
            debug=True,
        )

        weights = {
            "name": 0.45,
            "docstring": 0.45,
            "signature": 0.05,
            "file_path": 0.05,
        }
        searcher = GitHubCodeSearcher(github_token, scorer=scorer)
        elements = searcher.search_code_elements(
            args.repo_url,
            args.query,
            args.max_files,
            args.max_results,
            weights=weights,
        )
        logger.debug(f"{len(elements)} searched for the query={args.query}")
        searcher.print_results(elements, show_code=not args.no_code)

        if args.output:
            searcher.export_results(elements, args.output)

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
