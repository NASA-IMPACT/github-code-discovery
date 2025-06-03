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



## Pipeline: DOI Links

A pipeline to extract GitHub repository links from scientific papers using DOI links.

### Features
- Fetches metadata and full-text PDF URLs from Semantic Scholar for a list of DOIs
- Downloads full-text PDFs (if available)
- Extracts GitHub links from PDFs using regex-based heuristics
- Fetches README content from GitHub repos via GraphQL
- Runs a downstream Relevancy classification pipeline on the retrieved repositories 

### Usage

```bash
python3 doi2links.py ./data/extracted_dois 0 -1
```

## Pipeline: Keyword Search

A pipeline to discover and classify GitHub repositories using keyword-based search over the GitHub API.

### Features
- Searches GitHub repositories using a provided keyword and time range (in days)
- Automatically splits queries into 5 time intervals to bypass the 1000-results-per-query API limitation
- Fetches repository links and README content using GitHub's REST API
- Runs a downstream Relevancy classification pipeline on the retrieved repositories 

### Usage

```bash
python3 kw_search.py "<keyword>" <days_back> <output_csv_path>
```

## Pipeline: ASCL Search

A pipeline to extract and classify GitHub repository links from the Astrophysics Source Code Library (ASCL) JSON index.

### Features
- Fetches the latest metadata from the ASCL API (`https://ascl.net/code/json`)
- Extracts and filters new GitHub repository links not already present in the local dataset
- Retrieves README content for newly found repositories using GitHub's GraphQL API
- Runs a downstream Relevancy classification pipeline on the retrieved repositories 

### Usage

```bash
python3 ascl_search.py
```

## Pipeline: GitHub Code Search

For time being, we can search specific repo.
```bash
python scripts/test_search.py "https://github.com/NISH1001/tag-generator" "tfidf" --max-files 5 --max-results 10
```

We will improve this to be at 2 levels:
- First, search for a list of top N repotories
- Then search for code in each of those repo
