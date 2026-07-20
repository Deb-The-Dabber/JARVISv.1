import time
from functools import wraps
from typing import List, Optional

import requests

from config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_REDIRECT_URI, GITHUB_SCOPES
from tools.oauth_base import GitHubOAuthProvider
from tools.token_store import TokenStore

GITHUB_API_BASE = "https://api.github.com"


_github_provider = GitHubOAuthProvider(
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    redirect_uri=GITHUB_REDIRECT_URI,
    scopes=GITHUB_SCOPES,
)


def _require_github_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("github")
        if not tokens:
            return "GitHub not connected. Run /github-auth to authorize."
        if tokens.is_expired():
            return "GitHub token expired. Re-run /github-auth to re-authorize."
        return func(tokens.access_token, *args, **kwargs)

    return wrapper


def github_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _github_provider.get_authorization_url(redirect_uri=redirect_uri)


def github_handle_callback(code: str, state: str = "") -> str:
    print(f"[GitHub callback] Received code={code[:10]}... state={state[:20]}...")
    try:
        tokens = _github_provider.exchange_code(code, state)
        if tokens:
            print(f"[GitHub callback] Token obtained, saving... expires_at={tokens.expires_at}")
            TokenStore.save("github", tokens)
            try:
                user = _github_provider.get_user_info(tokens.access_token)
                email = user.get("email") or user.get("login", "unknown")
                print(f"[GitHub callback] Connected as {email}")
                return f"GitHub connected as {email}."
            except Exception as e:
                print(f"[GitHub callback] get_user_info failed: {e}")
                return "GitHub connected."
        print("[GitHub callback] No tokens returned from exchange_code")
        return "Failed to obtain GitHub tokens."
    except Exception as e:
        print(f"[GitHub callback] Exception: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return f"GitHub auth failed: {e}"


@_require_github_auth
def github_list_repos(visibility: str = "all", affiliation: str = "owner", per_page: int = 30, access_token: str = "") -> str:
    params = {"visibility": visibility, "affiliation": affiliation, "per_page": per_page, "sort": "updated"}
    response = requests.get(
        f"{GITHUB_API_BASE}/user/repos",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    repos = response.json()
    if not repos:
        return "No repositories found."
    return "\n".join(f"{r['full_name']} ({'private' if r['private'] else 'public'}) - {r.get('description', 'No description')[:80]}" for r in repos[:20])


@_require_github_auth
def github_search_code(query: str, per_page: int = 10, access_token: str = "") -> str:
    params = {"q": query, "per_page": per_page}
    response = requests.get(
        f"{GITHUB_API_BASE}/search/code",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    items = data.get("items", [])
    if not items:
        return "No code results found."
    return "\n".join(f"{item['repository']['full_name']}/{item['path']}: {item.get('text_matches', [{}])[0].get('fragment', '')[:100]}" for item in items)


@_require_github_auth
def github_create_issue(owner: str, repo: str, title: str, body: str = "", labels: Optional[List[str]] = None, access_token: str = "") -> str:
    data = {"title": title, "body": body}
    if labels:
        data["labels"] = labels
    response = requests.post(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        json=data,
        timeout=15,
    )
    response.raise_for_status()
    issue = response.json()
    return f"Issue created: {issue['html_url']}"


@_require_github_auth
def github_list_issues(owner: str, repo: str, state: str = "open", labels: Optional[str] = None, per_page: int = 20, access_token: str = "") -> str:
    params = {"state": state, "per_page": per_page}
    if labels:
        params["labels"] = labels
    response = requests.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    issues = response.json()
    if not issues:
        return "No issues found."
    return "\n".join(f"#{i['number']} {i['title']} ({i['state']}) - {i['html_url']}" for i in issues)


@_require_github_auth
def github_get_repo(owner: str, repo: str, access_token: str = "") -> str:
    response = requests.get(
        f"{GITHUB_API_BASE}/repos/{owner}/{repo}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        timeout=10,
    )
    response.raise_for_status()
    r = response.json()
    return f"{r['full_name']}\n{'Private' if r['private'] else 'Public'}\n{r.get('description', 'No description')}\nStars: {r['stargazers_count']} | Forks: {r['forks_count']}\n{r['html_url']}"


def github_status() -> str:
    tokens = TokenStore.load("github")
    if not tokens:
        return "GitHub: Not connected. Run /github-auth to authorize."
    if tokens.is_expired():
        return "GitHub: Connected but token expired. Re-run /github-auth."
    return f"GitHub: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


GITHUB_TOOLS = {
    "github_list_repos": github_list_repos,
    "github_search_code": github_search_code,
    "github_create_issue": github_create_issue,
    "github_list_issues": github_list_issues,
    "github_get_repo": github_get_repo,
    "github_status": github_status,
    "github_auth_url": github_auth_url,
    "github_handle_callback": github_handle_callback,
}

GITHUB_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "github_list_repos",
            "description": "List your GitHub repositories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "visibility": {"type": "string", "enum": ["all", "public", "private"], "default": "all"},
                    "affiliation": {"type": "string", "enum": ["owner", "collaborator", "organization_member"], "default": "owner"},
                    "per_page": {"type": "integer", "default": 30},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_search_code",
            "description": "Search code across GitHub repositories.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query (e.g., 'repo:owner/repo function_name')"}, "per_page": {"type": "integer", "default": 10}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_issue",
            "description": "Create a GitHub issue. Requires confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string", "default": ""},
                    "labels": {"type": "array", "items": {"type": "string"}, "default": []},
                },
                "required": ["owner", "repo", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_issues",
            "description": "List issues in a repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                    "labels": {"type": "string", "description": "Comma-separated labels"},
                    "per_page": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_repo",
            "description": "Get repository details.",
            "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]},
        },
    },
    {"type": "function", "function": {"name": "github_status", "description": "Check GitHub connection status.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "github_auth_url", "description": "Get OAuth authorization URL for GitHub.", "parameters": {"type": "object", "properties": {}}}},
    {
        "type": "function",
        "function": {
            "name": "github_handle_callback",
            "description": "Handle OAuth callback with authorization code.",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        },
    },
]
