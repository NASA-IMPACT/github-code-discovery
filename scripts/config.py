from __future__ import annotations
import os
import gdown
from loguru import logger
from dotenv import load_dotenv
load_dotenv()

GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")
if not GITHUB_ACCESS_TOKEN:
    logger.error("GITHUB_ACCESS_TOKEN environment variable not set. GitHub API access may fail.")
else:
    logger.info("GITHUB_ACCESS_TOKEN environment variable set.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY environment variable not set. OpenAI API access may fail.")
else:
    logger.info("OPENAI_API_KEY environment variable set.")

S2_API_KEY = os.getenv("S2_API_KEY")
if not S2_API_KEY:
    logger.error("S2_API_KEY environment variable not set. SemanticScholar API access may fail.")
else:
    logger.info("S2_API_KEY environment variable set.")

# Download the data from Google Drive
if not os.path.exists("./data/repositories_with_embeddings.csv"):
    file_id = "1nPaEWD9Wuf115aEmqJQusCvJlPc7AP7O"
    gdown.download(f"https://drive.google.com/uc?id={file_id}", "./data/repositories_with_embeddings.csv", quiet=False)
else:
    logger.info("Repositories with embeddings already downloaded.")

if not os.path.exists("./data/results_cache.csv"):
    file_id = "1hw_ceiWc1rGnMO0tV4spk-5ikHUgqJZ5"
    gdown.download(f"https://drive.google.com/uc?id={file_id}", "./data/results_cache.csv", quiet=False)
else:
    logger.info("Results cache already downloaded.")



