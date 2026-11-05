import sys
from pathlib import Path

import pytest

from app.connectors import ConnectorConfig, ConnectorError, ConnectorManager, tool_allowed
from tests.fake_mcp_server import server as fake_server

HERE = Path(__file__).parent


def cfg(**kw) -> ConnectorConfig:
    base = {"id": "tracker", "name": "Tracker", "transport": "stdio", "command": sys.executable,
            "args": [str(HERE / "fake_mcp_server.py")], "enabled": True}
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


def _mail_server():
    """A mail-like server whose tools pick the account from an argument, as Microsoft 365 and Google do."""
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations

    s = MCPServer("fake-mail")

    @s.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_mail(account: str = "") -> str:
        """List messages in one account's inbox."""
        return f"mail:{account}"

    @s.tool(annotations=ToolAnnotations(read_only_hint=True))
    def list_holidays(country: str = "US") -> str:
        """Public holidays (no account argument)."""
        return f"holidays:{country}"

    return s


def mail_cfg(**kw) -> ConnectorConfig:
    return cfg(id="mail", name="Mail", accounts={"param": "account", "vars": ["MAIL_ACCOUNTS"]}, **kw)


async def test_several_accounts_are_enforced_by_the_suite():
    mgr = ConnectorManager([mail_cfg()], env={"MAIL_ACCOUNTS": "work@corp.com, me@home.net"},
                           in_process={"mail": _mail_server()})
    try:
        assert mgr.accounts("mail") == ["work@corp.com", "me@home.net"]
        assert mgr.variables("mail")[0]["name"] == "MAIL_ACCOUNTS" and mgr.variables("mail")[0]["optional"]
        assert (await mgr.call("mail", "list_mail", {}))[0] == "mail:work@corp.com"  # default filled in
        assert (await mgr.call("mail", "list_mail", {"account": "ME@home.net"}))[0] == "mail:ME@home.net"
        with pytest.raises(ConnectorError, match="not enabled for Mail; allowed: work@corp.com, me@home.net"):
            await mgr.call("mail", "list_mail", {"account": "boss@other.org"})
        assert (await mgr.call("mail", "list_holidays", {}))[0] == "holidays:US"  # no account argument: untouched
    finally:
        await mgr.shutdown()


async def test_no_accounts_listed_leaves_the_choice_to_the_server():
    mgr = ConnectorManager([mail_cfg()], env={}, in_process={"mail": _mail_server()})
    try:
        assert mgr.accounts("mail") == []
        assert (await mgr.call("mail", "list_mail", {"account": "any@where.com"}))[0] == "mail:any@where.com"
        assert (await mgr.call("mail", "list_mail", {}))[0] == "mail:"
    finally:
        await mgr.shutdown()


def test_shipped_mail_presets_declare_read_only_and_accounts():
    from tests.conftest import ROOT
    mgr = ConnectorManager.from_file(None, presets=ROOT / "config" / "connectors.example.yaml")
    ms, gw = mgr.configs["microsoft365"], mgr.configs["google-workspace"]
    assert "--read-only" in ms.args and "--read-only" in gw.args
    assert ms.accounts.param == "account" and gw.accounts.param == "user_google_email"
    assert {"MS365_ACCOUNTS"} <= set(ms.variables()) and {"USER_GOOGLE_EMAIL", "GOOGLE_OTHER_ACCOUNTS"} <= set(gw.variables())


def test_every_shipped_connector_starts_switched_off():
    from tests.conftest import ROOT
    mgr = ConnectorManager.from_file(None, presets=ROOT / "config" / "connectors.example.yaml")
    assert mgr.configs and not [cid for cid, c in mgr.configs.items() if c.enabled]
    assert not [d["id"] for d in mgr.describe() if d["status"] != "disabled"]
