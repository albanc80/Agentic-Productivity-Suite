"""Chat answers in the background: a message is saved at once, follow-ups queue, sent messages can be edited."""

import asyncio
import json
import threading
import time

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.prompts import SUITE_RULES
from app.settings import load_settings
from tests.conftest import ROOT
from tests.test_chat import KEYS, setup_models

AGENT = "counselor"


def gated_server(seen: list, gate: threading.Event):
    """A model that waits for the test to open the gate, then echoes the person's message."""
    async def handler(req):
        if req.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [{"id": "m", "object": "model", "created": 0, "owned_by": "x"}]})
        body = json.loads(req.content)
        user = body["messages"][-1]["content"]
        seen.append({"system": body["messages"][0]["content"], "user": user})
        while not gate.is_set():
            await asyncio.sleep(0.02)
        asked = user.rsplit("## The person's message\n\n", 1)[-1].strip()
        return httpx2.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": body["model"],
                                          "choices": [{"index": 0, "finish_reason": "stop", "message": {
                                              "role": "assistant", "content": f"Answer to: {asked}"}}],
                                          "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    seen, gate = [], threading.Event()
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), http_client=gated_server(seen, gate))) as c:
        setup_models(c)
        yield c, seen, gate


def until(c, cid, check, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        chat = c.get(f"/api/chats/{cid}").json()
        if check(chat):
            return chat
        time.sleep(0.03)
    raise AssertionError(f"timed out: {chat['messages']}")


def test_new_chat_is_listed_at_once_and_a_message_shows_before_its_answer(chat_client):
    c, seen, gate = chat_client
    chat = c.post("/api/chats", json={"agent_id": AGENT}).json()
    assert [x["id"] for x in c.get("/api/chats").json()] == [chat["id"]]  # listed before any message
    r = c.post(f"/api/chats/{chat['id']}/messages", json={"content": "First question", "wait": False})
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["content"] for m in msgs] == ["First question"] and msgs[0]["status"] in ("queued", "working")
    listed = c.get("/api/chats").json()[0]
    assert listed["busy"] is True and listed["title"] == "First question"
    gate.set()
    done = until(c, chat["id"], lambda ch: not any(m.get("status") for m in ch["messages"]))
    assert [m["content"] for m in done["messages"]] == ["First question", "Answer to: First question"]
    assert done["messages"][1]["reply_to"] == done["messages"][0]["id"]
    assert c.get("/api/chats").json()[0]["busy"] is False


def test_follow_ups_queue_and_are_answered_in_order_with_the_earlier_answer(chat_client):
    c, seen, gate = chat_client
    cid = c.post("/api/chats", json={"agent_id": AGENT}).json()["id"]
    c.post(f"/api/chats/{cid}/messages", json={"content": "One", "wait": False})
    r = c.post(f"/api/chats/{cid}/messages", json={"content": "Two", "wait": False})  # sent while One is being answered
    assert [m.get("status") for m in r.json()["messages"]][1] == "queued"
    gate.set()
    done = until(c, cid, lambda ch: len(ch["messages"]) == 4 and not any(m.get("status") for m in ch["messages"]))
    assert [m["content"] for m in done["messages"]] == ["One", "Answer to: One", "Two", "Answer to: Two"]
    assert "Answer to: One" in seen[-1]["user"]  # Two was answered knowing One's answer


def test_edit_replaces_what_followed_and_is_refused_while_answering(chat_client):
    c, seen, gate = chat_client
    cid = c.post("/api/chats", json={"agent_id": AGENT}).json()["id"]
    c.post(f"/api/chats/{cid}/messages", json={"content": "Draft question", "wait": False})
    r = c.put(f"/api/chats/{cid}/messages/0", json={"content": "Better question"})
    assert r.status_code == 409 and "Wait for the answer" in r.json()["detail"]
    gate.set()
    until(c, cid, lambda ch: len(ch["messages"]) == 2)
    c.post(f"/api/chats/{cid}/messages", json={"content": "Follow-up"})
    assert len(c.get(f"/api/chats/{cid}").json()["messages"]) == 4
    r = c.put(f"/api/chats/{cid}/messages/0", json={"content": "Better question"})
    assert r.status_code == 200 and r.json()["content"] == "Answer to: Better question"
    chat = c.get(f"/api/chats/{cid}").json()
    assert [m["content"] for m in chat["messages"]] == ["Better question", "Answer to: Better question"]
    assert chat["title"] == "Better question"
    assert c.put(f"/api/chats/{cid}/messages/1", json={"content": "x"}).status_code == 404  # an answer, not yours
    assert any(e.get("event") == "chat_message_edited" for e in c.get("/api/audit").json())


def test_agent_and_data_class_can_change_until_the_first_message(chat_client):
    c, seen, gate = chat_client
    gate.set()
    cid = c.post("/api/chats", json={}).json()["id"]
    r = c.patch(f"/api/chats/{cid}", json={"agent_id": AGENT, "data_class": "public"})
    assert r.status_code == 200 and r.json()["agent_id"] == AGENT and r.json()["data_class"] == "public"
    assert c.patch(f"/api/chats/{cid}", json={"agent_id": "nope"}).status_code == 409
    c.post(f"/api/chats/{cid}/messages", json={"content": "hi"})
    assert c.patch(f"/api/chats/{cid}", json={"agent_id": "chief-of-staff"}).status_code == 409


def test_restart_drops_unused_chats_and_marks_unanswered_messages(tmp_path, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    app = create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))
    suite = app.state.suite
    empty = suite.chat.create(AGENT, None)
    used = suite.chat.create(AGENT, None)
    used["messages"] = [{"id": "msg_1", "role": "user", "content": "hi", "files": [], "status": "working"}]
    suite.store.save_chat(used)
    with TestClient(app) as c:  # start-up runs recover()
        assert [x["id"] for x in c.get("/api/chats").json()] == [used["id"]]
        assert c.get(f"/api/chats/{empty['id']}").status_code == 404
        m = c.get(f"/api/chats/{used['id']}").json()["messages"][0]
        assert "status" not in m and "closed before this was answered" in m["error"]


def test_agents_work_only_with_what_they_were_given():
    assert "Do not infer other mailboxes, accounts or systems" in SUITE_RULES
    assert "do not suggest connecting, forwarding or pasting from other sources" in SUITE_RULES


def test_the_rule_reaches_every_chat_answer(chat_client):
    c, seen, gate = chat_client
    gate.set()
    cid = c.post("/api/chats", json={"agent_id": AGENT}).json()["id"]
    c.post(f"/api/chats/{cid}/messages", json={"content": "What should I focus on today?"})
    assert "Do not infer other mailboxes" in seen[-1]["system"]
    assert "say what\nis missing" not in seen[-1]["system"]
