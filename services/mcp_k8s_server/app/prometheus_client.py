"""
Prometheus HTTP API client for instant PromQL queries.
"""

import os

import httpx

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")


def query(promql: str) -> list[dict]:
    """Execute an instant PromQL query and return the result vector.

    Sends a GET request to the Prometheus HTTP API and returns a list of
    dicts. Each dict contains the metric labels and the current sample value.
    Returns an empty list if no time series match the query.

    Raises httpx.HTTPStatusError on non-2xx responses.
    Raises RuntimeError if Prometheus reports a query error.
    """
    response = httpx.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": promql},
        timeout=10,
    )
    response.raise_for_status()
    body = response.json()

    if body["status"] != "success":
        raise RuntimeError(f"Prometheus query error: {body.get('error', 'unknown')}")

    result_type = body["data"]["resultType"]
    results = body["data"]["result"]

    if result_type == "vector":
        return [
            {
                "metric": item["metric"],
                "value": item["value"][1],
                "timestamp": item["value"][0],
            }
            for item in results
        ]

    if result_type == "scalar":
        return [{"value": results[1], "timestamp": results[0]}]

    # matrix or string — return raw result and let the LLM interpret it
    return results
