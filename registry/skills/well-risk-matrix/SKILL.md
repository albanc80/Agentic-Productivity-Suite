---
name: well-risk-matrix
description: Builds a 5x5 drilling risk matrix and ranked risk register. Scores each hazard for likelihood (1-5) and severity (1-5), assigns Low/Medium/High/Critical, and returns mitigations per ALARP and barrier management. Use for any hazard review, HAZID, drilling program risk section, pre-spud risk review, or when the user asks "what can go wrong", "what are the risks", "build a risk matrix", or "risk register" for a well, section, or phase. Do NOT use for casing load checks (casing-design-check), hookload/torque limits (torque-and-drag), or ECD and hole cleaning (drilling-hydraulics).
---

# Well Risk Matrix

Produces an engineering risk register for a drilling section: likelihood x severity scoring, ranked hazards, mitigations, and contingency actions.

## When to use

- Section-level HAZID or pre-spud risk review
- The risk section of a drilling program or well plan
- The user names hazards ("stuck pipe", "lost circulation", "kick") and wants them assessed
- Any request phrased as "what can go wrong", "rank these risks", "risk register", "risk matrix"

Never hand-score hazards in prose. Run the tool so likelihood, severity, and rank are reproducible.

## Inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `hazards` | array | yes | Each item needs `name`, `category`, `description` |
| `hazards[].category` | string | yes | One of `well_control`, `geomechanics`, `mechanical`, `hydraulics`, `HSE`, `operational`, `geological` |
| `well_type` | string | yes | e.g. `HPHT`, `deepwater`, `horizontal_shale`, `exploration` — matching is case-insensitive |
| `phase` | string | yes | Section or phase, e.g. `26-inch`, `17.5-inch`, `12.25-inch`, `8.5-inch`, `completion` |

Category drives the base likelihood and severity; `well_type` applies a modifier; wording in `description` can raise severity when it signals a high-consequence scenario. Choose the category that matches the failure mechanism, not the symptom.

## Run

```bash
python scripts/risk_matrix_generator.py '{
  "hazards": [
    {"name": "Kick while drilling", "category": "well_control",
     "description": "Unexpected overpressure in target sand"},
    {"name": "Stuck pipe", "category": "mechanical",
     "description": "Differential sticking across depleted sand"}
  ],
  "well_type": "HPHT",
  "phase": "12.25-inch"
}'
```

Also accepts `--input params.json` or JSON on stdin.

## Output

`risk_register` sorted highest score first, each entry carrying `hazard_id` (H-01 is the top-ranked hazard — the ID is assigned *after* ranking), `likelihood_1_5`, `severity_1_5`, `risk_score`, `risk_level`, `mitigations`, `contingency`. Plus a `summary` block with `overall_risk_rating`.

## Reporting rules

1. Present the register as a table ranked by score — never raw JSON.
2. State the well type and phase the scoring was run for; scores are not transferable between sections.
3. Every Critical or High hazard gets its mitigation *and* its contingency in the answer, not just the mitigation.
4. If any hazard scores Critical, say so in the Executive Summary and call for Well Integrity Board escalation.
5. If the user gave hazards without describing the mechanism, state the assumed mechanism you categorised against.
6. Close with: "Planning-grade estimate. Validate in certified engineering software before AFE approval."

## Limits

Scoring is a deterministic rule set keyed on category, well type, and description wording — it is a structured starting point for a HAZID, not a substitute for a facilitated team review or an operator's own risk register.
