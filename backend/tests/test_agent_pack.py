"""Installing the private agent layer from Settings (an agent pack), without a restart or a terminal."""

import io
import os
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.registry import Registry
from app.settings import load_settings
from tests.conftest import PRIVATE_FIXTURE, ROOT

POLICIES = ROOT / "config" / "policies"
COS = (PRIVATE_FIXTURE / "agents" / "chief-of-staff.yaml").read_bytes()
NOTICE = "Agent instructions are not installed"


def pack(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A desktop-like install with no private layer yet: the launcher's folder does not exist."""
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SUITE_PRIVATE_REGISTRY", str(tmp_path / "private-registry"))
    for k in ("SUITE_API_TOKEN", "SUITE_OFFLINE"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))) as c:
        yield c, tmp_path / "private-registry"


def test_import_zip_installs_and_clears_the_notice_without_restart(client):
    c, folder = client
    o = c.get("/api/overview").json()
    assert any(NOTICE in w for w in o["warnings"]) and o["agent_pack"]["installed"] is False
    # A pack zipped from the private repository: a top folder, an agents/ folder, and other YAML that is not an agent.
    data = pack({"agent-private-registry/agents/chief-of-staff.yaml": COS,
                 "agent-private-registry/ingest/report.yaml": b"not: an agent\n",
                 "__MACOSX/agent-private-registry/agents/._chief-of-staff.yaml": b"junk"})
    r = c.post("/api/agent-pack", files=[("files", ("pack.zip", data, "application/zip"))])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == ["chief-of-staff.yaml"] and body["installed"] is True and body["agents_with_instructions"] == 1
    assert (folder / "agents" / "chief-of-staff.yaml").read_bytes() == COS
    if os.name == "posix":
        assert stat.S_IMODE((folder / "agents" / "chief-of-staff.yaml").stat().st_mode) == 0o600
    o = c.get("/api/overview").json()
    assert not any(NOTICE in w for w in o["warnings"])
    assert o["agent_pack"] == {"installed": True, "folder": str(folder), "agents_total": 34, "agents_with_instructions": 1}
    # The running agents use it at once, and the UI still never sees the instructions.
    assert c.app.state.suite.registry.agent("chief-of-staff").instructions.startswith("FIXTURE INSTRUCTIONS")
    assert "instructions" not in c.get("/api/agents/chief-of-staff").json()
    assert "FIXTURE" not in c.get("/api/overview").text
    events = [e for e in c.get("/api/audit").json() if e.get("event") == "agent_pack_imported"]
    assert events and "FIXTURE" not in str(events)


def test_import_yaml_files_directly(client):
    c, folder = client
    r = c.post("/api/agent-pack", files=[("files", ("chief-of-staff.yaml", COS, "application/x-yaml")),
                                         ("files", ("notes.yaml", b"id: nobody\n", "application/x-yaml"))])
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == ["chief-of-staff.yaml"] and r.json()["skipped"] == ["notes.yaml"]


@pytest.mark.parametrize("name,data,reason", [
    ("pack.zip", b"not a zip", "could not be opened"),
    ("pack.zip", pack({"readme.txt": b"hi"}), "No agent files"),
    ("pack.zip", pack({"agents/x.yaml": b"id: not-in-catalog\n"}), "names an agent"),
    ("agent.yaml", b"id: [unclosed\n", "not a readable YAML"),
    ("agent.txt", b"id: chief-of-staff\n", ".zip agent pack"),
])
def test_bad_uploads_are_refused_readably_and_write_nothing(client, name, data, reason):
    c, folder = client
    r = c.post("/api/agent-pack", files=[("files", (name, data, "application/octet-stream"))])
    assert r.status_code == 422 and reason in r.json()["detail"], r.text
    assert not (folder / "agents").exists()
    assert any(NOTICE in w for w in c.get("/api/overview").json()["warnings"])


def test_zip_paths_cannot_escape_the_agents_folder(tmp_path):
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "missing")
    data = pack({"agents/../../../evil/chief-of-staff.yaml": COS})
    reg.import_private([("pack.zip", data)], tmp_path / "target")
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["target/agents/chief-of-staff.yaml"]


def test_a_broken_pack_file_never_stops_the_app(tmp_path):
    agents = tmp_path / "pr" / "agents"
    agents.mkdir(parents=True)
    (agents / "chief-of-staff.yaml").write_bytes(COS)
    (agents / "broken.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    (agents / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "pr")
    assert reg.agent("chief-of-staff").has_private
    assert any("broken.yaml could not be read" in w for w in reg.warnings)
    assert any("list.yaml could not be read" in w for w in reg.warnings)


def test_overview_reports_the_app_version(client):
    from app import __version__
    c, _ = client
    assert c.get("/api/overview").json()["version"] == __version__
