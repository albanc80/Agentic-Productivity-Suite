"""Loads the compiled agent registry (registry/) and the authored output policies."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Persona(BaseModel):
    id: str
    text: str


class AgentMode(BaseModel):
    summary: str = ""
    instructions: str


class Agent(BaseModel):
    id: str
    name: str
    callsign: str
    desk: str
    summary: str
    default_tier: str = "specialist"
    safety_critical: bool = False
    persona: Persona | None = None
    core_skills: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    default_mode: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    instructions: str
    modes: dict[str, AgentMode] = Field(default_factory=dict)

    def instructions_for(self, mode: str | None) -> str:
        if mode and mode != self.default_mode:
            if mode not in self.modes:
                raise KeyError(f"agent {self.id} has no mode '{mode}'")
            return self.modes[mode].instructions
        return self.instructions

    def public(self) -> dict:
        d = self.model_dump(exclude={"instructions", "modes", "persona"})
        d["modes"] = {k: v.summary for k, v in self.modes.items()}
        d["persona"] = self.persona.id if self.persona else None
        d["instruction_chars"] = len(self.instructions)
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
    def __init__(self, registry_dir: Path, policies_dir: Path):
        self.dir = registry_dir
        self.policies_dir = policies_dir
        self.agents: dict[str, Agent] = {}
        for p in sorted((registry_dir / "agents").glob("*.yaml")):
            a = Agent.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
            self.agents[a.id] = a
        desks = yaml.safe_load((registry_dir / "desks.yaml").read_text(encoding="utf-8"))["desks"]
        self.desks = {d["id"]: Desk.model_validate(d) for d in desks}
        idx = yaml.safe_load((registry_dir / "skills" / "index.yaml").read_text(encoding="utf-8"))["skills"]
        self.skills = {s["id"]: Skill.model_validate(s) for s in idx}
        if not self.agents:
            raise RuntimeError(f"No agents found in {registry_dir}. Run scripts/ingest_agents.py first.")

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
