from __future__ import annotations
import os
from loguru import logger
from dotenv import load_dotenv
load_dotenv()

GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")
if not GITHUB_ACCESS_TOKEN:
    logger.error("GITHUB_TOKEN environment variable not set. GitHub API access may fail.")
else:
    logger.info("GITHUB_TOKEN environment variable set.")

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

