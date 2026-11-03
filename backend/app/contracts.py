"""The handoff contract every agent step speaks.

HandoffOut (orchestrator -> agent) follows the six-field handoff from the
Managerial OS agents. HandoffIn (agent -> orchestrator) merges the engineering
pod's structured handoff with the suite's status vocabulary.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


class Status(StrEnum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_ACCEPTED_RISK = "COMPLETE_WITH_ACCEPTED_RISK"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    NEEDS_INPUT = "NEEDS_INPUT"


# Worst first: used to roll step statuses up into a run outcome.
STATUS_SEVERITY = [
    Status.REJECTED, Status.BLOCKED, Status.NEEDS_INPUT, Status.PARTIAL,
    Status.COMPLETE_WITH_ACCEPTED_RISK, Status.COMPLETE,
]


def worst(statuses: list[Status]) -> Status:
    if not statuses:
        return Status.PARTIAL
    return min(statuses, key=STATUS_SEVERITY.index)


class Label(StrEnum):
    FACT = "FACT"
    ASSUMPTION = "ASSUMPTION"
    INFERENCE = "INFERENCE"


class Claim(BaseModel):
    text: str
    label: Label = Label.ASSUMPTION
    trace: str | None = None

    @field_validator("label", mode="before")
    @classmethod
    def _norm_label(cls, v):
        return str(v).strip().upper() if v else Label.ASSUMPTION


class Risk(BaseModel):
    risk: str
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    mitigation: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def _norm_sev(cls, v):
        v = str(v or "medium").strip().lower()
        return v if v in {"low", "medium", "high", "critical"} else "medium"


class NextAction(BaseModel):
    action: str = ""
    owner: str = "UNKNOWN"
    gate: str = ""


class HandoffIn(BaseModel):
    status: Status = Status.PARTIAL
    summary: str = ""
    deliverable: str = ""
    claims: list[Claim] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_action: NextAction = NextAction()
    skills_invoked: list[str] = Field(default_factory=list)
    evidence: Literal["EXECUTED", "NOT_EXECUTED"] = "NOT_EXECUTED"
    verdict: Literal["PASS", "PASS_WITH_CHANGES", "FAIL"] | None = None
    findings: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v):
        s = re.sub(r"[\s-]+", "_", str(v or "PARTIAL").strip().upper())
        aliases = {"DONE": "COMPLETE", "SUCCESS": "COMPLETE", "NEEDS_REVIEW": "PARTIAL", "FAILED": "BLOCKED",
                   "READY_FOR_HUMAN_APPROVAL": "COMPLETE"}
        s = aliases.get(s, s)
        return s if s in Status.__members__ else "PARTIAL"

    @field_validator("verdict", mode="before")
    @classmethod
    def _norm_verdict(cls, v):
        if v is None or v == "":
            return None
        s = re.sub(r"[\s-]+", "_", str(v).strip().upper())
        return s if s in {"PASS", "PASS_WITH_CHANGES", "FAIL"} else None

    @field_validator("evidence", mode="before")
    @classmethod
    def _norm_evidence(cls, v):
        return "EXECUTED" if str(v or "").strip().upper() == "EXECUTED" else "NOT_EXECUTED"

    @field_validator("open_questions", "findings", "skills_invoked", mode="before")
    @classmethod
    def _listify(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [x if isinstance(x, str) else json.dumps(x) for x in v]

    @field_validator("claims", "risks", mode="before")
    @classmethod
    def _drop_bad_items(cls, v):
        if not isinstance(v, list):
            return []
        out = []
        for item in v:
            if isinstance(item, str):
                out.append({"text": item} if item else None)
            elif isinstance(item, dict):
                out.append(item)
        return [x for x in out if x]

    @field_validator("next_action", mode="before")
    @classmethod
    def _norm_next(cls, v):
        if isinstance(v, str):
            return {"action": v}
        return v or {}


class PriorFact(BaseModel):
    fact: str
    trace: str


class HandoffOut(BaseModel):
    request: str
    scope: str = "UNKNOWN"
    window: str = "UNKNOWN"
    constraints: str = "NONE"
    prior_context: list[PriorFact] = Field(default_factory=list)
    approval_state: Literal["NOT_APPROVED"] = "NOT_APPROVED"


CONTRACT_INSTRUCTIONS = """\
## Response format (required)

Write your deliverable in Markdown first. Then end your reply with exactly one fenced JSON block
labelled `json` that follows this schema. Do not put anything after the JSON block.

```json
{
  "status": "COMPLETE | COMPLETE_WITH_ACCEPTED_RISK | PARTIAL | BLOCKED | REJECTED | NEEDS_INPUT",
  "summary": "one or two sentences: the answer or recommendation",
  "claims": [{"text": "a material claim", "label": "FACT | ASSUMPTION | INFERENCE", "trace": "source id, input name, ticket, message or step id; null if none"}],
  "risks": [{"risk": "...", "severity": "low | medium | high | critical", "mitigation": "..."}],
  "open_questions": ["only questions whose answer would change the outcome"],
  "next_action": {"action": "...", "owner": "role or UNKNOWN", "gate": "approval needed, if any"},
  "skills_invoked": ["skill ids you applied"],
  "evidence": "EXECUTED only if you ran a tool and saw its result, otherwise NOT_EXECUTED",
  "verdict": "PASS | PASS_WITH_CHANGES | FAIL (review steps only, otherwise null)",
  "findings": ["review steps only: the issues that matter most, most severe first"]
}
```

Rules: label a claim FACT only when it has a trace to provided data, a tool result or a prior step.
Use NEEDS_INPUT when a missing input would change the decision, and say which input in open_questions.
"""

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*\n(\{.*?\})\s*\n```", re.S)


def _loose_json(blob: str) -> dict | None:
    try:
        v = json.loads(blob)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        pass
    # Tolerate trailing commas and smart quotes from smaller local models.
    fixed = re.sub(r",\s*([}\]])", r"\1", blob).replace("“", '"').replace("”", '"')
    try:
        v = json.loads(fixed)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None


def parse_handoff(text: str) -> tuple[HandoffIn | None, str]:
    """Split a model reply into (contract, deliverable markdown).

    Returns ``(None, text)`` when no valid contract block is found.
    """
    text = strip_reasoning(text)
    matches = list(_FENCE_RE.finditer(text))
    for m in reversed(matches):
        data = _loose_json(m.group(1))
        if data is None:
            continue
        deliverable = (text[: m.start()] + text[m.end():]).strip()
        data.pop("deliverable", None)
        try:
            h = HandoffIn.model_validate(data)
        except ValidationError:
            continue
        h.deliverable = deliverable
        return h, deliverable
    # Bare JSON object at the end without a fence.
    tail = text.rfind("\n{")
    if tail != -1:
        data = _loose_json(text[tail + 1:].strip())
        if data and "status" in data:
            try:
                h = HandoffIn.model_validate(data)
                h.deliverable = text[:tail].strip()
                return h, h.deliverable
            except ValidationError:
                pass
    return None, text.strip()


_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_reasoning(text: str) -> str:
    """Remove inline reasoning blocks some local reasoning models emit."""
    return _THINK_RE.sub("", text or "").strip()
