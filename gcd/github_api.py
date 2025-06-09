from __future__ import annotations
import base64
from typing import Any
import requests
import time
from datetime import datetime, timedelta
from loguru import logger

def get_github_repo_info(
    repo_url: str,
    token: str | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    owner, repo = repo_url.rstrip("/").split("/")[-2:]
    base_url = f"https://api.github.com/repos/{owner}/{repo}"

    # Get repo info
    repo_resp = requests.get(base_url, headers=headers)
    if not repo_resp.ok:
        logger.error(f"Failed to fetch repo info from {repo_url}: {repo_resp.status_code} {repo_resp.text}")

    repo_info = repo_resp.json()

    # Get owner's actual name
    owner_login = repo_info.get("owner", {}).get("login")
    owner_name = None
    if owner_login:
        owner_info = requests.get(
            f"https://api.github.com/users/{owner_login}",
            headers=headers,
        ).json()
        owner_name = owner_info.get("name", owner_login)

    # Get contributors' actual names
    contributors_resp = requests.get(
        repo_info.get("contributors_url", ""),
        headers=headers,
    )
    contributors_data = contributors_resp.json() if contributors_resp.ok else []
    contributors = []
    for contributor in contributors_data:
        login = contributor.get("login")
        user_info = requests.get(
            f"https://api.github.com/users/{login}",
            headers=headers,
        ).json()
        name = user_info.get("name", login)
        contributors.append(name)

    # Get README content
    readme_resp = requests.get(f"{base_url}/readme", headers=headers)
    readme_base64 = readme_resp.json().get("content", "") if readme_resp.ok else ""
    decoded_bytes = base64.b64decode(readme_base64)
    readme = decoded_bytes.decode("utf-8")

    return {
        "name": repo_info.get("name"),
        "description": repo_info.get("description"),
        "created_at": repo_info.get("created_at"),
        "authors": [owner_name, *contributors],
        "readme_text": readme,
    }


def get_github_readme(
    repo_url: str,
    token: str | None = None,
) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    owner, repo = repo_url.rstrip("/").split("/")[-2:]
    readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    resp = requests.get(readme_url, headers=headers)
    if not resp.ok:
        logger.error(f"README not found for {repo_url}")
    content = base64.b64decode(resp.json().get("content", "")).decode("utf-8")
    return {"readme_text": content}

def search_repositories(keyword, days_back=30, per_interval_max=100, GITHUB_TOKEN=None):
    SEARCH_URL = "https://api.github.com/search/repositories"
    HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
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
        total_pages = per_interval_max // per_page

        for page in range(1, total_pages + 1):
            params = {
                "q": f"{keyword} created:{created_filter}",
                "per_page": per_page,
                "page": page,
                "sort": "stars",
                "order": "desc"
            }

            response = requests.get(SEARCH_URL, headers=HEADERS, params=params)
            if response.status_code != 200:
                logger.error(f"Failed for {created_filter}, page {page}: {response.status_code}, {response.text}")
                break

            items = response.json().get("items", [])
            if not items:
                break

            for item in items:
                url = item["html_url"]
                if url not in seen_urls:
                    seen_urls.add(url)
                    try:
                        readme_dict = get_github_readme(item["html_url"], GITHUB_TOKEN)
                        readme = readme_dict.get("readme_text", "")
                    except Exception as e:
                        logger.error(f"Error fetching README for {item['html_url']}: {e}")
                        readme = ""
                    repos.append({
                        "name": item["full_name"],
                        "url": url,
                        "description": item["description"],
                        "readme": readme,
                        "stars": item["stargazers_count"],
                        "language": item["language"],
                        "created_at": item["created_at"]
                    })

            time.sleep(1)

    return repos
