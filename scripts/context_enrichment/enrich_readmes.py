"""
README Link Crawler & Enrichment Pipeline

This script extracts links from GitHub repository READMEs, crawls them,
assesses their relevancy, and enriches repository data with high-quality
external content.

Usage:
    python scripts/enrich_readmes.py --limit 10 --debug
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pandas as pd
from loguru import logger
from tqdm.asyncio import tqdm
from akd.agents.readme import (
    ReadmeContentRelevanceAgent,
    ReadmeContentRelevanceAgentInputSchema,
)
from akd.tools.scrapers.omni import DoclingScraper, DoclingScraperConfig
from akd.tools.misc import HttpUrlAdapter
from akd.utils import is_server_available


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class EnrichmentConfig:
    """Configuration for the enrichment pipeline."""

    # Data paths
    csv_path: str = "docs/repos_ready_for_enrichment.csv"
    output_csv: str = "docs/enriched_repositories.csv"

    # Processing limits
    test_subset_size: int = 10
    max_links_per_repo: int = 20
    max_concurrent_crawls: int = 10
    crawl_timeout: int = 30

    # High-signal domains (papers, docs, datasets)
    high_signal_domains: List[str] = field(default_factory=lambda: [
        # Academic & Research
        "arxiv.org", "doi.org", "dx.doi.org",
        "scholar.google", "researchgate.net", "pubmed.ncbi.nlm.nih.gov",
        "ieee.org", "acm.org", "springer.com", "sciencedirect.com",
        # Data repositories
        "zenodo.org", "figshare.com", "kaggle.com", "dataverse.org",
        "data.nasa.gov", "earthdata.nasa.gov", "datadryad.org",
        # Documentation
        "readthedocs.io", "readthedocs.org", "github.io", "docs.", "documentation.",
        "wiki.", "confluence.", "notion.site",
        # Datasets & Models
        "huggingface.co", "paperswithcode.com", "openml.org",
    ])

    # Exclude patterns (social media, badges, CI/CD)
    exclude_patterns: List[str] = field(default_factory=lambda: [
        "github.com", "gitlab.com", "bitbucket.org",  # Avoid recursive GitHub links
        "twitter.com", "x.com", "linkedin.com", "facebook.com",
        "badge", "shield", "travis-ci", "circleci", "appveyor",
        "codecov.io", "coveralls.io", "codeclimate.com",
        "img.shields.io", "badgen.net",
    ])

    # Content settings
    max_content_chars_assessment: int = 5000  # Max chars for relevancy assessment
    max_content_chars_enrichment: int = 5000  # Max chars per link in enriched output

    # Scraper settings
    scraper_mode: str = "fast"  # "fast" or "accurate"
    use_ocr: bool = False

    # Link validation
    link_validation_timeout: int = 5  # Timeout for link validation in seconds

    # Debug
    debug: bool = False


# ============================================================================
# Link Extractor
# ============================================================================

class LinkExtractor:
    """Extracts and filters high-signal links from README content."""

    def __init__(self, config: EnrichmentConfig):
        self.config = config

    def extract_links(self, readme_text: str) -> List[str]:
        """
        Extract all URLs from README markdown text.

        Handles:
        - Markdown links: [text](url)
        - Plain URLs: http://example.com
        - HTML links: <a href="url">
        """
        if not readme_text:
            return []

        urls = set()

        # Extract markdown links [text](url)
        markdown_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', readme_text)
        urls.update(url for _, url in markdown_links if url.startswith('http'))

        # Extract plain URLs
        plain_urls = re.findall(
            r'https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            readme_text
        )
        urls.update(plain_urls)

        # Extract HTML links <a href="url">
        html_links = re.findall(r'<a\s+href=["\']([^"\']+)["\']', readme_text)
        urls.update(url for url in html_links if url.startswith('http'))

        return list(urls)

    def is_high_signal_domain(self, url: str) -> bool:
        """Check if URL belongs to a high-signal domain."""
        try:
            parsed = urlparse(url.lower())
            domain = parsed.netloc

            # Check if domain matches any high-signal pattern
            for pattern in self.config.high_signal_domains:
                if pattern in domain:
                    return True
            return False
        except Exception as e:
            if self.config.debug:
                logger.debug(f"Error parsing URL {url}: {e}")
            return False

    def should_exclude(self, url: str) -> bool:
        """Check if URL matches exclude patterns."""
        url_lower = url.lower()
        for pattern in self.config.exclude_patterns:
            if pattern in url_lower:
                return True
        return False

    def filter_links(self, urls: List[str]) -> List[str]:
        """Filter URLs to keep only high-signal, non-excluded links."""
        filtered = []
        for url in urls:
            # Skip excluded patterns
            if self.should_exclude(url):
                continue

            # Keep high-signal domains
            if self.is_high_signal_domain(url):
                filtered.append(url)

        return filtered

    def deduplicate(self, urls: List[str]) -> List[str]:
        """Remove duplicate URLs while preserving order."""
        seen = set()
        deduped = []
        for url in urls:
            # Normalize URL (remove trailing slashes, fragments)
            normalized = url.rstrip('/').split('#')[0]
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(url)
        return deduped

    async def validate_links(self, urls: List[str]) -> List[str]:
        """Validate that URLs are reachable using is_server_available in parallel."""
        async def check_url(url: str) -> Optional[str]:
            """Check if a single URL is available using asyncio executor."""
            loop = asyncio.get_event_loop()
            try:
                # Run is_server_available in thread pool to avoid blocking
                is_available = await loop.run_in_executor(None, is_server_available, url)
                if is_available:
                    return url
                elif self.config.debug:
                    logger.debug(f"URL not reachable: {url}")
                return None
            except Exception as e:
                if self.config.debug:
                    logger.debug(f"Error validating {url}: {e}")
                return None

        # Validate all URLs in parallel
        tasks = [check_url(url) for url in urls]
        results = await asyncio.gather(*tasks)
        valid_urls = [url for url in results if url is not None]

        if self.config.debug:
            logger.debug(f"Validated {len(valid_urls)}/{len(urls)} URLs as reachable")

        return valid_urls

    async def extract_and_filter(self, readme_text: str, max_links: int = 20) -> List[str]:
        """
        Extract, filter, deduplicate, and validate links from README.

        Returns up to max_links high-signal, validated URLs.
        """
        # Extract all links
        all_links = self.extract_links(readme_text)

        if self.config.debug:
            logger.debug(f"Extracted {len(all_links)} total links")

        # Filter for high-signal domains
        filtered = self.filter_links(all_links)

        if self.config.debug:
            logger.debug(f"Filtered to {len(filtered)} high-signal links")

        # Deduplicate
        deduped = self.deduplicate(filtered)

        # Validate links (check if reachable) - async and parallel
        validated = await self.validate_links(deduped)

        # Limit to max_links
        result = validated[:max_links]

        if self.config.debug:
            logger.debug(f"Final: {len(result)} links after validation and limiting")

        return result


# ============================================================================
# Parallel Crawler
# ============================================================================

class ParallelCrawler:
    """Crawls URLs in parallel using DoclingScraper."""

    def __init__(self, config: EnrichmentConfig):
        self.config = config

        # Initialize DoclingScraper
        scraper_config = DoclingScraperConfig(
            pdf_mode=config.scraper_mode,
            use_ocr=config.use_ocr,
            export_type="markdown",
            debug=config.debug,
        )
        self.scraper = DoclingScraper(config=scraper_config)

        # Semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(config.max_concurrent_crawls)

    async def crawl_single(self, url: str) -> Optional[Dict[str, Any]]:
        """Crawl a single URL and return content + metadata."""
        async with self.semaphore:
            try:
                # Create scraper input
                from akd.tools.scrapers.omni import OmniScraperInputSchema

                scraper_input = OmniScraperInputSchema(url=url)

                # Crawl with timeout
                result = await asyncio.wait_for(
                    self.scraper.arun(scraper_input),
                    timeout=self.config.crawl_timeout
                )

                return {
                    "url": url,
                    "content": result.content,
                    "metadata": result.metadata.model_dump() if result.metadata else {},
                    "success": True,
                    "error": None,
                }

            except asyncio.TimeoutError:
                logger.warning(f"Timeout crawling {url}")
                return {
                    "url": url,
                    "content": "",
                    "metadata": {},
                    "success": False,
                    "error": "timeout",
                }
            except Exception as e:
                if self.config.debug:
                    logger.warning(f"Error crawling {url}: {e}")
                return {
                    "url": url,
                    "content": "",
                    "metadata": {},
                    "success": False,
                    "error": str(e),
                }

    async def crawl_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Crawl multiple URLs in parallel."""
        if not urls:
            return []

        logger.info(f"Crawling {len(urls)} URLs in parallel (max {self.config.max_concurrent_crawls} concurrent)...")

        tasks = [self.crawl_single(url) for url in urls]
        results = await asyncio.gather(*tasks)

        # Filter out None results
        results = [r for r in results if r is not None]

        # Log statistics
        successful = sum(1 for r in results if r["success"])
        logger.info(f"Crawling complete: {successful}/{len(urls)} successful")

        return results


# ============================================================================
# README Enrichment Pipeline
# ============================================================================

class ReadmeEnrichmentPipeline:
    """End-to-end pipeline for enriching repository data with crawled link content."""

    def __init__(self, config: EnrichmentConfig):
        self.config = config

        # Initialize components
        self.link_extractor = LinkExtractor(config)
        self.crawler = ParallelCrawler(config)

        # Initialize relevancy agent
        self.relevancy_agent = ReadmeContentRelevanceAgent()

    def load_repos(self, start: int = 0, limit: Optional[int] = None) -> pd.DataFrame:
        """Load repository data from CSV with start index and limit."""
        csv_path = Path(self.config.csv_path)

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        logger.info(f"Loading repository data from {csv_path}...")
        df = pd.read_csv(csv_path)

        total_repos = len(df)

        # Apply start index
        if start > 0:
            df = df.iloc[start:]
            logger.info(f"Starting from index {start} (skipped first {start} repos)")

        # Apply limit
        if limit:
            df = df.head(limit)
            end_index = start + len(df)
            logger.info(f"Processing repos {start} to {end_index-1} (limit: {limit})")

        logger.info(f"Loaded {len(df)} repositories out of {total_repos} total")
        return df

    async def process_single_repo(self, repo: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single repository: extract links, crawl, assess, enrich."""
        repo_name = repo.get("name", "Unknown")
        repo_url = repo.get("URL", "")
        readme_text = repo.get("text", "")

        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {repo_name}")
        logger.info(f"{'='*60}")

        # Step 1: Extract links
        links = await self.link_extractor.extract_and_filter(
            readme_text,
            max_links=self.config.max_links_per_repo
        )

        # Filter out recursive links (URLs pointing to same repo)
        filtered_links = []
        recursive_links = []
        for link in links:
            # Check if link points to the same repo
            if repo_url and repo_url.lower() in link.lower():
                recursive_links.append(link)
                if self.config.debug:
                    logger.debug(f"Filtered recursive link: {link}")
            else:
                filtered_links.append(link)

        links = filtered_links
        if recursive_links:
            logger.info(f"Filtered out {len(recursive_links)} recursive links")

        logger.info(f"Extracted {len(links)} high-signal links (after filtering)")

        if not links:
            logger.info(f"No high-signal links found, skipping enrichment")
            return {
                **repo,
                "enriched_text": readme_text,  # No enrichment
                "num_links_extracted": 0,
                "num_links_crawled": 0,
                "num_links_relevant": 0,
                "crawled_urls": json.dumps([]),
                "enrichment_metadata": json.dumps({"status": "no_links"}),
            }

        # Step 2: Crawl links
        crawled_results = await self.crawler.crawl_batch(links)
        successful_crawls = [r for r in crawled_results if r["success"] and r["content"]]

        logger.info(f"Crawled {len(successful_crawls)}/{len(links)} successfully")

        if not successful_crawls:
            logger.info(f"No successful crawls, skipping enrichment")
            return {
                **repo,
                "enriched_text": readme_text,
                "num_links_extracted": len(links),
                "num_links_crawled": 0,
                "num_links_relevant": 0,
                "crawled_urls": json.dumps([]),
                "enrichment_metadata": json.dumps({"status": "crawl_failed"}),
            }

        # Step 3: Assess relevancy using ReadmeContentRelevanceAgent
        logger.info(f"Assessing relevancy for {len(successful_crawls)} crawled pages...")

        relevant_crawls = []
        for crawl in successful_crawls:
            try:
                # Assess each crawled content against README
                assessment_input = ReadmeContentRelevanceAgentInputSchema(
                    readme=readme_text,
                    content=crawl["content"][:self.config.max_content_chars_assessment],
                )

                assessment_result = await self.relevancy_agent.arun(assessment_input)

                if assessment_result.is_relevant:
                    # Add to relevant list with metadata
                    crawl["is_relevant"] = True
                    crawl["relevance_reasoning"] = assessment_result.reasoning
                    relevant_crawls.append(crawl)

                    if self.config.debug:
                        logger.debug(f"{crawl['url']}: {assessment_result.reasoning}")
                elif self.config.debug:
                    logger.debug(f"{crawl['url']}: {assessment_result.reasoning}")

            except Exception as e:
                logger.warning(f"Error assessing {crawl['url']}: {e}")
                continue

        logger.info(f"{len(relevant_crawls)} links passed relevancy check")

        # Step 4: Enrich repository text (simple concatenation)
        enriched_text = readme_text

        # Simply concatenate relevant content without separators
        for crawl in relevant_crawls:
            enriched_text += crawl["content"][:self.config.max_content_chars_enrichment]

        # Step 5: Create enrichment metadata and crawled URLs list
        crawled_urls_list = [c["url"] for c in relevant_crawls]

        metadata = {
            "status": "success",
            "links_extracted": len(links),
            "links_crawled": len(successful_crawls),
            "links_relevant": len(relevant_crawls),
            "recursive_links_filtered": len(recursive_links) if recursive_links else 0,
        }

        return {
            **repo,
            "enriched_text": enriched_text,
            "num_links_extracted": len(links),
            "num_links_crawled": len(successful_crawls),
            "num_links_relevant": len(relevant_crawls),
            "crawled_urls": json.dumps(crawled_urls_list),  # New column: list of URLs that were crawled and deemed relevant
            "enrichment_metadata": json.dumps(metadata),
        }

    async def process_repos(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process all repositories in the dataframe with progress bar."""
        enriched_repos = []

        # Use tqdm for progress bar
        for idx, row in tqdm(
            df.iterrows(),
            total=len(df),
            desc="Processing repos",
            unit="repo"
        ):
            try:
                enriched = await self.process_single_repo(row.to_dict())
                enriched_repos.append(enriched)
            except Exception as e:
                logger.error(f"Error processing repo {row.get('name', 'Unknown')}: {e}")
                # Keep original data on error
                enriched_repos.append({
                    **row.to_dict(),
                    "enriched_text": row.get("text", ""),
                    "num_links_extracted": 0,
                    "num_links_crawled": 0,
                    "num_links_relevant": 0,
                    "enrichment_metadata": json.dumps({"status": "error", "error": str(e)}),
                })

        return pd.DataFrame(enriched_repos)

    async def run(self, start: int = 0, limit: Optional[int] = None) -> pd.DataFrame:
        """Run the complete enrichment pipeline."""
        logger.info("Starting README Enrichment Pipeline")
        logger.info(f"Configuration: {self.config}")

        # Load data
        df = self.load_repos(start=start, limit=limit)

        # Process repositories
        enriched_df = await self.process_repos(df)

        # Save results
        output_path = Path(self.config.output_csv)
        enriched_df.to_csv(output_path, index=False)

        logger.info(f"\n{'='*60}")
        logger.info(f"Pipeline complete!")
        logger.info(f"Enriched data saved to: {output_path}")
        logger.info(f"Total repos processed: {len(enriched_df)}")
        logger.info(f"{'='*60}")

        return enriched_df


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Enrich GitHub repo READMEs with crawled link content")
    parser.add_argument("--input", type=str, default="docs/repositories_with_embeddings_v4.csv",
                       help="Input CSV file (default: docs/repositories_with_embeddings_v4.csv)")
    parser.add_argument("--start", type=int, default=0, help="Start index (default: 0)")
    parser.add_argument("--limit", type=int, default=10, help="Number of repos to process (default: 10)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--output", type=str, help="Output CSV path (default: docs/enriched_repositories.csv)")

    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), level="DEBUG")

    # Create config
    config = EnrichmentConfig(
        csv_path=args.input,  # Use custom input file
        test_subset_size=args.limit,
        debug=args.debug,
    )

    if args.output:
        config.output_csv = args.output

    # Run pipeline
    pipeline = ReadmeEnrichmentPipeline(config)
    await pipeline.run(start=args.start, limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())
