import json
import os
import time
from functools import wraps
from typing import Optional

import requests

from config import (
    GOOGLE_DRIVE_CLIENT_ID,
    GOOGLE_DRIVE_CLIENT_SECRET,
    GOOGLE_DRIVE_REDIRECT_URI,
    GOOGLE_DRIVE_SCOPES,
)
from tools.oauth_base import OAuth2Provider, OAuthTokens
from tools.rate_limiter import acquire
from tools.token_store import TokenStore

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"


class DriveOAuthProvider(OAuth2Provider):
    def __init__(self):
        super().__init__(
            provider_name="google_drive",
            client_id=GOOGLE_DRIVE_CLIENT_ID,
            client_secret=GOOGLE_DRIVE_CLIENT_SECRET,
            redirect_uri=GOOGLE_DRIVE_REDIRECT_URI,
            scopes=GOOGLE_DRIVE_SCOPES,
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


_drive_provider = DriveOAuthProvider()


def _require_drive_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("google_drive")
        if not tokens:
            return "Google Drive not connected. Run gdrive_auth_url to authorize."
        if tokens.is_expired():
            tokens = _refresh_drive_tokens(tokens)
            if not tokens:
                return "Google Drive token expired. Re-run gdrive_auth_url to re-authorize."
        return func(tokens.access_token, *args, **kwargs)
    return wrapper


def _refresh_drive_tokens(tokens: OAuthTokens) -> Optional[OAuthTokens]:
    try:
        new_tokens = _drive_provider.refresh_access_token(tokens.refresh_token)
        if new_tokens:
            TokenStore.save("google_drive", new_tokens)
            return new_tokens
    except Exception as e:
        print(f"[Drive] Token refresh failed: {e}")
    return None


def _handle_api_error(response, service: str) -> str:
    if response.status_code == 401:
        return f"{service}: Token expired. Re-authorize."
    elif response.status_code == 403:
        return f"{service}: Permission denied."
    elif response.status_code == 404:
        return f"{service}: Resource not found."
    elif response.status_code == 429:
        return f"{service}: Rate limited."
    elif response.status_code >= 500:
        return f"{service}: Server error."
    else:
        return f"{service}: {response.text}"


def gdrive_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _drive_provider.get_authorization_url(redirect_uri=redirect_uri)


def gdrive_handle_callback(code: str, state: str = "") -> str:
    try:
        tokens = _drive_provider.exchange_code(code, state)
        if tokens:
            TokenStore.save("google_drive", tokens)
            try:
                user = _drive_provider.get_user_info(tokens.access_token)
                return f"Google Drive connected as {user.get('email', 'unknown')}."
            except Exception:
                return "Google Drive connected."
        return "Failed to obtain Drive tokens."
    except Exception as e:
        return f"Drive auth failed: {e}"


def gdrive_status() -> str:
    tokens = TokenStore.load("google_drive")
    if not tokens:
        return "Drive: Not connected. Run gdrive_auth_url to authorize."
    if tokens.is_expired():
        return "Drive: Connected but token expired. Re-run gdrive_auth_url."
    return f"Drive: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


@_require_drive_auth
def gdrive_list(folder_id: str = "root", page_size: int = 50, access_token: str = "") -> str:
    acquire("drive")
    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "pageSize": min(page_size, 100),
        "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink),nextPageToken",
        "orderBy": "folder,name",
    }
    response = requests.get(
        f"{DRIVE_API_BASE}/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Drive")
    data = response.json()
    files = data.get("files", [])
    if not files:
        return "Folder is empty."
    lines = []
    for f in files:
        icon = "📁" if f.get("mimeType") == "application/vnd.google-apps.folder" else "📄"
        size = f.get("size", "")
        if size:
            size = f" ({int(size) // 1024}KB)"
        lines.append(f"  {icon} {f['name']}{size}  ({f['id']})")
    return f"Contents ({len(files)} items):\n" + "\n".join(lines)


@_require_drive_auth
def gdrive_search(query: str, page_size: int = 50, access_token: str = "") -> str:
    acquire("drive")
    params = {
        "q": f"name contains '{query}' and trashed=false",
        "pageSize": min(page_size, 100),
        "fields": "files(id,name,mimeType,size,modifiedTime),nextPageToken",
    }
    response = requests.get(
        f"{DRIVE_API_BASE}/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Drive")
    data = response.json()
    files = data.get("files", [])
    if not files:
        return "No matching files found."
    lines = []
    for f in files:
        icon = "📁" if f.get("mimeType") == "application/vnd.google-apps.folder" else "📄"
        lines.append(f"  {icon} {f['name']}  ({f['id']})")
    return f"Found {len(files)} file(s):\n" + "\n".join(lines)


@_require_drive_auth
def gdrive_get(file_id: str, access_token: str = "") -> str:
    acquire("drive")
    params = {"fields": "id,name,mimeType,size,modifiedTime,webViewLink,owners,lastModifyingUser,description"}
    response = requests.get(
        f"{DRIVE_API_BASE}/files/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Drive")
    f = response.json()
    size = f.get("size", "?")
    if size != "?":
        size = f"{int(size) // 1024}KB"
    return (
        f"Name: {f.get('name')}\n"
        f"Type: {f.get('mimeType')}\n"
        f"Size: {size}\n"
        f"Modified: {f.get('modifiedTime', '?')}\n"
        f"Link: {f.get('webViewLink', 'N/A')}"
    )


@_require_drive_auth
def gdrive_download(file_id: str, dest_path: str = "", access_token: str = "") -> str:
    acquire("drive")
    response = requests.get(
        f"{DRIVE_API_BASE}/files/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "id,name,mimeType"},
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Drive")
    meta = response.json()
    name = meta.get("name", f"download_{file_id}")
    mime = meta.get("mimeType", "")

    download_url = f"{DRIVE_API_BASE}/files/{file_id}"
    if mime.startswith("application/vnd.google-apps"):
        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }
        mime_type = export_map.get(mime)
        if mime_type:
            download_url += "/export"
            params = {"mimeType": mime_type}
        else:
            return f"Cannot export {mime} format."
    else:
        params = {"alt": "media"}

    dl_response = requests.get(
        download_url,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=30,
    )
    if not dl_response.ok:
        return _handle_api_error(dl_response, "Drive")

    path = dest_path or os.path.join(os.path.expanduser("~"), "Downloads", name)
    with open(path, "wb") as f:
        f.write(dl_response.content)
    return f"Downloaded to {path} ({len(dl_response.content)} bytes)."


@_require_drive_auth
def gdrive_upload(local_path: str, folder_id: str = "root", name: str = "", access_token: str = "") -> str:
    acquire("drive")
    if not os.path.exists(local_path):
        return f"File not found: {local_path}"
    file_name = name or os.path.basename(local_path)
    file_size = os.path.getsize(local_path)
    if file_size > 50 * 1024 * 1024:
        return "File too large (max 50MB for simple upload)."

    metadata = {"name": file_name, "parents": [folder_id]}
    with open(local_path, "rb") as f:
        files = {
            "metadata": ("metadata.json", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (file_name, f, "application/octet-stream"),
        }
        response = requests.post(
            f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {access_token}"},
            files=files,
            timeout=60,
        )
    if response.ok:
        file = response.json()
        return f"Uploaded '{file_name}' (ID: {file['id']})."
    return _handle_api_error(response, "Drive")


@_require_drive_auth
def gdrive_create_folder(name: str, parent_id: str = "root", access_token: str = "") -> str:
    acquire("drive")
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    response = requests.post(
        f"{DRIVE_API_BASE}/files",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if response.ok:
        folder = response.json()
        return f"Created folder '{name}' (ID: {folder['id']})."
    return _handle_api_error(response, "Drive")


@_require_drive_auth
def gdrive_share(file_id: str, email: str, role: str = "reader", access_token: str = "") -> str:
    acquire("drive")
    if role not in ("reader", "writer", "commenter", "owner"):
        return "Role must be reader, writer, commenter, or owner."
    body = {
        "role": role,
        "type": "user",
        "emailAddress": email,
    }
    response = requests.post(
        f"{DRIVE_API_BASE}/files/{file_id}/permissions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if response.ok:
        perm = response.json()
        return f"Shared '{file_id}' with {email} as {role} (permission ID: {perm.get('id')})."
    return _handle_api_error(response, "Drive")


@_require_drive_auth
def gdrive_move(file_id: str, new_parent_id: str, access_token: str = "") -> str:
    acquire("drive")
    response = requests.get(
        f"{DRIVE_API_BASE}/files/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "parents"},
        timeout=10,
    )
    if not response.ok:
        return _handle_api_error(response, "Drive")
    old_parents = ",".join(response.json().get("parents", []))

    update_response = requests.patch(
        f"{DRIVE_API_BASE}/files/{file_id}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params={"addParents": new_parent_id, "removeParents": old_parents},
        json={},
        timeout=15,
    )
    if update_response.ok:
        return f"Moved '{file_id}' to new parent."
    return _handle_api_error(update_response, "Drive")


@_require_drive_auth
def gdrive_delete(file_id: str, access_token: str = "") -> str:
    acquire("drive")
    response = requests.delete(
        f"{DRIVE_API_BASE}/files/{file_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if response.ok:
        return f"Moved '{file_id}' to trash."
    return _handle_api_error(response, "Drive")


DRIVE_TOOLS = {
    "gdrive_list": gdrive_list,
    "gdrive_search": gdrive_search,
    "gdrive_get": gdrive_get,
    "gdrive_download": gdrive_download,
    "gdrive_upload": gdrive_upload,
    "gdrive_create_folder": gdrive_create_folder,
    "gdrive_share": gdrive_share,
    "gdrive_move": gdrive_move,
    "gdrive_delete": gdrive_delete,
    "gdrive_auth_url": gdrive_auth_url,
    "gdrive_handle_callback": gdrive_handle_callback,
    "gdrive_status": gdrive_status,
}

DRIVE_DEFINITIONS = [
    {"type": "function", "function": {"name": "gdrive_list", "description": "List files/folders in a Google Drive folder.", "parameters": {"type": "object", "properties": {"folder_id": {"type": "string", "description": "Folder ID (default: root)"}, "page_size": {"type": "integer", "description": "Max results (max 100)"}}, "required": []}}},
    {"type": "function", "function": {"name": "gdrive_search", "description": "Search for files in Google Drive by name.", "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query"}, "page_size": {"type": "integer", "default": 50}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "gdrive_get", "description": "Get metadata for a specific Drive file.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}}},
    {"type": "function", "function": {"name": "gdrive_download", "description": "Download a file from Google Drive.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}, "dest_path": {"type": "string", "description": "Local path (default: ~/Downloads/)"}}, "required": ["file_id"]}}},
    {"type": "function", "function": {"name": "gdrive_upload", "description": "Upload a local file to Google Drive.", "parameters": {"type": "object", "properties": {"local_path": {"type": "string"}, "folder_id": {"type": "string", "default": "root"}, "name": {"type": "string", "description": "Override filename"}}, "required": ["local_path"]}}},
    {"type": "function", "function": {"name": "gdrive_create_folder", "description": "Create a folder in Google Drive.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "parent_id": {"type": "string", "default": "root"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "gdrive_share", "description": "Share a Drive file/folder with a user.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}, "email": {"type": "string"}, "role": {"type": "string", "enum": ["reader", "writer", "commenter"]}}, "required": ["file_id", "email"]}}},
    {"type": "function", "function": {"name": "gdrive_move", "description": "Move a file to a different folder.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}, "new_parent_id": {"type": "string"}}, "required": ["file_id", "new_parent_id"]}}},
    {"type": "function", "function": {"name": "gdrive_delete", "description": "Move a Drive file to trash.", "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}}, "required": ["file_id"]}}},
    {"type": "function", "function": {"name": "gdrive_auth_url", "description": "Get OAuth authorization URL for Google Drive.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "gdrive_handle_callback", "description": "Handle OAuth callback for Google Drive.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "gdrive_status", "description": "Check Google Drive connection status.", "parameters": {"type": "object", "properties": {}}}},
]
