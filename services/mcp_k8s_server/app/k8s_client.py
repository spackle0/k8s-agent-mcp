#!/usr/bin/env python
"""
Basic libraries for kubernetes connectivity
"""

from functools import cache
from kubernetes import client, config


class K8sClient:
    """Holds initialized Kubernetes API clients."""

    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()

    def core(self) -> client.CoreV1Api:
        """Return the CoreV1Api instance."""
        return self._core_api

    def apps(self) -> client.AppsV1Api:
        """Return the AppsV1Api instance."""
        return self._apps_api


@cache
def get_client() -> K8sClient:
    """Return a cached K8sClient instance for the process."""
    return K8sClient()


def list_namespaces() -> list[str]:
    """Return a list of namespaces in a kubernetes cluster.
    """
    core_api = get_client().core()
    ns = core_api.list_namespace()
    return [n.metadata.name for n in ns.items]


def list_pods(namespace: str) -> list[dict]:
    """Return a list of structured pod dicts for the given namespace.

    Each dict contains:
      - name: str
      - phase: str
      - ready: bool
      - restart_count: int
      - reason: str | None

    This is JSON-serializable and safe to return from MCP tools.
    """
    core_api = get_client().core()
    pods = core_api.list_namespaced_pod(namespace=namespace)

    result: list[dict] = []
    for pod in pods.items:
        name = getattr(pod.metadata, "name", "")
        phase = getattr(pod.status, "phase", "Unknown")

        # Determine readiness: all container statuses must be ready
        ready = True
        restart_count = 0
        reason = None
        container_statuses = getattr(pod.status, "container_statuses", None) or []
        for status in container_statuses:
            ready = ready and bool(getattr(status, "ready", False))
            restart_count += int(getattr(status, "restart_count", 0))
            # If a waiting state is present, prefer that reason
            state = getattr(status, "state", None)
            if state:
                waiting = getattr(state, "waiting", None)
                if waiting and getattr(waiting, "reason", None):
                    reason = getattr(waiting, "reason")

        # Fall back to pod-level reason if none found
        if not reason:
            reason = getattr(pod.status, "reason", None)

        result.append(
            {
                "name": name,
                "phase": phase,
                "ready": ready,
                "restart_count": restart_count,
                "reason": reason,
            }
        )

    return result


def read_pod_log(namespace: str, pod: str, container: str | None = None, tail_lines: int = 20) -> str:
    """Return the last tail_lines lines of logs for a pod's container.

    If container is None, the pod's default container is used. Returns a plain
    string. Returns an empty string if no logs are available.
    """
    core_api = get_client().core()
    return core_api.read_namespaced_pod_log(
        name=pod,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
    )
