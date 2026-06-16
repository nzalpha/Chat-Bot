"""Small MCP tool server for the Session 6 agent demo.

The agent expects this file to exist next to it and expose tools over stdio.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "llm_gatewayV2" / ".env")

mcp = FastMCP("s6-tool-server")


@mcp.tool()
def add(a: float, b: float) -> dict:
    """Return a + b."""
    return {"result": a + b}


@mcp.tool()
def subtract(a: float, b: float) -> dict:
    """Return a - b."""
    return {"result": a - b}


@mcp.tool()
def get_temperature(city: str, units: str = "metric") -> dict:
    """Return the current temperature for a city using OpenWeatherMap.

    Args:
        city: City name, for example "London", "New York", or "Mumbai".
        units: "metric" for Celsius, "imperial" for Fahrenheit, or "standard" for Kelvin.
    """
    api_key = (
        os.getenv("WEATHER_API_KEY")
        or os.getenv("Weather_API_KEY")
        or os.getenv("OPENWEATHER_API_KEY")
    )
    if not api_key:
        return {
            "error": "Missing weather API key. Add WEATHER_API_KEY=your_key to s6/.env.",
        }

    normalized_units = units.lower().strip()
    if normalized_units not in {"metric", "imperial", "standard"}:
        normalized_units = "metric"

    try:
        response = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": normalized_units},
            timeout=10,
        )
        data = response.json()
    except Exception as exc:
        return {"error": f"Weather request failed: {exc}"}

    if response.status_code != 200:
        message = data.get("message") if isinstance(data, dict) else response.text[:200]
        return {
            "error": message or f"Weather API returned HTTP {response.status_code}",
            "city": city,
        }

    temperature = data["main"]["temp"]
    unit_label = {"metric": "C", "imperial": "F", "standard": "K"}[normalized_units]
    return {
        "city": data.get("name", city),
        "country": data.get("sys", {}).get("country"),
        "temperature": temperature,
        "unit": unit_label,
        "feels_like": data["main"].get("feels_like"),
        "description": (data.get("weather") or [{}])[0].get("description"),
        "humidity_pct": data["main"].get("humidity"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
