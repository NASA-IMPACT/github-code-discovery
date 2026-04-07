# GitHub Code Discovery for NASA-SMD

Tools for Discovering, Classifying, and Searching NASA-Relevant Open-Source Repositories on GitHub

This project provides a modular and scalable framework to automate the discovery of high-value, NASA-related open-source software on GitHub. It includes multiple discovery pipelines based on DOI links, keyword search, curated organization lists, and metadata from the Astrophysics Source Code Library (ASCL).

The system extracts GitHub repository links, retrieves README content and metadata, and classifies repositories for NASA relevance using large language models. It also supports semantic code search that allows users to find relevant code blocks based on natural language queries.

The final output is a structured CSV file that can be used in downstream workflows such as NASA's Science Discovery Engine (SDE).

## Setup Instructions

#### 1. Install UV

Choose one of the following methods:

```bash
# Using pip
pip install uv

# Using Homebrew
brew install uv
```

#### 2. Clone the Repository

```bash
git clone https://github.com/NASA-IMPACT/github-code-discovery.git
```

#### 3. Setup the Environment

```bash
cd github-code-discovery
uv venv
source .venv/bin/activate
```

#### 4. Install Dependencies

```bash
uv pip install -e .
```

#### 5. Configure API Keys

Create and configure your environment variables:

```bash
touch .env
nano .env
```

Add the following to your `.env` file:

```env
S2_API_KEY=your_s2_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
GITHUB_ACCESS_TOKEN=your_github_token_here
```

#### 6. Verify Configuration

Test that your API keys are properly configured:

```bash
python3 scripts/config.py
```

### Next Steps

You're now ready to use the GitHub Code Discovery tool! Check the documentation below for usage instructions and examples.

## Pipeline: DOI Links

A pipeline to extract GitHub repository links from scientific papers using DOI links.

### Features
- Fetches metadata and full-text PDF URLs from Semantic Scholar for a list of DOIs
- Downloads full-text PDFs (if available)
- Extracts GitHub links from PDFs using regex-based heuristics
- Fetches README content from GitHub repos via GraphQL
- Runs a downstream Relevancy classification pipeline on the retrieved repositories

> **Note:** The CSV file must contain a column named `'DOI'`, from which the links will be extracted.

### Usage

```bash
python scripts/gh_search.py dois <doi_csv_file> 

Example:
python scripts/gh_search.py dois ./data/extracted_dois.csv 
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
python scripts/gh_search.py keywords "<search_keyword>" <days_back> 

Example:
python scripts/gh_search.py keywords "Hubble" 90 
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
python scripts/gh_search.py ascl
```

## Pipeline: Org Search

A pipeline to discover and classify GitHub repositories from a list of GitHub organizations.

### Features
- Parse each input URL to determine whether it is a direct repository link or an org page.
- For org pages, use the GitHub GraphQL API to enumerate all public repositories under the organization.
- Fetch the README file for each repository.
- Save the list of valid base-level repositories and their READMEs to CSV

> **Note:** The CSV file must contain a column named `'URL'`, from which the links will be extracted.

### Usage

```bash
python scripts/gh_search.py org <input_csv_path> 

Example:
python scripts/gh_search.py org "./data/SMD_Sources.csv"
```

## Pipeline: GitHub Code Search

**Validate setup**

```bash
python scripts/cocde_search.py validate-setup
```

**search repo**

```bash
python scripts/code_search.py search-repo "weather forecasting" --top-k=5
```

**search code**


```bash
python scripts/code_search.py search-code
```

```bash
python scripts/code_search.py search-code "atmospheric pressure simulation"  --output-format=json --output-file="tmp/test.json" --top-cr=10 --top-r=5 --top-fr=5 --top-k=5
```

The search happens at 2 levels:
- First, search for a list of top N repositories (repo search)
- Then search for code in each of those repo (code search per repo)

## Pipeline: Context Enrichment

A pipeline to enrich GitHub repository READMEs with additional context by crawling high-signal external links found in the README content.

### Features
- Extracts and filters high-signal links from READMEs (arxiv, zenodo, readthedocs, huggingface, etc.)
- Crawls extracted links in parallel using Docling for content extraction
- Uses an LLM-based relevancy agent to assess whether crawled content is relevant to the original README
- Only enriches READMEs with content that passes the relevancy check

> **Note:** The input CSV must contain columns `name`, `URL`, and `text` (README content).

### Usage

```bash
python scripts/context_enrichment/enrich_readmes.py --input <input_csv> --output <output_csv> --limit <num_repos> --debug

Example:
python scripts/context_enrichment/enrich_readmes.py --input data/discovered_repos.csv --output data/enriched_repos.csv --limit 5 --debug
```
