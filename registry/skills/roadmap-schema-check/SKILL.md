---
name: roadmap-schema-check
description: Reports whether roadmap data has the fields required to simulate. Call after reading the roadmap, before any calculation.
---

# Skill 07 — Roadmap Schema Check

**Type:** AI Builder prompt
**Attached to:** Roadmap Shield
**Version:** 1.0

## Purpose

Read the roadmap file and report which required fields are missing or empty,
**before** the simulation runs. Turns "missing effort estimates" from something
the agent might notice into something it always knows.

## Inputs

| Name | Type | Source |
|---|---|---|
| `roadmap_data` | Text | `GetRoadmap` output — headers plus rows |
| `affected_scope` | Text | Milestones the pending request touches, or `ALL` |

## Required schema

| Column | Required for | Blocking if missing |
|---|---|---|
| `milestone_id` | Row identity, traceability | Yes |
| `milestone_name` | Output readability | No |
| `planned_start` | Date-shift math | Yes |
| `planned_end` | Date-shift math | Yes |
| `effort_hours` | Capacity math | Yes |
| `capacity_hours_per_week` | Capacity math | Yes |
| `depends_on` | Cascade propagation | No — absence limits results to first-order impact |
| `owner_team` | Contention detection | No |
| `externally_committed` | Customer-safe dating | No |

`capacity_hours_per_week` is the field most likely to be absent — this check
tells you on day one whether your roadmap file can support the simulation at all.

## Instruction

```
Inspect this roadmap data against the required schema and report readiness.
Do not simulate anything. Do not compute dates. Report structure only.

ROADMAP DATA
{roadmap_data}

SCOPE UNDER TEST: {affected_scope}

REQUIRED COLUMNS
milestone_id (blocking), planned_start (blocking), planned_end (blocking),
effort_hours (blocking), capacity_hours_per_week (blocking),
milestone_name, depends_on, owner_team, externally_committed

TASK
1. List required columns absent from the header row entirely.
2. For present columns, list rows in scope where the value is empty, zero where
   zero is implausible, or unparseable as its expected type.
3. Report dependency integrity: any depends_on value referencing a
   milestone_id that does not exist in the file.
4. Report circular dependencies if any chain returns to its origin.
5. Report date coherence: any row where planned_end precedes planned_start.
6. Report staleness: the most recent modification date present in the data, if
   the file carries one.

READINESS
- READY            — no blocking column missing, no blocking cell empty in scope
- DEGRADED         — all blocking fields present, but non-blocking gaps exist
                     (state precisely what the simulation will not be able to do)
- NOT_SIMULATABLE  — any blocking column or in-scope blocking cell is missing

Never infer, default, or fill a missing value. Report absence as absence. A
fabricated input produces a fabricated date, and dates get committed.
```

## Output contract (JSON)

```json
{
  "readiness": "READY | DEGRADED | NOT_SIMULATABLE",
  "missing_columns": ["string"],
  "empty_cells": [ { "milestone_id": "string", "column": "string" } ],
  "broken_dependencies": [ { "milestone_id": "string", "references": "string" } ],
  "circular_dependencies": [["milestone_id", "milestone_id"]],
  "date_incoherence": [ { "milestone_id": "string", "issue": "string" } ],
  "capability_loss": ["string"],
  "last_modified": "ISO date | null"
}
```

## Wiring

In Roadmap Shield, insert between step 1 and step 2:

> After reading the roadmap and before running the simulation, run Roadmap Schema
> Check. If `readiness` is NOT_SIMULATABLE, return `STATUS: NEEDS_INPUT` naming
> the exact missing columns or rows — do not simulate on partial data. If
> DEGRADED, proceed but copy every entry in `capability_loss` into GAPS so the
> manager knows what the card does not cover.

## Test cases

| # | Input | Pass condition |
|---|---|---|
| 1 | No `capacity_hours_per_week` column | `NOT_SIMULATABLE`, column named |
| 2 | Column present, empty for two in-scope rows | `NOT_SIMULATABLE`, both rows listed |
| 3 | No `depends_on` column | `DEGRADED`; capability_loss states cascade impact unavailable |
| 4 | `depends_on` pointing at a deleted milestone | Listed in `broken_dependencies` |
| 5 | A→B→C→A chain | Reported in `circular_dependencies` |
| 6 | `planned_end` before `planned_start` | Reported in `date_incoherence` |
| 7 | Complete file | `READY`, all lists empty |
