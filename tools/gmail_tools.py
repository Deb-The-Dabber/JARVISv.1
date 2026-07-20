import base64
import time
from functools import wraps
from typing import Any, Dict, Optional

import requests

from config import GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI, GMAIL_SCOPES
from tools.oauth_base import OAuth2Provider, OAuthTokens
from tools.token_store import TokenStore

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailOAuthProvider(OAuth2Provider):
    def __init__(self):
        super().__init__(
            provider_name="gmail",
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            redirect_uri=GMAIL_REDIRECT_URI,
            scopes=GMAIL_SCOPES,
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
        )

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


_gmail_provider = GmailOAuthProvider()


def _require_gmail_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("gmail")
        if not tokens:
            return "Gmail not connected. Run /gmail-auth to authorize."
        if tokens.is_expired():
            tokens = _refresh_gmail_tokens(tokens)
            if not tokens:
                return "Gmail token expired. Re-run /gmail-auth to re-authorize."
        return func(tokens.access_token, *args, **kwargs)

    return wrapper


def _gmail_api_request(method: str, url: str, access_token: str, **kwargs) -> requests.Response:
    """Make a Gmail API request with 401 detection → refresh → retry (Phase 1.4)."""
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"
    response = requests.request(method, url, headers=headers, **kwargs)
    if response.status_code == 401:
        tokens = TokenStore.load("gmail")
        if tokens and tokens.refresh_token:
            new_tokens = _refresh_gmail_tokens(tokens)
            if new_tokens:
                headers["Authorization"] = f"Bearer {new_tokens.access_token}"
                response = requests.request(method, url, headers=headers, **kwargs)
    response.raise_for_status()
    return response


def _refresh_gmail_tokens(tokens: OAuthTokens) -> Optional[OAuthTokens]:
    try:
        new_tokens = _gmail_provider.refresh_tokens(tokens.refresh_token)
        if new_tokens:
            TokenStore.save("gmail", new_tokens)
            return new_tokens
    except Exception as e:
        print(f"[Gmail] Token refresh failed: {e}")
    return None


def gmail_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _gmail_provider.get_authorization_url(redirect_uri=redirect_uri)


def gmail_handle_callback(code: str, state: str = "") -> str:
    try:
        tokens = _gmail_provider.exchange_code(code, state)
        if tokens:
            TokenStore.save("gmail", tokens)
            try:
                user = _gmail_provider.get_user_info(tokens.access_token)
                return f"Gmail connected as {user.get('email', 'unknown')}."
            except Exception:
                return "Gmail connected."
        return "Failed to obtain Gmail tokens."
    except Exception as e:
        return f"Gmail auth failed: {e}"


@_require_gmail_auth
def gmail_search(query: str, max_results: int = 20, access_token: str = "") -> str:
    params = {"q": query, "maxResults": max_results}
    response = _gmail_api_request("GET", f"{GMAIL_API_BASE}/messages", access_token, params=params, timeout=15)
    data = response.json()
    messages = data.get("messages", [])
    if not messages:
        return "No messages found."

    results = []
    for msg in messages[:10]:
        msg_detail = requests.get(
            f"{GMAIL_API_BASE}/messages/{msg['id']}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            timeout=10,
        ).json()
        headers = {h["name"]: h["value"] for h in msg_detail.get("payload", {}).get("headers", [])}
        results.append(f"From: {headers.get('From', '?')}\nSubject: {headers.get('Subject', '?')}\nDate: {headers.get('Date', '?')}\n---")

    return f"Found {len(messages)} messages (showing first 10):\n\n" + "\n".join(results)


@_require_gmail_auth
def gmail_send(to: str, subject: str, body: str, access_token: str = "") -> str:
    from email.mime.text import MIMEText

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    _gmail_api_request("POST", f"{GMAIL_API_BASE}/messages/send", access_token, json={"raw": raw}, timeout=15)
    return f"Email sent to {to}."


@_require_gmail_auth
def gmail_get_labels(access_token: str = "") -> str:
    response = _gmail_api_request("GET", f"{GMAIL_API_BASE}/labels", access_token, timeout=10)
    labels = response.json().get("labels", [])
    return "Labels:\n" + "\n".join(f"  {l['name']} ({l['id']})" for l in labels)


@_require_gmail_auth
def gmail_get_message(message_id: str, access_token: str = "") -> str:
    response = _gmail_api_request("GET", f"{GMAIL_API_BASE}/messages/{message_id}", access_token, params={"format": "full"}, timeout=15)
    msg = response.json()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    snippet = msg.get("snippet", "")
    body = ""
    if "parts" in msg.get("payload", {}):
        for part in msg["payload"]["parts"]:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                break
    return f"From: {headers.get('From', '?')}\nTo: {headers.get('To', '?')}\nSubject: {headers.get('Subject', '?')}\nDate: {headers.get('Date', '?')}\n\n{snippet}\n\n{body[:2000]}"


def gmail_status() -> str:
    tokens = TokenStore.load("gmail")
    if not tokens:
        return "Gmail: Not connected. Run /gmail-auth to authorize."
    if tokens.is_expired():
        return "Gmail: Connected but token expired. Re-run /gmail-auth."
    return f"Gmail: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


GMAIL_TOOLS = {
    "gmail_search": gmail_search,
    "gmail_send": gmail_send,
    "gmail_get_labels": gmail_get_labels,
    "gmail_get_message": gmail_get_message,
    "gmail_status": gmail_status,
    "gmail_auth_url": gmail_auth_url,
    "gmail_handle_callback": gmail_handle_callback,
}

GMAIL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "gmail_search",
            "description": "Search Gmail messages. Requires prior OAuth authorization via /gmail-auth.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Gmail search query (e.g., 'from:github subject:security')"}, "max_results": {"type": "integer", "default": 20}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Send an email via Gmail. Requires prior OAuth authorization via /gmail-auth.",
            "parameters": {
                "type": "object",
                "properties": {"to": {"type": "string", "description": "Recipient email address"}, "subject": {"type": "string"}, "body": {"type": "string"}},
                "required": ["to", "subject", "body"],
            },
        },
    },
    {"type": "function", "function": {"name": "gmail_get_labels", "description": "List all Gmail labels.", "parameters": {"type": "object", "properties": {}}}},
    {
        "type": "function",
        "function": {
            "name": "gmail_get_message",
            "description": "Get full message content by ID.",
            "parameters": {"type": "object", "properties": {"message_id": {"type": "string"}}, "required": ["message_id"]},
        },
    },
    {"type": "function", "function": {"name": "gmail_status", "description": "Check Gmail connection status.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "gmail_auth_url", "description": "Get OAuth authorization URL for Gmail.", "parameters": {"type": "object", "properties": {}}}},
    {
        "type": "function",
        "function": {
            "name": "gmail_handle_callback",
            "description": "Handle OAuth callback with authorization code.",
            "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
        },
    },
]
