#!/usr/bin/env python
"""
Basic libraries for kubernetes connectivity
"""

from kubernetes import client, config
from functools import cache
from typing import List, Optional


class K8sClient:
    """Connection manager for Kubernetes API clients.

    This class is responsible for creating, refreshing, and providing access
    to the underlying Kubernetes API client objects (CoreV1Api and AppsV1Api).
    It intentionally does NOT implement high-level operations to avoid a
    "god class" — those operations remain as module-level functions below.
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
        """Force reloading of configuration and recreate API clients.

        Call this if cluster credentials/config may have changed while the
        process is running.
        """
        self._init_clients()


@cache
def get_client() -> K8sClient:
    """Return a cached K8sClient instance for the process."""
    return K8sClient()


# Module-level convenience functions (preserve the previous public API)
def list_namespaces() -> List[str]:
    core_api = get_client().core()
    ns = core_api.list_namespace()
    return [n.metadata.name for n in ns.items]


def list_pods(namespace: str):
    core_api = get_client().core()
    pods = core_api.list_namespaced_pod(namespace=namespace)
    return pods.items


def read_pod_log(namespace: str, pod: str, container: Optional[str] = None, tail_lines: int = 20):
    core_api = get_client().core()
    return core_api.read_namespaced_pod_log(
        name=pod,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
    )
