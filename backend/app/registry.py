"""Loads the compiled agent registry (registry/) and the authored output policies."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field


class Persona(BaseModel):
    id: str
    text: str


class AgentMode(BaseModel):
    summary: str = ""
    instructions: str = ""


class Agent(BaseModel):
    """Public card (registry/catalog.yaml) merged with the private layer when it is present."""

    id: str
    name: str
    callsign: str
    desk: str
    summary: str
    capabilities: list[str] = Field(default_factory=list)
    default_tier: str = "specialist"
    safety_critical: bool = False
    core_skills: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    default_mode: str | None = None
    modes: dict[str, AgentMode] = Field(default_factory=dict)
    # Private layer, never committed or sent to the UI.
    persona: Persona | None = None
    merged_from: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    instructions: str = ""

    # Never sent to the UI: the instructions, the persona and where the agent came from
    # (source files and the agents it was merged from) are the suite's own design.
    PRIVATE: ClassVar[frozenset[str]] = frozenset({"instructions", "modes", "persona", "merged_from", "source"})

    @property
    def has_private(self) -> bool:
        return bool(self.instructions.strip())

    def instructions_for(self, mode: str | None) -> str:
        if mode and mode != self.default_mode:
            if mode not in self.modes:
                raise KeyError(f"agent {self.id} has no mode '{mode}'")
            return self.modes[mode].instructions or self.fallback_instructions(mode)
        return self.instructions or self.fallback_instructions(None)

    def fallback_instructions(self, mode: str | None) -> str:
        """Used when the private layer is not installed: the agent works from its public card."""
        lines = [f"You are the {self.name}. {self.summary}", "", "What you do:"]
        lines += [f"- {c}" for c in self.capabilities]
        if mode and mode in self.modes:
            lines += ["", f"Current mode: {mode}. {self.modes[mode].summary}"]
        lines += ["", "Stay inside this remit and say when a request is outside it. Separate facts from "
                      "assumptions, state every assumption, and never invent data, sources or results."]
        if self.safety_critical:
            lines += ["You are advisory only. Never override validated engineering or safety rules; "
                      "a qualified person makes and owns the decision."]
        return "\n".join(lines) + "\n"

    def public(self) -> dict:
        """What the UI may show: identity, capability summary, skills, tools and mode summaries."""
        d = self.model_dump(exclude=set(self.PRIVATE))
        d["modes"] = {k: v.summary for k, v in self.modes.items()}
        return d


class Desk(BaseModel):
    id: str
    name: str
    lead: str
    summary: str
    members: list[str]


class Skill(BaseModel):
    id: str
    description: str
    chars: int
    resources: list[str] = Field(default_factory=list)


class Registry:
    """Agents, desks and skills.

    The repository holds only the public catalog (``registry/catalog.yaml``). Each agent's full
    instructions, persona, mode instructions and lineage live in a private directory outside the
    repository (``<private>/agents/<agent-id>.yaml``) and are merged in at load time.
    """

    def __init__(self, registry_dir: Path, policies_dir: Path, private_dir: Path | None = None):
        self.dir = registry_dir
        self.policies_dir = policies_dir
        self.private_dir = private_dir
        self.warnings: list[str] = []
        self.agents: dict[str, Agent] = {}
        catalog = yaml.safe_load((registry_dir / "catalog.yaml").read_text(encoding="utf-8"))["agents"]
        for card in catalog:
            card = dict(card)
            card["modes"] = {k: {"summary": v} for k, v in (card.get("modes") or {}).items()}
            a = Agent.model_validate(card)
            self.agents[a.id] = a
        desks = yaml.safe_load((registry_dir / "desks.yaml").read_text(encoding="utf-8"))["desks"]
        self.desks = {d["id"]: Desk.model_validate(d) for d in desks}
        idx = yaml.safe_load((registry_dir / "skills" / "index.yaml").read_text(encoding="utf-8"))["skills"]
        self.skills = {s["id"]: Skill.model_validate(s) for s in idx}
        if not self.agents:
            raise RuntimeError(f"No agents found in {registry_dir / 'catalog.yaml'}.")
        self._load_private()

    def _load_private(self) -> None:
        d = self.private_dir / "agents" if self.private_dir else None
        if not d or not d.is_dir():
            self.warnings.append("Private agent layer not found: agents run on their public capability summary. "
                                 "Set SUITE_PRIVATE_REGISTRY (or private_registry in suite.yaml) to its folder.")
            return
        for p in sorted(d.glob("*.yaml")):
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            a = self.agents.get(raw.get("id", ""))
            if not a:
                self.warnings.append(f"Private agent file {p.name} matches no agent in the catalog; ignored.")
                continue
            a.instructions = raw.get("instructions") or ""
            a.persona = Persona.model_validate(raw["persona"]) if raw.get("persona") else None
            a.merged_from = list(raw.get("merged_from") or [])
            a.source = list(raw.get("source") or [])
            for mname, text in (raw.get("modes") or {}).items():
                if mname in a.modes:
                    a.modes[mname].instructions = text or ""
                else:
                    self.warnings.append(f"Private agent file {p.name} has mode '{mname}', which the catalog does not list; ignored.")
        missing = [a.id for a in self.agents.values() if not a.has_private]
        if missing:
            self.warnings.append(f"{len(missing)} agent(s) have no private instructions and run on their public "
                                 f"capability summary: {', '.join(missing)}.")

    def agent(self, agent_id: str) -> Agent:
        if agent_id not in self.agents:
            raise KeyError(f"unknown agent '{agent_id}'")
        return self.agents[agent_id]

    def skill_text(self, skill_id: str, resource: str | None = None) -> str:
        """Read a skill or one of its resources. Paths are confined to the skill folder."""
        if skill_id not in self.skills:
            raise KeyError(f"unknown skill '{skill_id}'")
        base = (self.dir / "skills" / skill_id).resolve()
        target = (base / (resource or "SKILL.md")).resolve()
        if base not in target.parents and target != base / "SKILL.md":
            raise PermissionError("resource path escapes the skill folder")
        if not target.exists():
            raise KeyError(f"skill '{skill_id}' has no resource '{resource}'")
        return target.read_text(encoding="utf-8")

    def policy_text(self, policy_id: str) -> str:
        p = self.policies_dir / f"{policy_id}.md"
        if not p.exists():
            raise KeyError(f"unknown output policy '{policy_id}'")
        return p.read_text(encoding="utf-8").strip()
