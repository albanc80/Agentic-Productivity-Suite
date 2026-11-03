---
name: impact-calculation
description: Computes date shifts and capacity math for a new request. The only permitted source of roadmap arithmetic.
---

# Skill 08 — Impact Calculation

**Type: CODE ACTION — deliberately NOT an AI prompt**
**Attached to:** Roadmap Shield
**Version:** 1.0
**Priority: BUILD FIRST**

---

## Why this is code and not a prompt

Date arithmetic across a dependency chain is exactly the work a language model
does confidently and wrongly. Roadmap Shield's instructions state that all
arithmetic runs through the calculation action and that the agent never computes
dates or hours itself. If this is implemented as a prompt, that rule becomes
unenforceable — there is no longer anywhere for the arithmetic to run except
inside the model.

A second reason: determinism. The same request must produce the same date every
time it is asked. A roadmap decision that changes because the question was
phrased differently is not a decision support system.

## Implementation options

| Option | When to choose |
|---|---|
| **Azure Function** (recommended) | Dependency graphs beyond ~50 milestones, or roadmap source may change later |

---

## Contract

### Input

```json
{
  "roadmap": [
    {
      "milestone_id": "M-101",
      "milestone_name": "Sensor firmware v2",
      "planned_start": "2026-09-01",
      "planned_end": "2026-10-15",
      "effort_hours": 240,
      "depends_on": ["M-098"],
      "owner_team": "Platform",
      "externally_committed": true
    }
  ],
  "capacity_hours_per_week": 120,
  "new_request": {
    "name": "Customer X telemetry export",
    "requester": "string",
    "effort_hours": 40,
    "requested_start": "2026-09-07",
    "priority_insert_before": "M-101"
  },
  "working_days_per_week": 5,
  "as_of_date": "2026-08-14"
}
```

`effort_hours` on `new_request` is **required**. If it is absent, the function
returns `NEEDS_INPUT` — it must never estimate. A fabricated input produces a
fabricated date, and dates get committed.

### Output

```json
{
  "status": "OK | NEEDS_INPUT | NOT_SIMULATABLE",
  "absorbed_without_impact": false,
  "slack_hours_available": 0,
  "capacity_math": {
    "capacity_hours_per_week": 120,
    "committed_hours_per_week": 118,
    "available_hours_per_week": 2,
    "request_hours": 40,
    "weeks_required": 20.0,
    "formula": "weeks_required = request_hours / available_hours_per_week = 40 / 2"
  },
  "affected_milestones": [
    {
      "milestone_id": "M-101",
      "milestone_name": "Sensor firmware v2",
      "old_end": "2026-10-15",
      "new_end": "2026-11-12",
      "slip_working_days": 20,
      "cascade_depth": 0,
      "externally_committed": true
    }
  ],
  "new_request_dates": { "start": "2026-09-07", "end": "2026-09-18" },
  "critical_path_changed": false,
  "externally_committed_dates_breached": ["M-101"],
  "gaps": ["M-114 has no effort_hours; excluded from cascade"],
  "assumptions": ["No holidays calendar supplied; working days assume Mon-Fri"],
  "as_of_date": "2026-08-14"
}
```

---

## Algorithm

1. **Validate.** Reject on missing `effort_hours`, missing
   `capacity_hours_per_week`, or any in-scope milestone lacking dates or effort.
   Return `NEEDS_INPUT` naming each missing field. Never default a value.
2. **Build the dependency graph.** Detect cycles; abort with
   `NOT_SIMULATABLE` and name the cycle rather than looping.
3. **Compute committed load per week** across the horizon from `effort_hours`
   spread over each milestone's planned span.
4. **Compute slack** = `capacity_hours_per_week − committed_hours_per_week`.
   If slack ≥ request hours across the requested window, set
   `absorbed_without_impact: true` and return with an empty
   `affected_milestones`. **Zero impact is a valid and useful result** — do not
   manufacture a slip to look rigorous.
5. **Insert the request** at `priority_insert_before` and displace downstream
   work by the overflow hours.
6. **Propagate the cascade** breadth-first through `depends_on`, recording
   `cascade_depth`. Every affected milestone appears in the output, not just the
   first-order one.
7. **Convert hours to dates** using `working_days_per_week`. Exclude weekends.
   If no holiday calendar is supplied, record that under `assumptions`.
8. **Flag externally committed breaches** separately — these carry different
   consequences from internal slips and must not be presented as equivalent.
9. **Emit the formula strings** in `capacity_math`. The Trade-off Card requires
   the arithmetic shown, and the agent is not permitted to reconstruct it.

## Edge cases the implementation must handle

| Case | Required behavior |
|---|---|
| Request fits in slack | `absorbed_without_impact: true`, no invented slip |
| Available capacity is zero or negative | Return `NOT_SIMULATABLE` with the overcommitment stated — do not divide by zero or emit an infinite date |
| Milestone already past `as_of_date` | Excluded from cascade; noted in `gaps` |
| Milestone missing `effort_hours` | Excluded, listed in `gaps` — never estimated |
| Circular dependency | `NOT_SIMULATABLE`, cycle named |
| Request larger than total remaining capacity | Compute anyway and report the full slip; do not cap it at a comfortable number |
| Two milestones sharing `owner_team` at full capacity | Contention noted in `gaps` if team-level capacity is not modeled |

## Test cases

| # | Scenario | Pass condition |
|---|---|---|
| 1 | 40h request, 60h slack | `absorbed_without_impact: true`, empty affected list |
| 2 | 40h request, 2h/wk slack | 20-week math shown in `formula` |
| 3 | Chain M-101→M-102→M-103 | All three in `affected_milestones` with ascending `cascade_depth` |
| 4 | Request with no `effort_hours` | `NEEDS_INPUT`, no estimate produced |
| 5 | Committed load exceeds capacity before the request | `NOT_SIMULATABLE`, overcommitment stated |
| 6 | Slip crosses an externally committed date | Milestone appears in `externally_committed_dates_breached` |
| 7 | Same input run twice | Byte-identical output |

Test 7 is the one that distinguishes this from a prompt. Run it as a regression
check after any change.
