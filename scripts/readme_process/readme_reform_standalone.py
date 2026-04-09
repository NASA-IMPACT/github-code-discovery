"""
Standalone README Reformulation Script

This script processes CSV files containing README content and reformulates them
for better vector search performance. It only depends on:
- akd.agents._base (BaseAgentConfig, LiteLLMInstructorBaseAgent)
- akd._base (InputSchema, OutputSchema)
- Standard library + pandas
"""

import sys
import os
import asyncio
import json
import argparse
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import Field

from akd._base import InputSchema, OutputSchema
from akd.agents._base import BaseAgentConfig, LiteLLMInstructorBaseAgent


# ============================================================================
# Inlined Prompt (from akd.configs.code_prompts)
# ============================================================================

README_REFORMULATION_PROMPT = """IDENTITY and PURPOSE:
You are a README reformulation specialist. Your task is to convert markdown-formatted README files into plain text that is optimized for vector search and semantic similarity matching.

## Core Objectives:
1. **Remove formatting artifacts**: Strip markdown syntax, HTML tags, and formatting that doesn't contribute to meaning
2. **Preserve and enhance semantic content**: Keep all meaningful information while making it more searchable
3. **Expand technical concepts**: Add brief explanations for acronyms, technical terms, and domain-specific language
4. **Improve context**: Make implicit information explicit for better search matching
5. **Structure for search**: Organize content to maximize vector similarity with potential search queries

## Transformation Guidelines:

### Content Preservation:
- Keep all essential information: project purpose, features, usage instructions, requirements
- Preserve code examples but format them as plain text descriptions when beneficial
- Maintain logical flow and relationships between concepts

### Formatting Cleanup:
- Remove markdown headers, bold/italic formatting, lists formatting, links formatting
- Convert tables to natural language descriptions
- Transform code blocks into descriptive text when appropriate
- Eliminate badges, shields, and decorative elements

### Semantic Enhancement:
- Expand abbreviations (e.g., "API" → "API application programming interface")
- Add context for technical terms (e.g., "React" → "React JavaScript frontend framework")
- Make implicit relationships explicit (e.g., mention what technologies work together)
- Include synonyms and alternative terms users might search for

### Search Optimization:
- Use natural language that matches how users would describe or search for the project
- Include problem-solution language (what problems does this solve?)
- Add use case descriptions and application scenarios
- Include relevant domain terminology and concepts

## Output Requirements:
- Generate flowing, natural text that reads coherently
- Ensure all key concepts are preserved and enhanced
- Create content that would match diverse search queries about the project
- Extract key topics that capture the project's essence
- Provide a clear, comprehensive summary

Focus on making the content as discoverable and semantically rich as possible while maintaining accuracy and completeness."""


# ============================================================================
# Inlined Schemas (from akd.agents.readme)
# ============================================================================


class ReadmeReformulationAgentInputSchema(InputSchema):
    """
    Input schema for the README Reformulation Agent.
    """

    readme: str = Field(..., description="The original README content with markdown formatting")
    project_context: Optional[str] = Field(
        None,
        description="Additional context about the project (e.g., from repository metadata)",
    )


class ReadmeReformulationAgentOutputSchema(OutputSchema):
    """
    Output schema for reformulated README content optimized for vector search.

    This schema represents a cleaned, plain-text version of the README that removes
    formatting artifacts while preserving and enhancing semantic content for better
    vector similarity matching.
    """

    reformulated_content: str = Field(..., description="Plain text version of README optimized for vector search")
    key_topics: list[str] = Field(..., description="List of key topics and concepts extracted from the README")
    summary: str = Field(
        ...,
        description="Concise summary of what the project does and its main features",
    )


class ReadmeReformulationAgent(
    LiteLLMInstructorBaseAgent[ReadmeReformulationAgentInputSchema, ReadmeReformulationAgentOutputSchema]
):
    """
    Agent that reformulates README content into plain text optimized for vector search.

    This agent:
    - Removes markdown formatting while preserving semantic content
    - Expands abbreviations and technical jargon with explanations
    - Adds contextual information to improve search relevance
    - Structures content in a way that enhances vector similarity matching
    - Eliminates redundant formatting artifacts that don't contribute to meaning

    The output is designed to improve vector search performance by making the content
    more semantically rich and removing noise from markdown syntax.
    """

    input_schema = ReadmeReformulationAgentInputSchema
    output_schema = ReadmeReformulationAgentOutputSchema


# ============================================================================
# Processing Logic
# ============================================================================


async def process_one(
    row, agent, out_dir: Path, id_field: str, idx: int, pause_s: float = 0.0
):
    """Process a single row and write a JSON file."""
    rid = row.get(id_field, idx)  # fallback to index if no id column
    out_path = out_dir / f"{rid}.json"

    # Resume-friendly: skip if already done
    if out_path.exists():
        print(f"[{rid}] Already processed, skipping")
        return

    # Basic retries to handle transient model errors
    openai_model = "gpt-4o-mini"
    inp = ReadmeReformulationAgentInputSchema(readme=row["text"])

    for attempt in range(3):
        try:
            result = await agent.arun(inp)

            payload = {
                "repo_id": rid,
                "repo_url": row.get("URL", ""),
                "reformulated_content": result.reformulated_content,
                "key_topics": result.key_topics,
            }

            with open(out_path, "w") as f:
                json.dump(payload, f, indent=2)

            print(f"[{rid}] Successfully processed")
            if pause_s:
                await asyncio.sleep(pause_s)
            return
        except Exception as e:
            # simple exponential backoff
            backoff = 0.5 * (2**attempt)
            print(
                f"[{rid}] attempt {attempt + 1}/3 failed: {e} -> retrying in {backoff:.1f}s"
            )
            await asyncio.sleep(backoff)

    # If all retries failed, try with OpenAI model
    try:
        print(f"[{rid}] Switching to OpenAI model after 3 failed attempts")
        cfg = BaseAgentConfig(
            model_name=openai_model,
            base_url="https://api.openai.com/v1/",
            system_prompt=README_REFORMULATION_PROMPT,
        )
        openai_agent = ReadmeReformulationAgent(config=cfg)
        result = await openai_agent.arun(inp)

        payload = {
            "repo_id": rid,
            "repo_url": row.get("URL", ""),
            "reformulated_content": result.reformulated_content,
            "key_topics": result.key_topics,
        }
        with open(out_path, "w") as f:
            json.dump(payload, f, indent=2)

        print(f"[{rid}] Successfully processed with OpenAI model")
        if pause_s:
            await asyncio.sleep(pause_s)
        return
    except Exception as e:
        print(f"[{rid}] Failed with OpenAI model as well: {e}")
        return


async def process_batch(
    batch_rows,
    agent,
    out_dir: Path,
    id_field: str,
    batch_start_idx: int,
    pause_s: float = 0.0,
):
    """Process a batch of rows concurrently."""
    tasks = []
    for i, (idx, row) in enumerate(batch_rows):
        task = process_one(row, agent, out_dir, id_field or "", idx, pause_s)
        tasks.append(task)

    # Wait for all tasks in this batch to complete
    await asyncio.gather(*tasks, return_exceptions=True)
    print(f"Completed batch starting at index {batch_start_idx}")


async def main(
    csv_path: str,
    output_dir: str = "results_readme_reformulated",
    model_name: str = "ollama/qwen3:4b",
    base_url: str = "http://localhost:11434/",
    batch_size: int = 10,
    pause_s: float = 0.0,
):
    """Main processing function."""
    df = pd.read_csv(csv_path)

    cfg = BaseAgentConfig(
        model_name=model_name,
        base_url=base_url,
        system_prompt=README_REFORMULATION_PROMPT,
    )
    agent = ReadmeReformulationAgent(config=cfg)

    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)

    # Choose an id column if present; fall back to 'id' or index
    id_field = (
        "id" if "id" in df.columns else ("repo_id" if "repo_id" in df.columns else None)
    )

    # PARALLEL: process in batches
    total_rows = len(df)

    for batch_start in range(0, total_rows, batch_size):
        batch_end = min(batch_start + batch_size, total_rows)
        batch_rows = list(df.iloc[batch_start:batch_end].iterrows())

        print(
            f"Processing batch {batch_start // batch_size + 1}: rows {batch_start} to {batch_end - 1}"
        )
        await process_batch(
            batch_rows, agent, out_dir, id_field, batch_start, pause_s=pause_s
        )


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Standalone README Reformulation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using local Ollama
  python readme_reform_standalone.py --csv data.csv --model ollama/qwen3:4b --base-url http://localhost:11434/

  # Using OpenAI
  python readme_reform_standalone.py --csv data.csv --model gpt-4o-mini --base-url https://api.openai.com/v1/

  # Custom output directory and batch size
  python readme_reform_standalone.py --csv data.csv --output results/ --batch-size 5
        """,
    )
    parser.add_argument(
        "--csv",
        type=str,
        required=True,
        help="Path to the input CSV file with README content (must have 'text' column)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results_readme_reformulated",
        help="Output directory for JSON results (default: results_readme_reformulated)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="ollama/qwen3:4b",
        help="Model name in LiteLLM format (default: ollama/qwen3:4b)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:11434/",
        help="Base URL for the model API (default: http://localhost:11434/)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of rows to process concurrently (default: 10)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.0,
        help="Pause in seconds between successful requests (default: 0.0)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(f"Running README Reformulation Agent in parallel batches of {args.batch_size}...")
    print(f"Input CSV: {args.csv}")
    print(f"Output directory: {args.output}")
    print(f"Model: {args.model}")
    print(f"Base URL: {args.base_url}")
    asyncio.run(
        main(
            csv_path=args.csv,
            output_dir=args.output,
            model_name=args.model,
            base_url=args.base_url,
            batch_size=args.batch_size,
            pause_s=args.pause,
        )
    )
