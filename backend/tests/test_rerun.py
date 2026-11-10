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


def test_update_this_run_replaces_the_earlier_run_once_the_new_one_completes(lib):
    c, bodies = lib
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Plan the launch"}}).json()["id"]
    wait(c, first)
    r = c.post(f"/api/runs/{first}/rerun", json={"inputs": {"request": "Plan the launch for March"},
                                                 "corrections": "March, not May.", "replace": True})
    assert r.status_code == 201
    new = wait(c, r.json()["id"])
    assert new["status"] == "completed" and new["options"]["replaces"] == first
    assert new["options"]["revision"]["of"] == first and "Draft v1." in prompts(bodies)  # still a revision
    assert c.get(f"/api/runs/{first}").status_code == 404  # the earlier run is gone...
    ids = [x["id"] for x in c.get("/api/runs").json()]
    assert new["id"] in ids and first not in ids  # ...and the Library shows one row
    events = [e["event"] for e in c.get(f"/api/audit?run_id={first}").json()]
    assert "run_replaced" in events  # the audit log keeps a record



def test_update_this_run_keeps_the_earlier_run_while_the_new_one_is_under_way_or_if_it_fails(lib):
    c, _ = lib
    store = c.app.state.suite.store
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Plan"}}).json()["id"]
    wait(c, first)
    # a replacement that has not finished: the earlier run is kept, but the Library shows only the new one
    pending = store.create_run("quick-ask", "Plan", "internal", {"request": "Plan"}, {"replaces": first})
    store.update_run(pending, status="awaiting_approval")
    ids = [x["id"] for x in c.get("/api/runs").json()]
    assert pending in ids and first not in ids
    assert c.get(f"/api/runs/{first}").status_code == 200
    for status in ("failed", "cancelled", "interrupted", "completed"):  # it ended: the earlier run is shown again
        store.update_run(pending, status=status)
        ids = [x["id"] for x in c.get("/api/runs").json()]
        assert first in ids and pending in ids, status


def test_update_this_run_keeps_the_earlier_run_when_the_new_one_ends_without_a_result(lib):
    """A model that cannot be reached ends a run "completed" with outcome BLOCKED: that must not delete a good run."""
    c, _ = lib
    store, eng = c.app.state.suite.store, c.app.state.suite.engine
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Plan"}}).json()["id"]
    wait(c, first)
    for outcome in ("BLOCKED", "REJECTED", "NEEDS_INPUT"):
        new = store.create_run("quick-ask", "Plan", "internal", {"request": "Plan"}, {"replaces": first})
        store.update_run(new, status="completed", outcome=outcome)
        eng._drop_replaced(new)
        assert c.get(f"/api/runs/{first}").status_code == 200, outcome
    new = store.create_run("quick-ask", "Plan", "internal", {"request": "Plan"}, {"replaces": first})
    store.update_run(new, status="completed", outcome="PARTIAL")  # a result, even with gaps, replaces it
    eng._drop_replaced(new)
    assert c.get(f"/api/runs/{first}").status_code == 404


def test_update_this_run_is_refused_while_the_earlier_run_is_still_going(lib):
    c, _ = lib
    store = c.app.state.suite.store
    first = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "Plan"}}).json()["id"]
    wait(c, first)
    store.update_run(first, status="awaiting_approval")
    r = c.post(f"/api/runs/{first}/rerun", json={"corrections": "Shorter", "replace": True})
    assert r.status_code == 409 and "still going" in r.json()["detail"]
    assert c.post(f"/api/runs/{first}/rerun", json={"corrections": "Shorter"}).status_code == 201  # run as new still works
