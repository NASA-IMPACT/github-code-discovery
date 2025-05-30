from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_TOKEN = os.getenv("OPENAI_API_KEY")
S2_TOKEN = os.getenv("S2_TOKEN")
