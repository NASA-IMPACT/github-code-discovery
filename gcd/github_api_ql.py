from __future__ import annotations
import json
import time
import pandas as pd
import requests
from loguru import logger
from datetime import datetime, timedelta

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

### GraphQL Utilities for Keyword Search pipeline

def search_repositories_graphql(keyword, days_back=30, per_interval_max=100, GITHUB_TOKEN=None):
    GRAPHQL_URL = "https://api.github.com/graphql"
    HEADERS = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    repos = []
    seen_urls = set()
    per_page = 100  

    today = datetime.utcnow().date()
    since_date = today - timedelta(days=days_back)

    if days_back >= 5:
        # Divide into 5 intervals
        interval_days = days_back // 5
        intervals = [
            (since_date + timedelta(days=i * interval_days),
             since_date + timedelta(days=(i + 1) * interval_days - 1))
            for i in range(5)
        ]
        # Ensure the last interval ends today
        intervals[-1] = (intervals[-1][0], today)
    else:
        intervals = [(since_date, today)]

    for start_date, end_date in intervals:
        created_filter = f"{start_date.isoformat()}..{end_date.isoformat()}"
        logger.info(f"Fetching: {created_filter}")
        
        # Calculate how many pages we need for this interval
        total_pages = per_interval_max // per_page
        
        cursor = None
        page_count = 0
        
        while page_count < total_pages:
            # Build the GraphQL query
            query = build_search_query(keyword, created_filter, per_page, cursor)
            
            payload = {"query": query}
            response = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload)
            
            if response.status_code != 200:
                logger.error(f"Failed for {created_filter}, page {page_count + 1}: {response.status_code}, {response.text}")
                break

            try:
                data = response.json()
                
                # Check for GraphQL errors
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    break
                
                search_result = data["data"]["search"]
                edges = search_result["edges"]
                
                if not edges:
                    break

                for edge in edges:
                    repo = edge["node"]
                    url = repo["url"]
                    
                    if url not in seen_urls:
                        seen_urls.add(url)
                        
                        # Extract README content
                        readme_content = ""
                        if repo["object"] and repo["object"]["text"]:
                            readme_content = repo["object"]["text"]

                        if not readme_content:
                            logger.error(f"No README content found for {url}")
                        
                        repos.append({
                            "name": repo["nameWithOwner"],
                            "url": url,
                            "description": repo["description"],
                            "readme": readme_content,
                            "stars": repo["stargazerCount"],
                            "language": repo["primaryLanguage"]["name"] if repo["primaryLanguage"] else None,
                            "created_at": repo["createdAt"]
                        })

                # Check if there are more pages
                page_info = search_result["pageInfo"]
                if not page_info["hasNextPage"]:
                    break
                
                cursor = page_info["endCursor"]
                page_count += 1
                
            except (KeyError, TypeError) as e:
                logger.error(f"Error parsing GraphQL response: {e}")
                break

            time.sleep(1)

    logger.info(f"Found {len(repos)} repos")
    return repos


def build_search_query(keyword, created_filter, per_page, cursor=None):
    """Build the GraphQL query for repository search"""
    
    after_clause = f', after: "{cursor}"' if cursor else ""
    
    query = f'''
    query {{
        search(
            query: "{keyword} created:{created_filter}"
            type: REPOSITORY
            first: {per_page}
            {after_clause}
        ) {{
            repositoryCount
            pageInfo {{
                hasNextPage
                endCursor
            }}
            edges {{
                node {{
                    ... on Repository {{
                        nameWithOwner
                        url
                        description
                        stargazerCount
                        createdAt
                        primaryLanguage {{
                            name
                        }}
                        object(expression: "HEAD:README.md") {{
                            ... on Blob {{
                                text
                            }}
                        }}
                    }}
                }}
            }}
        }}
    }}
    '''
    
    return query.strip()


def search_repositories_graphql_with_fallback(keyword, days_back=30, per_interval_max=100, GITHUB_TOKEN=None):
    """
    Enhanced version that tries multiple README file names if README.md is not found
    """
    GRAPHQL_URL = "https://api.github.com/graphql"
    HEADERS = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    repos = []
    seen_urls = set()
    per_page = 100

    today = datetime.utcnow().date()
    since_date = today - timedelta(days=days_back)

    if days_back >= 5:
        interval_days = days_back // 5
        intervals = [
            (since_date + timedelta(days=i * interval_days),
             since_date + timedelta(days=(i + 1) * interval_days - 1))
            for i in range(5)
        ]
        intervals[-1] = (intervals[-1][0], today)
    else:
        intervals = [(since_date, today)]

    for start_date, end_date in intervals:
        created_filter = f"{start_date.isoformat()}..{end_date.isoformat()}"
        logger.info(f"Fetching: {created_filter}")
        
        total_pages = per_interval_max // per_page
        cursor = None
        page_count = 0
        
        while page_count < total_pages:
            query = build_enhanced_search_query(keyword, created_filter, per_page, cursor)
            
            payload = {"query": query}
            response = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload)
            
            if response.status_code != 200:
                logger.error(f"Failed for {created_filter}, page {page_count + 1}: {response.status_code}, {response.text}")
                break

            try:
                data = response.json()
                
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    break
                
                search_result = data["data"]["search"]
                edges = search_result["edges"]
                
                if not edges:
                    break

                for edge in edges:
                    repo = edge["node"]
                    url = repo["url"]
                    
                    if url not in seen_urls:
                        seen_urls.add(url)
                        
                        # Try to get README content from multiple possible files
                        readme_content = ""
                        for readme_file in ["readmeMd", "readmeTxt", "readmeRst"]:
                            if repo[readme_file] and repo[readme_file]["text"]:
                                readme_content = repo[readme_file]["text"]
                                break
                        
                        repos.append({
                            "name": repo["nameWithOwner"],
                            "url": url,
                            "description": repo["description"],
                            "readme": readme_content,
                            "stars": repo["stargazerCount"],
                            "language": repo["primaryLanguage"]["name"] if repo["primaryLanguage"] else None,
                            "created_at": repo["createdAt"]
                        })

                page_info = search_result["pageInfo"]
                if not page_info["hasNextPage"]:
                    break
                
                cursor = page_info["endCursor"]
                page_count += 1
                
            except (KeyError, TypeError) as e:
                logger.error(f"Error parsing GraphQL response: {e}")
                break

            time.sleep(1)

    logger.info(f"Found {len(repos)} repos")
    return repos


def build_enhanced_search_query(keyword, created_filter, per_page, cursor=None):
    """Build GraphQL query that checks multiple README file variants"""
    
    after_clause = f', after: "{cursor}"' if cursor else ""
    
    query = f'''
    query {{
        search(
            query: "{keyword} created:{created_filter}"
            type: REPOSITORY
            first: {per_page}
            {after_clause}
        ) {{
            repositoryCount
            pageInfo {{
                hasNextPage
                endCursor
            }}
            edges {{
                node {{
                    ... on Repository {{
                        nameWithOwner
                        url
                        description
                        stargazerCount
                        createdAt
                        primaryLanguage {{
                            name
                        }}
                        readmeMd: object(expression: "HEAD:README.md") {{
                            ... on Blob {{
                                text
                            }}
                        }}
                        readmeTxt: object(expression: "HEAD:README.txt") {{
                            ... on Blob {{
                                text
                            }}
                        }}
                        readmeRst: object(expression: "HEAD:README.rst") {{
                            ... on Blob {{
                                text
                            }}
                        }}
                    }}
                }}
            }}
        }}
    }}
    '''
    
    return query.strip()
