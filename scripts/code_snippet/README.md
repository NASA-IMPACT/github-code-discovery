# Code Snippet Reconstruction

`reconstruct_dataset.py` populates the placeholder `text` column in the
[NASA Science Code Benchmark](https://huggingface.co/datasets/nasa-impact/nasa-science-code-benchmark-v0.1.1)
by fetching the original source files from GitHub and slicing out the exact
character spans stored in each row's metadata.

The benchmark ships with dummy text in place of real source code to respect
repository licensing. Each row carries enough metadata (`repo`, `path`,
`commit_hash`, and span fields) to reconstruct the original content without any
external lookup tables.

## Requirements

```bash
pip install requests python-dotenv tqdm huggingface_hub
```

For HuggingFace input sources, also install:

```bash
pip install datasets
```

Optionally, create a `.env` file in this directory with your GitHub token to
avoid hitting the 60 req/hr unauthenticated rate limit:

```env
GITHUB_TOKEN=ghp_your_token_here
```

## Usage

```bash
python reconstruct_dataset.py [INPUT_PATH] [OUTPUT_PATH] [OPTIONS]
```

`INPUT_PATH` can be:
- A **local directory** containing `corpus.jsonl`, `queries.jsonl`, and `qrels/`
- A **HuggingFace dataset ID** (e.g. `nasa-impact/nasa-science-code-benchmark-v0.1.1`)
- A **HuggingFace URL** (e.g. `https://huggingface.co/datasets/nasa-impact/nasa-science-code-benchmark-v0.1.1`)

### Examples

```bash
# From a local dataset copy
python reconstruct_dataset.py \
    /path/to/nasa-science-code-benchmark-v0.1.1 \
    /path/to/output

# Directly from HuggingFace (downloads corpus.jsonl and queries.jsonl automatically)
python reconstruct_dataset.py \
    nasa-impact/nasa-science-code-benchmark-v0.1.1 \
    /path/to/output

# Faster with parallel workers and an authenticated GitHub token
python reconstruct_dataset.py \
    nasa-impact/nasa-science-code-benchmark-v0.1.1 \
    /path/to/output \
    --workers 8 \
    --github-token ghp_your_token_here

# Test run — reconstruct only the first 10 rows of each file
python reconstruct_dataset.py \
    nasa-impact/nasa-science-code-benchmark-v0.1.1 \
    /path/to/output \
    --nrows 10 \
    --output-column text_reconstructed
```

## Options

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--workers` | `1` | Parallel threads for GitHub fetches. 8–16 recommended — bottleneck is network I/O, not CPU. |
| `--github-token` | `$GITHUB_TOKEN` | GitHub personal access token. Authenticated requests get 5,000 req/hr vs 60 req/hr unauthenticated. Falls back to the `GITHUB_TOKEN` environment variable or `.env` file. |
| `--nrows` | all | Reconstruct only the first N rows of each file. Useful for testing. |
| `--output-column` | `text` | Column to write the reconstructed value into. Defaults to `text`, replacing the placeholder in-place. Set to another name (e.g. `text_reconstructed`) to add a new column alongside the placeholder for comparison. |
| `--segment-breaker` | `\n<BREAKER>\n` | String inserted between discontinuous `code_span` segments. |

## How It Works

1. **Fetch** — for each row, the script requests the raw source file from
   `raw.githubusercontent.com/{repo}/{commit_hash}/{path}`. Files are cached
   in memory so rows sharing the same source file incur only one network request.

2. **Slice** — character spans stored in the row metadata are used to extract
   the relevant text:
   - `corpus.jsonl`: concatenates all `code_span` segments (joined by
     `--segment-breaker` when discontinuous).
   - `queries.jsonl`: extracts the first `identifier_spans` entry for
     `*-identifier-code` rows, or the first `docstring_spans` entry for
     `*-docstring-code` rows.

3. **Write** — reconstructed rows are written to `OUTPUT_PATH/corpus.jsonl`
   and `OUTPUT_PATH/queries.jsonl`. All other files (`qrels/`, etc.) are
   copied from the input unchanged.

## Output

The output directory mirrors the input structure:

```text
output/
├── corpus.jsonl       # text column populated with real source code
├── queries.jsonl      # text column populated with real identifiers/docstrings
└── qrels/             # copied unchanged from input
    ├── division/
    ├── programming_language/
    └── query_type/
```

A summary is printed on completion:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  corpus.jsonl    12345 / 12345 reconstructed  (0 skipped)
  queries.jsonl   88986 / 88986 reconstructed  (0 skipped)
  Output column:  text
  Time elapsed:   142.3s
  Output:         /path/to/output
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Rows are skipped (and a warning is printed) when the GitHub fetch returns a
404 or fails after 3 retries. The row is still written to the output with its
original placeholder text.
