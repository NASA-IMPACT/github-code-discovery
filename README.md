# github-code-discovery
Tools for discoverying github code

## Setup Instructions

#### 1. Install UV

Choose one of the following methods:

```bash
# Using pip
pip install uv

# Using Homebrew (macOS)
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

You're now ready to use the GitHub Code Discovery tool! Check the documentation for usage instructions and examples.

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
python scripts/gh_search.py dois <doi_csv_file> <start_row> <end_row>

Example:
python scripts/gh_search.py dois ./data/extracted_dois.csv 0 -1
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
python scripts/gh_search.py keywords "<search_keyword>" <days_back> <output_csv_path>

Example:
python scripts/gh_search.py keywords "NASA" 90 ./results/kw_output.csv
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

## Pipeline: GitHub Code Search

**Validate setup**

```bash
python scripts/cocde_search.py validate-setup
```

**search code**


```bash
python scripts/code_search.py search-code "simulation"
```

```bash
python scripts/code_search.py search-code "atmospheric pressure simulation"  --output-format=json --output-file="tmp/test.json" --top-cr=10 --top-r=5 --top-fr=5 --top-k=5
```

The search happens at 2 levels:
- First, search for a list of top N repotories
- Then search for code in each of those repo
