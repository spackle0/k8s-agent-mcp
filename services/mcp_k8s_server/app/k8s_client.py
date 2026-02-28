#!/usr/bin/env python
"""
Basic libraries for kubernetes connectivity
"""

from kubernetes import client, config

def init():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    return client.CoreV1Api(), client.AppsV1Api()


core_api, apps_api = init()


def list_namespaces():
    ns = core_api.list_namespace()
    return [n.metadata.name for n in ns.items]


def list_pods(namespace: str):
    pods = core_api.list_namespaced_pod(namespace=namespace)
    return pods.items


def read_pod_log(namespace: str, pod: str, container=None, tail_lines=200):
    return core_api.read_namespaced_pod_log(
        name=pod,
        namespace=namespace,
        container=container,
        tail_lines=tail_lines,
    )