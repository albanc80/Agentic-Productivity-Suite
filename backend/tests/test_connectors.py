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


def db_cfg(**kw) -> ConnectorConfig:
    return ConnectorConfig.model_validate({
        "id": "db", "name": "Databricks", "transport": "http", "enabled": True,
        "headers": {"Authorization": "Bearer ${DB_TOKEN}"},
        "parts": [{"id": "genie", "name": "Genie space", "url": "${DB_HOST}/genie/${DB_SPACE}"},
                  {"id": "search", "name": "Vector Search", "url": "${DB_HOST}/vs/${DB_CAT}/${DB_SCHEMA}"}], **kw})


async def test_grouped_connector_runs_each_ready_part_under_one_switch():
    env = {"DB_HOST": "https://ws", "DB_TOKEN": "t"}
    mgr = ConnectorManager([db_cfg()], env=env, in_process={"db.genie": fake_server, "db.search": fake_server})
    assert mgr.missing("db") == ["at least one of: Genie space; Vector Search"]
    mgr.apply_settings({}, {"DB_SPACE": "s1"})
    assert mgr.missing("db") == [] and [p.id for p in mgr.ready_parts("db")] == ["genie"]
    try:
        tools = {t.name: t for t in await mgr.tools("db", allowed_only=False)}
        assert set(tools) >= {"genie.get_issue", "genie.create_issue"} and not any(n.startswith("search.") for n in tools)
        assert tools["genie.get_issue"].qualified == "db__genie_get_issue" and not tools["genie.create_issue"].allowed
        text, err = await mgr.call("db", "genie.get_issue", {"key": "DEMO-1"})
        assert "Login fails" in text and not err
        with pytest.raises(ConnectorError, match="read-only policy"):
            await mgr.call("db", "genie.create_issue", {"title": "x"})
        assert next(d for d in mgr.describe() if d["id"] == "db")["status"] == "ready"
    finally:
        await mgr.shutdown()


def test_grouped_connector_fields_and_the_merge_of_the_old_databricks_connectors(tmp_path):
    from tests.conftest import ROOT
    old = tmp_path / "connectors.yaml"  # a file copied from an older version still lists the three connectors
    old.write_text("connectors:\n" + "".join(
        f"  - {{id: {i}, name: x, transport: http, url: 'https://x'}}\n"
        for i in ("databricks-genie", "databricks-uc-functions", "databricks-search")), encoding="utf-8")
    mgr = ConnectorManager.from_file(old, presets=ROOT / "config" / "connectors.example.yaml")
    assert "databricks" in mgr.configs and not {"databricks-genie", "databricks-search"} & set(mgr.configs)
    assert mgr.replaced_by()["databricks-uc-functions"] == "databricks"
    from app.connectors import ConnectorSetting
    mgr.apply_settings({"databricks-genie": ConnectorSetting(enabled=True)}, {})
    assert mgr.configs["databricks"].enabled, "the old switch carries over"
    v = {x["name"]: x for x in mgr.variables("databricks")}
    assert v["DATABRICKS_HOST"]["label"] == "Workspace URL" and v["DATABRICKS_UC_CATALOG"]["part"] == "functions"


def test_required_fields_come_first_and_account_lists_follow_them():
    from tests.conftest import ROOT
    mgr = ConnectorManager.from_file(None, presets=ROOT / "config" / "connectors.example.yaml")
    order = [v["name"] for v in mgr.variables("google-workspace")]
    assert order[:4] == ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "USER_GOOGLE_EMAIL", "GOOGLE_OTHER_ACCOUNTS"]
    for c in mgr.configs.values():
        if c.transport != "builtin":
            assert c.steps and c.docs_url.startswith("https://"), f"{c.id} needs setup steps and a docs link"


def test_github_needs_only_a_token_and_names_the_repositories():
    from tests.conftest import ROOT
    mgr = ConnectorManager.from_file(None, presets=ROOT / "config" / "connectors.example.yaml")
    v = {x["name"]: x for x in mgr.variables("github")}
    assert not v["GITHUB_PERSONAL_ACCESS_TOKEN"]["optional"] and v["GITHUB_HOST"]["optional"] and v["GITHUB_REPOS"]["optional"]
    mgr.apply_settings({}, {"GITHUB_PERSONAL_ACCESS_TOKEN": "t",
                            "GITHUB_REPOS": "https://github.com/acme/portal, acme/api.git"})
    assert mgr.missing("github") == []
    assert mgr.context_lines("github") == ["Repositories the person works in: acme/portal, acme/api. Use these unless asked about others."]


async def test_connectors_use_the_classic_handshake_every_server_speaks():
    """GitHub's server (Go SDK) took the SDK's server/discover probe as its handshake and then refused initialize
    ('duplicate "initialize" received'). Connectors start with initialize, like Claude Code and Codex."""
    mgr = ConnectorManager([cfg(id="strict", args=[str(HERE / "fake_strict_server.py")])], env={"PATH": "/usr/bin:/bin"})
    try:
        assert [t.name for t in await mgr.tools("strict")] == ["get_repo"]
    finally:
        await mgr.shutdown()
