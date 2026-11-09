"""Library: run a playbook again from an earlier run, or revise it (edit inputs, swap files, add corrections) as a new run."""

import json

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import load_settings
from tests.conftest import ROOT, contract
from tests.test_api import KEYS, wait


def recording_server(bodies: list):
    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [{"id": "m1", "object": "model", "created": 0, "owned_by": "x"}]})
        body = json.loads(req.content)
        bodies.append(body)
        return httpx2.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": body["model"],
                                          "choices": [{"index": 0, "finish_reason": "stop", "message": {
                                              "role": "assistant", "content": "Draft v1.\n" + contract()}}],
                                          "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}})
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


@pytest.fixture
def lib(tmp_path, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    bodies: list = []
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), http_client=recording_server(bodies))) as c:
        assert c.post("/api/endpoints", json={"id": "lan", "name": "Box", "base_url": "http://10.0.0.7:1234", "model": "m1",
                                              "context_tokens": 32768, "use_for": ["router", "specialist", "synthesis", "review"]}).status_code == 201
        yield c, bodies


def prompts(bodies):
    return "\n".join(m["content"] for b in bodies for m in b["messages"] if isinstance(m.get("content"), str))


def test_run_again_repeats_the_same_inputs_as_a_new_run(lib):
    c, bodies = lib
    up = c.post("/api/files", files={"file": ("notes.md", b"# Notes\nShip on Friday", "text/markdown")}).json()
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "data_class": "public",
                                      "inputs": {"request": "Summarise the notes", "documents": [up["id"]]}}).json()["id"]
    assert wait(c, first)["status"] == "completed"
    r = c.post(f"/api/runs/{first}/rerun", json={})
    assert r.status_code == 201
    again = wait(c, r.json()["id"])
    old = c.get(f"/api/runs/{first}").json()
    assert again["id"] != first and again["status"] == "completed" and old["status"] == "completed"  # the first is kept
    assert again["inputs"] == old["inputs"] and again["data_class"] == "public"
    assert again["options"]["rerun_of"] == first and "revision" not in again["options"]
    assert any(e["event"] == "run_repeated" for e in c.get(f"/api/audit?run_id={again['id']}").json())


def test_edit_and_run_as_new_sends_corrections_and_the_earlier_result(lib):
    c, bodies = lib
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Plan the launch"}}).json()["id"]
    wait(c, first)
    bodies.clear()
    r = c.post(f"/api/runs/{first}/rerun", json={"inputs": {"request": "Plan the launch for March"},
                                                 "corrections": "The date was wrong: launch is in March, not May."})
    assert r.status_code == 201
    new = wait(c, r.json()["id"])
    assert new["inputs"]["request"] == "Plan the launch for March" and new["title"].startswith("Plan the launch for March")
    assert new["options"]["revision"]["of"] == first
    sent = prompts(bodies)
    assert "launch is in March, not May" in sent and "revises an earlier run" in sent
    assert f'source="previous-run:{first}"' in sent and "Draft v1." in sent  # the earlier result, as untrusted data
    assert c.get(f"/api/runs/{first}").json()["inputs"]["request"] == "Plan the launch"  # the earlier run is unchanged


def test_revision_without_the_earlier_result_and_bad_requests(lib):
    c, bodies = lib
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Plan"}}).json()["id"]
    wait(c, first)
    bodies.clear()
    rid = c.post(f"/api/runs/{first}/rerun", json={"corrections": "Shorter please", "include_previous": False}).json()["id"]
    wait(c, rid)
    sent = prompts(bodies)
    assert "Shorter please" in sent and "previous-run:" not in sent
    assert c.post("/api/runs/run_nope/rerun", json={}).status_code == 404
    assert c.post(f"/api/runs/{first}/rerun", json={"inputs": {"request": ""}}).status_code == 422  # required input
