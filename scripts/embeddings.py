#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gcd.embeddings import Embedder
from gcd.vectorizer import RepoFinder


def main():
    # embedder = Embedder("nomic-ai/CodeRankEmbed", trust_remote_code=True)
    embedder = Embedder(
        "jinaai/jina-embeddings-v2-base-code",
        trust_remote_code=True,
        model_max_seq_length=1024,
    )
    # embedder = Embedder("sentence-transformers/all-MiniLM-L6-v2", trust_remote_code=True)

    _data = pd.read_csv("data/repositories.csv")  # .head(25)
    # _data = pd.read_csv("data/repositories_with_embeddings.csv")

    # Create vectorizer
    repo_finder = RepoFinder(embedder=embedder, data=_data, debug=True)

    # Generate embeddings
    repo_finder.generate_embeddings(batch_size=16)

    # Save to CSV
    repo_finder.save_to_csv("data/repositories_with_embeddings_jina.csv")


if __name__ == "__main__":
    main()
