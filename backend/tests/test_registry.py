"""The committed registry is complete, consistent and platform-neutral."""

import re
import subprocess
import sys

from app.registry import Registry
from tests.conftest import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
from ingest_agents import BRAND_RE  # noqa: E402  (one encoded deny list, shared with the ingest)

FORBIDDEN = re.compile(rf"(copilot|{BRAND_RE}|alberto|\bbeto\b|sharepoint|onedrive|work ?iq|dataverse)", re.I)
BRAND = re.compile(BRAND_RE, re.I)


def test_registry_is_platform_neutral():
    hits = []
    for p in (ROOT / "registry").rglob("*"):
        if p.is_file() and p.suffix in (".md", ".yaml") and p.name != "INGEST_REPORT.md":
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line) and not line.startswith("#"):
                    hits.append(f"{p.relative_to(ROOT)}:{n}")
    assert hits == [], hits[:10]


def test_no_vendor_brand_anywhere():
    """No vendor company, product or business-line name in any tracked file of any component."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    hits = []
    for rel in filter(None, files):
        p = ROOT / rel.decode()
        if not p.is_file():
            continue
        data = p.read_bytes()
        if BRAND.search(data.decode("latin-1")):
            hits.append(rel.decode())
    assert hits == [], hits


def test_every_agent_has_a_capability_summary():
    reg = Registry(ROOT / "registry", ROOT / "config" / "policies")
    for a in reg.agents.values():
        assert 3 <= len(a.capabilities) <= 6, a.id
        assert all(isinstance(c, str) and c.strip() and len(c) <= 120 for c in a.capabilities), a.id


def test_registry_consistency():
    reg = Registry(ROOT / "registry", ROOT / "config" / "policies")
    assert len(reg.agents) == 34
    for d in reg.desks.values():
        assert d.lead in d.members and all(m in reg.agents for m in d.members)
    for a in reg.agents.values():
        assert a.instructions.strip(), a.id
        for s in a.core_skills + a.skills:
            assert reg.skill_text(s).startswith("---"), (a.id, s)
        for m in a.modes.values():
            assert m.instructions.strip()
    assert reg.agent("chief-of-staff").persona.id == "persona_x"
    assert "persona_x" not in reg.agent("chief-of-staff").instructions  # persona lives in its own layer
    for pid in ("plain-voice", "action-first"):
        assert reg.policy_text(pid)


def test_skill_resource_path_is_confined():
    reg = Registry(ROOT / "registry", ROOT / "config" / "policies")
    import pytest
    with pytest.raises(PermissionError):
        reg.skill_text("ai-agent-engineer", "../../agents/chief-of-staff.yaml")
