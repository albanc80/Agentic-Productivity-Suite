---
name: narrative-synthesis-tech
description: Produces the technical-lead version of a status update, focused on blockers and dependencies. Call once per status request, after both fetches complete.
---

# Skill 02 — Narrative Synthesis: TECH

**Type:** AI Builder prompt
**Attached to:** Zero-Status
**Version:** 1.0

## Purpose

Rewrite raw work items and communications as a technical update oriented to
blockers and deployment hurdles.

## Inputs

| Name | Type | Source |
|---|---|---|
| `work_items` | Text | `GetWorkItems` output |
| `comms` | Text | `GetProjectComms` output |
| `project` | Text | SCOPE from the handoff |
| `window` | Text | WINDOW_USED — explicit dates |

## Instruction

```
You are producing a status update for a technical lead.

INPUT
Project: {project}
Window: {window}
Work items:
{work_items}
Communications:
{comms}

TASK
Report blockers and deployment hurdles. Completed work is secondary — one
grouped line is sufficient unless a completion unblocks something.

RULES
- Every blocker must carry its ticket ID and name the specific dependency
  holding it: a system, an environment, an approval, or another ticket. If the
  input does not identify the dependency, write `dependency: "UNIDENTIFIED"` —
  never infer a plausible one.
- Order blockers by how long they have been blocked, longest first. If the input
  does not carry a blocked-since timestamp, put those items last and mark
  `blocked_since: null`.
- Do not translate technical detail into business language. This audience wants
  the specifics.
- Do not characterize any person's work, speed, or reliability. Report the item
  and its state, never who is behind on it.
- An item in work_items with no supporting message in comms, or the reverse, is
  marked `unconfirmed: true`.
- If both inputs are empty, return `status: "NO_DATA"`.
- Never propose a fix or assign an owner. Report state only.
```

## Output contract (JSON)

```json
{
  "status": "COMPLETE | PARTIAL | NO_DATA",
  "blockers": [
    {
      "ticket_id": "string",
      "summary": "string",
      "dependency": "string | UNIDENTIFIED",
      "blocked_since": "ISO date | null",
      "unconfirmed": false,
      "trace": ["ticket ID or sender+timestamp"]
    }
  ],
  "in_progress": [ { "ticket_id": "string", "summary": "string" } ],
  "completed_summary": "string",
  "omitted": [ { "item": "string", "reason": "string" } ]
}
```

## Test cases

| # | Input | Pass condition |
|---|---|---|
| 1 | Blocker with no stated cause | `dependency: "UNIDENTIFIED"`, no invented cause |
| 2 | Three blockers, varied ages | Ordered longest-blocked first |
| 3 | Comms mention frustration with a named person | Person not characterized; only the item's state reported |
| 4 | Only completed items | `blockers: []`, completions grouped in one line |
| 5 | Zero activity | `status: NO_DATA` |
