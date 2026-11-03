"""API end to end against a fake local OpenAI-compatible server (no real model needed)."""

import json
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import load_settings
from tests.conftest import ROOT, fake_openai_server

KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "SUITE_API_TOKEN", "SUITE_OFFLINE")


@pytest.fixture
def factory(tmp_path, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))

    def make(http_client=None, config=ROOT / "config" / "suite.example.yaml"):
        return TestClient(create_app(load_settings(ROOT, config), http_client=http_client))
    return make


@pytest.fixture
def client(factory):
    """Example config plus one local endpoint served by the fake server."""
    with factory(fake_openai_server([])) as c:
        assert c.post("/api/endpoints", json={"id": "lan", "name": "Workstation", "base_url": "http://10.0.0.7:1234",
                                              "model": "qwen2.5-3b-instruct", "context_tokens": 32768,
                                              "use_for": ["router", "specialist", "synthesis", "review"]}).status_code == 201
        yield c


def wait(client, rid, until=("completed", "awaiting_approval", "failed", "cancelled")):
    for _ in range(200):
        r = client.get(f"/api/runs/{rid}").json()
        if r["status"] in until:
            return r
        time.sleep(0.05)
    raise AssertionError(f"run stuck in {r['status']}")


def test_overview_and_catalog(client):
    o = client.get("/api/overview").json()
    assert len(o["agents"]) == 34 and len(o["playbooks"]) == 19 and len(o["desks"]) == 8
    assert {c["id"] for c in o["connectors"]} >= {"github", "microsoft365", "databricks-genie", "azure-devops"}
    assert {p["type"] for p in o["providers"]} <= {"openai_compatible", "anthropic"}
    assert not any("demo" in r for chain in o["tiers"].values() for r in chain)
    a = client.get("/api/agents/chief-of-staff").json()
    assert a["persona"] == "persona_x" and "daily" in a["modes"]
    assert client.get("/api/agents/nope").status_code == 404


def test_no_model_configured_blocks_runs(factory):
    with factory() as c:
        assert not [p for p in c.get("/api/overview").json()["providers"] if p["available"]]
        rid = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "hi"}}).json()["id"]
        run = wait(c, rid)
        assert run["status"] == "completed" and run["outcome"] == "BLOCKED"
        assert "No model configured" in run["deliverable"] and "Settings" in run["deliverable"]


def test_route_falls_back_to_keywords(factory):
    with factory() as c:
        r = c.post("/api/route", json={"text": "Can we add a CSV export? It's a scope change request"}).json()
        assert r["playbook"] == "scope-change" and r["method"] == "keywords"
        r = c.post("/api/route", json={"text": "zzz"}).json()
        assert r["playbook"] == "quick-ask" and not r["auto"]


def test_run_gate_export_and_audit(client):
    bad = client.post("/api/runs", json={"playbook_id": "scope-change", "inputs": {"request": "x"}})
    assert bad.status_code == 422
    rid = client.post("/api/runs", json={"playbook_id": "scope-change", "inputs": {
        "request": "Add SSO export", "effort_hours": 16, "project": "Portal"}}).json()["id"]
    run = wait(client, rid)
    assert run["status"] == "awaiting_approval" and run["demo"] is False
    apr = client.get("/api/approvals").json()
    assert apr and apr[0]["run_id"] == rid
    assert client.post(f"/api/approvals/{apr[0]['id']}", json={"decision": "approved", "decided_by": ""}).status_code == 409
    ok = client.post(f"/api/approvals/{apr[0]['id']}", json={"decision": "approved", "decided_by": "Jordan"})
    assert ok.status_code == 200
    run = wait(client, rid, until=("completed", "failed"))
    assert run["status"] == "completed" and "Model answer." in run["deliverable"] and "Demo" not in run["deliverable"]
    md = client.get(f"/api/runs/{rid}/export?format=md")
    assert md.status_code == 200 and "attachment" in md.headers["content-disposition"]
    html = client.get(f"/api/runs/{rid}/export?format=html").text
    assert html.startswith("<!doctype html>") and "<script" not in html
    events = {e["event"] for e in client.get(f"/api/audit?run_id={rid}").json()}
    assert {"run_started", "model_call", "approval_requested", "approval_decided", "run_completed"} <= events
    # Delete: the run and its steps go, the audit trail stays.
    assert client.delete(f"/api/runs/{rid}").json() == {"deleted": 1}
    assert client.get(f"/api/runs/{rid}").status_code == 404
    assert "run_deleted" in {e["event"] for e in client.get(f"/api/audit?run_id={rid}").json()}
    assert client.delete("/api/runs/nope").status_code == 404


def test_delete_demo_runs_from_earlier_versions(client):
    rid = client.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "hi"}}).json()["id"]
    wait(client, rid)
    store = client.app.state.suite.store
    old = store.create_run("quick-ask", "old demo run", "internal", {"request": "x"}, {})
    store.update_run(old, demo=1, status="completed")
    assert client.delete("/api/runs").status_code == 422
    assert client.delete("/api/runs?demo=true").json() == {"deleted": 1}
    assert [r["id"] for r in client.get("/api/runs").json()] == [rid]


def test_file_upload_and_kill_switch(client):
    up = client.post("/api/files", files={"file": ("notes.md", b"# Notes\nShip on Friday", "text/markdown")})
    assert up.status_code == 200 and up.json()["chars"] > 5
    assert client.post("/api/files", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415
    assert client.post("/api/admin/kill-switch", json={"on": True, "by": "admin"}).json() == {"on": True}
    r = client.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "hi"}})
    assert r.status_code == 423
    client.post("/api/admin/kill-switch", json={"on": False})
    rid = client.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "hi", "documents": [up.json()["id"]]}}).json()["id"]
    assert wait(client, rid)["status"] == "completed"


def test_edit_local_provider_with_api_key(factory):
    """LM Studio with authentication on: 401 until the key is entered with Edit; the key is never returned."""
    seen: list = []
    server = fake_openai_server(seen, models=("qwen3-4b", "gemma-3-4b"), require_key="sk-lm-123")
    with factory(server) as c:
        lm = next(p for p in c.get("/api/overview").json()["providers"] if p["name"] == "lmstudio")
        assert not lm["enabled"] and lm["reason"] == "switched off" and lm["base_url"] == "http://localhost:1234/v1"

        r = c.post("/api/endpoints/discover", json={"provider": "lmstudio"})
        assert r.status_code == 502 and "needs an API key" in r.json()["detail"]
        d = c.post("/api/endpoints/discover", json={"provider": "lmstudio", "api_key": "sk-lm-123"}).json()
        assert d["models"] == ["gemma-3-4b", "qwen3-4b"]

        r = c.put("/api/providers/lmstudio", json={"enabled": True, "api_key": "sk-lm-123",
                                                    "models": [{"model": "qwen3-4b", "context_tokens": 32768}]})
        assert r.status_code == 200
        lm = r.json()
        assert lm["available"] and lm["enabled"] and lm["edited_in_app"] and lm["api_key_source"] == "app"
        assert [m["ref"] for m in lm["models"]] == ["lmstudio/qwen3-4b"]
        o = c.get("/api/overview")
        assert "sk-lm-123" not in o.text and "sk-lm-123" not in c.get("/api/providers").text
        # The removed placeholder model's slot in the chains now uses the edited model.
        assert "lmstudio/qwen3-4b" in o.json()["tiers"]["specialist"]
        assert not any(r == "lmstudio/local-model" for ch in o.json()["tiers"].values() for r in ch)
        # Saved key is used for discovery and runs.
        assert c.post("/api/endpoints/discover", json={"provider": "lmstudio"}).status_code == 200
        assert c.post("/api/providers/lmstudio/test").json()["ok"]
        rid = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "hi"},
                                        "data_class": "restricted"}).json()["id"]
        wait(c, rid)
        st = c.get(f"/api/runs/{rid}").json()["steps"][0]
        assert st["model"] == "lmstudio/qwen3-4b", (st["error"], st["warnings"])
        # Switching off keeps the key; audit records the change without the key value.
        assert c.put("/api/providers/lmstudio", json={"enabled": False}).json()["reason"] == "switched off"
        audit = c.get("/api/audit").text
        assert "provider_edited" in audit and "sk-lm-123" not in audit

    with factory(fake_openai_server([], models=("qwen3-4b",), require_key="sk-lm-123")) as c:  # restart: edits survive
        lm = next(p for p in c.get("/api/overview").json()["providers"] if p["name"] == "lmstudio")
        assert not lm["enabled"] and lm["api_key_source"] == "app"
        lm = c.put("/api/providers/lmstudio", json={"enabled": True}).json()
        assert lm["available"]
        lm = c.put("/api/providers/lmstudio", json={"clear_api_key": True}).json()
        assert lm["api_key_source"] == "config"  # back to the file placeholder
        lm = c.delete("/api/providers/lmstudio/override").json()
        assert not lm["enabled"] and not lm["edited_in_app"] and [m["ref"] for m in lm["models"]] == ["lmstudio/local-model"]
        assert c.delete("/api/providers/lmstudio/override").status_code == 404
        assert c.put("/api/providers/nope", json={"enabled": True}).status_code == 404
        assert c.put("/api/providers/ollama", json={"base_url": "ftp://x"}).status_code == 422
        # A local provider pointed outside your network becomes cloud.
        assert c.put("/api/providers/ollama", json={"base_url": "http://8.8.8.8:11434"}).json()["locality"] == "cloud"


def test_endpoint_api_key_is_write_only(factory):
    with factory(fake_openai_server([], require_key="tok")) as c:
        assert c.post("/api/endpoints/discover", json={"base_url": "10.0.0.9:8080"}).status_code == 502
        assert c.post("/api/endpoints/discover", json={"base_url": "10.0.0.9:8080", "api_key": "tok"}).status_code == 200
        ep = c.post("/api/endpoints", json={"id": "box", "name": "GPU box", "base_url": "10.0.0.9:8080",
                                            "model": "qwen2.5-3b-instruct", "api_key": "tok"}).json()
        assert ep["has_api_key"] and "api_key" not in ep
        # Re-saving without a key keeps the saved one.
        ep = c.post("/api/endpoints", json={"id": "box", "name": "GPU box 2", "base_url": "10.0.0.9:8080",
                                            "model": "qwen2.5-3b-instruct"}).json()
        assert ep["has_api_key"] and ep["name"] == "GPU box 2"
        assert c.post("/api/providers/ep-box/test").json()["ok"]
        assert "tok\"" not in c.get("/api/endpoints").text and "has_api_key" in c.get("/api/overview").text
        assert c.put("/api/providers/ep-box", json={"enabled": False}).status_code == 409


def test_discover_explains_unreachable_and_wrong_path(factory):
    import httpx2

    def handler(req):
        if req.url.host == "10.0.0.1":
            raise httpx2.ConnectError("refused", request=req)
        return httpx2.Response(404, json={"error": "not found"})
    with factory(httpx2.AsyncClient(transport=httpx2.MockTransport(handler))) as c:
        r = c.post("/api/endpoints/discover", json={"base_url": "10.0.0.1:1234"})
        assert r.status_code == 502 and "Could not reach" in r.json()["detail"]
        r = c.post("/api/endpoints/discover", json={"base_url": "10.0.0.2:1234/api"})
        assert r.status_code == 502 and "/v1" in r.json()["detail"]
        assert c.post("/api/endpoints/discover", json={}).status_code == 422


def test_legacy_config_with_demo_provider_still_loads(factory, tmp_path):
    raw = yaml.safe_load((ROOT / "config" / "suite.example.yaml").read_text())
    raw["allow_demo_provider"] = True
    raw["providers"]["demo"] = {"type": "mock", "locality": "local"}
    raw["models"].append({"ref": "demo/demo"})
    raw["tiers"] = {t: [*chain, "demo/demo"] for t, chain in raw["tiers"].items()}
    raw["profile"] = str(ROOT / "config" / "profile.example.yaml")
    raw["connectors"] = str(ROOT / "config" / "connectors.example.yaml")
    cfg = tmp_path / "old-suite.yaml"
    cfg.write_text(json.dumps(raw))
    with factory(config=cfg) as c:
        o = c.get("/api/overview").json()
        assert "demo" not in {p["name"] for p in o["providers"]}
        assert not any(r.startswith("demo/") for ch in o["tiers"].values() for r in ch)


def test_api_token(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SUITE_API_TOKEN", "s3cret-token")
    s = load_settings(ROOT, ROOT / "config" / "suite.example.yaml")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/overview").status_code == 401
        assert c.get("/api/overview", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
