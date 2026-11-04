---
name: torque-and-drag
description: Runs a soft-string torque and drag model with bottom-up tension integration over a survey. Returns string weight in air and buoyed, effective static hookload, pickup and slack-off drag, rotating torque, and surface hookload/torque for tripping in, tripping out, rotating, or sliding. Use for extended-reach and lateral feasibility, sliding vs rotating decisions, casing or liner running feasibility, WOB transfer and helical lockup concerns, and rig hookload or top-drive limit checks. Do NOT use for casing burst/collapse/tension ratings (casing-design-check), ECD or hole cleaning (drilling-hydraulics), or hazard scoring (well-risk-matrix).
---

# Torque and Drag

Soft-string T&D estimate along a survey — what the rig will see on the hook and at the top drive.

## When to use

- "Can we reach 16,000 ft MD with this string?"
- Slide vs. rotate, WOB delivery to bit, helical lockup risk
- Running casing or liner to bottom
- Checking hookload against rig capacity and torque against top-drive and connection make-up limits
- Friction factor sensitivity (what if the hole is dirtier than planned)

## Inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `well_profile` | array | yes | Minimum 2 stations; each `md_ft`, `inclination_deg`, `azimuth_deg` |
| `drillstring` | object | yes | `pipe_od_in`, `pipe_id_in`, `steel_weight_ppf` (weight in air) |
| `mud_weight_ppg` | number | yes | Drives the buoyancy factor |
| `wob_klbf` | number | yes | Desired weight on bit |
| `operation` | string | yes | `tripping_in` \| `tripping_out` \| `rotating` \| `sliding` |
| `friction_factor_open` | number | no | Typical 0.20–0.35 |
| `friction_factor_cased` | number | no | Typical 0.10–0.20 |
| `casing_depth_ft` | number | no | Shoe MD — above is cased, below is open hole |

Survey resolution matters. A two-station profile smears the build section and understates curvature contact force; pass the real survey when it exists.

## Run

```bash
python scripts/torque_drag_simulator.py '{
  "well_profile": [
    {"md_ft": 0,     "inclination_deg": 0,  "azimuth_deg": 0},
    {"md_ft": 8000,  "inclination_deg": 0,  "azimuth_deg": 0},
    {"md_ft": 10000, "inclination_deg": 90, "azimuth_deg": 180},
    {"md_ft": 16000, "inclination_deg": 90, "azimuth_deg": 180}
  ],
  "drillstring": {"pipe_od_in": 5.0, "pipe_id_in": 4.276, "steel_weight_ppf": 19.5},
  "mud_weight_ppg": 10.5, "wob_klbf": 25, "operation": "tripping_out",
  "friction_factor_open": 0.30, "friction_factor_cased": 0.20,
  "casing_depth_ft": 10000
}'
```

Also accepts `--input params.json` or JSON on stdin.

## Output

`results` carries `string_weight_air_klbf`, `string_weight_buoyed_klbf`, `effective_static_hookload_klbf`, `pickup_drag_klbf`, `slackoff_drag_klbf`, `rotating_torque_ftlbf`, `surface_hookload_klbf`, `surface_torque_ftlbf`. `section_detail_last_3` shows the deepest three intervals. `flags` fire on: trip drag > 50 klbf, rotating torque > 20,000 ft-lbf, slack-off drag approaching string weight (helical lockup / slide-transfer risk), and slide drag exceeding requested WOB.

Model: soft-string, gravity side force `buoyed weight x sin(inclination)` plus curvature contact force `tension x dogleg`, with tension integrated bottom-up from the bit.

## Reporting rules

1. Report **pickup drag, slack-off drag, effective static hookload, and rotating torque separately**. A single "drag" number hides the tripping-out case, which is the one that governs.
2. Compare hookload against rig hookload capacity and torque against top-drive rating and connection make-up torque. If those limits were not supplied, say the check is unresolved — do not assume a rig.
3. Reproduce all `flags` in the answer with their engineering consequence.
4. Always state the friction factors used and whether they were given or assumed — the result scales almost linearly with them. Run a high-FF sensitivity case on any marginal well.
5. Sliding: if drag exceeds requested WOB, say WOB delivery is compromised and discuss the alternatives (rotary steerable, lubricant, trajectory smoothing, lighter mud).
6. Close with: "Planning-grade estimate. Validate in certified engineering software before AFE approval."

## Limits

Soft-string only: no pipe stiffness, no buckling propagation, no stiff-string contact modelling, no BHA or heavyweight tapering — the string is treated as uniform drillpipe. For stiff-string behaviour, tortuosity effects, or buckling limits, escalate to certified software.
