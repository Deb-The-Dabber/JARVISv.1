import time
from functools import wraps
from typing import Optional

import requests

from config import (
    GOOGLE_SLIDES_CLIENT_ID,
    GOOGLE_SLIDES_CLIENT_SECRET,
    GOOGLE_SLIDES_REDIRECT_URI,
    GOOGLE_SLIDES_SCOPES,
)
from tools.oauth_base import OAuth2Provider
from tools.rate_limiter import acquire
from tools.token_store import TokenStore

SLIDES_API_BASE = "https://slides.googleapis.com/v1/presentations"


class SlidesOAuthProvider(OAuth2Provider):
    def __init__(self):
        super().__init__(
            provider_name="google_slides",
            client_id=GOOGLE_SLIDES_CLIENT_ID,
            client_secret=GOOGLE_SLIDES_CLIENT_SECRET,
            redirect_uri=GOOGLE_SLIDES_REDIRECT_URI,
            scopes=GOOGLE_SLIDES_SCOPES,
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


_slides_provider = SlidesOAuthProvider()


def _require_slides_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("google_slides")
        if not tokens:
            return "Google Slides not connected."
        if tokens.is_expired():
            tokens = _refresh_slides_tokens(tokens)
            if not tokens:
                return "Google Slides token expired. Re-authorize."
        return func(tokens.access_token, *args, **kwargs)

    return wrapper


def _refresh_slides_tokens(tokens):
    try:
        new_tokens = _slides_provider.refresh_access_token(tokens.refresh_token)
        TokenStore.save("google_slides", new_tokens)
        return new_tokens
    except Exception as e:
        print(f"[Slides] Token refresh failed: {e}")
    return None


def slides_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _slides_provider.get_authorization_url(redirect_uri=redirect_uri)


def slides_handle_callback(code: str, state: str = "") -> str:
    print(f"[Slides callback] Received code={code[:10]}... state={state[:20]}...")
    try:
        tokens = _slides_provider.exchange_code(code, state)
        if tokens:
            TokenStore.save("google_slides", tokens)
            try:
                user = _slides_provider.get_user_info(tokens.access_token)
                return f"Google Slides connected as {user.get('email', 'unknown')}."
            except Exception:
                return "Google Slides connected."
        return "Failed to obtain Slides tokens."
    except Exception as e:
        return f"Slides auth failed: {e}"


def slides_status() -> str:
    tokens = TokenStore.load("google_slides")
    if not tokens:
        return "Slides: Not connected."
    if tokens.is_expired():
        return "Slides: Connected but token expired."
    return f"Slides: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


@_require_slides_auth
def slides_get(presentation_id: str, access_token: str = "") -> str:
    acquire("slides")
    response = requests.get(
        f"{SLIDES_API_BASE}/{presentation_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not response.ok:
        return f"Slides API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    title = data.get("title", presentation_id)
    slides = data.get("slides", [])
    summary = [f"Title: {title}", f"Total slides: {len(slides)}"]
    for i, slide in enumerate(slides[:10]):
        elements = len(slide.get("pageElements", []))
        summary.append(f"  Slide {i + 1}: {elements} elements")
    return "\n".join(summary)


@_require_slides_auth
def slides_create(title: str, access_token: str = "") -> str:
    acquire("slides")
    body = {"title": title}
    response = requests.post(
        SLIDES_API_BASE,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if not response.ok:
        return f"Slides API error ({response.status_code}): {response.text[:200]}"
    data = response.json()
    pres_id = data.get("presentationId", "unknown")
    return f"Created presentation '{title}' with ID: {pres_id}"


@_require_slides_auth
def slides_add_slide(presentation_id: str, access_token: str = "") -> str:
    acquire("slides")
    response = requests.post(
        f"{SLIDES_API_BASE}/{presentation_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"requests": [{"createSlide": {"slideLayoutReference": {"predefinedLayout": "BLANK"}}}]},
        timeout=15,
    )
    if not response.ok:
        return f"Slides API error ({response.status_code}): {response.text[:200]}"
    return "Slide added."


@_require_slides_auth
def slides_replace_text(presentation_id: str, old_text: str, new_text: str, access_token: str = "") -> str:
    acquire("slides")
    response = requests.post(
        f"{SLIDES_API_BASE}/{presentation_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "requests": [
                {
                    "replaceAllText": {
                        "containsText": {"text": old_text, "matchCase": False},
                        "replaceText": new_text,
                    }
                }
            ]
        },
        timeout=15,
    )
    if not response.ok:
        return f"Slides API error ({response.status_code}): {response.text[:200]}"
    return f"Replaced '{old_text}' with '{new_text}'."


@_require_slides_auth
def slides_search(query: str, access_token: str = "") -> str:
    acquire("slides")
    return "Slides search requires Drive API. Use gdrive_search with mimeType='application/vnd.google-apps.presentation'."


SLIDES_TOOLS = {
    "slides_get": slides_get,
    "slides_create": slides_create,
    "slides_add_slide": slides_add_slide,
    "slides_replace_text": slides_replace_text,
    "slides_search": slides_search,
    "slides_auth_url": slides_auth_url,
    "slides_handle_callback": slides_handle_callback,
    "slides_status": slides_status,
}

SLIDES_DEFINITIONS = [
    {
        "name": "slides_get",
        "description": "Get summary of a Google Slides presentation",
        "parameters": {
            "type": "object",
            "properties": {"presentation_id": {"type": "string", "description": "Google Slides presentation ID"}},
            "required": ["presentation_id"],
        },
    },
    {
        "name": "slides_create",
        "description": "Create a new Google Slides presentation",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Title of the presentation"}},
            "required": ["title"],
        },
    },
    {
        "name": "slides_add_slide",
        "description": "Add a blank slide to a presentation",
        "parameters": {
            "type": "object",
            "properties": {"presentation_id": {"type": "string", "description": "Google Slides presentation ID"}},
            "required": ["presentation_id"],
        },
    },
    {
        "name": "slides_replace_text",
        "description": "Find and replace text across all slides",
        "parameters": {
            "type": "object",
            "properties": {
                "presentation_id": {"type": "string", "description": "Google Slides presentation ID"},
                "old_text": {"type": "string", "description": "Text to find"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["presentation_id", "old_text", "new_text"],
        },
    },
    {
        "name": "slides_search",
        "description": "Search for Google Slides by name (delegates to Drive search)",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "slides_auth_url",
        "description": "Get Google Slides authorization URL",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "slides_handle_callback",
        "description": "Handle Google Slides OAuth callback",
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
        "name": "slides_status",
        "description": "Check Google Slides connection status",
        "parameters": {"type": "object", "properties": {}},
    },
]
