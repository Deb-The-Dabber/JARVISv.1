
import requests

from config import GOOGLE_MAPS_API_KEY

GEO_BASE = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_BASE = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACE_DETAILS_BASE = "https://maps.googleapis.com/maps/api/place/details/json"
DIRECTIONS_BASE = "https://maps.googleapis.com/maps/api/directions/json"


def geocode_address(address: str):
    """Convert an address string to lat/lng coordinates."""
    try:
        resp = requests.get(
            GEO_BASE,
            params={"address": address, "key": GOOGLE_MAPS_API_KEY},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") != "OK":
            return f"Geocode failed: {data.get('status', 'unknown')}"
        result = data["results"][0]
        loc = result["geometry"]["location"]
        formatted = result.get("formatted_address", address)
        return f"{formatted} → {loc['lat']}, {loc['lng']}"
    except Exception as e:
        return f"Geocode request failed: {e}"


def reverse_geocode(lat: float, lon: float):
    """Convert lat/lng coordinates to an address."""
    try:
        resp = requests.get(
            GEO_BASE,
            params={"latlng": f"{lat},{lon}", "key": GOOGLE_MAPS_API_KEY},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") != "OK":
            return f"Reverse geocode failed: {data.get('status', 'unknown')}"
        return data["results"][0].get("formatted_address", "Unknown address")
    except Exception as e:
        return f"Reverse geocode request failed: {e}"


def place_search(query: str, location: str = "", radius: int = 5000):
    """Search for places (restaurants, stores, landmarks, etc.) near a location."""
    params = {"query": query, "key": GOOGLE_MAPS_API_KEY}
    if location:
        params["location"] = location
        params["radius"] = radius
    try:
        resp = requests.get(PLACES_BASE, params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "OK":
            return f"Place search failed: {data.get('status', 'unknown')}"
        results = data["results"][:5]
        if not results:
            return f"No places found for '{query}'."
        lines = [f"Places matching '{query}':"]
        for r in results:
            name = r.get("name", "")
            addr = r.get("formatted_address", "")
            rating = r.get("rating", "")
            rating_str = f" ★{rating}" if rating else ""
            lines.append(f"- {name}{rating_str}")
            if addr:
                lines.append(f"  {addr}")
        return "\n".join(lines)
    except Exception as e:
        return f"Place search request failed: {e}"


def get_directions(origin: str, destination: str, mode: str = "driving"):
    """Get driving/transit/walking/bicycling directions between two points."""
    valid_modes = {"driving", "walking", "bicycling", "transit"}
    if mode not in valid_modes:
        mode = "driving"
    try:
        resp = requests.get(
            DIRECTIONS_BASE,
            params={
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "key": GOOGLE_MAPS_API_KEY,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("status") != "OK":
            return f"Directions failed: {data.get('status', 'unknown')}"
        route = data["routes"][0]
        leg = route["legs"][0]
        distance = leg.get("distance", {}).get("text", "N/A")
        duration = leg.get("duration", {}).get("text", "N/A")
        steps = leg.get("steps", [])[:8]
        lines = [
            f"Directions: {origin} → {destination} ({mode})",
            f"Distance: {distance}  Duration: {duration}",
            "Steps:",
        ]
        for i, s in enumerate(steps, 1):
            instr = s.get("html_instructions", "")
            instr = instr.replace("<b>", "").replace("</b>", "")
            instr = instr.replace('<div style="font-size:0.9em">', ", ").replace("</div>", "")
            dist = s.get("distance", {}).get("text", "")
            lines.append(f"  {i}. {instr} ({dist})")
        return "\n".join(lines)
    except Exception as e:
        return f"Directions request failed: {e}"


MAPS_TOOLS = {
    "geocode_address": geocode_address,
    "reverse_geocode": reverse_geocode,
    "place_search": place_search,
    "get_directions": get_directions,
}

MAPS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "geocode_address",
            "description": "Convert an address string to lat/lng coordinates via Google Maps Geocoding API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Street address, city, or place name"},
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reverse_geocode",
            "description": "Convert lat/lng coordinates to a street address via Google Maps Geocoding API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude"},
                    "lon": {"type": "number", "description": "Longitude"},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_search",
            "description": "Search for places (restaurants, stores, landmarks) near a location via Google Places API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "location": {"type": "string", "description": "Center point as 'lat,lng' (optional)"},
                    "radius": {"type": "integer", "description": "Search radius in meters (default 5000)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_directions",
            "description": "Get step-by-step directions between two points via Google Maps Directions API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Starting address or lat,lng"},
                    "destination": {"type": "string", "description": "Destination address or lat,lng"},
                    "mode": {"type": "string", "description": "Travel mode: driving, walking, bicycling, or transit"},
                },
                "required": ["origin", "destination"],
            },
        },
    },
]
