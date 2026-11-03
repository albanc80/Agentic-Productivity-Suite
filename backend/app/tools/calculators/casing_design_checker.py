#!/usr/bin/env python3
"""casing_design_checker — extracted from the Senior Well Planner tool library (tools.py).

Planning-grade estimate. Validate in certified software (certified engineering software or
equivalent) before AFE approval.

Usage:
    python casing_design_checker.py '<json-input>'
    python casing_design_checker.py --input params.json
    cat params.json | python casing_design_checker.py
"""

import json
import math
import sys
from typing import Any


# ── Tool: casing_design_checker ───────────────────────────────────────────────

_GRADES = {
    "J-55": 55_000, "K-55": 55_000,
    "N-80": 80_000, "L-80": 80_000,
    "C-90": 90_000, "T-95": 95_000,
    "P-110": 110_000, "Q-125": 125_000,
    "V-150": 150_000,
}


def _wall_thickness(od: float, weight_ppf: float) -> float:
    """Solve w = 10.68·t·(OD−t) for t using the quadratic formula."""
    disc = (10.68 * od) ** 2 - 4 * 10.68 * weight_ppf
    if disc < 0:
        return od * 0.05  # fallback for out-of-range inputs
    return (10.68 * od - math.sqrt(disc)) / (2 * 10.68)


def _collapse_rating(ys: float, dt: float) -> tuple:
    """API Bulletin 5C3 collapse rating (psi), with regime selected by D/t.

    The yield-strength formula alone is only valid at low D/t (roughly < 14);
    most oilfield casing sits in the plastic or transition regime where actual
    collapse resistance is lower. This implements all four regimes — yield,
    plastic, transition, elastic — using the API 5C3 empirical factors and
    returns (rating_psi, regime).
    """
    if dt <= 1:
        return 0.0, "invalid"

    A = 2.8762 + 0.10679e-5 * ys + 0.21301e-10 * ys ** 2 - 0.53132e-16 * ys ** 3
    B = 0.026233 + 0.50609e-6 * ys
    C = -465.93 + 0.030867 * ys - 0.10483e-7 * ys ** 2 + 0.36989e-13 * ys ** 3
    ratio = (3 * B / A) / (2 + B / A)
    F = (46.95e6 * ratio ** 3) / (ys * (ratio - B / A) * (1 - ratio) ** 2)
    G = F * B / A

    # Regime boundaries (D/t breakpoints).
    dt_yp = (math.sqrt((A - 2) ** 2 + 8 * (B + C / ys)) + (A - 2)) / (2 * (B + C / ys))
    dt_pt = ys * (A - F) / (C + ys * (B - G))
    dt_te = (2 + B / A) / (3 * B / A)

    if dt <= dt_yp:
        p = 2 * ys * ((dt - 1) / dt ** 2)
        regime = "yield"
    elif dt <= dt_pt:
        p = ys * (A / dt - B) - C
        regime = "plastic"
    elif dt <= dt_te:
        p = ys * (F / dt - G)
        regime = "transition"
    else:
        p = 46.95e6 / (dt * (dt - 1) ** 2)
        regime = "elastic"
    return max(p, 0.0), regime


def casing_design_checker(
    casing_size_in: float,
    weight_ppf: float,
    grade: str,
    setting_depth_ft: float,
    pore_pressure_ppg: float,
    fracture_gradient_ppg: float,
    mud_weight_ppg: float,
    well_type: str = "standard",
) -> dict:
    grade_key = grade.upper().replace(" ", "-")
    grade_recognized = grade_key in _GRADES
    ys = _GRADES.get(grade_key, 80_000)
    od = casing_size_in
    t = _wall_thickness(od, weight_ppf)
    id_in = od - 2 * t
    dt = od / t  # D/t ratio

    # ── Burst (API Barlow with 87.5% tolerance factor) ────────────────────────
    burst_rating = 0.875 * 2 * ys * t / od  # psi

    # Load: full mud column inside, seawater (~8.6 ppg) outside (conservative)
    p_internal = 0.052 * mud_weight_ppg * setting_depth_ft
    p_external = 0.052 * 8.6 * setting_depth_ft
    burst_load = max(p_internal - p_external, 1.0)
    burst_df = burst_rating / burst_load
    burst_pass = burst_df >= 1.1

    # ── Collapse (API 5C3 — regime selected by D/t) ───────────────────────────
    collapse_rating, collapse_regime = _collapse_rating(ys, dt)  # psi

    # Worst case: full evacuation inside (gas to surface), mud column outside
    collapse_load = max(0.052 * mud_weight_ppg * setting_depth_ft, 1.0)
    collapse_df = collapse_rating / collapse_load
    collapse_pass = collapse_df >= 1.0

    # ── Tension (API pipe body yield) ────────────────────────────────────────
    area = math.pi / 4 * (od ** 2 - id_in ** 2)  # sq in
    tension_rating_klbf = ys * area / 1000

    buoyancy_factor = 1 - mud_weight_ppg / 65.4
    tension_load_klbf = max(buoyancy_factor * weight_ppf * setting_depth_ft / 1000, 0.01)
    tension_df = tension_rating_klbf / tension_load_klbf
    tension_pass = tension_df >= 1.3

    # ── MAASP & pressure window ───────────────────────────────────────────────
    maasp = (fracture_gradient_ppg - mud_weight_ppg) * 0.052 * setting_depth_ft
    pp_margin = mud_weight_ppg - pore_pressure_ppg
    fg_margin = fracture_gradient_ppg - mud_weight_ppg
    window = fracture_gradient_ppg - pore_pressure_ppg

    overall = "PASS" if (burst_pass and collapse_pass and tension_pass) else "FAIL"

    warnings = []
    if not grade_recognized:
        warnings.append(
            f"Grade '{grade}' not in table — assumed yield 80 ksi (N-80 equivalent). Verify grade."
        )

    return {
        "tool": "casing_design_checker",
        "input_summary": {
            "casing": f'{od}" {weight_ppf} lb/ft {grade}',
            "setting_depth_tvd_ft": setting_depth_ft,
            "mud_weight_ppg": mud_weight_ppg,
            "pp_ppg": pore_pressure_ppg,
            "fg_ppg": fracture_gradient_ppg,
        },
        "geometry": {
            "od_in": round(od, 3),
            "id_in": round(id_in, 3),
            "wall_thickness_in": round(t, 3),
            "dt_ratio": round(dt, 2),
            "cross_section_sqin": round(area, 3),
        },
        "burst": {
            "rating_psi": round(burst_rating),
            "load_psi": round(burst_load),
            "design_factor": round(burst_df, 2),
            "minimum_required_df": 1.10,
            "status": "PASS" if burst_pass else "FAIL",
        },
        "collapse": {
            "rating_psi": round(collapse_rating),
            "regime": collapse_regime,
            "load_psi": round(collapse_load),
            "design_factor": round(collapse_df, 2),
            "minimum_required_df": 1.00,
            "status": "PASS" if collapse_pass else "FAIL",
        },
        "tension": {
            "rating_klbf": round(tension_rating_klbf, 1),
            "load_klbf": round(tension_load_klbf, 1),
            "design_factor": round(tension_df, 2),
            "minimum_required_df": 1.30,
            "status": "PASS" if tension_pass else "FAIL",
        },
        "maasp_psi": round(maasp),
        "pressure_window": {
            "pp_to_mw_margin_ppg": round(pp_margin, 2),
            "mw_to_fg_margin_ppg": round(fg_margin, 2),
            "total_window_ppg": round(window, 2),
            "assessment": "NARROW (<1.5 ppg) — managed pressure drilling candidate"
            if window < 1.5 else "ADEQUATE (≥1.5 ppg)",
        },
        "overall_status": overall,
        "warnings": warnings,
        "note": (
            "Burst: Barlow with 87.5% wall tolerance. "
            f"Collapse: API 5C3 ({collapse_regime} regime). "
            "Tension: pipe body yield, buoyed load. "
            "Validate all design factors in certified software before AFE approval."
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
    print(json.dumps(casing_design_checker(**payload), indent=2))


if __name__ == "__main__":
    main()
