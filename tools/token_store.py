import base64
import json
import subprocess
from typing import Dict, Optional

from tools.oauth_base import OAuthTokens


class TokenStore:
    SERVICE_NAME = "jarvis"

    _provider_account_map = {
        "gmail": "gmail_oauth",
        "github": "github_oauth",
        "google_drive": "google_drive_oauth",
        "google_sheets": "google_sheets_oauth",
        "google_docs": "google_docs_oauth",
        "google_slides": "google_slides_oauth",
        "google_forms": "google_forms_oauth",
    }

    @classmethod
    def _get_account(cls, provider: str) -> str:
        return cls._provider_account_map.get(provider, f"{provider}_oauth")

    @classmethod
    def save(cls, provider: str, tokens: OAuthTokens) -> bool:
        account = cls._get_account(provider)
        data = json.dumps(tokens.to_dict())
        encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")

        try:
            subprocess.run(
                ["security", "add-generic-password", "-a", account, "-s", cls.SERVICE_NAME, "-w", encoded, "-U"],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"[TokenStore] Failed to save {provider} tokens: {e.stderr.decode() if e.stderr else e}")
            return False

    @classmethod
    def load(cls, provider: str) -> Optional[OAuthTokens]:
        account = cls._get_account(provider)

        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-a", account, "-s", cls.SERVICE_NAME, "-w"],
                capture_output=True,
                text=True,
                check=True,
            )
            encoded = result.stdout.strip()
            data = json.loads(base64.b64decode(encoded).decode("utf-8"))
            return OAuthTokens.from_dict(data)
        except subprocess.CalledProcessError:
            return None
        except Exception as e:
            print(f"[TokenStore] Failed to load {provider} tokens: {e}")
            return None

    @classmethod
    def delete(cls, provider: str) -> bool:
        account = cls._get_account(provider)

        try:
            subprocess.run(
                ["security", "delete-generic-password", "-a", account, "-s", cls.SERVICE_NAME],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @classmethod
    def is_configured(cls, provider: str) -> bool:
        return cls.load(provider) is not None

    @classmethod
    def get_all_status(cls) -> Dict[str, bool]:
        return {provider: cls.is_configured(provider) for provider in cls._provider_account_map.keys()}
