# server.py
#

from typing import Any

import httpx
from fastmcp import FastMCP

from services.mcp_k8s_server.app import k8s_client

# Create the FastMCP server instance. The name ("weather") is metadata that
# clients can read but does not affect routing or tool resolution.
mcp = FastMCP("weather")

# NWS REST API base URL and the User-Agent header it requires.
# The NWS rejects requests without a descriptive User-Agent.
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "weather-app/1.0"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Send a GET request to the NWS API and return the parsed JSON body.

    Uses httpx for async HTTP so the server event loop is never blocked.
    Returns None on any error (network failure, non-2xx status, etc.) so
    callers can handle the missing-data case without catching exceptions.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


def format_alert(feature: dict) -> str:
    """Convert a single GeoJSON alert feature into a readable text block.

    The NWS returns alerts as a GeoJSON FeatureCollection. Each feature's
    metadata lives under the "properties" key — this helper pulls the fields
    most relevant to an end user and formats them as a plain-text summary.
    """
    props = feature["properties"]
    return f"""
Event: {props.get("event", "Unknown")}
Area: {props.get("areaDesc", "Unknown")}
Severity: {props.get("severity", "Unknown")}
Description: {props.get("description", "No description available")}
Instructions: {props.get("instruction", "No specific instructions provided")}
"""


@mcp.tool()
async def get_alerts(state: str) -> str:
    """Get weather alerts for a US state.

    Calls the NWS active-alerts endpoint filtered by state, then formats
    each alert into a human-readable block separated by "---" dividers.
    Returns a plain error string (rather than raising) so the LLM can relay
    the failure message to the user gracefully.

    Args:
        state: Two-letter US state code (e.g. CA, NY)
    """
    url = f"{NWS_API_BASE}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        return "Unable to fetch alerts or no alerts found."

    if not data["features"]:
        return "No active alerts for this state."

    alerts = [format_alert(feature) for feature in data["features"]]
    return "\n---\n".join(alerts)


@mcp.tool()
async def get_forecast(latitude: float, longitude: float) -> str:
    """Get weather forecast for a location.

    The NWS forecast API is a two-step process:
      1. Hit /points/{lat},{lon} to get the grid metadata for that location,
         which includes the URL of the actual forecast endpoint.
      2. Hit that forecast URL to retrieve the time-segmented periods.

    We return the next 5 periods (e.g. "Tonight", "Thursday", …) so the
    response stays concise while still being useful.

    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
    """
    # Step 1: resolve the lat/lon to an NWS forecast grid cell.
    points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)

    if not points_data:
        return "Unable to fetch forecast data for this location."

    # Step 2: fetch the actual forecast using the URL from the grid metadata.
    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)

    if not forecast_data:
        return "Unable to fetch detailed forecast."

    # Format each period into a short block and join them with dividers.
    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show the next 5 periods
        forecast = f"""
{period["name"]}:
Temperature: {period["temperature"]}°{period["temperatureUnit"]}
Wind: {period["windSpeed"]} {period["windDirection"]}
Forecast: {period["detailedForecast"]}
"""
        forecasts.append(forecast)

    return "\n---\n".join(forecasts)


def main():
    # Start the FastMCP server using the streamable-HTTP transport.
    # By default, this listens on port 8000 at /mcp, matching MCP_SERVER_URL
    # in agent.py.
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
