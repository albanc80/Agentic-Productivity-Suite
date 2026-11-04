---
name: drilling-hydraulics
description: Solves drilling hydraulics with the Bingham Plastic model (API RP 13D) — ECD, annular and drillstring pressure losses, standpipe pressure, bit pressure drop, jet velocity, hydraulic horsepower, and hole-cleaning assessment. Use for ECD-constrained and narrow-window sections, flow rate and nozzle optimization, cuttings-bed and hole-cleaning questions, pump pressure limit checks, and high-angle transport velocity screening. Do NOT use for casing load checks (casing-design-check), hookload or torque (torque-and-drag), or hazard scoring (well-risk-matrix).
---

# Drilling Hydraulics

Bingham Plastic hydraulics for a section: what the pumps see, what the formation sees, and whether the hole cleans.

## When to use

- ECD against fracture gradient in a narrow window
- Flow rate and nozzle selection, HHP optimization
- Hole cleaning in high-angle or horizontal sections, cuttings beds, sweep planning
- Standpipe pressure against rig pump pressure rating
- Screening a section before committing to an MPD or a mud-weight change

## Inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `flow_rate_gpm` | number | yes | US gpm |
| `mud_weight_ppg` | number | yes | Static mud weight |
| `plastic_viscosity_cp` | number | yes | PV |
| `yield_point_lbf100sqft` | number | yes | YP |
| `hole_size_in` | number | yes | Hole / bit diameter |
| `drillpipe_od_in` | number | yes | Must be smaller than hole size |
| `tvd_ft` | number | yes | Drives ECD |
| `md_ft` | number | yes | Drives length-dependent losses |
| `drillpipe_id_in` | number | no | Estimated as OD − 0.40" if omitted — pass the real ID when known |
| `bit_nozzles` | array | no | Sizes in 32nds, e.g. `[12, 12, 13]`; without it jet velocity and bit ΔP are not resolved |
| `formation_angle_deg` | number | no | 0 = vertical, 90 = horizontal; degrades cuttings transport with inclination |

Always pass `formation_angle_deg` on a deviated section. Omitting it makes hole cleaning look better than it is.

## Run

```bash
python scripts/hydraulics_solver.py '{
  "flow_rate_gpm": 620, "mud_weight_ppg": 11.5,
  "plastic_viscosity_cp": 18, "yield_point_lbf100sqft": 14,
  "hole_size_in": 8.5, "drillpipe_od_in": 5.0,
  "tvd_ft": 8200, "md_ft": 9800,
  "bit_nozzles": [12, 12, 13], "formation_angle_deg": 88
}'
```

Also accepts `--input params.json` or JSON on stdin.

## Output

`hydraulics`: annular velocity, annular flow regime, annular Reynolds number, annular and drillstring pressure losses, bit ΔP, standpipe pressure, ECD and ECD increase over static, bit HHP, HHP per sq in of hole, jet velocity. `hole_cleaning`: cuttings slip velocity, net transport velocity, wellbore angle, status and note. `flags` fire on: ECD > 1.05 x MW, SPP > 4,500 psi, annular velocity < 80 ft/min, and turbulent annular flow (erosion risk on soft formations).

## Reporting rules

1. ECD is the headline number on any narrow-window section. **Always compare ECD against the fracture gradient** — the tool does not know the FG, so state it and do the comparison, or say the comparison is unresolved.
2. Report standpipe pressure against the rig pump pressure rating. If the rating was not supplied, say so rather than assuming a rig.
3. Report hole cleaning as velocity numbers plus status, and carry the note about the target annular velocity for the section angle. High-angle sections need the sweep and RPM discussion, not just a status word.
4. Reproduce all `flags` with their consequence and a specific corrective action (flow rate, rheology, nozzle change, pipe OD, sweeps).
5. When you change one parameter to fix a flag, re-run and show the before/after — flow rate up fixes hole cleaning and worsens ECD and SPP simultaneously. Show the tradeoff, never a one-way recommendation.
6. State whether `drillpipe_id_in` and `bit_nozzles` were supplied or estimated.
7. Close with: "Planning-grade estimate. Validate in certified engineering software before AFE approval."

## Limits

Single homogeneous annular section — no BHA or hole-size staging, no cuttings loading feedback into ECD, no surge/swab, no temperature/pressure rheology correction. ECD is validated only where PWD data exists.

Known quirk to be aware of when reporting: `annular_flow_regime` is set by comparing annular velocity to the Bingham critical velocity, while `Re_annular` is an apparent-viscosity Reynolds number — the two can disagree (a "Laminar" label alongside a high Re). Trust the regime label and the turbulence flag, and do not present the Reynolds number on its own as a regime determination.
