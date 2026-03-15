# server.py
#
# FastMCP server that exposes Kubernetes cluster information as MCP tools.
# Any MCP-compatible client (such as agent.py) can connect over
# streamable-HTTP and call these tools by name.
#
# Tools exposed:
#   - list_namespaces()   → all namespace names in the cluster
#   - list_pods()         → pod status dicts for a given namespace
#   - read_pod_log()      → last N lines of a pod's container logs
#   - query_prometheus()  → instant PromQL query against Prometheus

from fastmcp import FastMCP

from services.mcp_k8s_server.app import k8s_client, prometheus_client

# Create the FastMCP server instance. The name is metadata clients can read
# but does not affect routing or tool resolution.
mcp = FastMCP("k8s-agent")


@mcp.tool()
def list_namespaces() -> list[str]:
    """List all namespaces in the Kubernetes cluster.

    Returns a plain list of namespace name strings. Takes no arguments.
    """
    return k8s_client.list_namespaces()


@mcp.tool()
def list_pods(namespace: str) -> list[dict]:
    """List all pods in a given namespace with their current status.

    Takes a namespace string and returns a list of dicts, each with:
      - name: pod name
      - phase: overall pod phase (Running, Pending, Failed, Succeeded, Unknown)
      - ready: true if all containers are passing their readiness checks
      - restart_count: total restarts across all containers in the pod
      - reason: waiting reason if a container is stuck (e.g., CrashLoopBackOff,
                ImagePullBackOff, OOMKilled), or null if not applicable
    """
    return k8s_client.list_pods(namespace)


@mcp.tool()
def read_pod_log(namespace: str, pod: str, container: str | None = None, tail_lines: int = 20) -> str:
    """Read the logs for a pod's container.

    Returns the last `tail_lines` lines of the pod's logs as a plain string.
    If `container` is None, logs from the pod's default container are returned.
    """
    logs = k8s_client.read_pod_log(namespace, pod, container=container, tail_lines=tail_lines)
    # Kubernetes client returns a raw string for logs; ensure we return a string.
    return logs or ""


@mcp.tool()
def query_prometheus(query: str) -> list[dict]:
    """Execute an instant PromQL query against Prometheus and return matching time series.

    Takes a PromQL query string and returns a list of dicts, each with:
      - metric: dict of label key/value pairs identifying the time series
                (e.g. {"pod": "my-pod", "namespace": "default", "job": "kubelet"})
      - value: the current sample value as a string (e.g. "1", "0.042")
      - timestamp: Unix timestamp of the sample as a float

    Returns an empty list if no time series match the query.

    Example queries:
      - up
      - container_cpu_usage_seconds_total{namespace="default"}
      - kube_pod_container_status_restarts_total > 0
      - rate(http_requests_total[5m])
    """
    return prometheus_client.query(query)


def main():
    # Start the FastMCP server using the streamable-HTTP transport.
    # By default, this listens on port 8000 at /mcp, matching MCP_SERVER_URL
    # in agent.py.
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
