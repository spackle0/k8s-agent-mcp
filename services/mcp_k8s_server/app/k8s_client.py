#!/usr/bin/env python
"""
Basic libraries for kubernetes connectivity
"""

from kubernetes import client, config
from functools import cache
from typing import List, Optional


class K8sClient:
    """Connection manager for Kubernetes API clients.

    Responsible for creating, refreshing, and providing access to the
    underlying Kubernetes API client objects (CoreV1Api and AppsV1Api).
    """

    def __init__(self) -> None:
        self._init_clients()

    def _init_clients(self) -> None:
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

    def refresh(self) -> None:
        """Reload configuration and recreate API clients."""
        self._init_clients()

    def close(self) -> None:
        """Attempt to close underlying ApiClient connections if supported.

        This is best-effort; the kubernetes ApiClient exposes a `close()` on
        its `api_client` attribute which we call when available.
        """
        try:
            if hasattr(self._core_api, "api_client") and hasattr(self._core_api.api_client, "close"):
                self._core_api.api_client.close()
        except Exception:
            # Best-effort close; swallow exceptions to avoid noisy shutdown
            pass

        try:
            if hasattr(self._apps_api, "api_client") and hasattr(self._apps_api.api_client, "close"):
                self._apps_api.api_client.close()
        except Exception:
            pass


@cache
def get_client() -> K8sClient:
    """Return a cached K8sClient instance for the process."""
    return K8sClient()


def refresh_client() -> None:
    """Refresh the cached client's credentials/configuration."""
    get_client().refresh()


def close_client() -> None:
    """Close the cached client and clear the cache so a new instance will be created.

    Use this when credentials or network resources change and you want a fresh
    client object on next access.
    """
    try:
        get_client().close()
    finally:
        # Clear the cached instance so get_client() will construct a new one.
        get_client.cache_clear()


# Module-level convenience functions (preserve previous public API)
def list_namespaces() -> List[str]:
    core_api = get_client().core()
    ns = core_api.list_namespace()
    return [n.metadata.name for n in ns.items]


def list_pods(namespace: str) -> List[dict]:
    """Return a list of structured pod dicts for the given namespace.

    Each dict contains:
      - name: str
      - phase: str
      - ready: bool
      - restart_count: int
      - reason: Optional[str]

    This is JSON-serializable and safe to return from MCP tools.
    """
    core_api = get_client().core()
    pods = core_api.list_namespaced_pod(namespace=namespace)

    result: List[dict] = []
    for p in pods.items:
        name = getattr(p.metadata, "name", "")
        phase = getattr(p.status, "phase", "Unknown")

        # Determine readiness: all container statuses must be ready
        ready = True
        restart_count = 0
        reason = None
        container_statuses = getattr(p.status, "container_statuses", None) or getattr(p.status, "containerStatuses", None) or []
        for cs in container_statuses:
            ready = ready and bool(getattr(cs, "ready", False))
            restart_count += int(getattr(cs, "restart_count", getattr(cs, "restartCount", 0)))
            # If a waiting state is present, prefer that reason
            state = getattr(cs, "state", None)
            if state:
                waiting = getattr(state, "waiting", None)
                if waiting and getattr(waiting, "reason", None):
                    reason = getattr(waiting, "reason")

        # Fall back to pod-level reason if none found
        if not reason:
            reason = getattr(p.status, "reason", None)

        result.append({
            "name": name,
            "phase": phase,
            "ready": ready,
            "restart_count": restart_count,
            "reason": reason,
        })

    return result


def read_pod_log(namespace: str, pod: str, container: Optional[str] = None, tail_lines: int = 20) -> str:
    core_api = get_client().core()
    return core_api.read_namespaced_pod_log(
        name=pod,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
    )
