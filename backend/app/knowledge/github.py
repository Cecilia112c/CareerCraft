"""Read a bounded public GitHub repository overview through the fixed GitHub API host."""

import re
from collections import Counter
from urllib.parse import urlparse

import httpx


def repository_parts(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.port is not None:
        raise ValueError("只接受 https://github.com 的仓库地址")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", part) for part in parts[:2]):
        raise ValueError("仓库地址格式不正确")
    return parts[0], parts[1].removesuffix(".git")


def public_repo_overview(url: str, token: str = "") -> tuple[str, dict]:
    owner, repo = repository_parts(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "CareerCraft/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(base_url="https://api.github.com", headers=headers, timeout=12, follow_redirects=False) as client:
        response = client.get(f"/repos/{owner}/{repo}")
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("private") and not token:
            raise ValueError("私有仓库需要本次请求提供 Token")
        branch = metadata.get("default_branch") or "main"
        tree_response = client.get(f"/repos/{owner}/{repo}/git/trees/{branch}", params={"recursive": "1"})
        tree_response.raise_for_status()
        files = [entry.get("path", "") for entry in tree_response.json().get("tree", [])
                 if entry.get("type") == "blob"][:3000]
        readme = client.get(f"/repos/{owner}/{repo}/readme", headers={"Accept": "application/vnd.github.raw+json"})
        readme_text = readme.text[:30000] if readme.status_code == 200 else ""
        languages_response = client.get(f"/repos/{owner}/{repo}/languages")
        languages = languages_response.json() if languages_response.status_code == 200 else {}
        commits_response = client.get(f"/repos/{owner}/{repo}/commits", params={"per_page": 20})
        recent_authors = Counter()
        if commits_response.status_code == 200:
            for commit in commits_response.json()[:20]:
                author = (commit.get("author") or {}).get("login") or (commit.get("commit") or {}).get("author", {}).get("name")
                if author:
                    recent_authors[str(author)[:100]] += 1
    meta = {"repository": f"{owner}/{repo}", "description": metadata.get("description") or "",
            "languages": languages, "topics": metadata.get("topics") or [],
            "recent_commit_authors": dict(recent_authors), "files": files[:100],
            "file_count": len(files), "stars": metadata.get("stargazers_count", 0),
            "has_tests": any("test" in path.lower() for path in files),
            "has_ci": any(".github/workflows/" in path or ".gitlab-ci" in path for path in files),
            "readme_summary": readme_text[:1200]}
    text = f"# {owner}/{repo}\n{meta['description']}\n\n{readme_text}\n\n## 文件清单\n" + "\n".join(files[:300])
    return text[:100000], meta
