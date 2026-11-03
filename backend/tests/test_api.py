"""API end to end with the demo provider (no model needed)."""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import load_settings
from tests.conftest import ROOT


@pytest.fixture
def client(tmp_path, monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "SUITE_API_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    s = load_settings(ROOT, ROOT / "config" / "suite.example.yaml")
    with TestClient(create_app(s)) as c:
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
    assert len(o["agents"]) == 34 and len(o["playbooks"]) == 9 and len(o["desks"]) == 8
    assert {c["id"] for c in o["connectors"]} >= {"github", "microsoft365", "databricks-genie", "azure-devops"}
    demo = next(p for p in o["providers"] if p["name"] == "demo")
    assert demo["available"]
    a = client.get("/api/agents/chief-of-staff").json()
    assert a["persona"] == "persona_x" and "daily" in a["modes"]
    assert client.get("/api/agents/nope").status_code == 404


def test_route_falls_back_to_keywords(client):
    r = client.post("/api/route", json={"text": "Can we add a CSV export? It's a scope change request"}).json()
    assert r["playbook"] == "scope-change" and r["method"] == "keywords"
    r = client.post("/api/route", json={"text": "zzz"}).json()
    assert r["playbook"] == "quick-ask" and not r["auto"]


def test_demo_run_gate_export_and_audit(client):
    bad = client.post("/api/runs", json={"playbook_id": "scope-change", "inputs": {"request": "x"}})
    assert bad.status_code == 422
    rid = client.post("/api/runs", json={"playbook_id": "scope-change", "inputs": {
        "request": "Add SSO export", "effort_hours": 16, "project": "Portal"}}).json()["id"]
    run = wait(client, rid)
    assert run["status"] == "awaiting_approval" and run["demo"] is True
    apr = client.get("/api/approvals").json()
    assert apr and apr[0]["run_id"] == rid
    assert client.post(f"/api/approvals/{apr[0]['id']}", json={"decision": "approved", "decided_by": ""}).status_code == 409
    ok = client.post(f"/api/approvals/{apr[0]['id']}", json={"decision": "approved", "decided_by": "Jordan"})
    assert ok.status_code == 200
    run = wait(client, rid, until=("completed", "failed"))
    assert run["status"] == "completed" and "Demo output" in run["deliverable"]
    md = client.get(f"/api/runs/{rid}/export?format=md")
    assert md.status_code == 200 and "attachment" in md.headers["content-disposition"]
    html = client.get(f"/api/runs/{rid}/export?format=html").text
    assert html.startswith("<!doctype html>") and "<script" not in html
    events = {e["event"] for e in client.get(f"/api/audit?run_id={rid}").json()}
    assert {"run_started", "model_call", "approval_requested", "approval_decided", "run_completed"} <= events


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


def test_api_token(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SUITE_API_TOKEN", "s3cret-token")
    s = load_settings(ROOT, ROOT / "config" / "suite.example.yaml")
    with TestClient(create_app(s)) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/overview").status_code == 401
        assert c.get("/api/overview", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
