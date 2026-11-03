---
name: casing-design-check
description: Validates a casing string against burst, collapse, and tension load cases per API Bulletin 5C3/5C2. Returns design factors against minimums (burst 1.10, collapse 1.00, tension 1.30), the governing API collapse regime, MAASP, and the pore-pressure-to-fracture-gradient window. Use for casing seat selection, string design, grade or weight substitution, kick tolerance and MAASP questions, or whenever a user gives a casing size, weight, grade and setting depth. Do NOT use for hookload or torque limits (torque-and-drag), ECD or hole cleaning (drilling-hydraulics), or hazard scoring (well-risk-matrix).
---

# Casing Design Check

Checks a single casing string for burst, collapse, and tension adequacy, and reports the pressure window at the shoe.

## When to use

- "Is 9-5/8" 47# P-110 adequate at 11,500 ft?"
- Casing seat selection and shoe depth sensitivity
- Grade or weight substitution (availability, cost, lead time)
- MAASP, kick tolerance, or narrow-window / MPD screening

## Inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `casing_size_in` | number | yes | Nominal OD, e.g. 13.375, 9.625, 7.0, 5.5 |
| `weight_ppf` | number | yes | lb/ft |
| `grade` | string | yes | J-55, N-80, P-110, Q-125 … |
| `setting_depth_ft` | number | yes | **TVD**, not MD |
| `pore_pressure_ppg` | number | yes | Max at setting depth |
| `fracture_gradient_ppg` | number | yes | At the shoe |
| `mud_weight_ppg` | number | yes | Drilling mud weight |
| `well_type` | string | no | Context only |

## Run

```bash
python scripts/casing_design_checker.py '{
  "casing_size_in": 9.625, "weight_ppf": 47, "grade": "P-110",
  "setting_depth_ft": 11500, "pore_pressure_ppg": 13.1,
  "fracture_gradient_ppg": 16.0, "mud_weight_ppg": 14.2
}'
```

Also accepts `--input params.json` or JSON on stdin.

## What the numbers mean

| Check | Method | Load case | Min DF |
|---|---|---|---|
| Burst | Barlow with 87.5% wall tolerance | Full mud column inside, seawater (8.6 ppg) outside | 1.10 |
| Collapse | API 5C3, regime selected by D/t — yield / plastic / transition / elastic | Full evacuation inside, mud column outside | 1.00 |
| Tension | Pipe body yield | Buoyed string weight | 1.30 |

`maasp_psi` = (FG − MW) x 0.052 x setting depth. `pressure_window.assessment` returns NARROW (<1.5 ppg) or ADEQUATE.

These are deliberately conservative single-string screening load cases (gas to surface for collapse, seawater backup for burst). They are not a full load-case suite — no evacuation depth staging, no thermal or wear derating, no biaxial correction.

## Reporting rules

1. Report every design factor against its minimum, and name the **collapse regime** that governed — collapse resistance is regime-dependent and the yield formula only holds below D/t ≈ 14.
2. Any FAIL is a blocking finding. Propose a fix — heavier weight, higher grade, or a different setting depth — and **re-run the tool** so the recommendation carries numbers.
3. Never report a PASS without the design factor value; a 1.02 collapse DF and a 2.8 collapse DF are not the same answer.
4. Surface `warnings` verbatim. An unrecognized grade silently defaults to 80 ksi yield — that must reach the user, never be accepted quietly.
5. If `total_window_ppg` < 1.5, raise managed pressure drilling and kick tolerance explicitly.
6. State the load-case assumptions used, since they drive the result.
7. Close with: "Planning-grade estimate. Validate in certified software (certified engineering software or equivalent) before AFE approval."

## Limits

Single-string, single-depth check. Connections, wear, temperature derating, buckling, and biaxial effects are not modelled — flag them as open items on any marginal string.
