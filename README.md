# github-code-discovery
Tools for discoverying github code

# Setup the environment

We use [uv](https://github.com/astral-sh/uv) with virtualenv

## First time -> init project using uv
```bash
uv init
uv venv --python 3.12
```

## activate virtual env

`source venv/bin/activate`

## install pre-commit hooks

```bash
uv pip install pre-commit-hooks
pre-commit install
```



## Pipeline 1 - doi2links

A pipeline to extract GitHub repository links from scientific papers using DOI links.

### Features
- Fetches metadata and full-text PDF URLs from Semantic Scholar for a list of DOIs
- Downloads full-text PDFs (if available)
- Extracts GitHub links from PDFs using regex-based heuristics
- Fetches README content from GitHub repos via GraphQL

### Usage

```bash
python3 doi2links.py ./data/extracted_dois 0 -1
```

```bash
python scripts/test_search.py "https://github.com/NISH1001/tag-generator" "tfidf" --max-files 5 --max-results 10
```
