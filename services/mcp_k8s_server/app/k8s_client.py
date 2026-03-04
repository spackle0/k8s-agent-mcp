#!/usr/bin/env python
"""
Basic libraries for kubernetes connectivity
"""

from kubernetes import client, config

def init():
    """
    Initialize and cache Kubernetes API clients.

    This function is safe to call multiple times; it will only perform
    configuration loading and client construction on first use.
    """
    global core_api, apps_api

    if core_api is not None and apps_api is not None:
        return core_api, apps_api

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    return core_api, apps_api


core_api = None
apps_api = None


def list_namespaces() -> list[str]:
    core_api_client, _ = init()
    ns = core_api_client.list_namespace()
    return [n.metadata.name for n in ns.items]


def list_pods(namespace: str) -> list[str]:
    core_api_client, _ = init()
    pods = core_api_client.list_namespaced_pod(namespace=namespace)
    return pods.items


def read_pod_log(namespace: str, pod: str, container=None, tail_lines=20) -> list[str]:
    core_api_client, _ = init()
    return core_api_client.read_namespaced_pod_log(
        name=pod,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
    )