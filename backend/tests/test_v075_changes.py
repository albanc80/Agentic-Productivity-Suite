"""0.7.5: 20 lookups by default (old files and saved settings upgraded once), no cost line on runs, PB-01 can
leave a tracker out, and agents only reach Google accounts that are signed in (Google's server opens a sign-in
page in the browser for every call to any other account)."""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from app.connectors import ConnectorConfig, ConnectorError, ConnectorManager, setup_hints
from app.main import create_app
from app.settings import Budgets, load_settings
from tests.conftest import ROOT, contract, run_to_rest
from tests.test_chat import KEYS

# ---------------------------------------------------------------- 20 tool calls


def test_twenty_lookups_by_default_and_old_files_are_upgraded(tmp_path):
    assert Budgets().max_tool_calls_per_step == 20
    assert yaml.safe_load((ROOT / "config" / "suite.example.yaml").read_text())["budgets"]["max_tool_calls_per_step"] == 20
    old = yaml.safe_load((ROOT / "config" / "suite.example.yaml").read_text())
    old["budgets"]["max_tool_calls_per_step"] = 8  # what releases before 0.7.5 copied into ~/.productivity-suite
    (tmp_path / "suite.yaml").write_text(yaml.safe_dump(old))
    assert load_settings(ROOT, tmp_path / "suite.yaml").budgets.max_tool_calls_per_step == 20
    old["budgets"]["max_tool_calls_per_step"] = 12  # a value someone chose stays
    (tmp_path / "suite.yaml").write_text(yaml.safe_dump(old))
    assert load_settings(ROOT, tmp_path / "suite.yaml").budgets.max_tool_calls_per_step == 12


def test_limits_saved_in_the_app_with_the_old_default_are_raised_once(tmp_path, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings(ROOT, ROOT / "config" / "suite.example.yaml")
    with TestClient(create_app(settings)) as c:
        b = {**c.get("/api/overview").json()["budgets"], "max_tool_calls_per_step": 8}
        suite = c.app.state.suite
        suite.store.set_setting("general", {"budgets": b})  # as saved by 0.7.4
        suite.store.set_setting("upgraded_tool_calls_default", False)
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))) as c:
        assert c.get("/api/overview").json()["budgets"]["max_tool_calls_per_step"] == 20
        assert c.put("/api/settings/general", json={"budgets": {**b, "max_tool_calls_per_step": 8}}).status_code == 200
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))) as c:
        assert c.get("/api/overview").json()["budgets"]["max_tool_calls_per_step"] == 8  # chosen after: kept


# ---------------------------------------------------------------- PB-01 trackers and no cost line


async def test_daily_plan_leaves_out_a_tracker_unticked_on_the_start_form(make_engine):
    from tests.fake_mcp_server import server
    offered: list[list[str]] = []

    def script(system, messages, tools):
        offered.append(sorted(t.name for t in tools or []))
        return "Plan.\n" + contract()

    conns = ConnectorManager([
        ConnectorConfig(id="github", name="GitHub", transport="stdio", command="unused", enabled=True),
        ConnectorConfig(id="atlassian", name="Jira", transport="stdio", command="unused", enabled=True),
    ], in_process={"github": server, "atlassian": server})
    eng, *_ = make_engine(cloud_script=script, connectors=conns)
    try:
        rid = await eng.start("daily-plan", {"trackers": ["Jira", "Azure DevOps"], "tasks": "ship the export"})
        await run_to_rest(eng, rid)
    finally:
        await conns.shutdown()
    digest = offered[0]
    assert any(n.startswith("atlassian__") for n in digest) and not any(n.startswith("github__") for n in digest)
    assert "connector github not looked up: left out on the start form" in eng.store.steps(rid)[0]["warnings"]
    card = eng.playbooks["daily-plan"].card()
    assert card["connector_choice"]["github"] == {"input": "trackers", "contains": "GitHub"}
    deliverable = eng.store.run(rid).get("deliverable_md") or json.dumps(eng.store.run(rid))
    assert "Cost:" not in deliverable and "Tokens:" in deliverable


# ---------------------------------------------------------------- Google accounts that are not signed in

google = MCPServer("fake-workspace")


@google.tool(annotations=ToolAnnotations(read_only_hint=True))
def search_gmail_messages(query: str, user_google_email: str = "") -> str:
    """Search Gmail."""
    return f"searched {user_google_email or 'nobody'}"


def gw(tmp_path: Path, accounts: str = "", others: str = "") -> ConnectorManager:
    creds = tmp_path / "credentials"
    creds.mkdir(exist_ok=True)
    cfg = ConnectorConfig.model_validate({
        "id": "google-workspace", "name": "Google Workspace", "transport": "stdio", "command": "unused", "enabled": True,
        "accounts": {"param": "user_google_email", "vars": ["USER_GOOGLE_EMAIL", "GOOGLE_OTHER_ACCOUNTS"]},
        "signin": {"provider": "Google", "kind": "tool", "tool": "start_google_auth", "credentials_dir": str(creds)}})
    return ConnectorManager([cfg], env={"USER_GOOGLE_EMAIL": accounts, "GOOGLE_OTHER_ACCOUNTS": others},
                            in_process={"google-workspace": google})


def sign_in(tmp_path: Path, email: str) -> None:  # what workspace-mcp's callback writes
    (tmp_path / "credentials" / f"{email}.json").write_text("{}")


async def test_calls_never_reach_a_google_account_that_is_not_signed_in(tmp_path):
    """Seen on 0.7.4: the Advanced Protection address typed first stayed the default; every lookup without an
    account went to it and the server opened a Google sign-in page each time."""
    conns = gw(tmp_path, accounts="blocked@gmail.com", others="me@gmail.com")
    sign_in(tmp_path, "me@gmail.com")
    try:
        assert conns.usable_accounts("google-workspace") == ["me@gmail.com"]
        assert conns.unsigned_accounts("google-workspace") == ["blocked@gmail.com"]
        text, err = await conns.call("google-workspace", "search_gmail_messages", {"query": "is:unread"})
        assert text == "searched me@gmail.com" and not err  # the signed-in account is the default
        with pytest.raises(ConnectorError, match="listed for Google Workspace but not signed in"):
            await conns.call("google-workspace", "search_gmail_messages", {"query": "x", "user_google_email": "blocked@gmail.com"})
        lines = "\n".join(conns.agent_lines("google-workspace"))
        assert "me@gmail.com (default)" in lines and "blocked@gmail.com is not signed in" in lines
        described = next(c for c in conns.describe() if c["id"] == "google-workspace")
        assert described["unsigned_accounts"] == ["blocked@gmail.com"]
    finally:
        await conns.shutdown()


async def test_with_no_account_listed_only_signed_in_ones_are_used(tmp_path):
    conns = gw(tmp_path)
    try:
        with pytest.raises(ConnectorError, match="No Google Workspace account is signed in"):
            await conns.call("google-workspace", "search_gmail_messages", {"query": "x"})
        with pytest.raises(ConnectorError, match="not signed in"):
            await conns.call("google-workspace", "search_gmail_messages", {"query": "x", "user_google_email": "who@gmail.com"})
        sign_in(tmp_path, "me@gmail.com")
        assert (await conns.call("google-workspace", "search_gmail_messages", {"query": "x"}))[0] == "searched me@gmail.com"
    finally:
        await conns.shutdown()


def test_a_google_sign_in_that_must_be_redone_is_named():
    # Real output of workspace-mcp 2.3.0 for an account with no sign-in (it also opened a browser to sign in)
    text = ("Error calling tool 'search_gmail_messages': **ACTION REQUIRED: Google Authentication Needed for Google "
            "Gmail for 'me@gmail.com'**\n\n1. The authorization page has been **automatically opened in your browser**. "
            "Please complete the authorization there.\n   If it did not appear, open this URL manually:")
    assert setup_hints(text) == ["Google asked to sign in me@gmail.com again (its sign-in expired or is incomplete). "
                                 "Sign in again from Settings > Connectors > Google Workspace."]
