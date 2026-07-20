import base64
import hashlib
import secrets
import time
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    token_type: str = "Bearer"
    scope: str = ""

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        return time.time() >= (self.expires_at - buffer_seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthTokens":
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=data["expires_at"],
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
        )


_OAUTH_SESSIONS: Dict[str, dict] = {}


class OAuth2Provider(ABC):
    def __init__(
        self,
        provider_name: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
        auth_url: str,
        token_url: str,
        revoke_url: Optional[str] = None,
    ):
        self.provider_name = provider_name
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self.auth_url = auth_url
        self.token_url = token_url
        self.revoke_url = revoke_url

    def generate_pkce(self) -> tuple[str, str]:
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
        return code_verifier, code_challenge

    def generate_state(self) -> str:
        return secrets.token_urlsafe(32)

    def get_authorization_url(self, redirect_uri: Optional[str] = None) -> str:
        actual_redirect_uri = redirect_uri or self.redirect_uri
        code_verifier, code_challenge = self.generate_pkce()
        state = self.generate_state()

        _OAUTH_SESSIONS[state] = {
            "code_verifier": code_verifier,
            "redirect_uri": actual_redirect_uri,
        }

        params = {
            "client_id": self.client_id,
            "redirect_uri": actual_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str, state: str) -> OAuthTokens:
        sess = _OAUTH_SESSIONS.pop(state, None)
        if not sess:
            raise ValueError("Invalid or expired OAuth state parameter")

        code_verifier = sess["code_verifier"]
        actual_redirect_uri = sess["redirect_uri"]

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": actual_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }

        response = requests.post(self.token_url, data=data, timeout=30)
        response.raise_for_status()
        token_data = response.json()

        expires_in = token_data.get("expires_in", 3600)
        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=time.time() + expires_in,
            token_type=token_data.get("token_type", "Bearer"),
            scope=token_data.get("scope", " ".join(self.scopes)),
        )

    def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        response = requests.post(self.token_url, data=data, timeout=30)
        response.raise_for_status()
        token_data = response.json()

        expires_in = token_data.get("expires_in", 3600)
        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", refresh_token),
            expires_at=time.time() + expires_in,
            token_type=token_data.get("token_type", "Bearer"),
            scope=token_data.get("scope", " ".join(self.scopes)),
        )

    def revoke_token(self, token: str) -> bool:
        if not self.revoke_url:
            return False
        try:
            response = requests.post(
                self.revoke_url,
                data={"token": token, "client_id": self.client_id, "client_secret": self.client_secret},
                timeout=10,
            )
            return response.ok
        except Exception:
            return False

    @abstractmethod
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        pass


class GmailOAuthProvider(OAuth2Provider):
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, scopes: list[str]):
        super().__init__(
            provider_name="gmail",
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes,
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            revoke_url="https://oauth2.googleapis.com/revoke",
        )

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()


class GitHubOAuthProvider(OAuth2Provider):
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, scopes: list[str]):
        super().__init__(
            provider_name="github",
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scopes=scopes,
            auth_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            revoke_url="https://github.com/settings/connections/applications",
        )

    def exchange_code(self, code: str, state: str) -> OAuthTokens:
        sess = _OAUTH_SESSIONS.pop(state, None)
        if not sess:
            print(f"[GitHub exchange_code] State not found in _OAUTH_SESSIONS (state={state[:20]}...)")
            raise ValueError("Invalid or expired OAuth state parameter")

        actual_redirect_uri = sess["redirect_uri"]
        code_verifier = sess["code_verifier"]
        print(f"[GitHub exchange_code] Using redirect_uri={actual_redirect_uri}, client_id={self.client_id[:8]}...")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": actual_redirect_uri,
            "code_verifier": code_verifier,
        }

        headers = {"Accept": "application/json"}
        response = requests.post(self.token_url, data=data, headers=headers, timeout=30)

        print(f"[GitHub exchange_code] Token endpoint returned status={response.status_code}")
        print(f"[GitHub exchange_code] Raw response ({len(response.text)} chars): {response.text[:500]}")

        if response.status_code != 200:
            raise ValueError(f"GitHub token exchange failed ({response.status_code}): {response.text[:500]}")

        try:
            token_data = response.json()
        except ValueError:
            raise ValueError(f"GitHub returned non-JSON response ({len(response.text)} chars): {response.text[:500]}")

        if "error" in token_data:
            raise ValueError(f"GitHub OAuth error: {token_data.get('error_description', token_data['error'])}")

        print(f"[GitHub exchange_code] Success! Got access_token ending in ...{token_data.get('access_token', 'N/A')[-8:]}")

        expires_in = 3600 * 8
        return OAuthTokens(
            access_token=token_data["access_token"],
            refresh_token=None,
            expires_at=time.time() + expires_in,
            token_type=token_data.get("token_type", "Bearer"),
            scope=token_data.get("scope", " ".join(self.scopes)),
        )

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        response = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
