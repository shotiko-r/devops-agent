import requests

import config


PROMETHEUS_URL = config.PROMETHEUS_URL


def prometheus_query(query: str):
    """
    Execute a PromQL query against the local Prometheus server.
    """

    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=config.PROMETHEUS_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("status") != "success":
            return f"Prometheus error: {data}"

        return data["data"]["result"]

    except requests.RequestException as e:
        return f"Prometheus connection error: {e}"