#!/usr/bin/env python3
"""risk_matrix_generator — extracted from the Senior Well Planner tool library (tools.py).

Planning-grade estimate. Validate in certified software (certified engineering software or
equivalent) before AFE approval.

Usage:
    python risk_matrix_generator.py '<json-input>'
    python risk_matrix_generator.py --input params.json
    cat params.json | python risk_matrix_generator.py
"""

import json
import math
import sys
from typing import Any


# ── Risk matrix data ──────────────────────────────────────────────────────────

_LIKELIHOOD_BASE = {
    "well_control": 2, "geomechanics": 2, "mechanical": 3,
    "hydraulics": 2,  "HSE": 2,           "operational": 3, "geological": 2,
}

_SEVERITY_BASE = {
    "well_control": 5, "geomechanics": 4, "mechanical": 3,
    "hydraulics": 3,  "HSE": 4,           "operational": 3, "geological": 4,
}

# Keys matched case-insensitively (well_type is lower-cased before lookup).
_WELL_TYPE_MOD = {
    "hpht": 1, "deepwater": 1, "exploration": 1,
    "multilateral": 1, "horizontal_shale": 0, "injector": 0, "appraisal": 0,
}

_HIGH_RISK_WORDS = {
    "blowout", "kick", "lost circulation", "h2s", "well control",
    "collapse", "stuck", "sidetrack", "shallow gas", "overpressure",
    "fault", "salt", "hpht", "washout", "milling",
}

_MITIGATIONS = {
    "well_control": [
        "Install and pressure-test BOP stack per API 53 prior to each section",
        "Pre-spud and pre-POOH well control drills — IWCF-certified crew mandatory",
        "Continuous pit volume / flow monitoring — define kick tolerance per section",
        "Maintain kill-weight mud volume on standby at surface (1.5× well volume)",
    ],
    "geomechanics": [
        "Update pore pressure prognosis from offset logs and MDT data before spud",
        "Run PWD / EWD for real-time pore pressure and ECD monitoring",
        "Keep mud weight within ±0.3 ppg of design window midpoint",
        "Prepare wellbore stabilization pill recipe (inhibited PHPA / KCl) on standby",
    ],
    "mechanical": [
        "Full pre-run BHA inspection including DSTJ, float, and MWD surfaces",
        "Define vibration alert limits: MSE, surface torque, RPM, shock threshold",
        "Monitor trend: surface WOB vs bit WOB and T&D delta to detect stuck pipe early",
        "Pre-position fishing equipment (junk basket, overshot, jar) per well risk level",
    ],
    "hydraulics": [
        "Monitor ECD continuously with PWD — alert at ≥90% of fracture gradient",
        "Optimise flow rate for hole cleaning vs ECD — validate with hydraulics model",
        "Define max trip speed for surge/swab — confirm rig drawworks compliance",
        "Schedule wiper trips per programme — do not defer without engineering sign-off",
    ],
    "HSE": [
        "H2S monitoring: fixed detectors + personal monitors, escape sets at each station",
        "Enforce PTW and LoTo for all simultaneous operations (SIMOPS)",
        "Emergency response plan current, drilled within 30 days, posted at mustering point",
        "Environmental monitoring per regulatory requirements — zero discharge in sensitive areas",
    ],
    "operational": [
        "Conduct pre-spud multi-discipline planning meeting; distribute drilling programme",
        "Define go/no-go criteria for all critical operations — document in morning report",
        "Confirm weather window, supply chain, and critical spares before section start",
        "All contingency plans pre-approved and resourced before primary operation begins",
    ],
    "geological": [
        "Review offset well composite logs and integrate into formation-top prognosis",
        "Select MWD/LWD sensor suite for real-time formation evaluation and geosteering",
        "Define casing-point decision criteria with ±200 ft uncertainty band",
        "Identify contingency casing string and confirm availability in case of early kick",
    ],
}


def _risk_level(likelihood: int, severity: int) -> str:
    score = likelihood * severity
    if score >= 15:
        return "Critical"
    if score >= 8:
        return "High"
    if score >= 4:
        return "Medium"
    return "Low"


def _desc_severity_mod(description: str) -> int:
    lower = description.lower()
    return 1 if any(w in lower for w in _HIGH_RISK_WORDS) else 0


# ── Tool: risk_matrix_generator ───────────────────────────────────────────────

def risk_matrix_generator(hazards: list, well_type: str, phase: str) -> dict:
    wt_mod = _WELL_TYPE_MOD.get(well_type.lower().replace("-", "_"), 0)
    register = []

    for h in hazards:
        cat = h["category"]
        L = min(5, _LIKELIHOOD_BASE.get(cat, 2) + wt_mod)
        S = min(5, _SEVERITY_BASE.get(cat, 3) + _desc_severity_mod(h["description"]))
        level = _risk_level(L, S)
        mitigations = _MITIGATIONS.get(cat, ["Review and mitigate per operator standards"])[:3]

        register.append({
            "name": h["name"],
            "category": cat,
            "description": h["description"],
            "likelihood_1_5": L,
            "severity_1_5": S,
            "risk_score": L * S,
            "risk_level": level,
            "mitigations": mitigations,
            "contingency": (
                f"Escalate to Well Integrity Board if residual risk remains {level}; "
                "consider section redesign or POOH."
            ),
        })

    register.sort(key=lambda x: x["risk_score"], reverse=True)
    # Assign IDs after ranking so H-01 is the highest-scoring hazard.
    for idx, r in enumerate(register, start=1):
        r["hazard_id"] = f"H-{idx:02d}"

    counts = {lvl: sum(1 for r in register if r["risk_level"] == lvl)
              for lvl in ("Critical", "High", "Medium", "Low")}

    return {
        "tool": "risk_matrix_generator",
        "well_type": well_type,
        "phase": phase,
        "risk_register": register,
        "summary": {
            "total_hazards": len(register),
            **counts,
            "top_3_risks": [r["name"] for r in register[:3]],
            "overall_risk_rating": register[0]["risk_level"] if register else "N/A",
        },
        "note": (
            "Risk scores based on industry benchmarks and well-type modifiers. "
            "Validate against site-specific HAZID/HAZOP before operations."
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
    print(json.dumps(risk_matrix_generator(**payload), indent=2))


if __name__ == "__main__":
    main()
