"""Sign in to a connector from the app: the connector's own server signs in with a code shown in Settings;
the suite never handles a token. A fake CLI (tests/fake_signin_cli.py) plays the server."""

import asyncio
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
        assert m["signin"] == {"provider": "Microsoft", "kind": "command", "confirms": "MAIL_ENABLED",
                               "accounts_vars": ["MAIL_ACCOUNTS"]}
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


# ---------------------------------------------------------------- Google: sign-in through the server's own tool

CLIENT = {"installed": {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-test",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth"}}


def google_cfg(**kw) -> ConnectorConfig:
    base = {"id": "google", "name": "Google", "transport": "stdio", "command": sys.executable,
            "args": [str(HERE / "fake_google_server.py"), "--read-only"],
            "env": {"GOOGLE_OAUTH_CLIENT_ID": "${GOOGLE_OAUTH_CLIENT_ID}",
                    "GOOGLE_OAUTH_CLIENT_SECRET": "${GOOGLE_OAUTH_CLIENT_SECRET}",
                    "USER_GOOGLE_EMAIL": "${USER_GOOGLE_EMAIL}", "WORKSPACE_MCP_CREDENTIALS_DIR": "${CREDS}",
                    "FAKE_GOOGLE_FAIL": "${FAKE_GOOGLE_FAIL:-}", "FAKE_GOOGLE_CALLBACK": "${FAKE_GOOGLE_CALLBACK:-}"},
            "accounts": {"param": "user_google_email", "vars": ["USER_GOOGLE_EMAIL", "GOOGLE_OTHER_ACCOUNTS"]},
            "client_file": {"name": "google-oauth-client.json",
                            "vars": {"client_id": "GOOGLE_OAUTH_CLIENT_ID", "client_secret": "GOOGLE_OAUTH_CLIENT_SECRET"}},
            "signin": {"provider": "Google", "kind": "tool", "tool": "start_google_auth",
                       "tool_args": {"service_name": "Google Workspace"}, "account_arg": "user_google_email",
                       "credentials_dir": "${WORKSPACE_MCP_CREDENTIALS_DIR:-~/nowhere}", "timeout_s": 30,
                       "success_log": r"Successfully authenticated user: (\S+?)\.?\s*$",
                       "error_log": r"(Authentication failed: .*|Error processing OAuth callback: .*)"}}
    base.update(kw)
    return ConnectorConfig.model_validate(base)


@pytest.fixture
def creds(tmp_path):
    d = tmp_path / "credentials"
    d.mkdir()
    return d


@pytest.fixture
def gclient(tmp_path, monkeypatch, creds):
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SUITE_API_TOKEN", raising=False)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "google-oauth-client.json").write_text(json.dumps(CLIENT), encoding="utf-8")

    def make(**env):
        mgr = ConnectorManager([google_cfg()], env={"CREDS": str(creds), "PATH": os.environ["PATH"], **env})
        return TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), connectors=mgr))
    return make


def google(c: TestClient) -> dict:
    return next(x for x in c.get("/api/connectors").json() if x["id"] == "google")


def gvalues(c: TestClient) -> dict:
    return {v["name"]: v for v in google(c)["variables"]}


def gwait(c: TestClient, *statuses: str, timeout: float = 30) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        s = c.get("/api/connectors/google/signin").json()
        if s["status"] in statuses:
            return s
        time.sleep(0.05)
    raise AssertionError(f"sign-in never reached {statuses}: {s}")


def google_callback(creds: Path, email: str) -> None:
    """What the server's callback does once the person approves: one credentials file per address."""
    from urllib.parse import quote
    (creds / f"{quote(email, safe='@._-')}.json").write_text('{"token": "never-read-by-the-suite"}', encoding="utf-8")


def test_google_sign_in_uses_the_built_in_client_and_the_server_s_own_sign_in(gclient, creds):
    with gclient() as c:
        g = google(c)
        assert g["signin"]["kind"] == "tool" and g["signin"]["accounts_vars"] == ["USER_GOOGLE_EMAIL", "GOOGLE_OTHER_ACCOUNTS"]
        v = gvalues(c)
        assert v["GOOGLE_OAUTH_CLIENT_ID"]["source"] == "bundled" and v["GOOGLE_OAUTH_CLIENT_ID"]["set"]
        assert v["GOOGLE_OAUTH_CLIENT_SECRET"]["value"] is None  # a built-in secret is never sent to the page
        assert g["missing"] == ["USER_GOOGLE_EMAIL"]  # the client is built in: only an account is missing
        assert "GOCSPX-test" not in c.get("/api/overview").text

        r = c.post("/api/connectors/google/signin", json={})
        assert r.status_code == 409 and "Enter the Google address" in r.json()["detail"]
        assert c.post("/api/connectors/google/signin", json={"account": "me@gmail.com"}).status_code == 200
        s = gwait(c, "waiting")
        assert s["url"].startswith("https://accounts.google.com/o/oauth2/auth?client_id=123-abc.apps.googleusercontent.com")
        assert "login_hint=me@gmail.com" in s["url"] and not s["code"]
        google_callback(creds, "me@gmail.com")
        assert gwait(c, "done")["account"] == "me@gmail.com"
        g = google(c)
        assert g["enabled"] and g["missing"] == [] and gvalues(c)["USER_GOOGLE_EMAIL"]["value"] == "me@gmail.com"

        # A second account; Google signs in whichever account the person picks, and that is what is saved.
        c.post("/api/connectors/google/signin", json={"account": "work@corp.com"})
        gwait(c, "waiting")
        google_callback(creds, "first.last+ops@corp.com")
        assert gwait(c, "done")["account"] == "first.last+ops@corp.com"
        v = gvalues(c)
        assert v["USER_GOOGLE_EMAIL"]["value"] == "me@gmail.com"
        assert v["GOOGLE_OTHER_ACCOUNTS"]["value"] == "first.last+ops@corp.com"
        accounts = c.get("/api/connectors/google/accounts").json()["accounts"]
        assert [(a["username"], a["selected"]) for a in accounts] == [("first.last+ops@corp.com", False), ("me@gmail.com", True)]

        # Signing out the default promotes the next account; the server's file for it is gone.
        r = c.delete("/api/connectors/google/accounts/nobody@corp.com")
        assert r.status_code == 409 and "not signed in" in r.json()["detail"]
        with pytest.raises(SigninError, match="not signed in"):  # only an address the server saved can be removed
            asyncio.run(c.app.state.suite.signin.remove("google", "../../secret@x.com"))
        left = c.delete("/api/connectors/google/accounts/me@gmail.com").json()["accounts"]
        assert [a["username"] for a in left] == ["first.last+ops@corp.com"] and not (creds / "me@gmail.com.json").exists()
        v = gvalues(c)
        assert v["USER_GOOGLE_EMAIL"]["value"] == "first.last+ops@corp.com" and not v["GOOGLE_OTHER_ACCOUNTS"]["set"]
        c.delete("/api/connectors/google/accounts/first.last+ops@corp.com")
        assert list(creds.iterdir()) == [] and not google(c)["enabled"]
        audit = c.get("/api/audit").text
        assert "connector_signed_in" in audit and "never-read-by-the-suite" not in audit


def test_google_sign_in_reports_the_server_s_error_and_can_be_cancelled(gclient, creds):
    with gclient(FAKE_GOOGLE_FAIL="1") as c:
        c.post("/api/connectors/google/signin", json={"account": "me@gmail.com"})
        s = gwait(c, "failed")
        assert s["error"].startswith("Authentication Error: OAuth client credentials not found")  # markdown removed
    with gclient() as c:
        c.post("/api/connectors/google/signin", json={"account": "me@gmail.com"})
        gwait(c, "waiting")
        assert c.delete("/api/connectors/google/signin").json()["status"] == "cancelled"
        google_callback(creds, "me@gmail.com")  # too late: nothing is saved
        time.sleep(1.5)
        assert c.get("/api/connectors/google/signin").json()["status"] == "cancelled"
        # The address typed to sign in is the default account at once; nothing signed in, so the connector stays off.
        assert gvalues(c)["USER_GOOGLE_EMAIL"]["value"] == "me@gmail.com" and not google(c)["enabled"]


def test_google_accounts_signed_in_earlier_can_be_used(gclient, creds):
    google_callback(creds, "earlier@gmail.com")
    (creds / "oauth_states.json").write_text("{}")  # the server's own bookkeeping, not an account
    with gclient() as c:
        assert [a["username"] for a in c.get("/api/connectors/google/accounts").json()["accounts"]] == ["earlier@gmail.com"]
        assert c.post("/api/connectors/google/accounts/use").status_code == 200
        assert gvalues(c)["USER_GOOGLE_EMAIL"]["value"] == "earlier@gmail.com" and google(c)["enabled"]


def test_built_in_client_file_is_the_lowest_priority(tmp_path):
    folder = tmp_path / "cfg"
    folder.mkdir()
    (folder / "google-oauth-client.json").write_text(json.dumps({"web": CLIENT["installed"]}), encoding="utf-8")
    mgr = ConnectorManager([google_cfg()], env={"GOOGLE_OAUTH_CLIENT_SECRET": "from-env"})
    assert mgr.load_client_files([tmp_path / "missing", folder]) == []
    mgr.apply_settings({}, {"GOOGLE_OAUTH_CLIENT_ID": "typed-in-app"})
    assert mgr.env["GOOGLE_OAUTH_CLIENT_ID"] == "typed-in-app"  # the app beats the built-in client
    assert mgr.env["GOOGLE_OAUTH_CLIENT_SECRET"] == "from-env"  # the environment beats both
    mgr.apply_settings({}, {})
    assert mgr.env["GOOGLE_OAUTH_CLIENT_ID"] == "123-abc.apps.googleusercontent.com"
    (folder / "google-oauth-client.json").write_text("{not json", encoding="utf-8")
    assert "This is not a JSON file" in mgr.load_client_files([folder])[0]
    assert "GOOGLE_OAUTH_CLIENT_ID" not in mgr.env
    (folder / "google-oauth-client.json").write_text(json.dumps({"installed": {"client_id": "x"}}), encoding="utf-8")
    assert "The file has no client_secret" in mgr.load_client_files([folder])[0]


def test_shipped_google_connector_signs_in_through_its_server():
    cfg = ConnectorManager.from_file(ROOT / "config" / "connectors.example.yaml").file_configs["google-workspace"]
    assert cfg.signin.kind == "tool" and cfg.signin.tool == "start_google_auth"
    assert cfg.signin.account_arg == cfg.accounts.param == "user_google_email"
    assert cfg.client_file.vars == {"client_id": "GOOGLE_OAUTH_CLIENT_ID", "client_secret": "GOOGLE_OAUTH_CLIENT_SECRET"}
    assert "--read-only" in cfg.args
    # The sign-in server keeps the same services and read-only mode; only the tier changes (last one wins).
    assert cfg.signin.login == ["--tool-tier", "complete"] and cfg.args.index("--tools") < len(cfg.args)


def test_client_file_is_uploaded_in_settings_and_wins(gclient, tmp_path):
    with gclient() as c:
        assert google(c)["client_file"] == {"name": "google-oauth-client.json", "source": "uploaded"}  # in the data folder
        assert c.delete("/api/connectors/google/client-file").json()["client_file"]["source"] is None
        g = google(c)
        assert not gvalues(c)["GOOGLE_OAUTH_CLIENT_ID"]["set"] and "GOOGLE_OAUTH_CLIENT_ID" in g["missing"]
        bad = c.post("/api/connectors/google/client-file", files={"file": ("x.json", b'{"installed": {"client_id": "x"}}')})
        assert bad.status_code == 422 and "no client_secret" in bad.json()["detail"]
        assert c.post("/api/connectors/google/client-file", files={"file": ("x.json", b"not json")}).status_code == 422
        big = c.post("/api/connectors/google/client-file", files={"file": ("x.json", b"{" + b" " * 70000 + b"}")})
        assert big.status_code == 422 and "too large" in big.json()["detail"]
        mine = {"installed": {"client_id": "999-mine.apps.googleusercontent.com", "client_secret": "GOCSPX-mine"}}
        g = c.post("/api/connectors/google/client-file", files={"file": ("client_secret_999.json", json.dumps(mine).encode())}).json()
        assert g["client_file"]["source"] == "uploaded" and g["missing"] == ["USER_GOOGLE_EMAIL"]
        saved = tmp_path / "data" / "google-oauth-client.json"
        assert json.loads(saved.read_text()) == mine and (saved.stat().st_mode & 0o077) == 0  # this user only
        assert "GOCSPX-mine" not in c.get("/api/overview").text and "GOCSPX-mine" not in c.get("/api/audit").text
        assert "999-mine.apps.googleusercontent.com" in c.get("/api/audit").text  # the ID is not secret
        assert c.post("/api/connectors/nope/client-file", files={"file": ("x.json", b"{}")}).status_code == 404
        assert c.post("/api/connectors/google/signin", json={"account": "me@gmail.com"}).status_code == 200
        assert "client_id=999-mine" in gwait(c, "waiting")["url"]  # the sign-in uses the uploaded client


def test_an_uploaded_client_beats_one_built_into_the_app(tmp_path):
    uploaded, shipped = tmp_path / "data", tmp_path / "shipped"
    uploaded.mkdir()
    shipped.mkdir()
    (shipped / "google-oauth-client.json").write_text(json.dumps(CLIENT), encoding="utf-8")
    mgr = ConnectorManager([google_cfg()], env={})
    mgr.uploads_dir = uploaded
    mgr.load_client_files([uploaded, shipped])
    assert mgr.env["GOOGLE_OAUTH_CLIENT_ID"].startswith("123-abc")
    assert mgr.describe()[0]["client_file"]["source"] == "built-in"
    (uploaded / "google-oauth-client.json").write_text(json.dumps({"web": {"client_id": "up", "client_secret": "s"}}))
    mgr.load_client_files([uploaded, shipped])
    assert mgr.env["GOOGLE_OAUTH_CLIENT_ID"] == "up" and mgr.describe()[0]["client_file"]["source"] == "uploaded"



def test_google_sign_in_reads_the_server_s_own_report(gclient, creds, tmp_path):
    """Google's answer reaches the server, not the app; the server's log says how it ended. Success counts even if
    no credentials file shows up where the app looks, and Google's error is shown at once, not after the timeout."""
    with gclient(FAKE_GOOGLE_CALLBACK="ok:other@gmail.com") as c:
        c.post("/api/connectors/google/signin", json={"account": "typed@gmail.com"})
        assert gvalues(c)["USER_GOOGLE_EMAIL"]["value"] == "typed@gmail.com"  # the default as soon as Sign in is pressed
        s = gwait(c, "done", "failed")
        assert s["status"] == "done" and s["account"] == "other@gmail.com", s
        assert gvalues(c)["USER_GOOGLE_EMAIL"]["value"] == "other@gmail.com" and google(c)["enabled"]
        log = tmp_path / "data" / "logs" / "google-signin.log"
        assert "Successfully authenticated user: other@gmail.com" in log.read_text()
    with gclient(FAKE_GOOGLE_CALLBACK="error") as c:
        started = time.time()
        c.post("/api/connectors/google/signin", json={"account": "me@gmail.com"})
        s = gwait(c, "failed", "done", timeout=10)
        assert s["status"] == "failed" and time.time() - started < 10  # not the 30-second timeout
        assert "Google did not complete the sign-in: Authentication failed: Google returned an error: access_denied." in s["error"]
        assert "Details:" in s["error"] and "google-signin.log" in s["error"] and "\x1b" not in s["error"]


def test_a_typed_address_google_did_not_sign_in_is_replaced(gclient, creds):
    with gclient() as c:
        c.post("/api/connectors/google/signin", json={"account": "typed@gmail.com"})
        gwait(c, "waiting")
        google_callback(creds, "real@gmail.com")
        gwait(c, "done")
        v = gvalues(c)
        assert v["USER_GOOGLE_EMAIL"]["value"] == "real@gmail.com" and not v["GOOGLE_OTHER_ACCOUNTS"]["set"]
