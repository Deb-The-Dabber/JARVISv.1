"""Onshape API request signing (HMAC-SHA256).

Implements the "Request Signature" authentication method per:
https://onshape-public.github.io/docs/auth/apikeys/#request-signature

Usage:
    from tools.onshape_auth import build_onshape_headers

    headers = build_onshape_headers("GET", "https://cad.onshape.com/api/v6/documents",
                                    ACCESS_KEY, SECRET_KEY)
    requests.get(url, headers=headers)
"""
import base64
import hmac
import hashlib
import os
import time
import urllib.parse
from typing import Tuple


class OnshapeAuthError(Exception):
    """Raised when request signing fails."""
    pass


def _generate_nonce() -> str:
    """Generate a URL-safe base64 nonce (16 random bytes)."""
    return base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")


def _rfc1123_date() -> str:
    """Current time in RFC 1123 format (GMT)."""
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())


def _build_signing_string(
    method: str,
    url: str,
    content_type: str,
    date: str,
    nonce: str,
) -> str:
    """Build the canonical signing string per Onshape spec."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()

    # Method, nonce, date, content-type, path, query — each on new line, all lowercase
    parts = [
        method.upper(),
        nonce,
        date,
        content_type.lower(),
        path,
        query,
    ]
    return "\n".join(parts).lower()


def _hmac_sha256_base64(secret_key: str, data: str) -> str:
    """HMAC-SHA256(secret_key, data) -> base64 encoded."""
    digest = hmac.new(
        secret_key.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def build_onshape_headers(
    method: str,
    url: str,
    access_key: str,
    secret_key: str,
    content_type: str = "application/json",
) -> dict:
    """Build Onshape request signature headers.

    Returns dict with: Date, On-Nonce, Authorization, Content-Type, Accept.
    """
    if not access_key or not secret_key:
        raise OnshapeAuthError("Missing Onshape API credentials")

    date = _rfc1123_date()
    nonce = _generate_nonce()

    signing_string = _build_signing_string(method, url, content_type, date, nonce)
    signature = _hmac_sha256_base64(secret_key, signing_string)

    auth_header = f"On {access_key}:HmacSHA256:{signature}"

    return {
        "Date": date,
        "On-Nonce": nonce,
        "Authorization": auth_header,
        "Content-Type": content_type,
        "Accept": "application/json;charset=UTF-8;qs=0.09",
    }


def build_basic_auth_headers(access_key: str, secret_key: str) -> dict:
    """Build Basic Auth headers (for testing / local dev only).

    Less secure than request signature — use only for quick verification.
    """
    credentials = base64.b64encode(f"{access_key}:{secret_key}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json;charset=UTF-8;qs=0.09",
    }


# Load from env at module import for convenience
def _load_keys() -> Tuple[str, str]:
    access_key = os.getenv("ONSHAPE_ACCESS_KEY", "")
    secret_key = os.getenv("ONSHAPE_SECRET_KEY", "")
    return access_key, secret_key


ACCESS_KEY, SECRET_KEY = _load_keys()


def get_default_headers(method: str, url: str, content_type: str = "application/json") -> dict:
    """Convenience: build signed headers using env-loaded keys.
    
    Uses Basic Auth (works for API Keys) since it's simpler and works for personal use.
    """
    if not ACCESS_KEY or not SECRET_KEY:
        raise OnshapeAuthError(
            "ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY must be set in environment"
        )
    return build_basic_auth_headers(ACCESS_KEY, SECRET_KEY)