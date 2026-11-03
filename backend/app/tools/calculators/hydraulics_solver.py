#!/usr/bin/env python3
"""hydraulics_solver — extracted from the Senior Well Planner tool library (tools.py).

Planning-grade estimate. Validate in certified software (certified engineering software or
equivalent) before AFE approval.

Usage:
    python hydraulics_solver.py '<json-input>'
    python hydraulics_solver.py --input params.json
    cat params.json | python hydraulics_solver.py
"""

import json
import math
import sys
from typing import Any


# ── Tool: hydraulics_solver ───────────────────────────────────────────────────

def hydraulics_solver(
    flow_rate_gpm: float,
    mud_weight_ppg: float,
    plastic_viscosity_cp: float,
    yield_point_lbf100sqft: float,
    hole_size_in: float,
    drillpipe_od_in: float,
    tvd_ft: float,
    md_ft: float,
    drillpipe_id_in: float = None,
    bit_nozzles: list = None,
    formation_angle_deg: float = 0.0,
) -> dict:
    PV = plastic_viscosity_cp
    YP = yield_point_lbf100sqft
    Dh = hole_size_in
    Dp = drillpipe_od_in
    Q = flow_rate_gpm
    MW = mud_weight_ppg
    L = md_ft

    ann_area = Dh ** 2 - Dp ** 2
    if ann_area <= 0:
        return {"error": "Drillpipe OD must be smaller than hole size."}

    # ── Annular velocity (Va ft/min = 24.51 × Q_gpm / (Dh²−Dp²)) ─────────────
    Va = 24.51 * Q / ann_area  # ft/min

    # ── Bourgoyne critical velocity (BP laminar→turbulent transition) ──────────
    # Bourgoyne et al., Applied Drilling Engineering Eq. 4.82
    d_ann = Dh - Dp
    _inner = PV ** 2 + 9.97 * MW * YP * d_ann ** 2
    Va_crit = (97 * PV + 97 * math.sqrt(max(_inner, 0.0))) / max(MW * d_ann, 0.001)

    # ── Annular pressure loss (Bingham Plastic, API RP 13D / Bourgoyne Eq. 4.82) ─
    if Va > Va_crit:
        # Turbulent: Dodge-Metzner/Fanning friction factor approach
        f = 0.316 * max(
            109 * MW * Va * d_ann / max(PV + 6 * YP * d_ann / max(Va, 0.01), 1), 1
        ) ** (-0.25)
        Pa = f * MW * (Va / 60) ** 2 * L / (25.81 * d_ann)  # Va→fps inside
        regime = "Turbulent"
    else:
        Pa = (PV * Va * L) / (60_000 * d_ann ** 2) + (YP * L) / (200 * d_ann)
        regime = "Laminar"

    Re = 109 * MW * Va * d_ann / max(PV + 6 * YP * d_ann / max(Va, 0.01), 1)

    # ── Drillstring interior pressure loss ────────────────────────────────────
    # Use the supplied drillpipe ID when available; otherwise approximate from OD.
    dp_id = drillpipe_id_in if (drillpipe_id_in and drillpipe_id_in > 0) else max(Dp - 0.40, 0.5)
    Vp = 24.51 * Q / (dp_id ** 2)  # ft/min

    # Check if turbulent inside drillpipe (Bourgoyne Eq. 4.82 adapted for pipe)
    _inner_p = PV ** 2 + 9.97 * MW * YP * dp_id ** 2
    Vp_crit = (97 * PV + 97 * math.sqrt(max(_inner_p, 0.0))) / max(MW * dp_id, 0.001)

    if Vp > Vp_crit:
        # Turbulent: Darcy-Weisbach + Blasius friction factor.
        # The 0.45 is an empirical calibration of the simplified bore loss to
        # measured standpipe pressure (tool-joint upsets, ID variation, internal
        # coatings reduce the textbook smooth-bore loss). Replace with a measured
        # SPP correlation if available for your string.
        Re_pipe = 928 * MW * Vp * dp_id / max(PV + 6 * YP * dp_id / max(Vp, 0.01), 1)
        f_pipe = 0.316 * max(Re_pipe, 1) ** (-0.25)
        Pa_ds = f_pipe * MW * (Vp / 60) ** 2 * L / (13.81 * dp_id) * 0.45
    else:
        # Laminar pipe flow (Bourgoyne Eq. 4.76)
        Pa_ds = (PV * Vp * L) / (144_000 * dp_id ** 2) + (YP * L) / (225 * dp_id)

    # ── Bit pressure drop ─────────────────────────────────────────────────────
    if bit_nozzles:
        An = sum(math.pi / 4 * (n / 32) ** 2 for n in bit_nozzles)
        dP_bit = MW * Q ** 2 / (12_042 * An ** 2)
        jet_vel = round(Q / (3.117 * An), 1)
        hhp_bit = round(dP_bit * Q / 1714, 1)
        hhp_sqin = round(hhp_bit / (math.pi / 4 * Dh ** 2), 2)
    else:
        dP_bit = 600.0  # assumed typical if nozzles not given
        jet_vel = None
        hhp_bit = round(dP_bit * Q / 1714, 1)
        hhp_sqin = None

    # ── Standpipe pressure ────────────────────────────────────────────────────
    SPP = Pa_ds + Pa + dP_bit

    # ── ECD ───────────────────────────────────────────────────────────────────
    ECD = MW + Pa / (0.052 * tvd_ft) if tvd_ft > 0 else MW

    # ── Hole cleaning (Stokes slip velocity, BP fluid) ────────────────────────
    rho_cut = 21.7  # ppg (average rock density ~2.6 SG)
    dc = 0.25       # in (typical cutting size)
    Vs = max(0.0, 0.2 * (rho_cut - MW) * dc ** 2 / max(PV, 1))  # ft/min

    # Inclination degrades effective cuttings transport (cuttings-bed tendency on
    # the low side above ~30°); angle_factor scales the effective carrying velocity.
    angle_factor = max(0.4, 1.0 - 0.007 * max(0, formation_angle_deg - 30))
    Vt = max(0.0, Va * angle_factor - Vs)  # net effective transport velocity

    if formation_angle_deg > 60:
        hc_status = "CHALLENGING" if Va < 120 else "ADEQUATE"
        hc_note = f"High-angle section ({round(formation_angle_deg)}°) — target Va ≥ 120 ft/min; consider viscous sweeps"
    elif formation_angle_deg > 30:
        hc_status = "MARGINAL" if Va < 100 else "ADEQUATE"
        hc_note = f"Inclined section ({round(formation_angle_deg)}°) — Va = {round(Va)} ft/min; monitor cuttings bed"
    else:
        hc_status = "GOOD" if Va > 80 else "MARGINAL"
        hc_note = f"Near-vertical — Va = {round(Va)} ft/min {'OK' if Va > 80 else '— consider higher flow rate'}"

    flags = []
    if ECD > MW * 1.05:
        flags.append(f"ECD = {round(ECD, 2)} ppg ({round(ECD - MW, 2)} ppg over static) — confirm against FG")
    if SPP > 4500:
        flags.append(f"SPP = {round(SPP)} psi — verify rig pump pressure rating")
    if Va < 80:
        flags.append(f"Low annular velocity ({round(Va, 1)} ft/min) — hole cleaning risk; increase Q or reduce pipe OD")
    if Va > Va_crit:
        flags.append(f"Turbulent annular flow (Re={round(Re)}, Va_crit={round(Va_crit)} ft/min) — erosion risk on soft formations")

    return {
        "tool": "hydraulics_solver",
        "model": "Bingham Plastic (API RP 13D)",
        "inputs": {
            "Q_gpm": Q, "MW_ppg": MW, "PV_cp": PV, "YP_lbf100sqft": YP,
            "hole_in": Dh, "DP_od_in": Dp, "md_ft": L, "tvd_ft": tvd_ft,
        },
        "hydraulics": {
            "annular_velocity_ftmin": round(Va, 1),
            "annular_flow_regime": regime,
            "Re_annular": round(Re),
            "annular_pressure_loss_psi": round(Pa),
            "drillstring_pressure_loss_psi": round(Pa_ds),
            "bit_pressure_drop_psi": round(dP_bit),
            "standpipe_pressure_psi": round(SPP),
            "ECD_ppg": round(ECD, 3),
            "ECD_increase_over_static_ppg": round(ECD - MW, 3),
            "bit_HHP": hhp_bit,
            "HHP_per_sqin_hole": hhp_sqin,
            "jet_velocity_fps": jet_vel if jet_vel else "N/A — nozzles not specified",
        },
        "hole_cleaning": {
            "cutting_slip_velocity_ftmin": round(Vs, 1),
            "net_transport_velocity_ftmin": round(Vt, 1),
            "wellbore_angle_deg": formation_angle_deg,
            "status": hc_status,
            "note": hc_note,
        },
        "flags": flags,
        "note": (
            "Annular losses: Bingham Plastic API method. "
            "Bit ΔP: ρQ²/(12042·An²). ECD validated only where PWD data exists. "
            "Use full hydraulics software for critical ECD-constrained sections."
        ),
    }


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--input":
        payload = json.load(open(args[1]))
    elif args and args[0] not in ("-", "--stdin"):
        payload = json.loads(args[0])
    else:
        payload = json.load(sys.stdin)
    print(json.dumps(hydraulics_solver(**payload), indent=2))


if __name__ == "__main__":
    main()
