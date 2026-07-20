import time
from functools import wraps
from typing import Optional

import requests

from config import (
    GOOGLE_FORMS_CLIENT_ID,
    GOOGLE_FORMS_CLIENT_SECRET,
    GOOGLE_FORMS_REDIRECT_URI,
    GOOGLE_FORMS_SCOPES,
)
from tools.oauth_base import OAuth2Provider
from tools.rate_limiter import acquire
from tools.token_store import TokenStore

FORMS_API_BASE = "https://forms.googleapis.com/v1/forms"


class FormsOAuthProvider(OAuth2Provider):
    def __init__(self):
        super().__init__(
            provider_name="google_forms",
            client_id=GOOGLE_FORMS_CLIENT_ID,
            client_secret=GOOGLE_FORMS_CLIENT_SECRET,
            redirect_uri=GOOGLE_FORMS_REDIRECT_URI,
            scopes=GOOGLE_FORMS_SCOPES,
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


_forms_provider = FormsOAuthProvider()


def _require_forms_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("google_forms")
        if not tokens:
            return "Google Forms not connected."
        if tokens.is_expired():
            tokens = _refresh_forms_tokens(tokens)
            if not tokens:
                return "Google Forms token expired. Re-authorize."
        return func(tokens.access_token, *args, **kwargs)

    return wrapper


def _refresh_forms_tokens(tokens):
    try:
        new_tokens = _forms_provider.refresh_access_token(tokens.refresh_token)
        TokenStore.save("google_forms", new_tokens)
        return new_tokens
    except Exception as e:
        print(f"[Forms] Token refresh failed: {e}")
    return None


def forms_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _forms_provider.get_authorization_url(redirect_uri=redirect_uri)


def forms_handle_callback(code: str, state: str = "") -> str:
    print(f"[Forms callback] Received code={code[:10]}... state={state[:20]}...")
    try:
        tokens = _forms_provider.exchange_code(code, state)
        if tokens:
            TokenStore.save("google_forms", tokens)
            try:
                user = _forms_provider.get_user_info(tokens.access_token)
                return f"Google Forms connected as {user.get('email', 'unknown')}."
            except Exception:
                return "Google Forms connected."
        return "Failed to obtain Forms tokens."
    except Exception as e:
        return f"Forms auth failed: {e}"


def forms_status() -> str:
    tokens = TokenStore.load("google_forms")
    if not tokens:
        return "Forms: Not connected."
    if tokens.is_expired():
        return "Forms: Connected but token expired."
    return f"Forms: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


@_require_forms_auth
def forms_get(form_id: str, access_token: str = "") -> str:
    acquire("forms")
    response = requests.get(
        f"{FORMS_API_BASE}/{form_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not response.ok:
        return f"Forms API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    info = data.get("info", {})
    title = info.get("title", form_id)
    items = data.get("items", [])
    summary = [f"Title: {title}", f"Total questions: {len(items)}"]
    for item in items[:10]:
        q_title = item.get("title", "Untitled")
        summary.append(f"  - {q_title}")
    return "\n".join(summary)


@_require_forms_auth
def forms_create(title: str, access_token: str = "") -> str:
    acquire("forms")
    body = {
        "info": {"title": title, "documentTitle": title},
    }
    response = requests.post(
        FORMS_API_BASE,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if not response.ok:
        return f"Forms API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    form_id = data.get("formId", "unknown")
    return f"Created form '{title}' with ID: {form_id}"


@_require_forms_auth
def forms_add_question(form_id: str, question: str, access_token: str = "") -> str:
    acquire("forms")
    response = requests.post(
        f"{FORMS_API_BASE}/{form_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "requests": [
                {
                    "createItem": {
                        "item": {
                            "title": question,
                            "questionItem": {
                                "question": {
                                    "required": False,
                                    "textQuestion": {"paragraph": False},
                                }
                            },
                        },
                        "location": {"index": 0},
                    }
                }
            ]
        },
        timeout=15,
    )
    if not response.ok:
        return f"Forms API error ({response.status_code}): {response.text[:200]}"
    return f"Question added to form {form_id}."


@_require_forms_auth
def forms_get_responses(form_id: str, access_token: str = "") -> str:
    acquire("forms")
    response = requests.get(
        f"{FORMS_API_BASE}/{form_id}/responses",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not response.ok:
        return f"Forms API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    responses = data.get("responses", [])
    if not responses:
        return "No responses yet."
    summary = [f"Total responses: {len(responses)}"]
    for i, r in enumerate(responses[:10]):
        answers = r.get("answers", {})
        summary.append(f"  Response {i + 1}: {len(answers)} answers")
    return "\n".join(summary)


FORMS_TOOLS = {
    "forms_get": forms_get,
    "forms_create": forms_create,
    "forms_add_question": forms_add_question,
    "forms_get_responses": forms_get_responses,
    "forms_auth_url": forms_auth_url,
    "forms_handle_callback": forms_handle_callback,
    "forms_status": forms_status,
}

FORMS_DEFINITIONS = [
    {
        "name": "forms_get",
        "description": "Get details of a Google Form",
        "parameters": {
            "type": "object",
            "properties": {"form_id": {"type": "string", "description": "Google Forms form ID"}},
            "required": ["form_id"],
        },
    },
    {
        "name": "forms_create",
        "description": "Create a new Google Form",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Title of the form"}},
            "required": ["title"],
        },
    },
    {
        "name": "forms_add_question",
        "description": "Add a text question to a Google Form",
        "parameters": {
            "type": "object",
            "properties": {"form_id": {"type": "string", "description": "Google Forms form ID"}, "question": {"type": "string", "description": "The question text"}},
            "required": ["form_id", "question"],
        },
    },
    {
        "name": "forms_get_responses",
        "description": "Get responses submitted to a Google Form",
        "parameters": {
            "type": "object",
            "properties": {"form_id": {"type": "string", "description": "Google Forms form ID"}},
            "required": ["form_id"],
        },
    },
    {
        "name": "forms_auth_url",
        "description": "Get Google Forms authorization URL",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "forms_handle_callback",
        "description": "Handle Google Forms OAuth callback",
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
        "name": "forms_status",
        "description": "Check Google Forms connection status",
        "parameters": {"type": "object", "properties": {}},
    },
]
