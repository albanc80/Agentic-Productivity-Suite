"""The public catalog is complete, consistent and platform-neutral; the private layer loads on top."""

import base64
import re
import subprocess

import pytest

from app.registry import Registry
from tests.conftest import PRIVATE_FIXTURE, ROOT

# Vendor company, product and business-line names that must never appear anywhere in the suite.
# Stored encoded so that the deny list itself does not put those names into the repository.
BRAND_TERMS = base64.b64decode(
    "aGFsbGlidXJ0b24sbGFuZG1hcmssd2VsbHBsYW4sZGVjaXNpb25zcGFjZSxzcGVycnksYmFyb2lk"
).decode().split(",")
BRAND = re.compile("|".join(BRAND_TERMS), re.I)
FORBIDDEN = re.compile(rf"(copilot|{BRAND.pattern}|alberto|\bbeto\b|sharepoint|onedrive|work ?iq|dataverse)", re.I)
POLICIES = ROOT / "config" / "policies"


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [f.decode() for f in out.split(b"\0") if f]


def test_registry_is_platform_neutral():
    hits = []
    for p in (ROOT / "registry").rglob("*"):
        if p.is_file() and p.suffix in (".md", ".yaml"):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line) and not line.startswith("#"):
                    hits.append(f"{p.relative_to(ROOT)}:{n}")
    assert hits == [], hits[:10]


def test_no_vendor_brand_anywhere():
    """No vendor company, product or business-line name in any tracked file of any component."""
    hits = [f for f in tracked_files() if (ROOT / f).is_file() and BRAND.search((ROOT / f).read_bytes().decode("latin-1"))]
    assert hits == [], hits


def test_private_agent_layer_is_never_committed():
    """Instructions, personas and lineage live outside the repository (fixtures excepted)."""
    files = [f for f in tracked_files() if not f.startswith("backend/tests/fixtures/")]
    assert not [f for f in files if f.startswith(("private-registry/", "registry/agents/"))]
    assert "registry/INGEST_REPORT.md" not in files and "scripts/ingest_agents.py" not in files
    catalog = (ROOT / "registry" / "catalog.yaml").read_text(encoding="utf-8")
    for key in ("instructions:", "persona:", "merged_from:", "source:", "callsign:"):
        assert key not in catalog, key


def test_catalog_consistency():
    reg = Registry(ROOT / "registry", POLICIES)
    assert len(reg.agents) == 34
    for d in reg.desks.values():
        assert d.lead in d.members and all(m in reg.agents for m in d.members)
    for a in reg.agents.values():
        assert 3 <= len(a.capabilities) <= 6, a.id
        assert all(isinstance(c, str) and c.strip() and len(c) <= 120 for c in a.capabilities), a.id
        for s in a.core_skills + a.skills:
            assert reg.skill_text(s).startswith("---"), (a.id, s)
    for pid in ("plain-voice", "action-first"):
        assert reg.policy_text(pid)


def test_without_private_layer_agents_run_on_their_public_card(tmp_path):
    reg = Registry(ROOT / "registry", POLICIES, tmp_path / "missing")
    assert any("Private agent layer not found" in w for w in reg.warnings)
    wp = reg.agent("well-planner")
    text = wp.instructions_for(None)
    assert wp.name in text and all(c in text for c in wp.capabilities) and "advisory only" in text
    assert "investment" in reg.agent("enterprise-architect").instructions_for("investment").lower()
    assert reg.agent("chief-of-staff").persona is None


def test_private_layer_overlays_the_catalog():
    reg = Registry(ROOT / "registry", POLICIES, PRIVATE_FIXTURE)
    cos = reg.agent("chief-of-staff")
    assert cos.instructions_for(None).startswith("FIXTURE INSTRUCTIONS")
    assert cos.instructions_for("daily").startswith("FIXTURE DAILY MODE")
    assert cos.persona.id == "fixture-voice" and "FIXTURE PERSONA" not in cos.instructions  # persona lives in its own layer
    assert cos.merged_from == ["fixture-a", "fixture-b"]
    assert "unknown-agent" not in reg.agents and any("unknown-agent.yaml" in w for w in reg.warnings)
    assert any("run on their public capability summary" in w for w in reg.warnings)  # the other 33
    with pytest.raises(KeyError):
        cos.instructions_for("nope")


def test_skill_resource_path_is_confined():
    reg = Registry(ROOT / "registry", POLICIES)
    with pytest.raises(PermissionError):
        reg.skill_text("ai-agent-engineer", "../../desks.yaml")
