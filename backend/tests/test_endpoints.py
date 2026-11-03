"""UI-managed model endpoints (e.g. a small model served from a phone) and the runtime offline switch."""

import time

import pytest
from fastapi.testclient import TestClient

from app.endpoints import Endpoint, is_local_host, locality_of, normalize_url
from app.main import create_app
from app.settings import load_settings
from tests.conftest import ROOT, fake_openai_server


def test_locality_is_decided_by_address():
    for host in ("localhost", "127.0.0.1", "192.168.1.20", "10.0.0.5", "172.20.1.1", "169.254.3.4", "::1", "fd00::1", "pixel.local"):
        assert is_local_host(host, resolve=False), host
    for host in ("8.8.8.8", "172.32.0.1", "api.example.com"):
        assert not is_local_host(host, resolve=False), host
    assert normalize_url("192.168.1.20:8080") == "http://192.168.1.20:8080/v1"
    assert normalize_url("http://phone.local:11434/v1/") == "http://phone.local:11434/v1"
    assert locality_of("https://8.8.8.8/v1") == "cloud"
    with pytest.raises(ValueError):
        normalize_url("ftp://x")
    with pytest.raises(ValueError):
        Endpoint(id="a", name="a", base_url="http://x", model="m", use_for=["everything"])


def phone_server(seen):
    return fake_openai_server(seen)


@pytest.fixture
def app_factory(tmp_path, monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "SUITE_API_TOKEN", "SUITE_OFFLINE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))

    def make(http_client=None):
        return create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), http_client=http_client)
    return make


def wait(c, rid):
    for _ in range(200):
        r = c.get(f"/api/runs/{rid}").json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(0.05)
    raise AssertionError("stuck")


def test_phone_endpoint_discover_add_and_run_restricted(app_factory):
    seen = []
    with TestClient(app_factory(phone_server(seen))) as c:
        d = c.post("/api/endpoints/discover", json={"base_url": "192.168.1.42:8080"}).json()
        assert d == {"base_url": "http://192.168.1.42:8080/v1", "locality": "local",
                     "models": ["gemma-2-2b-it", "qwen2.5-3b-instruct"]}
        ep = c.post("/api/endpoints", json={"id": "Pixel 9", "name": "Phone (Pixel 9)", "base_url": d["base_url"],
                                            "model": "qwen2.5-3b-instruct", "use_for": ["specialist", "synthesis"]}).json()
        assert ep["provider"] == "ep-pixel-9" and ep["locality"] == "local"
        o = c.get("/api/overview").json()
        assert o["tiers"]["synthesis"][0] == "ep-pixel-9/qwen2.5-3b-instruct"
        # Not chosen for review: still a fallback there, after the models already in the chain.
        assert o["tiers"]["review"][-1] == "ep-pixel-9/qwen2.5-3b-instruct"
        assert next(p for p in o["providers"] if p["name"] == "ep-pixel-9")["available"]
        # Restricted data may only reach local models: the phone qualifies.
        rid = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Summarise my notes"},
                                        "data_class": "restricted"}).json()["id"]
        run = wait(c, rid)
        step = c.get(f"/api/runs/{rid}").json()["steps"][0]
        assert run["status"] == "completed" and step["model"] == "ep-pixel-9/qwen2.5-3b-instruct"
        assert any(w.startswith("context fit") for w in step["warnings"]), "4k context must trim the prompt and say so"
        assert c.post("/api/providers/ep-pixel-9/test").json()["ok"]
        assert c.delete("/api/endpoints/pixel-9").status_code == 200
        assert all("ep-pixel-9/qwen2.5-3b-instruct" not in ch for ch in c.get("/api/overview").json()["tiers"].values())


def test_public_endpoint_is_cloud_and_blocked_for_restricted(app_factory):
    with TestClient(app_factory(phone_server([]))) as c:
        c.post("/api/endpoints", json={"id": "rented", "name": "Rented GPU", "base_url": "http://8.8.8.8:8000",
                                       "model": "qwen2.5-3b-instruct", "use_for": ["specialist", "synthesis", "router", "review"]})
        o = c.get("/api/overview").json()
        assert next(p for p in o["providers"] if p["name"] == "ep-rented")["locality"] == "cloud"
        rid = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "x"}, "data_class": "restricted"}).json()["id"]
        run = c.get(f"/api/runs/{wait(c, rid)['id']}").json()
        step = run["steps"][0]
        assert step["status"] == "BLOCKED" and not step["model"]
        assert "No model configured" in step["error"] and "not allowed for 'restricted'" in step["error"]


def test_offline_toggle_persists_and_limits_endpoints(app_factory):
    with TestClient(app_factory(phone_server([]))) as c:
        assert c.post("/api/admin/offline", json={"on": True}).json()["on"] is True
        o = c.get("/api/overview").json()
        assert o["offline"] and o["offline_override"] is True
        assert all(not p["available"] for p in o["providers"] if p["locality"] == "cloud")
        assert c.post("/api/endpoints/discover", json={"base_url": "http://8.8.8.8"}).status_code == 409
        assert c.post("/api/endpoints", json={"id": "x", "name": "x", "base_url": "http://8.8.8.8", "model": "m"}).status_code == 409
        assert c.post("/api/endpoints", json={"id": "lan", "name": "Laptop", "base_url": "http://10.0.0.7:11434",
                                              "model": "qwen2.5-3b-instruct"}).status_code == 201
    with TestClient(app_factory(phone_server([]))) as c:  # restart: choice survives
        o = c.get("/api/overview").json()
        assert o["offline"] and [e["id"] for e in o["endpoints"]] == ["lan"]
        assert c.post("/api/admin/offline", json={"on": None}).json() == {"on": False, "override": None, "default": False}
