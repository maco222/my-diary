"""Weather collector — Open-Meteo (free, no API key)."""

from __future__ import annotations

import httpx

from my_diary.collectors.base import BaseCollector
from my_diary.models import CollectorResult

# Warsaw coordinates (default)
_DEFAULT_LAT = 52.23
_DEFAULT_LON = 21.01

# WMO weather codes → description
_WMO_CODES = {
    0: "Bezchmurnie", 1: "Prawie bezchmurnie", 2: "Częściowe zachmurzenie",
    3: "Pochmurno", 45: "Mgła", 48: "Szadź",
    51: "Lekka mżawka", 53: "Mżawka", 55: "Gęsta mżawka",
    61: "Lekki deszcz", 63: "Deszcz", 65: "Silny deszcz",
    71: "Lekki śnieg", 73: "Śnieg", 75: "Silny śnieg",
    77: "Ziarna śniegu", 80: "Lekkie przelotne opady", 81: "Przelotne opady",
    82: "Silne przelotne opady", 85: "Lekki śnieg przelotny", 86: "Silny śnieg przelotny",
    95: "Burza", 96: "Burza z lekkim gradem", 99: "Burza z silnym gradem",
}


class WeatherCollector(BaseCollector):
    """Fetch weather data from Open-Meteo API."""

    async def collect(self) -> CollectorResult:
        city = self.config.get("city", "Warsaw")
        lat = self.config.get("latitude", _DEFAULT_LAT)
        lon = self.config.get("longitude", _DEFAULT_LON)

        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            f"weather_code,wind_speed_10m,wind_direction_10m,surface_pressure"
            f"&timezone=Europe%2FWarsaw"
        )

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current", {})
        code = current.get("weather_code", -1)

        weather_info = {
            "city": city,
            "temp_c": current.get("temperature_2m", ""),
            "feels_like_c": current.get("apparent_temperature", ""),
            "humidity": current.get("relative_humidity_2m", ""),
            "description": _WMO_CODES.get(code, f"Kod {code}"),
            "wind_kmph": current.get("wind_speed_10m", ""),
            "wind_dir_degrees": current.get("wind_direction_10m", ""),
            "pressure_mb": current.get("surface_pressure", ""),
        }

        return CollectorResult(
            source=self.name,
            data=weather_info,
            summary=f"{city}: {weather_info['temp_c']}°C, {weather_info['description']}",
        )
