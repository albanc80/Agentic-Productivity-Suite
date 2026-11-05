"""Playbook schema, loading and validation.

A playbook is a fixed sequence of steps. Step kinds:
  agent      one specialist call (optionally with read-only connector tools)
  parallel   several agent steps at once
  review     an independent agent checks an earlier step (never its own author)
  gate       pause for a named human decision
  tool       a deterministic tool (calculator, evidence validator)
  connector  one read-only MCP tool call whose result becomes data for later steps
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from .registry import Registry


class PlaybookInput(BaseModel):
    id: str
    label: str
    type: Literal["text", "longtext", "number", "select", "multiselect", "documents", "date"] = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    default: Any = None
    help: str = ""
    example: str = ""  # shown as placeholder; never submitted
    untrusted: bool | None = None  # defaults: longtext and documents are untrusted data

    @property
    def is_data(self) -> bool:
        return self.untrusted if self.untrusted is not None else self.type in ("longtext", "documents")


class When(BaseModel):
    input: str
    equals: Any = None
    contains: Any = None
    not_equals: Any = None

    def holds(self, inputs: dict) -> bool:
        v = inputs.get(self.input)
        if self.equals is not None:
            return v == self.equals
        if self.not_equals is not None:
            return v != self.not_equals
        if self.contains is not None:
            return isinstance(v, list | str) and self.contains in v
        return bool(v)


class Step(BaseModel):
    id: str
    kind: Literal["agent", "parallel", "review", "gate", "tool", "connector"]
    title: str = ""
    when: When | None = None
    # agent / review
    agent: str | None = None
    mode: str | None = None
    task: str = ""
    context_from: list[str] | None = None
    tier: str | None = None
    models: list[str] | None = None
    skills: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    # parallel
    steps: list[Step] = Field(default_factory=list)
    # review
    target: str | None = None
    on_fail: Literal["continue", "revise"] = "continue"
    # gate
    instructions: str = ""
    required_role: str | None = None
    payload_from: str | None = None
    # tool / connector
    tool: str | None = None
    connector: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    args_from_input: str | None = None  # tool step: JSON object input used as arguments
    optional: bool = True

    @model_validator(mode="after")
    def _shape(self) -> Step:
        need = {"agent": ["agent", "task"], "review": ["agent", "target"], "tool": ["tool"],
                "connector": ["connector", "tool"], "parallel": ["steps"], "gate": ["title"]}
        for f in need.get(self.kind, []):
            if not getattr(self, f):
                raise ValueError(f"step '{self.id}' ({self.kind}) needs '{f}'")
        return self


class Playbook(BaseModel):
    id: str
    code: str
    name: str
    area: str
    desk: str
    summary: str
    status: Literal["mvp", "next", "later"] = "mvp"
    style: Literal["chat", "document"] = "document"
    patterns: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    safety_critical: bool = False
    inputs: list[PlaybookInput]
    steps: list[Step]
    deliverable: str

    def input(self, iid: str) -> PlaybookInput | None:
        return next((i for i in self.inputs if i.id == iid), None)

    def flat_steps(self) -> list[Step]:
        out: list[Step] = []
        for s in self.steps:
            out.append(s)
            out.extend(s.steps)
        return out

    def step(self, sid: str) -> Step:
        for s in self.flat_steps():
            if s.id == sid:
                return s
        raise KeyError(sid)

    def card(self) -> dict:
        return {
            "id": self.id, "code": self.code, "name": self.name, "area": self.area, "desk": self.desk,
            "summary": self.summary, "status": self.status, "style": self.style, "patterns": self.patterns,
            "safety_critical": self.safety_critical, "inputs": [i.model_dump() for i in self.inputs],
            "steps": [{"id": s.id, "kind": s.kind, "title": s.title or s.id, "agent": s.agent,
                       "children": [{"id": c.id, "agent": c.agent, "title": c.title or c.id} for c in s.steps]}
                      for s in self.steps],
            "connectors": sorted({c for s in self.flat_steps() for c in s.connectors} |
                                 {s.connector for s in self.flat_steps() if s.connector}),
        }


class PlaybookError(Exception):
    pass


def validate(pb: Playbook, registry: Registry, connector_ids: set[str] | None = None) -> list[str]:
    """Raise on structural errors. Returns non-fatal warnings."""
    from .tools import TOOLS

    warnings: list[str] = []
    seen: list[str] = []
    authors: dict[str, str] = {}
    for top in pb.steps:
        group = top.steps if top.kind == "parallel" else [top]
        group_ids = []
        for s in group:
            if s.id in seen or s.id in group_ids:
                raise PlaybookError(f"{pb.id}: duplicate step id '{s.id}'")
            if s.kind == "parallel":
                raise PlaybookError(f"{pb.id}: nested parallel step '{s.id}'")
            if s.kind in ("agent", "review"):
                agent = registry.agents.get(s.agent or "")
                if not agent:
                    raise PlaybookError(f"{pb.id}: step '{s.id}' uses unknown agent '{s.agent}'")
                if s.mode and s.mode != agent.default_mode and s.mode not in agent.modes:
                    raise PlaybookError(f"{pb.id}: agent '{s.agent}' has no mode '{s.mode}'")
                for sk in s.skills:
                    if sk not in registry.skills:
                        raise PlaybookError(f"{pb.id}: step '{s.id}' uses unknown skill '{sk}'")
                for t in s.tools:
                    if t not in TOOLS:
                        raise PlaybookError(f"{pb.id}: step '{s.id}' uses unknown tool '{t}'")
                for ref in s.context_from or []:
                    if ref not in seen:
                        raise PlaybookError(f"{pb.id}: step '{s.id}' reads '{ref}' before it runs")
                if connector_ids is not None:
                    for c in s.connectors:
                        if c not in connector_ids:
                            warnings.append(f"{pb.id}: step '{s.id}' lists connector '{c}' that is not defined")
            if s.kind == "agent":
                authors[s.id] = s.agent or ""
            if s.kind == "review":
                if s.target not in seen:
                    raise PlaybookError(f"{pb.id}: review '{s.id}' targets '{s.target}' which has not run yet")
                if authors.get(s.target or "") == s.agent:
                    raise PlaybookError(f"{pb.id}: review '{s.id}' would let '{s.agent}' review its own work")
                if s.on_fail == "revise" and s.target not in authors:
                    raise PlaybookError(f"{pb.id}: review '{s.id}' can only revise an agent step")
            if s.kind == "tool" and s.tool not in TOOLS:
                raise PlaybookError(f"{pb.id}: unknown tool '{s.tool}'")
            if s.args_from_input and not pb.input(s.args_from_input):
                raise PlaybookError(f"{pb.id}: step '{s.id}' reads arguments from unknown input '{s.args_from_input}'")
            if s.kind == "gate" and s.payload_from and s.payload_from not in seen:
                raise PlaybookError(f"{pb.id}: gate '{s.id}' payload '{s.payload_from}' has not run yet")
            if s.when and not pb.input(s.when.input):
                raise PlaybookError(f"{pb.id}: step '{s.id}' condition uses unknown input '{s.when.input}'")
            group_ids.append(s.id)
        seen.extend(group_ids)
        if top.kind == "parallel":
            seen.append(top.id)
    if pb.deliverable not in seen:
        raise PlaybookError(f"{pb.id}: deliverable step '{pb.deliverable}' does not exist")
    if pb.safety_critical and not any(s.kind == "gate" for s in pb.steps):
        raise PlaybookError(f"{pb.id}: safety-critical playbooks need a human gate")
    return warnings


def load_playbooks(directory: Path, registry: Registry, connector_ids: set[str] | None = None,
                   aliases: dict[str, str] | None = None) -> tuple[dict[str, Playbook], list[str]]:
    """``aliases`` maps connector ids that were merged (databricks-genie) to the connector that replaced them."""
    books: dict[str, Playbook] = {}
    warnings: list[str] = []
    for p in sorted(directory.glob("*.yaml")):
        pb = Playbook.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))
        for s in pb.flat_steps():
            if aliases and s.connectors:
                s.connectors = list(dict.fromkeys(aliases.get(c, c) for c in s.connectors))
        if pb.id in books:
            raise PlaybookError(f"duplicate playbook id '{pb.id}' in {p.name}")
        warnings += validate(pb, registry, connector_ids)
        books[pb.id] = pb
    return books, warnings


# ------------------------------------------------------------------ templating

_TPL = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def render(template: str, ctx: dict[str, Any]) -> str:
    def sub(m: re.Match) -> str:
        cur: Any = ctx
        for part in m.group(1).split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                return "UNKNOWN"
        if isinstance(cur, list):
            return ", ".join(map(str, cur)) or "NONE"
        return str(cur) if cur != "" else "UNKNOWN"
    return _TPL.sub(sub, template)


def render_args(args: Any, ctx: dict[str, Any], outputs: dict[str, dict]) -> Any:
    if isinstance(args, str):
        return render(args, ctx)
    if isinstance(args, list):
        return [render_args(a, ctx, outputs) for a in args]
    if isinstance(args, dict):
        if set(args) == {"from_step"}:
            return outputs.get(args["from_step"], {}).get("handoff") or {}
        if set(args) == {"from_input"}:
            return ctx["inputs"].get(args["from_input"])
        return {k: render_args(v, ctx, outputs) for k, v in args.items()}
    return args


def resolve_window(text: str | None, today: date) -> str:
    """Turn relative windows ('today', 'last week') into explicit dates."""
    if not text:
        return "UNKNOWN"
    t = text.strip().lower()
    monday = today - timedelta(days=today.weekday())
    table = {
        "today": (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "tomorrow": (today + timedelta(days=1), today + timedelta(days=1)),
        "this week": (monday, monday + timedelta(days=6)),
        "last week": (monday - timedelta(days=7), monday - timedelta(days=1)),
        "next week": (monday + timedelta(days=7), monday + timedelta(days=13)),
        "this month": (today.replace(day=1), today),
        "last 7 days": (today - timedelta(days=7), today),
        "last 14 days": (today - timedelta(days=14), today),
        "last 30 days": (today - timedelta(days=30), today),
    }
    if t in table:
        a, b = table[t]
        return f"{a.isoformat()} to {b.isoformat()} ({text.strip()})"
    return text.strip()
