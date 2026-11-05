"""Everything a person needs to configure can be done from the app: connectors, local files, offline,
model chains, budgets, data policy, profile."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.connectors import ConnectorConfig, ConnectorManager
from app.local_files import FolderError, Roots, build_server, check_folder
from app.main import create_app
from app.settings import load_settings
from tests.conftest import ROOT, fake_openai_server

KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "SUITE_API_TOKEN", "SUITE_OFFLINE",
        "DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_GENIE_SPACE_ID", "MS365_MCP_ENABLED", "GITHUB_PERSONAL_ACCESS_TOKEN")


@pytest.fixture
def factory(tmp_path, monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))

    def make(http_client=None):
        return TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"), http_client=http_client))
    return make


@pytest.fixture
def shared(tmp_path):
    d = tmp_path / "Reports"
    (d / "q3").mkdir(parents=True)
    (d / "q3" / "summary.md").write_text("# Q3\nRevenue up 12 percent.", encoding="utf-8")
    (d / "notes.txt").write_text("Ship on Friday.", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    return d


def cn(o, cid):
    return next(c for c in o["connectors"] if c["id"] == cid)


def test_folder_checks(shared, tmp_path):
    assert check_folder(str(shared)) == shared.resolve()
    for bad, msg in [("", "enter"), ("relative/path", "full path"), (str(tmp_path / "nope"), "not found"),
                     (str(shared / "notes.txt"), "not a folder"), ("/", "whole drive")]:
        with pytest.raises(FolderError, match=msg):
            check_folder(bad)
    roots = Roots([str(shared)])
    assert roots.resolve("q3/summary.md") == (shared / "q3" / "summary.md").resolve()
    assert roots.resolve("Reports/notes.txt") == (shared / "notes.txt").resolve()
    for escape in ("../secret.txt", str(tmp_path / "secret.txt"), "q3/../../secret.txt"):
        with pytest.raises(FolderError, match="outside|not found"):
            roots.resolve(escape)


async def test_builtin_local_files_reads_only_inside_folders(shared, tmp_path):
    link = shared / "escape"
    link.symlink_to(tmp_path)  # a symlink out of the shared folder must not be followed
    cfg = ConnectorConfig(id="local-files", name="Local files", transport="builtin", network=False, folders=[str(shared)],
                          enabled=True)
    mgr = ConnectorManager([cfg], env={}, offline=True)  # works offline: no network needed
    try:
        tools = await mgr.tools("local-files", allowed_only=False)
        assert {t.name for t in tools} == {"list_allowed_directories", "list_directory", "search_files", "read_file", "get_file_info"}
        assert all(t.allowed and t.reason == "declared read-only" for t in tools)
        text, err = await mgr.call("local-files", "read_file", {"path": "q3/summary.md"})
        assert not err and "Revenue up 12 percent" in text
        text, err = await mgr.call("local-files", "search_files", {"pattern": "summary"})
        assert "Reports/q3/summary.md" in text
        text, err = await mgr.call("local-files", "read_file", {"path": "escape/secret.txt"})
        assert err and "outside" in text
        text, err = await mgr.call("local-files", "read_file", {"path": "../secret.txt"})
        assert err
    finally:
        await mgr.shutdown()
    assert build_server([])  # no folders: server still builds and says so


def test_legacy_npx_local_files_becomes_builtin():
    old = ConnectorConfig(id="local-files", name="x", transport="stdio", command="npx", args=["${SUITE_FILES_DIR}"])
    mgr = ConnectorManager([old], env={})
    assert mgr.configs["local-files"].transport == "builtin" and mgr.missing("local-files") == ["a folder"]


def test_local_files_set_up_from_the_app(factory, shared):
    with factory() as c:
        lf = cn(c.get("/api/overview").json(), "local-files")
        # Off until set up and switched on by the user.
        assert lf["builtin"] and lf["status"] == "disabled" and not lf["enabled"] and lf["missing"] == ["a folder"] and not lf["network"]
        r = c.put("/api/connectors/local-files", json={"enabled": True})
        assert r.status_code == 422 and "needs a folder before it can be switched on" in r.json()["detail"]
        r = c.put("/api/connectors/local-files", json={"folders": ["relative"]})
        assert r.status_code == 422 and "full path" in r.json()["detail"]
        lf = c.put("/api/connectors/local-files", json={"enabled": True, "folders": [str(shared), str(shared)]}).json()
        assert lf["folders"] == [str(shared.resolve())] and lf["status"] == "idle"
        tools = c.post("/api/connectors/local-files/connect").json()["tools"]
        assert any(t["name"] == "read_file" and t["allowed"] for t in tools)
        # Offline mode keeps local files available.
        c.post("/api/admin/offline", json={"on": True})
        assert cn(c.get("/api/overview").json(), "local-files")["status"] != "offline"
    with factory() as c:  # survives a restart
        assert cn(c.get("/api/overview").json(), "local-files")["folders"] == [str(shared.resolve())]
        lf = c.delete("/api/connectors/local-files/settings").json()
        assert lf["folders"] == [] and lf["status"] == "disabled" and not lf["enabled"]  # reset means off again


def test_connector_values_are_shared_and_secrets_write_only(factory, monkeypatch):
    with factory() as c:
        db = cn(c.get("/api/overview").json(), "databricks")
        names = {v["name"]: v for v in db["variables"]}
        assert names["DATABRICKS_TOKEN"]["secret"] and not names["DATABRICKS_HOST"]["secret"]
        assert db["status"] == "disabled" and not db["enabled"] and "DATABRICKS_TOKEN" in db["missing"]
        assert any(m.startswith("at least one of: Genie space") for m in db["missing"])
        # one connector: shared fields first and required, each service's fields after them and optional
        order = [v["name"] for v in db["variables"]]
        assert order[:2] == ["DATABRICKS_HOST", "DATABRICKS_TOKEN"] and not names["DATABRICKS_HOST"]["optional"]
        assert names["DATABRICKS_GENIE_SPACE_ID"]["optional"] and names["DATABRICKS_GENIE_SPACE_ID"]["part"] == "genie"
        assert names["DATABRICKS_UC_SCHEMA"]["part"] == "functions" and names["DATABRICKS_HOST"]["part"] is None
        r = c.put("/api/connectors/databricks", json={"enabled": True})
        assert r.status_code == 422 and "DATABRICKS_HOST" in r.json()["detail"]  # cannot switch on before setup
        r = c.put("/api/connectors/databricks", json={"values": {
            "DATABRICKS_HOST": "https://adb-1.azuredatabricks.net", "DATABRICKS_TOKEN": "dapi-secret-1",
            "DATABRICKS_GENIE_SPACE_ID": "space1"}})
        db = r.json()
        assert db["status"] == "disabled" and db["missing"] == [], db  # set up, but still off until switched on
        assert {p["id"]: p["ready"] for p in db["parts"]} == {"genie": True, "functions": False, "search": False}
        db = c.put("/api/connectors/databricks", json={"enabled": True}).json()
        assert db["status"] == "idle", db
        vals = {v["name"]: v for v in db["variables"]}
        assert vals["DATABRICKS_TOKEN"]["set"] and vals["DATABRICKS_TOKEN"]["value"] is None
        assert vals["DATABRICKS_HOST"]["value"] == "https://adb-1.azuredatabricks.net"
        o = c.get("/api/overview")
        assert "dapi-secret-1" not in o.text and "dapi-secret-1" not in c.get("/api/audit").text
        # A second service needs only its own fields: the host and token are entered once.
        db = c.put("/api/connectors/databricks", json={"values": {"DATABRICKS_UC_CATALOG": "main", "DATABRICKS_UC_SCHEMA": "ops"}}).json()
        assert {p["id"]: p["ready"] for p in db["parts"]}["functions"] is True
        # Saving with an empty secret keeps it; an empty plain value clears it.
        db = c.put("/api/connectors/databricks", json={"values": {"DATABRICKS_TOKEN": "", "DATABRICKS_GENIE_SPACE_ID": ""}}).json()
        vals = {v["name"]: v for v in db["variables"]}
        assert vals["DATABRICKS_TOKEN"]["set"] and not vals["DATABRICKS_GENIE_SPACE_ID"]["set"]
        assert c.put("/api/connectors/databricks", json={"values": {"NOT_USED": "x"}}).status_code == 422
        assert c.put("/api/connectors/databricks", json={"values": {"DATABRICKS_HOST": "a\nb"}}).status_code == 422
        db = c.put("/api/connectors/databricks", json={"clear": ["DATABRICKS_TOKEN"]}).json()
        assert not {v["name"]: v for v in db["variables"]}["DATABRICKS_TOKEN"]["set"]
        # Opt-in flags (Microsoft 365 needs a one-time sign-in first) are ticked in the app.
        m = cn(c.get("/api/overview").json(), "microsoft365")
        assert m["status"] == "disabled" and any(v["flag"] for v in m["variables"])
        m = c.put("/api/connectors/microsoft365", json={"values": {"MS365_MCP_ENABLED": "1"}, "enabled": True}).json()
        assert m["status"] == "idle"  # values and the switch can be saved together
        # Switching off.
        assert c.put("/api/connectors/microsoft365", json={"enabled": False}).json()["status"] == "disabled"
    monkeypatch.setenv("DATABRICKS_HOST", "https://from-env")
    with factory() as c:  # the environment wins over a value typed in the app
        v = {x["name"]: x for x in cn(c.get("/api/overview").json(), "databricks")["variables"]}
        assert v["DATABRICKS_HOST"]["source"] == "env" and v["DATABRICKS_HOST"]["value"] is None


def test_offline_pauses_every_cloud_provider_and_internet_connector_at_once(factory):
    with factory() as c:
        c.put("/api/providers/openai", json={"api_key": "sk-test"})
        c.put("/api/connectors/microsoft365", json={"values": {"MS365_MCP_ENABLED": "1"}, "enabled": True})
        o = c.get("/api/overview").json()
        assert next(p for p in o["providers"] if p["name"] == "openai")["available"]
        c.post("/api/admin/offline", json={"on": True})
        o = c.get("/api/overview").json()
        cloud = [p for p in o["providers"] if p["locality"] == "cloud"]
        assert cloud and all(p["offline_paused"] and not p["available"] and p["reason"] == "offline mode" for p in cloud)
        assert all(not p["offline_paused"] for p in o["providers"] if p["locality"] == "local")
        net = [x for x in o["connectors"] if x["network"]]
        assert all(x["offline_paused"] for x in net)
        assert all(x["status"] == "offline" for x in net if x["enabled"]) and cn(o, "microsoft365")["status"] == "offline"
        # The person's choices are kept: going online restores them without touching each one.
        c.post("/api/admin/offline", json={"on": False})
        o = c.get("/api/overview").json()
        assert next(p for p in o["providers"] if p["name"] == "openai")["available"]
        assert cn(o, "microsoft365")["status"] == "idle"


def test_chains_budgets_data_policy_and_profile(factory):
    with factory(fake_openai_server([], models=("qwen3-4b",))) as c:
        c.put("/api/providers/lmstudio", json={"enabled": True, "models": [
            {"model": "qwen3-4b", "context_tokens": 32768, "price_in_per_mtok": 0.0}]})
        c.put("/api/providers/openai", json={"api_key": "sk-test", "models": [
            {"model": "gpt-x", "context_tokens": 128000, "price_in_per_mtok": 1.25, "price_out_per_mtok": 10}]})
        o = c.get("/api/overview").json()
        m = next(x for x in next(p for p in o["providers"] if p["name"] == "openai")["models"])
        assert m["price_in_per_mtok"] == 1.25 and m["price_out_per_mtok"] == 10
        spec = o["tiers"]["specialist"]
        assert "lmstudio/qwen3-4b" in spec
        # Put the local model first and drop a cloud model from the chain.
        order = ["lmstudio/qwen3-4b"] + [r for r in spec if r not in ("lmstudio/qwen3-4b", "anthropic/claude-sonnet-5-5")]
        o = c.put("/api/settings/general", json={"tiers": {"specialist": order}}).json()
        assert o["tiers"]["specialist"] == order and "tiers" in o["general_edited"]
        assert c.put("/api/settings/general", json={"tiers": {"specialist": ["nope/x"]}}).status_code == 422
        # Budgets.
        b = {**o["budgets"], "max_run_cost_usd": 0.5, "max_tool_calls_per_step": 3}
        o = c.put("/api/settings/general", json={"budgets": b}).json()
        assert o["budgets"]["max_run_cost_usd"] == 0.5 and o["budgets"]["max_tool_calls_per_step"] == 3
        assert c.put("/api/settings/general", json={"budgets": {**b, "max_context_fraction": 2}}).status_code == 422
        # Data policy: keep confidential data local; restricted stays local whatever is sent.
        o = c.put("/api/settings/general", json={"cloud_allowed": {"confidential": False}, "default_data_class": "confidential",
                                                 "persona_exports": True, "store_prompts": True}).json()
        assert o["data_classes"]["confidential"] == ["local"] and o["data_classes"]["restricted"] == ["local"]
        assert o["default_data_class"] == "confidential" and o["persona"]["exports"] and o["store_prompts"]
        assert c.put("/api/settings/general", json={"cloud_allowed": {"restricted": True}}).status_code == 422
        # A run with the default class now stays on the local model.
        rid = c.post("/api/runs", json={"playbook_id": "quick-ask", "inputs": {"request": "hi"}}).json()["id"]
        for _ in range(100):
            run = c.get(f"/api/runs/{rid}").json()
            if run["status"] not in ("queued", "running"):
                break
        assert run["data_class"] == "confidential" and run["steps"][0]["model"] == "lmstudio/qwen3-4b"
        # Profile.
        p = c.put("/api/settings/profile", json={"name": "Sam", "role": "Drilling engineer", "goals": ["Cut NPT", " ", "Faster reviews"],
                                                 "working_preferences": ["Answer first"]}).json()
        assert p["role"] == "Drilling engineer" and p["goals"] == ["Cut NPT", "Faster reviews"]
        assert c.app.state.suite.engine.profile["role"] == "Drilling engineer"  # the engine sees it immediately
        o = c.get("/api/overview").json()
        assert o["profile_configured"] and o["profile_saved_in_app"]
    with factory() as c:  # everything survives a restart
        o = c.get("/api/overview").json()
        assert o["budgets"]["max_run_cost_usd"] == 0.5 and o["data_classes"]["confidential"] == ["local"]
        assert o["profile"]["name"] == "Sam"
        o = c.delete("/api/settings/general/all").json()
        assert o["budgets"]["max_run_cost_usd"] == 2.0 and o["data_classes"]["confidential"] == ["local", "cloud"]
        assert c.delete("/api/settings/general/whatever").status_code == 422
        p = c.delete("/api/settings/profile").json()
        assert p["name"] == "" and not c.get("/api/overview").json()["profile_configured"]
        events = {e["event"] for e in c.get("/api/audit").json()}
        assert {"settings_changed", "settings_reset", "profile_saved", "profile_reset", "provider_edited"} <= events


def test_restart_stops_workers():
    mgr = ConnectorManager([], env={})
    asyncio.run(mgr.restart())
    assert mgr.workers == {}
