import os

import requests

from config import USER_LAT, USER_LON, USER_TIMEZONE

SUSPICIOUS_KEYWORDS = {"thunderstorm", "thunder", "hail", "tornado"}  # keywords that trigger WeatherAPI verification


def weather_fallback_detailed():
    """Open-Meteo primary → WeatherAPI.com → Visual Crossing (final fallback)."""
    result = _open_meteo()
    if result and not _is_suspicious(result):
        return result
    if result:
        print("  Suspicious weather detected — verifying with WeatherAPI...")
    api_key = os.getenv("WEATHERAPI_API_KEY", "").strip()
    if api_key:
        fallback = _weather_api(result)
        if fallback:
            return fallback
    vc_key = os.getenv("VISUAL_CROSSING_API_KEY", "").strip()
    if vc_key:
        vc_result = _visual_crossing()
        if vc_result:
            return vc_result
    if result:
        return result
    return "Couldn't fetch weather from any provider."


def _open_meteo():
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={USER_LAT}&longitude={USER_LON}"
            f"&current=temperature_2m,weathercode,windspeed_10m,relativehumidity_2m"
            f"&hourly=precipitation_probability"
            f"&temperature_unit=fahrenheit&windspeed_unit=mph&timezone={USER_TIMEZONE}"
        )
        data = requests.get(url, timeout=10).json()
        current = data["current"]
        conditions = {
            0: "clear sky",
            1: "mainly clear",
            2: "partly cloudy",
            3: "overcast",
            45: "foggy",
            51: "light drizzle",
            61: "light rain",
            63: "rain",
            65: "heavy rain",
            71: "light snow",
            73: "snow",
            75: "heavy snow",
            80: "rain showers",
            95: "thunderstorm",
        }
        condition = conditions.get(current["weathercode"], "mixed conditions")
        precip = data["hourly"]["precipitation_probability"][:3]
        rain_chance = max(precip) if precip else 0
        return f"Temperature: {current['temperature_2m']}°F, {condition}. Humidity: {current['relativehumidity_2m']}%, Wind: {current['windspeed_10m']} mph. Rain chance next 3 hours: {rain_chance}%."
    except Exception:
        return None


def _is_suspicious(result: str) -> bool:
    """Check if result mentions thunderstorm/hail/tornado."""
    result_lower = result.lower()
    return any(kw in result_lower for kw in SUSPICIOUS_KEYWORDS)


def _weather_api(open_meteo_fallback: str = None):
    """WeatherAPI.com fallback with proper condition codes."""
    try:
        resp = requests.get(
            "https://api.weatherapi.com/v1/current.json",
            params={"key": os.getenv("WEATHERAPI_API_KEY", ""), "q": f"{USER_LAT},{USER_LON}"},
            timeout=10,
        )
        data = resp.json()
        current = data["current"]
        return f"Temperature: {current['temp_f']}°F, {current['condition']['text'].lower()}. Humidity: {current['humidity']}%, Wind: {current['wind_mph']} mph. Feels like: {current['feelslike_f']}°F."
    except Exception:
        if open_meteo_fallback:
            return open_meteo_fallback
        return None


def _visual_crossing():
    """Visual Crossing final fallback."""
    try:
        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"{USER_LAT},{USER_LON}"
            f"?unitGroup=us&include=current&key={os.getenv('VISUAL_CROSSING_API_KEY', '')}&contentType=json"
        )
        data = requests.get(url, timeout=10).json()
        current = data["currentConditions"]
        return (
            f"Temperature: {current['temp']}°F, {current.get('conditions', 'unknown').lower()}. "
            f"Humidity: {current['humidity']}%, "
            f"Wind: {current['windspeed']} mph. "
            f"Feels like: {current.get('feelslike', 'N/A')}°F."
        )
    except Exception:
        return None
