import pytest

# Import the server module directly so we can patch its k8s_client import.
from services.mcp_k8s_server.app import server as server_app


@pytest.fixture(autouse=True)
def patch_k8s_client(monkeypatch):
    """Patch the k8s_client functions so we don't need a real K8s cluster.

    This makes the smoke test fast and hermetic: the server functions are
    exercised end-to-end, but the underlying K8s calls are stubbed.
    """

    # noinspection PyUnusedLocal
    class FakeK8sClient:
        @staticmethod
        def list_namespaces():
            return ["default", "kube-system"]

        @staticmethod
        def list_pods(namespace: str):
            return [{
                "name": "mypod",
                "phase": "Running",
                "ready": True,
                "restart_count": 0,
                "reason": None,
            }]

        @staticmethod
        def read_pod_log(namespace: str, pod: str, container=None, tail_lines=20):
            return "line1\nline2\nline3"

    monkeypatch.setattr(server_app.k8s_client, "get_client", lambda: FakeK8sClient())
    monkeypatch.setattr(server_app.k8s_client, "list_namespaces", lambda: FakeK8sClient().list_namespaces())
    monkeypatch.setattr(server_app.k8s_client, "list_pods", lambda ns: FakeK8sClient().list_pods(ns))
    monkeypatch.setattr(server_app.k8s_client, "read_pod_log", lambda ns, p, container=None, tail_lines=20: FakeK8sClient().read_pod_log(ns, p, container=container, tail_lines=tail_lines))


def test_list_namespaces():
    ns = server_app.list_namespaces()
    assert isinstance(ns, list)
    assert "default" in ns


def test_list_pods():
    pods = server_app.list_pods("default")
    assert isinstance(pods, list)
    assert isinstance(pods[0], dict)
    assert pods[0]["name"] == "mypod"


def test_read_pod_log():
    logs = server_app.read_pod_log("default", "mypod")
    assert isinstance(logs, str)
    assert "line1" in logs
