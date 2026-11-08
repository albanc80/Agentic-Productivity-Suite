"""Installing the private agent layer from Settings (an agent pack), without a restart or a terminal."""

import base64
import importlib.util
import io
import os
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.registry import PACK_MAGIC, Registry, decrypt_pack, encrypt_pack, parse_pack_key, read_pack_key
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
    assert body["imported_files"] == ["chief-of-staff.yaml"] and body["installed"] is True and body["agents_with_instructions"] == 1
    assert (folder / "agents" / "chief-of-staff.yaml").read_bytes() == COS
    if os.name == "posix":
        assert stat.S_IMODE((folder / "agents" / "chief-of-staff.yaml").stat().st_mode) == 0o600
    o = c.get("/api/overview").json()
    assert not any(NOTICE in w for w in o["warnings"])
    assert o["agent_pack"] == {"installed": True, "folder": str(folder), "agents_total": 34, "agents_with_instructions": 1,
                             "built_in": 0, "imported": 1}
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
    assert r.json()["imported_files"] == ["chief-of-staff.yaml"] and r.json()["skipped"] == ["notes.yaml"]


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


# ---------------------------------------------------------------- built into the installers, encrypted (ADR 0007)

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()
OTHER_KEY = base64.urlsafe_b64encode(bytes(range(1, 33))).decode()


def sealed(tmp_path, key=KEY, entries=None) -> Path:
    f = tmp_path / "agent-pack.enc"
    f.write_bytes(encrypt_pack(pack(entries or {"agent-pack/agents/chief-of-staff.yaml": COS}), parse_pack_key(key)))
    return f


def test_encryption_round_trip_and_wrong_key():
    blob = encrypt_pack(b"zip bytes", parse_pack_key(KEY))
    assert blob.startswith(PACK_MAGIC) and b"zip bytes" not in blob
    assert decrypt_pack(blob, parse_pack_key(KEY)) == b"zip bytes"
    with pytest.raises(ValueError, match="does not match"):
        decrypt_pack(blob, parse_pack_key(OTHER_KEY))
    with pytest.raises(ValueError):
        parse_pack_key("too-short")


def test_built_in_pack_runs_the_agents_without_any_import(tmp_path):
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "no-folder", pack_file=sealed(tmp_path), pack_key=KEY)
    assert reg.agent("chief-of-staff").instructions.startswith("FIXTURE INSTRUCTIONS")
    assert reg.layer == {"chief-of-staff": "built-in"}
    assert not any(NOTICE in w for w in reg.warnings)
    st = reg.private_status()
    assert st["installed"] and st["built_in"] == 1 and st["imported"] == 0


def test_an_imported_pack_replaces_the_built_in_one_per_agent(tmp_path):
    folder = tmp_path / "pr" / "agents"
    folder.mkdir(parents=True)
    (folder / "chief-of-staff.yaml").write_text("id: chief-of-staff\ninstructions: MY OWN VERSION\n", encoding="utf-8")
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "pr", pack_file=sealed(tmp_path), pack_key=KEY)
    cos = reg.agent("chief-of-staff")
    assert cos.instructions == "MY OWN VERSION" and cos.persona is None and cos.modes["daily"].instructions == ""
    assert reg.layer == {"chief-of-staff": "imported"}


def test_a_wrong_key_says_so_and_falls_back(tmp_path):
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "none", pack_file=sealed(tmp_path), pack_key=OTHER_KEY)
    assert any("built into this app could not be opened (the key does not match" in w for w in reg.warnings)
    assert any(NOTICE in w for w in reg.warnings) and not reg.agent("chief-of-staff").has_private


def test_without_a_key_the_pack_stays_closed(tmp_path):
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "none", pack_file=sealed(tmp_path), pack_key=None)
    assert any(NOTICE in w for w in reg.warnings) and not reg.layer


def test_key_comes_from_the_environment_or_the_build(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "agent-pack.key").write_text(KEY + "\n", encoding="utf-8")
    monkeypatch.delenv("SUITE_AGENT_PACK_KEY", raising=False)
    assert read_pack_key(tmp_path) == KEY
    monkeypatch.setenv("SUITE_AGENT_PACK_KEY", "")
    assert read_pack_key(tmp_path) is None  # empty means "no key", for tests and for switching it off
    monkeypatch.setenv("SUITE_AGENT_PACK_KEY", OTHER_KEY)
    assert read_pack_key(tmp_path) == OTHER_KEY


def test_app_uses_the_built_in_pack_and_never_shows_it(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SUITE_PRIVATE_REGISTRY", str(tmp_path / "private-registry"))
    monkeypatch.setenv("SUITE_AGENT_PACK", str(sealed(tmp_path)))
    monkeypatch.setenv("SUITE_AGENT_PACK_KEY", KEY)
    for k in ("SUITE_API_TOKEN", "SUITE_OFFLINE"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(create_app(load_settings(ROOT, ROOT / "config" / "suite.example.yaml"))) as c:
        o = c.get("/api/overview")
        assert o.json()["agent_pack"]["built_in"] == 1 and not any(NOTICE in w for w in o.json()["warnings"])
        for text in (o.text, c.get("/api/agents/chief-of-staff").text, c.get("/api/audit").text):
            assert "FIXTURE" not in text and KEY not in text
        assert c.app.state.suite.registry.agent("chief-of-staff").instructions.startswith("FIXTURE INSTRUCTIONS")


def test_the_committed_pack_is_encrypted_and_no_key_or_plain_pack_is_tracked():
    from tests.test_registry import tracked_files
    blob = (ROOT / "registry" / "agent-pack.enc").read_bytes()
    assert blob.startswith(PACK_MAGIC)
    for plain in (b"instructions:", b"persona:", b"merged_from", b"agents/"):
        assert plain not in blob
    files = tracked_files()
    assert not [f for f in files if f.endswith(".key") or (f.endswith(".zip") and "agent-pack" in f)]


def _bundle_module():
    spec = importlib.util.spec_from_file_location("bundle_agent_key", ROOT / "desktop" / "bundle_agent_key.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_step_writes_only_a_key_that_opens_the_pack(tmp_path, monkeypatch, capsys):
    mod = _bundle_module()
    monkeypatch.setattr(mod, "PACK", sealed(tmp_path))
    monkeypatch.setattr(mod, "TARGET", tmp_path / "agent-pack.key")
    monkeypatch.delenv("AGENT_PACK_KEY", raising=False)
    assert mod.main() == 0 and not (tmp_path / "agent-pack.key").exists()  # no secret: build goes on without it
    monkeypatch.setenv("AGENT_PACK_KEY", OTHER_KEY)
    assert mod.main() == 1 and not (tmp_path / "agent-pack.key").exists()  # wrong key fails the build
    monkeypatch.setenv("AGENT_PACK_KEY", KEY)
    assert mod.main() == 0 and (tmp_path / "agent-pack.key").read_text().strip() == KEY
    assert KEY not in capsys.readouterr().out
