# server.py
#
# FastMCP server that exposes Kubernetes cluster information as MCP tools.
# Any MCP-compatible client (such as agent.py) can connect over
# streamable-HTTP and call these tools by name.
#
# Tools exposed:
#   - list_namespaces() → all namespace names in the cluster

from fastmcp import FastMCP

from services.mcp_k8s_server.app import k8s_client

# Create the FastMCP server instance. The name is metadata clients can read
# but does not affect routing or tool resolution.
mcp = FastMCP("k8s-agent")


@mcp.tool()
def list_namespaces() -> list[str]:
    """List all namespaces in the Kubernetes cluster.

    Queries the cluster using the in-cluster service account when running
    inside a pod, or falls back to the local kubeconfig when running locally.
    Returns a plain list of namespace name strings.
    """
    return k8s_client.list_namespaces()


def main():
    # Start the FastMCP server using the streamable-HTTP transport.
    # By default this listens on port 8000 at /mcp, matching MCP_SERVER_URL
    # in agent.py.
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
