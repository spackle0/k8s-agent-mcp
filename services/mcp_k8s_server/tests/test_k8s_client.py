"""Tests for the field extraction in k8s_client.

test_smoke.py stubs k8s_client out entirely to exercise the MCP tool wrappers.
These tests go the other way: they feed real kubernetes client model objects
through the extraction logic, which is where the interesting behaviour lives
(readiness, restart summing, waiting-reason precedence, pod-level fallback).

Real V1Pod objects are used rather than simple stand-ins so that a rename in
the kubernetes client (`container_statuses`, `restart_count`) fails the tests
instead of silently returning defaults through `getattr`.
"""

import pytest
from kubernetes.client import (
    V1ContainerState,
    V1ContainerStateWaiting,
    V1ContainerStatus,
    V1Namespace,
    V1NamespaceList,
    V1ObjectMeta,
    V1Pod,
    V1PodList,
    V1PodStatus,
)
from services.mcp_k8s_server.app import k8s_client

# --- helpers ----------------------------------------------------------------


def container_status(name="web", ready=True, restart_count=0, waiting_reason=None):
    """Build a V1ContainerStatus, optionally stuck in a waiting state."""
    state = None
    if waiting_reason is not None:
        state = V1ContainerState(waiting=V1ContainerStateWaiting(reason=waiting_reason))
    return V1ContainerStatus(
        name=name,
        ready=ready,
        restart_count=restart_count,
        image="example:latest",
        image_id="",
        state=state,
    )


def pod(name="mypod", phase="Running", container_statuses=None, reason=None):
    """Build a V1Pod with the status fields list_pods reads."""
    return V1Pod(
        metadata=V1ObjectMeta(name=name),
        status=V1PodStatus(phase=phase, container_statuses=container_statuses, reason=reason),
    )


class FakeCoreApi:
    """Stands in for CoreV1Api, recording the arguments it was called with."""

    def __init__(self, pods=None, namespaces=None, log_text=""):
        self._pods = pods if pods is not None else []
        self._namespaces = namespaces if namespaces is not None else []
        self._log_text = log_text
        self.calls = []

    def list_namespaced_pod(self, namespace):
        self.calls.append(("list_namespaced_pod", {"namespace": namespace}))
        return V1PodList(items=self._pods)

    def list_namespace(self):
        self.calls.append(("list_namespace", {}))
        return V1NamespaceList(
            items=[V1Namespace(metadata=V1ObjectMeta(name=n)) for n in self._namespaces]
        )

    def read_namespaced_pod_log(self, name, namespace, container, tail_lines):
        self.calls.append(
            (
                "read_namespaced_pod_log",
                {
                    "name": name,
                    "namespace": namespace,
                    "container": container,
                    "tail_lines": tail_lines,
                },
            )
        )
        return self._log_text


@pytest.fixture
def fake_api(monkeypatch):
    """Patch get_client so no real cluster or kubeconfig is needed.

    get_client is @cache'd, so patching the module attribute rather than the
    K8sClient constructor keeps a cached instance from leaking between tests.
    """
    api = FakeCoreApi()

    class FakeK8sClient:
        @staticmethod
        def core():
            return api

    monkeypatch.setattr(k8s_client, "get_client", lambda: FakeK8sClient())
    return api


# --- list_pods: readiness ---------------------------------------------------


def test_ready_when_all_containers_ready(fake_api):
    fake_api._pods = [pod(container_statuses=[container_status(ready=True)])]
    assert k8s_client.list_pods("default")[0]["ready"] is True


def test_not_ready_when_any_container_not_ready(fake_api):
    """Readiness is an AND across containers, not a property of the first one."""
    fake_api._pods = [
        pod(
            container_statuses=[
                container_status(name="web", ready=True),
                container_status(name="sidecar", ready=False),
            ]
        )
    ]
    assert k8s_client.list_pods("default")[0]["ready"] is False


def test_not_ready_when_no_container_statuses(fake_api):
    """A Pending pod has no container statuses and must not report as ready.

    This is the case that matters most for the agent: reporting a pod stuck
    waiting to be scheduled as ready sends the LLM down the wrong path.
    """
    fake_api._pods = [pod(phase="Pending", container_statuses=None)]
    result = k8s_client.list_pods("default")[0]
    assert result["ready"] is False
    assert result["phase"] == "Pending"


# --- list_pods: restart counts ----------------------------------------------


def test_restart_count_sums_across_containers(fake_api):
    fake_api._pods = [
        pod(
            container_statuses=[
                container_status(name="web", restart_count=3),
                container_status(name="sidecar", restart_count=4),
            ]
        )
    ]
    assert k8s_client.list_pods("default")[0]["restart_count"] == 7


def test_restart_count_zero_with_no_container_statuses(fake_api):
    fake_api._pods = [pod(phase="Pending", container_statuses=None)]
    assert k8s_client.list_pods("default")[0]["restart_count"] == 0


# --- list_pods: reason ------------------------------------------------------


def test_waiting_reason_is_reported(fake_api):
    fake_api._pods = [
        pod(
            container_statuses=[
                container_status(ready=False, restart_count=5, waiting_reason="CrashLoopBackOff")
            ]
        )
    ]
    result = k8s_client.list_pods("default")[0]
    assert result["reason"] == "CrashLoopBackOff"
    assert result["ready"] is False
    assert result["restart_count"] == 5


def test_reason_is_none_when_running_cleanly(fake_api):
    fake_api._pods = [pod(container_statuses=[container_status()])]
    assert k8s_client.list_pods("default")[0]["reason"] is None


def test_falls_back_to_pod_level_reason(fake_api):
    """Evicted pods carry the reason on the pod status, not on a container."""
    fake_api._pods = [
        pod(
            phase="Failed",
            container_statuses=[container_status(ready=False)],
            reason="Evicted",
        )
    ]
    assert k8s_client.list_pods("default")[0]["reason"] == "Evicted"


def test_container_waiting_reason_wins_over_pod_reason(fake_api):
    """A container-level waiting reason is more specific, so it takes priority."""
    fake_api._pods = [
        pod(
            phase="Pending",
            container_statuses=[container_status(ready=False, waiting_reason="ImagePullBackOff")],
            reason="SomethingBroader",
        )
    ]
    assert k8s_client.list_pods("default")[0]["reason"] == "ImagePullBackOff"


# --- list_pods: shape and plumbing ------------------------------------------


def test_returns_json_serializable_dicts(fake_api):
    """MCP tools must return serializable types, so no V1* objects may leak."""
    import json

    fake_api._pods = [
        pod(name="a", container_statuses=[container_status()]),
        pod(name="b", phase="Pending", container_statuses=None),
    ]
    result = k8s_client.list_pods("default")

    json.dumps(result)  # raises TypeError if a kubernetes model leaked through
    assert [p["name"] for p in result] == ["a", "b"]
    assert set(result[0]) == {"name", "phase", "ready", "restart_count", "reason"}


def test_empty_namespace_returns_empty_list(fake_api):
    fake_api._pods = []
    assert k8s_client.list_pods("default") == []


def test_namespace_is_passed_through(fake_api):
    k8s_client.list_pods("kube-system")
    assert fake_api.calls == [("list_namespaced_pod", {"namespace": "kube-system"})]


# --- list_namespaces --------------------------------------------------------


def test_list_namespaces_returns_names(fake_api):
    fake_api._namespaces = ["default", "kube-system", "monitoring"]
    assert k8s_client.list_namespaces() == ["default", "kube-system", "monitoring"]


# --- read_pod_log -----------------------------------------------------------


def test_read_pod_log_forwards_arguments(fake_api):
    fake_api._log_text = "line1\nline2"
    result = k8s_client.read_pod_log("default", "mypod", container="web", tail_lines=50)

    assert result == "line1\nline2"
    assert fake_api.calls == [
        (
            "read_namespaced_pod_log",
            {"name": "mypod", "namespace": "default", "container": "web", "tail_lines": 50},
        )
    ]


def test_read_pod_log_defaults(fake_api):
    k8s_client.read_pod_log("default", "mypod")
    _, kwargs = fake_api.calls[0]
    assert kwargs["container"] is None
    assert kwargs["tail_lines"] == 20
