#!/usr/bin/env python3
"""torque_drag_simulator — extracted from the Senior Well Planner tool library (tools.py).

Planning-grade estimate. Validate in certified software (certified engineering software or
equivalent) before AFE approval.

Usage:
    python torque_drag_simulator.py '<json-input>'
    python torque_drag_simulator.py --input params.json
    cat params.json | python torque_drag_simulator.py
"""

import json
import math
import sys
from typing import Any


# ── Tool: torque_drag_simulator ───────────────────────────────────────────────

def torque_drag_simulator(
    well_profile: list,
    drillstring: dict,
    mud_weight_ppg: float,
    wob_klbf: float,
    operation: str,
    friction_factor_open: float = 0.25,
    friction_factor_cased: float = 0.15,
    casing_depth_ft: float = 0.0,
) -> dict:
    pipe_od = drillstring["pipe_od_in"]
    w_air = drillstring["steel_weight_ppf"]  # lb/ft in air

    bf = 1 - mud_weight_ppg / 65.4
    w_buoy = w_air * bf          # buoyed lb/ft
    r_ft = (pipe_od / 2) / 12    # torque moment arm (ft)

    stations = sorted(well_profile, key=lambda s: s["md_ft"])
    if len(stations) < 2:
        return {"error": "well_profile needs at least 2 survey stations.",
                "tool": "torque_drag_simulator"}
    max_md = stations[-1]["md_ft"]

    # Build wellbore elements between consecutive survey stations.
    elements = []
    for i in range(1, len(stations)):
        s0, s1 = stations[i - 1], stations[i]
        dl = s1["md_ft"] - s0["md_ft"]
        if dl <= 0:
            continue
        i0, i1 = math.radians(s0["inclination_deg"]), math.radians(s1["inclination_deg"])
        a0, a1 = math.radians(s0["azimuth_deg"]), math.radians(s1["azimuth_deg"])
        avg_inc = (i0 + i1) / 2
        dogleg = math.sqrt((i1 - i0) ** 2 + (math.sin(avg_inc) * (a1 - a0)) ** 2)  # rad / interval
        mid_md = (s0["md_ft"] + s1["md_ft"]) / 2
        mu = friction_factor_cased if mid_md < casing_depth_ft else friction_factor_open
        elements.append({
            "from": s0["md_ft"], "to": s1["md_ft"], "dl": dl,
            "avg_inc": avg_inc, "dogleg": dogleg, "mu": mu,
        })

    def _integrate(friction_sign: int):
        """Soft-string tension integration from the bit (bottom) up to surface.

        Contact (normal) force per element combines the curvature term
        (axial tension × dogleg angle) with the gravity side-force
        (buoyed element weight × sin inclination) — the standard soft-string
        formulation. The previous version used buoyed *weight* in place of
        tension for curvature and scaled the gravity term by 0.08, which
        under-predicted drag/torque in deviated wells by ~10×.

        friction_sign: +1 pulling up (trip out), −1 running in (trip in /
        slide), 0 rotating off-bottom (axial friction relieved).
        Returns (surface_tension_lbf, rows[top-down]).
        """
        T = 0.0
        rows = []
        for el in reversed(elements):
            w_elem = w_buoy * el["dl"]  # buoyed element weight (lbf)
            N = abs(T * el["dogleg"]) + abs(w_elem * math.sin(el["avg_inc"]))
            T += w_elem * math.cos(el["avg_inc"]) + friction_sign * el["mu"] * N
            rows.append({
                "from": el["from"], "to": el["to"], "dl": el["dl"],
                "avg_inc": el["avg_inc"], "dogleg": el["dogleg"],
                "N": N, "friction": el["mu"] * N, "torque": el["mu"] * N * r_ft,
            })
        rows.reverse()  # restore top-down order
        return T, rows

    static_T, static_rows = _integrate(0)   # projected buoyed (rotating) hookload + contacts
    trip_in_T, _ = _integrate(-1)
    trip_out_T, _ = _integrate(+1)

    drag_in_klbf = (static_T - trip_in_T) / 1000     # slack-off (running in) drag
    drag_out_klbf = (trip_out_T - static_T) / 1000   # pickup (pulling out) drag
    rotating_torque = sum(r["torque"] for r in static_rows)  # ft-lbf

    if operation == "tripping_in":
        hookload, drag_klbf, surf_torque = trip_in_T / 1000, drag_in_klbf, 0.0
    elif operation == "tripping_out":
        hookload, drag_klbf, surf_torque = trip_out_T / 1000, drag_out_klbf, 0.0
    elif operation == "rotating":
        hookload, drag_klbf, surf_torque = static_T / 1000, 0.0, rotating_torque
    else:  # sliding: drilling with a mud motor, string not rotating
        # Slack-off hookload (axial drag as when running in); surface torque is the
        # motor's reactive torque — reported as the off-bottom rotating reference.
        hookload, drag_klbf, surf_torque = trip_in_T / 1000, drag_in_klbf, rotating_torque

    # Cumulative drag from the bit upward, for the section detail.
    cum, detail = 0.0, []
    for r in reversed(static_rows):
        cum += r["friction"]
        detail.append({
            "from_ft_md": round(r["from"]),
            "to_ft_md": round(r["to"]),
            "avg_inc_deg": round(math.degrees(r["avg_inc"]), 1),
            "dls_deg_100ft": round(math.degrees(r["dogleg"] / r["dl"]) * 100, 2) if r["dl"] > 0 else 0,
            "normal_force_lbf": round(r["N"]),
            "friction_lbf": round(r["friction"]),
            "cumulative_drag_klbf": round(cum / 1000, 2),
        })
    detail.reverse()

    W_buoy_total = w_buoy * max_md / 1000   # klbf (vertical-equivalent)
    W_air_total = w_air * max_md / 1000     # klbf

    flags = []
    worst_drag = max(drag_in_klbf, drag_out_klbf)
    if worst_drag > 50:
        flags.append(f"High trip drag ({round(worst_drag, 1)} klbf) — consider lubricant treatment or trajectory smoothing")
    if rotating_torque > 20_000:
        flags.append(f"Rotating torque {round(rotating_torque):,} ft-lbf — verify top-drive and make-up torque limits")
    if drag_in_klbf >= static_T / 1000 * 0.9 and operation in ("tripping_in", "sliding"):
        flags.append("Slack-off drag approaching string weight — helical-lockup / slide-transfer risk; check WOB delivery")
    if drag_klbf > wob_klbf and operation == "sliding":
        flags.append("Slide drag exceeds WOB request — WOB delivery to bit may be compromised")

    return {
        "tool": "torque_drag_simulator",
        "model": "Soft-string with bottom-up tension integration (planning-grade estimate)",
        "operation": operation,
        "inputs": {
            "total_md_ft": max_md,
            "pipe": f'{pipe_od}" OD @ {w_air} lb/ft in air',
            "mud_weight_ppg": mud_weight_ppg,
            "buoyancy_factor": round(bf, 4),
            "mu_open_hole": friction_factor_open,
            "mu_cased_hole": friction_factor_cased,
            "casing_shoe_md_ft": casing_depth_ft,
        },
        "results": {
            "string_weight_air_klbf": round(W_air_total, 1),
            "string_weight_buoyed_klbf": round(W_buoy_total, 1),
            "effective_static_hookload_klbf": round(static_T / 1000, 1),
            "pickup_drag_klbf": round(drag_out_klbf, 1),
            "slackoff_drag_klbf": round(drag_in_klbf, 1),
            "rotating_torque_ftlbf": round(rotating_torque),
            "surface_hookload_klbf": round(hookload, 1),
            "surface_torque_ftlbf": round(surf_torque),
            "wob_requested_klbf": wob_klbf,
        },
        "section_detail_last_3": detail[-3:] if len(detail) > 3 else detail,
        "flags": flags,
        "note": (
            "Soft-string: contact force = tension×dogleg + buoyed-weight×sin(inc); "
            "tension integrated bottom-up. Order-of-magnitude planning estimate. "
            "Use certified engineering software or equivalent for certified T&D design."
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
    print(json.dumps(torque_drag_simulator(**payload), indent=2))


if __name__ == "__main__":
    main()
