"""Guardrails that do not depend on a model behaving well.

* Injection screening of untrusted content (pasted text, files, connector results).
  Content is never blocked for matching; it is wrapped as data and the match is
  surfaced in the run, so the user sees what tried to give instructions.
* People-evaluation screening of deliverables (the suite reports work, not people).
* Secret redaction for anything written to logs or the audit trail.
"""

from __future__ import annotations

import html
import re

INJECTION_PATTERNS = [
    (r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|all|any)\b.{0,20}\b(instructions?|rules|prompts?)\b", "override instructions"),
    (r"\byou are now\b|\bfrom now on you\b|\bnew (system )?instructions?\s*:", "role reassignment"),
    (r"\b(reveal|print|show|repeat)\b.{0,30}\b(system prompt|your instructions|hidden instructions|api key|secret)", "prompt or secret extraction"),
    (r"</?\s*(system|assistant|instructions?)\s*>|\[/?(system|inst)\]|BEGIN SYSTEM", "fake role markers"),
    (r"\b(send|email|forward|post|upload|share)\b.{0,60}\b(to|with)\b.{0,40}(@|https?://)", "exfiltration request"),
    (r"approval_state\s*[:=]\s*\"?approved", "approval forgery"),
    (r"\b(do not|don't|never)\b.{0,30}\b(tell|inform|show)\b.{0,20}\b(the )?user\b", "concealment request"),
]
_INJ = [(re.compile(p, re.I | re.S), label) for p, label in INJECTION_PATTERNS]

PEOPLE_EVAL = re.compile(
    r"\b(lazy|incompetent|underperform\w*|low performer|poor performer|bad attitude|not a team player|"
    r"unprofessional|difficult person|toxic|should be (fired|replaced|let go)|lacks? (skill|competence|commitment))\b",
    re.I,
)

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"dapi[0-9a-f]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)((api[_-]?key|token|password|secret)\s*[:=]\s*)[\"']?[^\s\"']{8,}"),
]


def scan_injection(text: str) -> list[str]:
    found = []
    for rx, label in _INJ:
        m = rx.search(text or "")
        if m:
            found.append(f"{label}: \"{m.group(0)[:80]}\"")
    return found


def scan_people_eval(text: str) -> list[str]:
    return sorted({m.group(0) for m in PEOPLE_EVAL.finditer(text or "")})


def redact(text: str) -> str:
    out = text or ""
    for rx in SECRET_PATTERNS:
        if rx.groups:
            out = rx.sub(lambda m: m.group(1) + "[REDACTED]", out)
        else:
            out = rx.sub("[REDACTED]", out)
    return out


def wrap_data(source: str, content: str, max_chars: int | None = None) -> tuple[str, list[str], bool]:
    """Wrap untrusted content in a data envelope. Returns (block, injection_flags, truncated)."""
    flags = scan_injection(content)
    truncated = False
    if max_chars and len(content) > max_chars:
        content = content[:max_chars]
        truncated = True
    # Neutralise attempts to close the envelope early.
    safe = content.replace("</data>", "&lt;/data&gt;")
    attr = html.escape(source, quote=True)
    note = ' truncated="true"' if truncated else ""
    return f'<data source="{attr}" trust="untrusted"{note}>\n{safe}\n</data>', flags, truncated
