from __future__ import annotations
import json
import time
import pandas as pd
import requests
from loguru import logger

def get_github_readme(repo_url: str, token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    owner, repo = repo_url.rstrip("/").split("/")[-2:]

    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        object(expression: "HEAD:README.md") {
          ... on Blob {
            text
          }
        }
      }
    }
    """

    variables = {
        "owner": owner,
        "name": repo,
    }

    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=headers,
    )

    if not response.ok:
        logger.error(f"GraphQL query failed: {response.status_code} {response.text}")


    data = response.json()
    readme_text = data["data"]["repository"]["object"]["text"]
    return {"readme_text": readme_text}


def process_github_links_from_csv(
    token: str,
    links_csv_path: str = "./doi_results/extracted_github_links.csv",
    json_output_path: str = "data/github_repo_readme.json",
    csv_output_path: str = "data/github_repo_readme.csv",
    sleep_time: float = 1.0,
):
    """
    Reads GitHub repo URLs from a CSV, fetches README contents using GraphQL,
    and saves the output to both JSON and CSV formats.

    Args:
        links_csv_path: Path to input CSV with a 'GitHub Link' column.
        token: GitHub token for API access.
        json_output_path: File path to save full README results in JSON.
        csv_output_path: File path to save flattened CSV output.
        sleep_time: Time (in seconds) to sleep between requests.
    """
    df = pd.read_csv(links_csv_path)
    links = df["GitHub Link"].dropna().unique().tolist()

    output_data = {}
    logger.info(f"Fetching GitHub README files...")

    for link in links:
        logger.info(f"Processing {link}")
        try:
            info = get_github_readme(link, token=token)
            output_data[link] = info
            time.sleep(sleep_time)  # avoid rate limits
        except Exception as e:
            logger.error(f"Failed for {link}: {e}")

    # Save JSON
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    logger.info(f"Saved README info to {json_output_path}")

    # Save CSV
    csv_rows = [
        {
            "repo_url": k,
            "readme_text": v["readme_text"].replace("\n", " ")
            if v.get("readme_text")
            else "",
        }
        for k, v in output_data.items()
    ]
    pd.DataFrame(csv_rows).to_csv(csv_output_path, index=False)
    logger.info(f"Saved README CSV to {csv_output_path}")
