"""Sign in to a connector from the app: the connector's own server signs in with a code shown in Settings;
the suite never handles a token. A fake CLI (tests/fake_signin_cli.py) plays the server."""

import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.connectors import ConnectorConfig, ConnectorManager
from app.main import create_app
from app.settings import load_settings
from app.signin import SigninError, SigninManager, parse_json, parse_prompt
from tests.conftest import ROOT

HERE = Path(__file__).parent
MS_PROMPT = ("To sign in, use a web browser to open the page https://login.microsoft.com/device and enter the code "
             "LTGWWUVK3 to authenticate.")  # printed by @softeria/ms-365-mcp-server --login (captured Nov 2026)


def mail_cfg(**kw) -> ConnectorConfig:
    base = {"id": "mail", "name": "Mail", "transport": "stdio", "command": sys.executable,
            "args": [str(HERE / "fake_signin_cli.py"), "--read-only"],
            "env": {"FAKE_SIGNIN_STATE": "${FAKE_SIGNIN_STATE}", "FAKE_SIGNIN_FAIL": "${FAKE_SIGNIN_FAIL:-}"},
            "requires": ["MAIL_ENABLED"], "accounts": {"param": "account", "vars": ["MAIL_ACCOUNTS"]},
            "signin": {"provider": "Microsoft", "login": ["--login"], "accounts": ["--list-accounts"],
                       "remove": ["--remove-account"], "confirms": "MAIL_ENABLED"}}
    base.update(kw)
    return ConnectorConfig.model_validate(base)


@pytest.fixture
def state(tmp_path):
    return tmp_path / "signin-state.json"


@pytest.fixture
def client(tmp_path, monkeypatch, state):
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SUITE_API_TOKEN", raising=False)

    def make(**env):
        mgr = ConnectorManager([mail_cfg()], env={"FAKE_SIGNIN_STATE": str(state), "PATH": os.environ["PATH"], **env})
        return TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), connectors=mgr))
    return make


def approve(state: Path, user: str) -> None:
    data = json.loads(state.read_text()) if state.exists() else {"accounts": []}
    state.write_text(json.dumps({**data, "approve": user}))


def wait_for(c: TestClient, *statuses: str, timeout: float = 20) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        s = c.get("/api/connectors/mail/signin").json()
        if s["status"] in statuses:
            return s
        time.sleep(0.05)
    raise AssertionError(f"sign-in never reached {statuses}: {s}")


def mail(c: TestClient) -> dict:
    return next(x for x in c.get("/api/connectors").json() if x["id"] == "mail")


def values(c: TestClient) -> dict:
    return {v["name"]: v for v in mail(c)["variables"]}


def test_prompt_and_results_are_read_from_the_server_output():
    assert parse_prompt(MS_PROMPT) == ("https://login.microsoft.com/device", "LTGWWUVK3")
    assert parse_prompt("Open https://microsoft.com/devicelogin.") == ("https://microsoft.com/devicelogin", "")
    out = ["noise", '{"success": false, "message": "early"}', "{not json", '{"success": true, "message": "ok"}', ""]
    assert parse_json(out, "success")["message"] == "ok"
    assert parse_json(['{"accounts": []}'], "success") is None


def test_sign_in_from_the_app_adds_the_account_and_switches_the_connector_on(client, state):
    with client() as c:
        m = mail(c)
        assert m["signin"] == {"provider": "Microsoft", "confirms": "MAIL_ENABLED", "accounts_var": "MAIL_ACCOUNTS"}
        assert m["status"] == "disabled" and "MAIL_ENABLED" in m["missing"]
        assert c.get("/api/connectors/mail/signin").json()["status"] == "none"
        assert c.post("/api/connectors/mail/signin").status_code == 200
        s = wait_for(c, "waiting")
        assert (s["url"], s["code"]) == ("https://login.microsoft.com/device", "FAKE12345")
        assert c.post("/api/connectors/mail/signin").json()["code"] == "FAKE12345"  # a second press reuses it
        approve(state, "me@outlook.com")
        s = wait_for(c, "done")
        assert s["account"] == "me@outlook.com"  # named as the server lists it, not as Graph reported it
        m = mail(c)
        assert m["enabled"] and m["missing"] == [] and m["status"] == "idle", m
        assert values(c)["MAIL_ACCOUNTS"]["value"] == "me@outlook.com" and values(c)["MAIL_ENABLED"]["set"]
        audit = c.get("/api/audit").text
        assert "connector_signed_in" in audit and "connector_signin_started" in audit
        assert "FAKE12345" not in audit  # the code is never logged

        # A second account is added after the first, which stays the default.
        c.post("/api/connectors/mail/signin")
        wait_for(c, "waiting")
        approve(state, "work@contoso.com")
        wait_for(c, "done")
        assert values(c)["MAIL_ACCOUNTS"]["value"] == "me@outlook.com, work@contoso.com"
        accounts = c.get("/api/connectors/mail/accounts").json()["accounts"]
        assert [a["username"] for a in accounts] == ["me@outlook.com", "work@contoso.com"] and accounts[0]["selected"]

        # Signing out removes the account from the server and from the list agents may use.
        assert c.delete("/api/connectors/mail/accounts/x;rm -rf").status_code == 409
        assert c.delete("/api/connectors/mail/accounts/uid-9.tid").status_code == 409
        left = c.delete(f"/api/connectors/mail/accounts/{accounts[0]['id']}").json()["accounts"]
        assert [a["username"] for a in left] == ["work@contoso.com"]
        assert values(c)["MAIL_ACCOUNTS"]["value"] == "work@contoso.com" and mail(c)["enabled"]
        # The last one out switches the connector off: nothing is left to read with.
        c.delete(f"/api/connectors/mail/accounts/{left[0]['id']}")
        m = mail(c)
        assert not m["enabled"] and "MAIL_ENABLED" in m["missing"] and not values(c)["MAIL_ACCOUNTS"]["set"]
        assert "connector_signed_out" in c.get("/api/audit").text


def test_accounts_signed_in_earlier_in_a_terminal_are_kept(client, state):
    state.write_text(json.dumps({"accounts": [
        {"id": "a.t", "username": "old@outlook.com", "name": "old", "selected": False},
        {"id": "b.t", "username": "default@outlook.com", "name": "def", "selected": True}]}))
    with client() as c:
        c.post("/api/connectors/mail/signin")
        wait_for(c, "waiting")
        approve(state, "new@outlook.com")
        wait_for(c, "done")
        # Until now the server chose among every account: they stay allowed, its default first.
        assert values(c)["MAIL_ACCOUNTS"]["value"] == "default@outlook.com, old@outlook.com, new@outlook.com"


def test_a_failed_sign_in_says_why(client, state):
    with client(FAKE_SIGNIN_FAIL="1") as c:
        c.post("/api/connectors/mail/signin")
        s = wait_for(c, "failed")
        assert s["error"] == "Login failed: the user declined"
        assert not mail(c)["enabled"]


def test_cancel_stops_the_sign_in(client, state):
    with client() as c:
        c.post("/api/connectors/mail/signin")
        wait_for(c, "waiting")
        assert c.delete("/api/connectors/mail/signin").json()["status"] == "cancelled"
        proc = c.app.state.suite.signin.sessions["mail"].proc
        for _ in range(100):
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        assert proc.poll() is not None
        approve(state, "late@outlook.com")  # too late: nothing is saved
        time.sleep(0.3)
        assert c.get("/api/connectors/mail/signin").json()["status"] == "cancelled"
        assert not values(c)["MAIL_ACCOUNTS"]["set"]


def test_sign_in_refuses_clearly(client, tmp_path):
    with client() as c:
        assert c.post("/api/connectors/nope/signin").status_code == 404
        c.app.state.suite.connectors.offline = True
        r = c.post("/api/connectors/mail/signin")
        assert r.status_code == 409 and "Offline mode" in r.json()["detail"]
    mgr = ConnectorManager([mail_cfg(command="npx"), mail_cfg(id="plain", signin=None)], env={"PATH": str(tmp_path)})
    signin = SigninManager(mgr)
    with pytest.raises(SigninError, match="Node.js is not installed"):
        signin._argv(mgr.configs["mail"], ["--login"])
    with pytest.raises(SigninError, match="does not sign in from the app"):
        signin.config("plain")


def test_shipped_microsoft_sign_in_asks_for_the_connector_s_own_read_only_permissions(tmp_path):
    npx = tmp_path / "npx"
    npx.write_text("#!/bin/sh\n")
    npx.chmod(0o755)
    mgr = ConnectorManager.from_file(ROOT / "config" / "connectors.example.yaml")
    mgr.apply_settings({}, {})
    mgr.env = {"PATH": str(tmp_path)}
    cfg = mgr.configs["microsoft365"]
    argv, _env = SigninManager(mgr)._argv(cfg, cfg.signin.login)
    assert argv[0] == str(npx) and argv[-1] == "--login"
    assert "--read-only" in argv and argv[argv.index("--preset") + 1] == "personal"  # same scopes as the connector
    assert cfg.signin.confirms in cfg.requires and cfg.accounts.vars == ["MS365_ACCOUNTS"]


def test_a_connectors_file_copied_before_sign_in_existed_gets_it(tmp_path):
    shipped = ROOT / "config" / "connectors.example.yaml"
    raw = __import__("yaml").safe_load(shipped.read_text(encoding="utf-8"))
    old = next(c for c in raw["connectors"] if c["id"] == "microsoft365")
    old = {k: v for k, v in old.items() if k != "signin"} | {"steps": ["Run npx ... --login in a terminal"]}
    path = tmp_path / "connectors.yaml"
    path.write_text(__import__("yaml").safe_dump({"connectors": [old]}), encoding="utf-8")
    ms = ConnectorManager.from_file(path, presets=shipped).file_configs["microsoft365"]
    assert ms.signin and ms.signin.login == ["--login"] and "Sign in with Microsoft" in " ".join(ms.steps)
    # A changed launch is left alone: the shipped sign-in might not fit what it runs.
    path.write_text(__import__("yaml").safe_dump({"connectors": [old | {"args": ["-y", "my-fork", "--read-only"]}]}),
                    encoding="utf-8")
    ms = ConnectorManager.from_file(path, presets=shipped).file_configs["microsoft365"]
    assert ms.signin is None and ms.steps == ["Run npx ... --login in a terminal"]


async def test_an_account_id_never_carries_shell_characters(state):
    mgr = ConnectorManager([mail_cfg()], env={"FAKE_SIGNIN_STATE": str(state), "PATH": os.environ["PATH"]})
    for bad in ("x;rm -rf ~", "a&b", "$(id)", "", "a b"):
        with pytest.raises(SigninError, match="not a valid account id"):
            await SigninManager(mgr).remove("mail", bad)
