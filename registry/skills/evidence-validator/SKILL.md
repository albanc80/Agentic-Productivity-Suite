---
name: evidence-validator
description: Audits a drafted output against raw retrieved data for unsupported claims. Call as the final step before returning any findings.
---

# Skill 06 — Evidence Validator

**Type:** AI Builder prompt
**Attached to:** Zero-Status, Sentiment Radar, Roadmap Shield (all three)
**Version:** 1.0

## Purpose

Audit a drafted output against the raw retrieved data and return every claim
lacking a supporting trace. Runs as the **last step before HANDOFF OUT**, in all
three child agents.

## Why it works

The model is substantially better at auditing a finished draft than at policing
itself mid-generation. This is the cheapest defense against the failure mode the
entire guardrail set is built around — a fluent, confident, unsupported claim.

## Inputs

| Name | Type | Source |
|---|---|---|
| `draft_output` | Text | The FINDINGS block about to be returned |
| `raw_data` | Text | Every tool result retrieved this turn, concatenated |
| `module` | Text | `ZERO_STATUS` \| `SENTIMENT_RADAR` \| `ROADMAP_SHIELD` |

## Instruction

```
You are auditing a draft before it is returned to a manager. You are not
improving it, rewriting it, or making it read better. You are finding claims
that the evidence does not support.

DRAFT
{draft_output}

RAW RETRIEVED DATA
{raw_data}

MODULE: {module}

TASK
Decompose the draft into individual factual claims. A claim is any statement
asserting a status, date, number, quantity, name, quote, causal relationship, or
score. For each claim, locate the supporting evidence in the raw data.

VERDICTS
- SUPPORTED   — evidence exists and matches the claim exactly
- OVERSTATED  — evidence exists but is weaker, narrower, or more hedged than
                the claim
- UNSUPPORTED — no evidence in the raw data
- CONTRADICTED— raw data says something different

ADDITIONAL CHECKS
- Any date, hour figure, percentage, or currency amount in the draft that does
  not appear verbatim in the raw data is UNSUPPORTED, even if it is arithmetically
  derivable. Derived figures must cite the source figures they came from.
- Any quoted sentence must match the raw data character for character. A cleaned
  up, trimmed, or grammatically corrected quote is UNSUPPORTED.
- Any statement about a person's performance, competence, attitude, or
  temperament is flagged PERSON_JUDGMENT regardless of evidence.
- If the draft asserts something is approved, cleared, sent, or agreed, flag it
  APPROVAL_CLAIM regardless of evidence.
- If the raw data is empty but the draft contains claims, every claim is
  UNSUPPORTED.

Do not rewrite the draft. Do not suggest better wording. Return the audit only.
```

## Output contract (JSON)

```json
{
  "verdict": "PASS | FAIL",
  "claims": [
    {
      "claim": "string",
      "status": "SUPPORTED | OVERSTATED | UNSUPPORTED | CONTRADICTED",
      "evidence": "verbatim excerpt from raw data | null"
    }
  ],
  "person_judgments": ["string"],
  "approval_claims": ["string"],
  "unsupported_count": 0
}
```

## Wiring

In each child agent, insert before HANDOFF OUT:

> Before returning, run Evidence Validator against your draft FINDINGS and the
> raw tool results from this turn. If `verdict` is FAIL, remove or downgrade
> every UNSUPPORTED and CONTRADICTED claim, soften every OVERSTATED one to match
> its evidence, and record the removals under GAPS. Never return a draft with an
> unresolved UNSUPPORTED claim. Any entry in `person_judgments` or
> `approval_claims` must be removed outright and noted in FLAGS.

## Test cases

| # | Input | Pass condition |
|---|---|---|
| 1 | Draft with a date absent from raw data | `UNSUPPORTED`, `verdict: FAIL` |
| 2 | Draft says "significantly delayed", raw says "may slip a day" | `OVERSTATED` |
| 3 | Quote with corrected grammar vs. raw | `UNSUPPORTED` |
| 4 | Draft calls a stakeholder "unreasonable" | Listed in `person_judgments` |
| 5 | Draft says "the customer has approved" | Listed in `approval_claims` |
| 6 | Fully traced clean draft | `verdict: PASS`, zero unsupported |
| 7 | Empty raw data, populated draft | Every claim `UNSUPPORTED` |
