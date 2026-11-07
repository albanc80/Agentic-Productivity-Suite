"""A connector that breaks in an unexpected way, or starts slowly, never breaks chat or the Test button.

Seen on Windows (v0.7.2): GitHub's runtime folder raised PermissionError while being checked. Test and every chat
answered "Internal Server Error", although the model could have answered without GitHub."""

import asyncio
import time

from fastapi.testclient import TestClient

from app import chat as chat_module
from app.connectors import ConnectorConfig, ConnectorManager
from app.main import create_app
from app.settings import load_settings
from tests.conftest import ROOT
from tests.fake_mcp_server import server
from tests.test_chat import KEYS, tracker_model


def manager(tmp_path, monkeypatch, prepare) -> ConnectorManager:
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    conns = ConnectorManager([
        ConnectorConfig(id="tracker", name="Team tracker", transport="stdio", command="unused", enabled=True),
        ConnectorConfig(id="github", name="GitHub", transport="stdio", command="github-mcp-server", enabled=True),
    ], in_process={"tracker": server})
    real = conns.prepare

    async def patched(cfg):
        if cfg.id == "github":
            return await prepare(cfg)
        return await real(cfg)
    conns.prepare = patched
    return conns


def client(conns, seen):
    app = create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), connectors=conns,
                     http_client=tracker_model(seen))
    return TestClient(app, raise_server_exceptions=False)


def with_model(c):
    c.put("/api/providers/openai", json={"enabled": True, "api_key": "sk-test",
                                         "models": [{"model": "gpt-x", "context_tokens": 128000, "tools": True}]})


async def access_denied(cfg):
    raise PermissionError(13, "Access is denied", r"C:\Program Files\Agentic Productivity Suite\_internal\tools")


def test_test_button_says_why_a_connector_failed_instead_of_internal_server_error(tmp_path, monkeypatch):
    with client(manager(tmp_path, monkeypatch, access_denied), []) as c:
        r = c.post("/api/connectors/github/connect")
        assert r.status_code == 409
        assert "PermissionError" in r.json()["detail"] and "Access is denied" in r.json()["detail"]
        assert c.post("/api/connectors/tracker/connect").status_code == 200  # the others are unaffected


def test_chat_answers_and_uses_other_connectors_when_one_breaks(tmp_path, monkeypatch):
    seen: list = []
    with client(manager(tmp_path, monkeypatch, access_denied), seen) as c:
        with_model(c)
        chat = c.post("/api/chats", json={"agent_id": "critical-mentor", "data_class": "public"}).json()
        r = c.post(f"/api/chats/{chat['id']}/messages", json={"content": "What is open in OPS?"})
        assert r.status_code == 200, r.text
        msg = r.json()
        assert "OPS-1" in msg["content"]  # the working connector was still called
        assert any("github unavailable" in w and "PermissionError" in w for w in msg["warnings"])
        system = next(b for b in seen if b.get("tools"))["messages"][0]["content"]
        assert "GitHub is switched on but could not start (PermissionError" in system


def test_chat_does_not_wait_for_a_connector_that_is_still_starting(tmp_path, monkeypatch):
    async def slow(cfg):
        await asyncio.sleep(60)
    monkeypatch.setattr(chat_module, "CHAT_CONNECTOR_WAIT", 0.5)
    seen: list = []
    with client(manager(tmp_path, monkeypatch, slow), seen) as c:
        with_model(c)
        chat = c.post("/api/chats", json={"agent_id": "critical-mentor", "data_class": "public"}).json()
        start = time.monotonic()
        r = c.post(f"/api/chats/{chat['id']}/messages", json={"content": "What is open in OPS?"})
        assert r.status_code == 200, r.text
        assert time.monotonic() - start < 10
        assert "OPS-1" in r.json()["content"]
        assert any("github is still starting" in w for w in r.json()["warnings"])
        system = next(b for b in seen if b.get("tools"))["messages"][0]["content"]
        assert "GitHub is switched on but still connecting" in system


def test_an_unexpected_error_is_shown_with_its_reason(tmp_path, monkeypatch):
    with client(manager(tmp_path, monkeypatch, access_denied), []) as c:
        suite = c.app.state.suite
        monkeypatch.setattr(suite.chat, "list", lambda: (_ for _ in ()).throw(RuntimeError("database is locked")))
        r = c.get("/api/chats")
        assert r.status_code == 500
        assert r.json()["detail"].startswith("Unexpected error: RuntimeError: database is locked")


def test_connectors_that_are_on_start_in_the_background_when_the_app_starts(tmp_path, monkeypatch):
    started = []

    async def record(cfg):
        started.append(cfg.id)
        raise PermissionError(13, "Access is denied")
    conns = manager(tmp_path, monkeypatch, record)
    with client(conns, []) as c:
        for _ in range(50):
            if started:
                break
            time.sleep(0.05)
        assert started == ["github"]
        assert c.get("/api/health").status_code == 200


def test_a_failed_first_message_does_not_leave_empty_new_chats_in_the_list(tmp_path, monkeypatch):
    """Each failed send used to leave a "New chat" behind, and sending again made another."""
    with client(manager(tmp_path, monkeypatch, access_denied), []) as c:  # no model: every answer fails
        for _ in range(2):
            chat = c.post("/api/chats", json={"agent_id": "critical-mentor", "data_class": "public"}).json()
            assert c.post(f"/api/chats/{chat['id']}/messages", json={"content": "hello"}).status_code == 409
        assert c.get("/api/chats").json() == []
        assert c.get(f"/api/chats/{chat['id']}").status_code == 200  # still there to retry in
