"""Onshape REST API client — Phase 1: Read-only operations.

Provides safe, read-only access to Onshape documents, elements, features, and parameters.
All functions return {"ok": true, "data": ...} or {"ok": false, "error": "..."}.

Docs: https://onshape-public.github.io/docs/api-intro/
"""
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

from tools.onshape_auth import ACCESS_KEY, SECRET_KEY, get_default_headers, OnshapeAuthError

ONSHAPE_BASE_URL = os.getenv("ONSHAPE_BASE_URL", "https://cad.onshape.com/api/v6")


class OnshapeAPIError(Exception):
    """Raised for unexpected API errors (network, 5xx, etc.)."""
    pass


def _full_url(endpoint: str) -> str:
    """Join base URL with endpoint path."""
    if endpoint.startswith("/"):
        endpoint = endpoint[1:]
    return f"{ONSHAPE_BASE_URL.rstrip('/')}/{endpoint}"


def _request(method: str, endpoint: str, params: Optional[Dict] = None, json_body: Optional[Dict] = None) -> Dict:
    """Make a signed request to Onshape API. Returns parsed JSON or raises."""
    url = _full_url(endpoint)
    try:
        headers = get_default_headers(method, url)
        resp = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=30,
        )
    except OnshapeAuthError as e:
        return {"ok": False, "error": f"Auth error: {e}"}
    except requests.RequestException as e:
        return {"ok": False, "error": f"Network error: {e}"}

    if resp.status_code == 401:
        return {"ok": False, "error": "Authentication failed (401) — check API keys"}
    if resp.status_code == 403:
        return {"ok": False, "error": "Forbidden (403) — keys may lack required permissions"}
    if resp.status_code == 404:
        return {"ok": False, "error": "Not found (404) — check document/workspace/element IDs"}
    if resp.status_code >= 500:
        return {"ok": False, "error": f"Onshape server error ({resp.status_code})"}

    try:
        return {"ok": True, "data": resp.json()}
    except ValueError:
        return {"ok": False, "error": f"Invalid JSON response: {resp.text[:200]}"}


# ──────────────────────────────────────────────────────────────
# URL / ID Parsing
# ──────────────────────────────────────────────────────────────

ONSHAPE_URL_RE = re.compile(
    r"https?://cad\.onshape\.com/documents/([a-f0-9]+)/w/([a-f0-9]+)/e/([a-f0-9]+)",
    re.IGNORECASE,
)

API_URL_RE = re.compile(
    r"/api/v\d+/partstudios/d/([a-f0-9]+)/w/([a-f0-9]+)/e/([a-f0-9]+)",
    re.IGNORECASE,
)

# Query parameter style: https://cad.onshape.com/documents?resourceType=...&nodeId={eid}
# The document ID might be in the URL path or need to be looked up
QUERY_URL_RE = re.compile(
    r"https?://cad\.onshape\.com/documents\?.*[?&]nodeId=([a-f0-9]{24})",
    re.IGNORECASE,
)

# Also match documents/{did} without workspace/element
DOC_URL_RE = re.compile(
    r"https?://cad\.onshape\.com/documents/([a-f0-9]{24})(?:/w/([a-f0-9]{24}))?(?:/e/([a-f0-9]{24}))?",
    re.IGNORECASE,
)


def parse_onshape_url(url: str) -> Tuple[str, str, str]:
    """Extract (did, wid, eid) from a document or API URL.

    Supports:
      - https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}
      - https://cad.onshape.com/documents?...&nodeId={eid}
      - https://cad.onshape.com/documents/{did}
      - /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/features
    """
    # Try full path format: documents/{did}/w/{wid}/e/{eid}
    m = DOC_URL_RE.search(url)
    if m:
        did = m.group(1)
        wid = m.group(2) or ""
        eid = m.group(3) or ""
        return did, wid, eid

    # Try query parameter style: nodeId={eid}
    m = QUERY_URL_RE.search(url)
    if m:
        eid = m.group(1)
        # We only have element ID, not document/workspace
        return "", "", eid

    # Try API URL format
    m = API_URL_RE.search(url)
    if m:
        return m.group(1), m.group(2), m.group(3)

    raise ValueError(f"Could not parse Onshape URL: {url}")


def _extract_ids_from_message(message: str) -> Optional[Tuple[str, str, str]]:
    """Try to extract (did, wid, eid) from a user message (URL or bare IDs)."""
    # Try full URL
    try:
        return parse_onshape_url(message)
    except ValueError:
        pass
    # Try bare IDs (three hex strings separated by spaces/commas/slashes)
    parts = re.split(r"[\s,/]+", message.strip())
    hex_parts = [p for p in parts if re.fullmatch(r"[a-f0-9]{24}", p, re.IGNORECASE)]
    if len(hex_parts) >= 3:
        return hex_parts[0], hex_parts[1], hex_parts[2]
    # Try two parts — assume did, wid (workspace-level queries are more common)
    if len(hex_parts) >= 2:
        return hex_parts[0], hex_parts[1], ""
    # Try single eid
    if len(hex_parts) == 1:
        return "", "", hex_parts[0]
    return None


# ──────────────────────────────────────────────────────────────
# Phase 1: Read Functions (6 total)
# ──────────────────────────────────────────────────────────────

def list_documents(
    limit: int = 20,
    offset: int = 0,
    query: str = "",
    owner_type: int = 0,
    sort_column: str = "modifiedAt",
    sort_order: str = "desc",
) -> Dict:
    """List documents accessible to the API key owner."""
    params = {
        "limit": min(limit, 100),
        "offset": offset,
        "ownerType": owner_type,
        "sortColumn": sort_column,
        "sortOrder": sort_order,
    }
    if query:
        params["q"] = query
    result = _request("GET", "documents", params=params)
    if not result.get("ok"):
        return result
    # Onshape returns {items: [...], next: ..., href: ...}
    data = result["data"]
    if isinstance(data, dict) and "items" in data:
        result["data"] = data["items"]
    return result


def get_document(did: str) -> Dict:
    """Get full document metadata including workspaces and elements."""
    result = _request("GET", f"documents/{did}")
    if not result.get("ok"):
        return result
    data = result["data"]
    if isinstance(data, dict) and "workspaces" in data:
        # Already in the right format
        pass
    return result


def list_elements(did: str, wid: str) -> Dict:
    """List all elements (Part Studios, Assemblies, Drawings) in a workspace."""
    result = _request("GET", f"documents/{did}/w/{wid}/elements")
    if not result.get("ok"):
        return result
    data = result["data"]
    if isinstance(data, dict) and "items" in data:
        result["data"] = data["items"]
    return result


def get_features(did: str, wid: str, eid: str) -> Dict:
    """Get full feature list for a Part Studio element.

    Returns feature tree with parameters, feature types, IDs, and state.
    """
    params = {"includeParameters": "true"}
    result = _request("GET", f"partstudios/d/{did}/w/{wid}/e/{eid}/features", params=params)
    if not result.get("ok"):
        return result
    # Onshape returns {features: [...], btType: ..., ...}
    data = result["data"]
    if isinstance(data, dict) and "features" in data:
        result["data"] = data["features"]
    return result


def get_feature_params(did: str, wid: str, eid: str, feature_id: str) -> Dict:
    """Get parameters for a specific feature by its featureId.

    Convenience wrapper around get_features + filter.
    """
    result = get_features(did, wid, eid)
    if not result.get("ok"):
        return result
    features = result["data"]
    for f in features:
        if f.get("featureId") == feature_id:
            return {"ok": True, "data": {
                "featureId": f.get("featureId"),
                "name": f.get("name"),
                "featureType": f.get("featureType"),
                "parameters": f.get("parameters", []),  # API returns list
                "featureState": f.get("featureState"),
            }}
    return {"ok": False, "error": f"Feature '{feature_id}' not found in Part Studio"}


def get_part_studio_info(did: str, wid: str, eid: str) -> Dict:
    """Get Part Studio metadata: parts, bodies, microversion, etc."""
    result = _request("GET", f"partstudios/d/{did}/w/{wid}/e/{eid}")
    if not result.get("ok"):
        return result
    data = result["data"]
    if isinstance(data, dict) and "parts" in data:
        # Already in the right format
        pass
    return result


# ──────────────────────────────────────────────────────────────
# Helpers for Natural Language Formatting
# ──────────────────────────────────────────────────────────────

def format_document_list(docs: List[Dict], max_items: int = 10) -> str:
    """Format document list for user-facing reply."""
    if not docs:
        return "No documents found."
    lines = []
    for i, d in enumerate(docs[:max_items], 1):
        name = d.get("name", "Unnamed")
        did = d.get("documentId", "")[:8]
        modified = d.get("modifiedAt", "")[:10]
        lines.append(f"  {i}. {name}  (id: {did}..., modified: {modified})")
    if len(docs) > max_items:
        lines.append(f"  ... and {len(docs) - max_items} more")
    return "\n".join(lines)


def format_feature_list(features: List[Dict], max_items: int = 15) -> str:
    """Format feature list for user-facing reply."""
    if not features:
        return "No features found."
    lines = []
    for i, f in enumerate(features[:max_items], 1):
        fid = f.get("featureId", "")[:8]
        name = f.get("name", "Unnamed")
        ftype = f.get("featureType", "unknown")
        state = f.get("featureState", "UNKNOWN")
        lines.append(f"  {i}. {name}  [{ftype}]  id:{fid}...  state:{state}")
    if len(features) > max_items:
        lines.append(f"  ... and {len(features) - max_items} more")
    return "\n".join(lines)


def format_feature_params(params: List[Dict]) -> str:
    """Format feature parameters for user-facing reply (mm units).
    
    Onshape returns parameters as a list of parameter objects.
    """
    if not params:
        return "No parameters."
    lines = []
    for p in params:
        pname = p.get("parameterId", "unknown")
        ptype = p.get("btType", "").replace("BTMParameter", "").replace("-147", "").replace("-144", "").replace("-145", "").replace("-148", "")
        value = p.get("value")
        expression = p.get("expression", "")
        units = p.get("units", "")
        
        if value is not None:
            if p.get("btType", "").endswith("Quantity-147"):
                # Quantity parameter with units
                if expression:
                    lines.append(f"  {pname}: {expression}")
                elif units == "meter":
                    val_mm = float(value) * 1000
                    lines.append(f"  {pname}: {val_mm:.3f} mm")
                else:
                    lines.append(f"  {pname}: {value} {units}")
            elif p.get("btType", "").endswith("Boolean-144"):
                lines.append(f"  {pname}: {value}")
            elif p.get("btType", "").endswith("Enum-145"):
                lines.append(f"  {pname}: {value}")
            elif expression:
                lines.append(f"  {pname}: {expression}")
            else:
                lines.append(f"  {pname}: {value}")
    return "\n".join(lines) if lines else "No dimensional parameters found."


def format_part_studio_info(data: Dict) -> str:
    """Format Part Studio info for user-facing reply."""
    parts = data.get("parts", [])
    if not parts:
        return "No parts in this Part Studio."
    lines = [f"Parts ({len(parts)}):"]
    for p in parts[:10]:
        name = p.get("name", "Unnamed")
        pid = p.get("partId", "")[:8]
        volume = p.get("volume")
        mass = p.get("mass")
        lines.append(f"  • {name}  (id:{pid}...)  vol:{volume}  mass:{mass}")
    if len(parts) > 10:
        lines.append(f"  ... and {len(parts) - 10} more")
    return "\n".join(lines)