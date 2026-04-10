"""
reconstruct_dataset.py
======================
Reconstructs the `text` column of a BEIR-style dataset whose source code has
been replaced with dummy/masked text for licensing reasons.

For each row in corpus.jsonl and queries.jsonl, the script fetches the
original source file from GitHub using the stored commit hash, then slices the
relevant character spans to recover the real text.

Reconstruction logic
--------------------
corpus.jsonl
    Uses `code_span`: a list of [start, end] character index pairs into the
    source file. All segments are concatenated; discontinuous segments are
    joined with a configurable breaker string (default: "\\n<BREAKER>\\n").

queries.jsonl
    Uses `type` to determine which span to extract:

    - "function-identifier-code" / "class-identifier-code"
        → extract from `identifier_spans` (first occurrence only)
    - "function-docstring-code"  / "class-docstring-code"
        → extract from `docstring_spans`  (first occurrence only)

    Both `identifier_spans` and `docstring_spans` are lists of [start, end]
    pairs and may be empty (row is skipped if the relevant list is empty).

Row metadata used
-----------------
    repo             GitHub repository in "owner/name" format
    path             File path within the repository
    commit_hash      Full SHA of the commit pinning the exact file version
    type             One of: function-identifier-code, class-identifier-code,
                              function-docstring-code, class-docstring-code
    code_span        [[start, end], ...]  character spans for the code block
    identifier_spans [[start, end], ...]  character spans for the identifier
    docstring_spans  [[start, end], ...]  character spans for the docstring
"""

import argparse
import glob
import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Iterator

import requests
from dotenv import load_dotenv
from tqdm import tqdm

# Load .env from the same directory as this script
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Reconstruct BEIR-style dataset text columns from GitHub source files. "
                "input_path can be a local directory or a HuggingFace dataset URL/ID.",
)
parser.add_argument(
    "input_path",
    nargs="?",
    default="nasa-impact/nasa-science-code-benchmark-v0.1.1",
    help="Local BEIR dataset directory OR HuggingFace dataset ID / URL "
         "(e.g. nasa-impact/nasa-science-code-benchmark-v0.1.1 or "
         "https://huggingface.co/datasets/nasa-impact/nasa-science-code-benchmark-v0.1.1).",
)
parser.add_argument(
    "output_path",
    nargs="?",
    default="/rhome/sawale/indus_traning/sentense_transformers/gen_code_data/TheVault/data/step5_5_reconstruction/nasa-science-code-benchmark-v0.1.1_reconstructed",
    help="Path to write the reconstructed dataset.",
)
parser.add_argument(
    "--output-column",
    default="text",
    help="Column to write the reconstructed value into (default: 'text', which replaces the dummy text). "
         "Set to a different name (e.g. 'text_reconstructed') to add a new column alongside 'text' "
         "for comparison.",
)
parser.add_argument(
    "--segment-breaker",
    default="\n<BREAKER>\n",
    help="String inserted between discontinuous code_span segments (default: '\\n<BREAKER>\\n').",
)
parser.add_argument(
    "--nrows",
    type=int,
    default=None,
    help="If set, reconstruct only the first N rows of corpus.jsonl and queries.jsonl (for testing).",
)
parser.add_argument(
    "--workers",
    type=int,
    default=1,
    help="Number of parallel threads for GitHub fetches (default: 1). "
         "Increase to 8-16 for faster reconstruction — bottleneck is network I/O, not CPU.",
)
parser.add_argument(
    "--github-token",
    default=None,
    help="GitHub personal access token for authenticated requests (5000 req/hr vs 60 req/hr). "
         "Falls back to the GITHUB_TOKEN environment variable if not provided.",
)
args = parser.parse_args()

input_path  = args.input_path
output_path = args.output_path

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SEGMENT_BREAKER = args.segment_breaker

# Token priority: --github-token arg > GITHUB_TOKEN env var > unauthenticated
GITHUB_TOKEN = args.github_token or os.environ.get("GITHUB_TOKEN", "")

# ---------------------------------------------------------------------------
# SOURCE DETECTION
# ---------------------------------------------------------------------------
HF_URL_PREFIX = "https://huggingface.co/datasets/"

def _extract_hf_id(path: str) -> str:
    return path.removeprefix(HF_URL_PREFIX).rstrip("/")

def is_hf_source(path: str) -> bool:
    if path.startswith(HF_URL_PREFIX):
        return True
    parts = path.split("/")
    if len(parts) == 2 and not os.path.exists(path):
        return True
    return False

# ---------------------------------------------------------------------------
# ROW ITERATORS
# ---------------------------------------------------------------------------

def iter_local_jsonl(file_path: str) -> Iterator[dict]:
    with open(file_path) as f:
        for line in f:
            yield json.loads(line)


def iter_hf_split(dataset_id: str, split: str) -> Iterator[dict]:
    """Download corpus.jsonl / queries.jsonl directly from the HF Hub and iterate rows.

    The corpus and queries files are plain JSONL files in the dataset repo, not
    named dataset configs, so load_dataset(..., config="corpus") does not work.
    hf_hub_download fetches the file to the local HF cache and returns its path.
    """
    from huggingface_hub import hf_hub_download
    local_path = hf_hub_download(
        repo_id=dataset_id,
        filename=f"{split}.jsonl",
        repo_type="dataset",
    )
    yield from iter_local_jsonl(local_path)

# ---------------------------------------------------------------------------
# STEP 1 – fetch raw file from GitHub
#   • thread-local Session for connection reuse per thread
#   • thread-safe in-memory cache shared across all threads
# ---------------------------------------------------------------------------
_file_cache: dict[tuple[str, str, str], str | None] = {}
_cache_lock  = threading.Lock()
_thread_local = threading.local()


def _get_session() -> requests.Session:
    """Return a per-thread requests.Session (created on first use)."""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        if GITHUB_TOKEN:
            session.headers.update({"Authorization": f"token {GITHUB_TOKEN}"})
        _thread_local.session = session
    return _thread_local.session


def fetch_github_file(repo: str, commit_hash: str, path: str) -> str | None:
    """Return raw file content at a specific commit, or None on failure."""
    key = (repo, commit_hash, path)

    with _cache_lock:
        if key in _file_cache:
            return _file_cache[key]

    url     = f"https://raw.githubusercontent.com/{repo}/{commit_hash}/{path}"
    session = _get_session()
    content = None

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                content = resp.text
                break
            if resp.status_code == 404:
                tqdm.write(f"  [404] {url}")
                break
            if resp.status_code == 429:
                wait = 2 ** (attempt + 2)
                tqdm.write(f"  [429] rate-limited, waiting {wait}s …")
                time.sleep(wait)
                continue
        except requests.RequestException as e:
            tqdm.write(f"  [error] {url}: {e}")
            time.sleep(2 ** attempt)

    with _cache_lock:
        _file_cache[key] = content
    return content

# ---------------------------------------------------------------------------
# STEP 2 – span extraction helpers
# ---------------------------------------------------------------------------

def extract_spans(content: str, spans: list, breaker: str = SEGMENT_BREAKER) -> str:
    segments = [content[int(s[0]):int(s[1])] for s in spans]
    return breaker.join(segments) if len(segments) > 1 else (segments[0] if segments else "")


def reconstruct_corpus_text(row: dict, content: str) -> str:
    return extract_spans(content, row["code_span"])


def reconstruct_query_text(row: dict, content: str) -> str:
    if "identifier" in row.get("type", ""):
        spans = row.get("identifier_spans", [])
    else:
        spans = row.get("docstring_spans", [])
    if not spans:
        return ""
    return extract_spans(content, [spans[0]])


def _process_row(row: dict, mode: str, output_column: str) -> tuple[dict, bool]:
    """Fetch + reconstruct a single row. Returns (row, success)."""
    repo        = row.get("repo", "")
    path        = row.get("path", "")
    commit_hash = row.get("commit_hash", "")

    content = fetch_github_file(repo, commit_hash, path)
    if content is None:
        tqdm.write(f"  [skip] {repo}@{commit_hash[:8]}:{path}")
        return row, False

    reconstructed = (
        reconstruct_corpus_text(row, content)
        if mode == "corpus"
        else reconstruct_query_text(row, content)
    )
    row[output_column] = reconstructed
    return row, True

# ---------------------------------------------------------------------------
# STEP 3 – reconstruct from a row iterator
# ---------------------------------------------------------------------------

def reconstruct_from_rows(
    rows: Iterator[dict],
    output_file: str,
    mode: str,
    output_column: str = "text",
    nrows: int | None = None,
    workers: int = 1,
) -> tuple[int, int]:
    """Returns (total, failed) counts."""
    assert mode in ("corpus", "queries")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    row_list = []
    for row in rows:
        if nrows is not None and len(row_list) >= nrows:
            break
        row_list.append(row)

    process = partial(_process_row, mode=mode, output_column=output_column)
    failed  = 0

    with open(output_file, "w") as fout:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = executor.map(process, row_list)
            for row, success in tqdm(results, total=len(row_list), desc=f"  {mode}", unit="rows"):
                if not success:
                    failed += 1
                fout.write(json.dumps(row) + "\n")

    return len(row_list), failed

# ---------------------------------------------------------------------------
# STEP 4 – copy all other files from input to output unchanged
# ---------------------------------------------------------------------------
RECONSTRUCT_FILES = {"corpus.jsonl", "queries.jsonl"}

def copy_other_files_local(src_dir: str, dst_dir: str) -> None:
    for src_path in glob.glob(os.path.join(src_dir, "**", "*"), recursive=True):
        if not os.path.isfile(src_path):
            continue
        if os.path.basename(src_path) in RECONSTRUCT_FILES:
            continue
        rel  = os.path.relpath(src_path, src_dir)
        dest = os.path.join(dst_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src_path, dest)


def copy_qrels_hf(dataset_id: str, dst_dir: str) -> None:
    """Mirror the qrels/ directory from HF Hub to dst_dir using file-level downloads.

    Uses list_repo_files + hf_hub_download to preserve the exact directory
    structure (qrels/division/*.tsv, qrels/programming_language/*.tsv, etc.)
    without relying on dataset configs, which only cover merged splits.
    """
    from huggingface_hub import hf_hub_download, list_repo_files

    try:
        qrels_files = [
            f for f in list_repo_files(dataset_id, repo_type="dataset")
            if f.startswith("qrels/") and f.endswith(".tsv")
        ]
    except Exception as e:
        print(f"  [warn] Could not list HF repo files: {e}")
        return

    if not qrels_files:
        print("  [warn] No qrels TSV files found in HF dataset — skipping qrels.")
        return

    for rel_path in qrels_files:
        try:
            local_path = hf_hub_download(
                repo_id=dataset_id, filename=rel_path, repo_type="dataset"
            )
            dest = os.path.join(dst_dir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(local_path, dest)
            print(f"  Saved {rel_path}")
        except Exception as e:
            print(f"  [warn] Could not download '{rel_path}': {e}")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
t0 = time.time()

use_hf = is_hf_source(input_path)

if use_hf:
    dataset_id = _extract_hf_id(input_path)
    print(f"Source: HuggingFace dataset  →  {dataset_id}")
    corpus_rows  = iter_hf_split(dataset_id, "corpus")
    queries_rows = iter_hf_split(dataset_id, "queries")
else:
    print(f"Source: local directory  →  {input_path}")
    corpus_rows  = iter_local_jsonl(os.path.join(input_path, "corpus.jsonl"))
    queries_rows = iter_local_jsonl(os.path.join(input_path, "queries.jsonl"))

output_col = args.output_column
if output_col != "text":
    print(f"Output column: '{output_col}'  (new column alongside 'text' for comparison)")
else:
    print("Output column: 'text'  (replacing dummy text in-place)")

print(f"Workers: {args.workers}  |  nrows: {args.nrows or 'all'}\n")

print("Reconstructing corpus.jsonl …")
c_total, c_failed = reconstruct_from_rows(
    corpus_rows, os.path.join(output_path, "corpus.jsonl"),
    mode="corpus", output_column=output_col, nrows=args.nrows, workers=args.workers,
)

print("\nReconstructing queries.jsonl …")
q_total, q_failed = reconstruct_from_rows(
    queries_rows, os.path.join(output_path, "queries.jsonl"),
    mode="queries", output_column=output_col, nrows=args.nrows, workers=args.workers,
)

print("\nCopying other files …")
if use_hf:
    copy_qrels_hf(dataset_id, os.path.join(output_path, "qrels"))
else:
    copy_other_files_local(input_path, output_path)

elapsed = time.time() - t0
print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  corpus.jsonl   {c_total - c_failed:>7,} / {c_total:,} reconstructed  ({c_failed} skipped)
  queries.jsonl  {q_total - q_failed:>7,} / {q_total:,} reconstructed  ({q_failed} skipped)
  Output column: {output_col}
  Time elapsed:  {elapsed:.1f}s
  Output:        {output_path}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")
