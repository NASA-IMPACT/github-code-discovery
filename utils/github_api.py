from __future__ import annotations

import base64
from typing import Any

import requests


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
        raise Exception(
            f"Failed to fetch repo info from {repo_url}: {repo_resp.status_code} {repo_resp.text}",
        )
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
        raise Exception(
            f"Failed to fetch README from {repo_url}: {resp.status_code} {resp.text}",
        )
    content = base64.b64decode(resp.json().get("content", "")).decode("utf-8")
    return {"readme_text": content}
