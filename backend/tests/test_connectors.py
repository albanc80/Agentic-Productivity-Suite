import sys
from pathlib import Path

import pytest

from app.connectors import ConnectorConfig, ConnectorError, ConnectorManager, tool_allowed
from tests.fake_mcp_server import server as fake_server

HERE = Path(__file__).parent


def cfg(**kw) -> ConnectorConfig:
    base = {"id": "tracker", "name": "Tracker", "transport": "stdio", "command": sys.executable,
            "args": [str(HERE / "fake_mcp_server.py")]}
    base.update(kw)
    return ConnectorConfig.model_validate(base)


class Ann:
    def __init__(self, ro=None, destructive=None):
        self.read_only_hint = ro
        self.destructive_hint = destructive


def test_policy_rules():
    c = cfg()
    assert tool_allowed(c, "list_issues", Ann(ro=True))[0]
    assert not tool_allowed(c, "anything", Ann(ro=True, destructive=True))[0]
    assert not tool_allowed(c, "list_issues", Ann(ro=False))[0]
    assert tool_allowed(c, "get_issue", None)[0]
    assert not tool_allowed(c, "get_and_update_issue", None)[0]  # write verb wins
    assert not tool_allowed(c, "sync_everything", None)[0]
    assert not tool_allowed(cfg(infer_read_only=False), "get_issue", None)[0]
    assert not tool_allowed(cfg(deny_tools=["list_*"]), "list_issues", Ann(ro=True))[0]
    allow = cfg(allow_tools=["read_file"])
    assert tool_allowed(allow, "read_file", None)[0]
    assert not tool_allowed(allow, "list_issues", Ann(ro=True))[0]


def test_required_env_and_unconfigured():
    c = cfg(id="gh", env={"TOKEN": "${GH_TOKEN}", "OPT": "${OPT:-x}"})
    mgr = ConnectorManager([c], env={})
    assert mgr.missing_env("gh") == ["GH_TOKEN"]
    assert not mgr.configured("gh")
    assert mgr.describe()[0]["status"] == "unconfigured"
    assert ConnectorManager([c], env={"GH_TOKEN": "t"}).configured("gh")


async def test_in_process_read_only_enforcement():
    mgr = ConnectorManager([cfg()], env={}, in_process={"tracker": fake_server})
    try:
        tools = {t.name for t in await mgr.tools("tracker")}
        assert tools == {"list_issues", "get_issue"}
        text, is_error = await mgr.call("tracker", "list_issues", {"project": "ABC"})
        assert "ABC-1" in text and not is_error
        with pytest.raises(ConnectorError, match="blocked by the read-only policy"):
            await mgr.call("tracker", "create_issue", {"title": "x"})
        with pytest.raises(ConnectorError, match="blocked"):
            await mgr.call("tracker", "delete_issue", {"key": "x"})
        status = mgr.describe()[0]
        assert status["status"] == "ready"
        assert {t["name"]: t["allowed"] for t in status["tools"]}["sync_everything"] is False
    finally:
        await mgr.shutdown()


async def test_stdio_transport_round_trip():
    mgr = ConnectorManager([cfg()], env={"PATH": "/usr/bin:/bin"})
    try:
        text, _ = await mgr.call("tracker", "get_issue", {"key": "DEMO-1"})
        assert text.startswith("DEMO-1:")
    finally:
        await mgr.shutdown()


async def test_failed_connector_reports_error():
    mgr = ConnectorManager([cfg(command="/nonexistent/binary", timeout_s=5)], env={})
    with pytest.raises(ConnectorError, match="failed to start"):
        await mgr.tools("tracker")
    assert mgr.describe()[0]["status"] == "error"
    await mgr.shutdown()
