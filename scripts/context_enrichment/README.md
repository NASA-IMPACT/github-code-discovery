# Context Enrichment

Enriches GitHub repository READMEs by crawling external links and appending relevant content. See the [main README](../../README.md#pipeline-context-enrichment) for usage instructions.

## How it works

1. Extracts high-signal links from README text (arxiv, zenodo, readthedocs, huggingface, etc.)
2. Filters out low-value domains (social media, CI/CD badges)
3. Crawls validated links in parallel using Docling
4. Assesses relevancy of crawled content against the original README using an LLM agent
5. Appends only relevant content to the README text

## Requirements

- `OPENAI_API_KEY` in `.env` for LLM-based relevancy assessment
- Dependencies: `akd` framework, `docling`, `pandas`, `loguru`
