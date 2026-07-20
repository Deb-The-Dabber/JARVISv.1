import time
from functools import wraps
from typing import Optional

import requests

from config import (
    GOOGLE_DOCS_CLIENT_ID,
    GOOGLE_DOCS_CLIENT_SECRET,
    GOOGLE_DOCS_REDIRECT_URI,
    GOOGLE_DOCS_SCOPES,
)
from tools.oauth_base import OAuth2Provider
from tools.rate_limiter import acquire
from tools.token_store import TokenStore

DOCS_API_BASE = "https://docs.googleapis.com/v1/documents"


class DocsOAuthProvider(OAuth2Provider):
    def __init__(self):
        super().__init__(
            provider_name="google_docs",
            client_id=GOOGLE_DOCS_CLIENT_ID,
            client_secret=GOOGLE_DOCS_CLIENT_SECRET,
            redirect_uri=GOOGLE_DOCS_REDIRECT_URI,
            scopes=GOOGLE_DOCS_SCOPES,
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            revoke_url="https://oauth2.googleapis.com/revoke",
        )

    def get_user_info(self, access_token: str) -> dict:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


_docs_provider = DocsOAuthProvider()


def _require_docs_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("google_docs")
        if not tokens:
            return "Google Docs not connected."
        if tokens.is_expired():
            tokens = _refresh_docs_tokens(tokens)
            if not tokens:
                return "Google Docs token expired. Re-authorize."
        return func(tokens.access_token, *args, **kwargs)

    return wrapper


def _refresh_docs_tokens(tokens):
    try:
        new_tokens = _docs_provider.refresh_access_token(tokens.refresh_token)
        TokenStore.save("google_docs", new_tokens)
        return new_tokens
    except Exception as e:
        print(f"[Docs] Token refresh failed: {e}")
    return None


def docs_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _docs_provider.get_authorization_url(redirect_uri=redirect_uri)


def docs_handle_callback(code: str, state: str = "") -> str:
    print(f"[Docs callback] Received code={code[:10]}... state={state[:20]}...")
    try:
        tokens = _docs_provider.exchange_code(code, state)
        if tokens:
            TokenStore.save("google_docs", tokens)
            try:
                user = _docs_provider.get_user_info(tokens.access_token)
                return f"Google Docs connected as {user.get('email', 'unknown')}."
            except Exception:
                return "Google Docs connected."
        return "Failed to obtain Docs tokens."
    except Exception as e:
        return f"Docs auth failed: {e}"


def docs_status() -> str:
    tokens = TokenStore.load("google_docs")
    if not tokens:
        return "Docs: Not connected."
    if tokens.is_expired():
        return "Docs: Connected but token expired."
    return f"Docs: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


@_require_docs_auth
def docs_get(document_id: str, access_token: str = "") -> str:
    acquire("docs")
    response = requests.get(
        f"{DOCS_API_BASE}/{document_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not response.ok:
        return f"Docs API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    title = data.get("title", document_id)
    body = data.get("body", {}).get("content", [])
    text_parts = []
    for element in body:
        if "paragraph" in element:
            for seg in element["paragraph"].get("elements", []):
                if "textRun" in seg:
                    text_parts.append(seg["textRun"].get("content", ""))
    content = "".join(text_parts)
    return f"Title: {title}\n\n{content[:2000]}"


@_require_docs_auth
def docs_create(title: str, access_token: str = "") -> str:
    acquire("docs")
    body = {"title": title}
    response = requests.post(
        DOCS_API_BASE,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if not response.ok:
        return f"Docs API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    doc_id = data.get("documentId", "unknown")
    return f"Created doc '{title}' with ID: {doc_id}"


@_require_docs_auth
def docs_append_text(document_id: str, text: str, access_token: str = "") -> str:
    acquire("docs")
    requests.post(
        f"{DOCS_API_BASE}/{document_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": text,
                    }
                }
            ]
        },
        timeout=15,
    )
    return "Text appended."


@_require_docs_auth
def docs_search(query: str, access_token: str = "") -> str:
    acquire("docs")
    return "Docs search requires Drive API. Use gdrive_search with mimeType='application/vnd.google-apps.document'."


DOCS_TOOLS = {
    "docs_get": docs_get,
    "docs_create": docs_create,
    "docs_append_text": docs_append_text,
    "docs_search": docs_search,
    "docs_auth_url": docs_auth_url,
    "docs_handle_callback": docs_handle_callback,
    "docs_status": docs_status,
}

DOCS_DEFINITIONS = [
    {
        "name": "docs_get",
        "description": "Get content of a Google Doc by document ID",
        "parameters": {
            "type": "object",
            "properties": {"document_id": {"type": "string", "description": "Google Doc document ID"}},
            "required": ["document_id"],
        },
    },
    {
        "name": "docs_create",
        "description": "Create a new Google Doc with a title",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Title of the document"}},
            "required": ["title"],
        },
    },
    {
        "name": "docs_append_text",
        "description": "Append text to a Google Doc",
        "parameters": {
            "type": "object",
            "properties": {"document_id": {"type": "string", "description": "Google Doc document ID"}, "text": {"type": "string", "description": "Text to append"}},
            "required": ["document_id", "text"],
        },
    },
    {
        "name": "docs_search",
        "description": "Search for Google Docs by name (delegates to Drive search)",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "docs_auth_url",
        "description": "Get Google Docs authorization URL",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "docs_handle_callback",
        "description": "Handle Google Docs OAuth callback",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "state": {"type": "string"},
            },
            "required": ["code", "state"],
        },
    },
    {
        "name": "docs_status",
        "description": "Check Google Docs connection status",
        "parameters": {"type": "object", "properties": {}},
    },
]
