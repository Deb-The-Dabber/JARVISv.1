import json
import time
from functools import wraps
from typing import Optional

import requests

from config import (
    GOOGLE_SHEETS_CLIENT_ID,
    GOOGLE_SHEETS_CLIENT_SECRET,
    GOOGLE_SHEETS_REDIRECT_URI,
    GOOGLE_SHEETS_SCOPES,
)
from tools.oauth_base import OAuth2Provider, OAuthTokens
from tools.rate_limiter import acquire
from tools.token_store import TokenStore

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsOAuthProvider(OAuth2Provider):
    def __init__(self):
        super().__init__(
            provider_name="google_sheets",
            client_id=GOOGLE_SHEETS_CLIENT_ID,
            client_secret=GOOGLE_SHEETS_CLIENT_SECRET,
            redirect_uri=GOOGLE_SHEETS_REDIRECT_URI,
            scopes=GOOGLE_SHEETS_SCOPES,
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


_sheets_provider = SheetsOAuthProvider()


def _require_sheets_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        tokens = TokenStore.load("google_sheets")
        if not tokens:
            return "Google Sheets not connected. Run gsheets_auth_url to authorize."
        if tokens.is_expired():
            tokens = _refresh_sheets_tokens(tokens)
            if not tokens:
                return "Google Sheets token expired. Re-run gsheets_auth_url to re-authorize."
        return func(tokens.access_token, *args, **kwargs)
    return wrapper


def _refresh_sheets_tokens(tokens: OAuthTokens) -> Optional[OAuthTokens]:
    try:
        new_tokens = _sheets_provider.refresh_access_token(tokens.refresh_token)
        if new_tokens:
            TokenStore.save("google_sheets", new_tokens)
            return new_tokens
    except Exception as e:
        print(f"[Sheets] Token refresh failed: {e}")
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


def gsheets_auth_url(redirect_uri: Optional[str] = None) -> str:
    return _sheets_provider.get_authorization_url(redirect_uri=redirect_uri)


def gsheets_handle_callback(code: str, state: str = "") -> str:
    try:
        tokens = _sheets_provider.exchange_code(code, state)
        if tokens:
            TokenStore.save("google_sheets", tokens)
            try:
                user = _sheets_provider.get_user_info(tokens.access_token)
                return f"Google Sheets connected as {user.get('email', 'unknown')}."
            except Exception:
                return "Google Sheets connected."
        return "Failed to obtain Sheets tokens."
    except Exception as e:
        return f"Sheets auth failed: {e}"


def gsheets_status() -> str:
    tokens = TokenStore.load("google_sheets")
    if not tokens:
        return "Sheets: Not connected. Run gsheets_auth_url to authorize."
    if tokens.is_expired():
        return "Sheets: Connected but token expired."
    return f"Sheets: Connected (expires in {int(tokens.expires_at - time.time()) // 3600}h)."


@_require_sheets_auth
def gsheets_get(spreadsheet_id: str, access_token: str = "") -> str:
    acquire("sheets")
    params = {"fields": "spreadsheetId,properties.title,sheets.properties"}
    response = requests.get(
        f"{SHEETS_API_BASE}/{spreadsheet_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Sheets")
    data = response.json()
    title = data.get("properties", {}).get("title", "Untitled")
    sheets = data.get("sheets", [])
    sheet_names = [s.get("properties", {}).get("title", "Sheet1") for s in sheets]
    return f"Spreadsheet: {title}\nSheets: {', '.join(sheet_names)}"


@_require_sheets_auth
def gsheets_read_range(spreadsheet_id: str, range_name: str, access_token: str = "") -> str:
    acquire("sheets")
    response = requests.get(
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{range_name}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"valueRenderOption": "FORMATTED_VALUE"},
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Sheets")
    data = response.json()
    values = data.get("values", [])
    if not values:
        return f"No data in range '{range_name}'."
    lines = []
    for i, row in enumerate(values, 1):
        lines.append(f"  Row {i}: {' | '.join(str(c) for c in row)}")
    return f"Range: {range_name} ({len(values)} rows):\n" + "\n".join(lines)


@_require_sheets_auth
def gsheets_read_sheet(spreadsheet_id: str, sheet_name: str, access_token: str = "") -> str:
    return gsheets_read_range(spreadsheet_id, sheet_name, access_token)


@_require_sheets_auth
def gsheets_append(
    spreadsheet_id: str,
    range_name: str,
    values: list,
    value_input_option: str = "USER_ENTERED",
    access_token: str = "",
) -> str:
    acquire("sheets")
    if not isinstance(values, list):
        return "Values must be a list (e.g., [[\"col1\", \"col2\"]])"
    body = {
        "values": values if isinstance(values[0], list) else [values],
        "majorDimension": "ROWS",
    }
    params = {"valueInputOption": value_input_option, "insertDataOption": "INSERT_ROWS"}
    response = requests.post(
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{range_name}:append",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params=params,
        json=body,
        timeout=15,
    )
    if response.ok:
        updated = response.json().get("updates", {}).get("updatedRows", 0)
        return f"Appended {updated} row(s) to {range_name}."
    return _handle_api_error(response, "Sheets")


@_require_sheets_auth
def gsheets_update_range(
    spreadsheet_id: str,
    range_name: str,
    values: list,
    value_input_option: str = "USER_ENTERED",
    access_token: str = "",
) -> str:
    acquire("sheets")
    if not isinstance(values, list):
        return "Values must be a list."
    body = {
        "values": values if isinstance(values[0], list) else [values],
        "majorDimension": "ROWS",
    }
    params = {"valueInputOption": value_input_option}
    response = requests.put(
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{range_name}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        params=params,
        json=body,
        timeout=15,
    )
    if response.ok:
        updated = response.json().get("updatedRows", 0)
        return f"Updated {updated} row(s) in {range_name}."
    return _handle_api_error(response, "Sheets")


@_require_sheets_auth
def gsheets_batch_update(spreadsheet_id: str, requests_list: list, access_token: str = "") -> str:
    acquire("sheets")
    body = {"requests": requests_list}
    response = requests.post(
        f"{SHEETS_API_BASE}/{spreadsheet_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=20,
    )
    if response.ok:
        replies = response.json().get("replies", [])
        return f"Batch update completed ({len(replies)} operations)."
    return _handle_api_error(response, "Sheets")


@_require_sheets_auth
def gsheets_create(title: str, sheets_data: Optional[list] = None, access_token: str = "") -> str:
    acquire("sheets")
    body = {"properties": {"title": title}}
    if sheets_data:
        body["sheets"] = sheets_data
    response = requests.post(
        SHEETS_API_BASE,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=20,
    )
    if response.ok:
        data = response.json()
        return f"Created spreadsheet '{title}' (ID: {data['spreadsheetId']})."
    return _handle_api_error(response, "Sheets")


@_require_sheets_auth
def gsheets_add_sheet(
    spreadsheet_id: str,
    title: str,
    rows: int = 1000,
    cols: int = 26,
    access_token: str = "",
) -> str:
    acquire("sheets")
    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": title,
                        "gridProperties": {"rowCount": rows, "columnCount": cols},
                    }
                }
            }
        ]
    }
    response = requests.post(
        f"{SHEETS_API_BASE}/{spreadsheet_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if response.ok:
        reply = response.json().get("replies", [{}])[0].get("addSheet", {}).get("properties", {}).get("title", title)
        return f"Added sheet '{reply}' to spreadsheet."
    return _handle_api_error(response, "Sheets")


@_require_sheets_auth
def gsheets_get_values(
    spreadsheet_id: str,
    range_name: str,
    major_dimension: str = "ROWS",
    access_token: str = "",
) -> str:
    acquire("sheets")
    params = {
        "majorDimension": major_dimension,
        "valueRenderOption": "FORMATTED_VALUE",
    }
    response = requests.get(
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{range_name}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if not response.ok:
        return _handle_api_error(response, "Sheets")
    data = response.json()
    values = data.get("values", [])
    if not values:
        return "No values found."
    return json.dumps(values, indent=2)


SHEETS_TOOLS = {
    "gsheets_get": gsheets_get,
    "gsheets_read_range": gsheets_read_range,
    "gsheets_read_sheet": gsheets_read_sheet,
    "gsheets_append": gsheets_append,
    "gsheets_update_range": gsheets_update_range,
    "gsheets_batch_update": gsheets_batch_update,
    "gsheets_create": gsheets_create,
    "gsheets_add_sheet": gsheets_add_sheet,
    "gsheets_get_values": gsheets_get_values,
    "gsheets_auth_url": gsheets_auth_url,
    "gsheets_handle_callback": gsheets_handle_callback,
    "gsheets_status": gsheets_status,
}

SHEETS_DEFINITIONS = [
    {"type": "function", "function": {"name": "gsheets_get", "description": "Get spreadsheet metadata and list its sheets.", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}}, "required": ["spreadsheet_id"]}}},
    {"type": "function", "function": {"name": "gsheets_read_range", "description": "Read cell values from a range (e.g., 'Sheet1!A1:C10').", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string"}}, "required": ["spreadsheet_id", "range_name"]}}},
    {"type": "function", "function": {"name": "gsheets_read_sheet", "description": "Read all values from a sheet by name.", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "sheet_name": {"type": "string"}}, "required": ["spreadsheet_id", "sheet_name"]}}},
    {"type": "function", "function": {"name": "gsheets_append", "description": "Append rows to the bottom of a range.", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string"}, "values": {"type": "array", "items": {"type": "array"}, "description": "e.g., [[\"A\",\"B\"],[\"C\",\"D\"]]"}}, "required": ["spreadsheet_id", "range_name", "values"]}}},
    {"type": "function", "function": {"name": "gsheets_update_range", "description": "Overwrite values in a specific range.", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string"}, "values": {"type": "array", "items": {"type": "array"}}, "value_input_option": {"type": "string", "enum": ["USER_ENTERED", "RAW"]}}, "required": ["spreadsheet_id", "range_name", "values"]}}},
    {"type": "function", "function": {"name": "gsheets_batch_update", "description": "Execute batch operations (format, insert rows, etc.).", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "requests_list": {"type": "array", "items": {"type": "object"}}}, "required": ["spreadsheet_id", "requests_list"]}}},
    {"type": "function", "function": {"name": "gsheets_create", "description": "Create a new Google Sheet.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "sheets_data": {"type": "array", "description": "Optional initial sheet config"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "gsheets_add_sheet", "description": "Add a new sheet/tab to an existing spreadsheet.", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "title": {"type": "string"}, "rows": {"type": "integer", "default": 1000}, "cols": {"type": "integer", "default": 26}}, "required": ["spreadsheet_id", "title"]}}},
    {"type": "function", "function": {"name": "gsheets_get_values", "description": "Get values with dimension control.", "parameters": {"type": "object", "properties": {"spreadsheet_id": {"type": "string"}, "range_name": {"type": "string"}, "major_dimension": {"type": "string", "enum": ["ROWS", "COLUMNS"]}}, "required": ["spreadsheet_id", "range_name"]}}},
    {"type": "function", "function": {"name": "gsheets_auth_url", "description": "Get OAuth authorization URL for Google Sheets.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "gsheets_handle_callback", "description": "Handle OAuth callback for Google Sheets.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "gsheets_status", "description": "Check Google Sheets connection status.", "parameters": {"type": "object", "properties": {}}}},
]
