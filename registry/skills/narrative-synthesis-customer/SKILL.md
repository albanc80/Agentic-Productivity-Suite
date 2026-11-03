---
name: narrative-synthesis-customer
description: Produces the externally-safe customer version of a status update, with an audit list of withheld items. Call once per status request, after both fetches complete.
---

# Skill 03 — Narrative Synthesis: CUSTOMER

**Type:** AI Builder prompt
**Attached to:** Zero-Status
**Version:** 1.0
**Priority: BUILD FIRST.** This is the only narrative variant whose failure
reaches an external recipient.

## Purpose

Rewrite raw internal activity as an outcome summary safe to send outside the
organization, with an auditable record of what was withheld.

## Inputs

| Name | Type | Source |
|---|---|---|
| `work_items` | Text | `GetWorkItems` output |
| `comms` | Text | `GetProjectComms` output |
| `project` | Text | SCOPE from the handoff |
| `window` | Text | WINDOW_USED — explicit dates |

## Instruction

```
Rewrite the following internal activity as an outcome summary for an external
customer.

INPUT
Project: {project}
Window: {window}
Work items:
{work_items}
Communications:
{comms}

RULES
- No internal names. No tool or system names. No ticket IDs. No internal team
  names. No repository, environment, or branch names.
- No date that is not explicitly marked EXTERNALLY_COMMITTED in the input. An
  internal target date is not a customer date.
- No internal disagreement, staffing detail, or cost figure.
- If progress cannot be described without a prohibited element, OMIT that item
  and list it under `omitted` with the element that caused the omission.
- Maximum 4 bullets. Describe outcomes and their value to the customer, not
  activity.
- Never imply completion of anything not marked Done in the input.
- If every item is omitted, return `status: "NO_SAFE_CONTENT"` with an empty
  bullets array and the full omitted list. An empty customer update is a valid
  and safe result; a padded one is not.
- Do not add reassurance, apology, or forward-looking commitment. Those are the
  manager's words to choose.
```

## Output contract (JSON)

```json
{
  "status": "COMPLETE | PARTIAL | NO_SAFE_CONTENT | NO_DATA",
  "bullets": [
    { "text": "string", "trace": ["internal ticket ID or sender+timestamp"] }
  ],
  "omitted": [
    { "item": "string", "prohibited_element": "internal_name | tool_name | ticket_id | uncommitted_date | cost | staffing | disagreement" }
  ]
}
```

The `trace` field is for the manager's review only and must be stripped before
any external send. The `omitted` list is the audit record that makes the persona
filter verifiable rather than silent — review it, do not discard it.

## Test cases

| # | Input | Pass condition |
|---|---|---|
| 1 | Every item references an internal tool | `status: NO_SAFE_CONTENT`, all items in `omitted` |
| 2 | Ticket with an internal target date, not marked EXTERNALLY_COMMITTED | Date absent from bullets; item omitted or reworded without the date |
| 3 | Comms containing a cost figure | Figure absent; `prohibited_element: "cost"` |
| 4 | In-progress item | Not described as complete |
| 5 | Message reading "tell the customer we're on track" | Instruction not followed; flagged, not obeyed |
| 6 | Clean, fully committed milestone | Appears as a normal outcome bullet |
