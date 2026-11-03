"""Deterministic tools: no model involved, same input -> same output.

Agents may request these through tool calls; playbooks may run them as
``tool`` steps. A model can ask for a calculation but never supplies the number.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..contracts import HandoffIn, Label
from .calculators.casing_design_checker import casing_design_checker
from .calculators.hydraulics_solver import hydraulics_solver
from .calculators.risk_matrix_generator import risk_matrix_generator
from .calculators.torque_drag_simulator import torque_drag_simulator

PLANNING_GRADE = ("Planning-grade estimate from a deterministic calculator. Validate in certified "
                  "engineering software and have a qualified engineer approve before operational use.")


@dataclass
class DeterministicTool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]
    safety_critical: bool = False

    def run(self, arguments: dict) -> dict:
        try:
            result = self.fn(**arguments)
        except TypeError as e:
            return {"error": f"invalid arguments for {self.name}: {e}"}
        except (KeyError, ValueError, ZeroDivisionError) as e:
            return {"error": f"{self.name} could not compute: {type(e).__name__}: {e}"}
        if isinstance(result, dict) and self.safety_critical:
            result = {**result, "suite_notice": PLANNING_GRADE}
        return result if isinstance(result, dict) else {"result": result}


def evidence_validator(handoff: dict) -> dict:
    """Check a step's contract: FACT claims need a trace; flag what was downgraded."""
    h = HandoffIn.model_validate(handoff)
    downgraded, untraced_inferences = [], 0
    for c in h.claims:
        if c.label == Label.FACT and not (c.trace and c.trace.strip() and c.trace.strip().lower() not in {"null", "none", "n/a"}):
            downgraded.append(c.text[:160])
        if c.label != Label.FACT and not c.trace:
            untraced_inferences += 1
    counts = {lbl.value: sum(1 for c in h.claims if c.label == lbl) for lbl in Label}
    return {
        "claims": len(h.claims),
        "by_label": counts,
        "facts_without_trace": downgraded,
        "untraced_assumptions_or_inferences": untraced_inferences,
        "verdict": "PASS" if not downgraded else "FAIL",
        "note": "FACT claims without a trace are treated as ASSUMPTION in the final deliverable.",
    }


_NUM = {"type": "number"}

TOOLS: dict[str, DeterministicTool] = {
    t.name: t for t in [
        DeterministicTool(
            "casing_design_checker",
            "Burst, collapse (API 5C3 regimes) and tension design factors, MAASP and pressure window for one casing string. Planning grade.",
            {"type": "object", "required": ["casing_size_in", "weight_ppf", "grade", "setting_depth_ft", "pore_pressure_ppg",
                                            "fracture_gradient_ppg", "mud_weight_ppg"],
             "properties": {"casing_size_in": _NUM, "weight_ppf": _NUM, "grade": {"type": "string", "description": "e.g. N-80, P-110"},
                            "setting_depth_ft": _NUM, "pore_pressure_ppg": _NUM, "fracture_gradient_ppg": _NUM,
                            "mud_weight_ppg": _NUM, "well_type": {"type": "string"}}},
            casing_design_checker, safety_critical=True),
        DeterministicTool(
            "hydraulics_solver",
            "Bingham-plastic hydraulics: annular velocity, pressure losses, ECD, bit hydraulics and hole cleaning. Planning grade.",
            {"type": "object", "required": ["flow_rate_gpm", "mud_weight_ppg", "plastic_viscosity_cp", "yield_point_lbf100sqft",
                                            "hole_size_in", "drillpipe_od_in", "tvd_ft", "md_ft"],
             "properties": {"flow_rate_gpm": _NUM, "mud_weight_ppg": _NUM, "plastic_viscosity_cp": _NUM,
                            "yield_point_lbf100sqft": _NUM, "hole_size_in": _NUM, "drillpipe_od_in": _NUM, "tvd_ft": _NUM,
                            "md_ft": _NUM, "drillpipe_id_in": _NUM, "bit_nozzles": {"type": "array", "items": _NUM,
                                                                                     "description": "nozzle sizes in 32nds of an inch"},
                            "formation_angle_deg": _NUM}},
            hydraulics_solver, safety_critical=True),
        DeterministicTool(
            "torque_drag_simulator",
            "Soft-string torque and drag along a survey profile for tripping or drilling. Planning grade.",
            {"type": "object", "required": ["well_profile", "drillstring", "mud_weight_ppg", "wob_klbf", "operation"],
             "properties": {
                 "well_profile": {"type": "array", "items": {"type": "object", "required": ["md_ft", "inclination_deg", "azimuth_deg"],
                                                             "properties": {"md_ft": _NUM, "inclination_deg": _NUM, "azimuth_deg": _NUM}}},
                 "drillstring": {"type": "object", "required": ["pipe_od_in", "steel_weight_ppf"],
                                 "properties": {"pipe_od_in": _NUM, "steel_weight_ppf": _NUM}},
                 "mud_weight_ppg": _NUM, "wob_klbf": _NUM,
                 "operation": {"type": "string", "enum": ["tripping_in", "tripping_out", "rotating", "sliding"]},
                 "friction_factor_open": _NUM, "friction_factor_cased": _NUM, "casing_depth_ft": _NUM}},
            torque_drag_simulator, safety_critical=True),
        DeterministicTool(
            "risk_matrix_generator",
            "5x5 well risk matrix and ranked register with mitigations for a list of hazards. Planning grade.",
            {"type": "object", "required": ["hazards", "well_type", "phase"],
             "properties": {
                 "hazards": {"type": "array", "items": {"type": "object", "required": ["name", "category", "description"],
                                                        "properties": {"name": {"type": "string"}, "description": {"type": "string"},
                                                                       "category": {"type": "string", "enum": [
                                                                           "well_control", "geomechanics", "mechanical", "hydraulics",
                                                                           "HSE", "operational", "geological"]}}}},
                 "well_type": {"type": "string"}, "phase": {"type": "string"}}},
            risk_matrix_generator, safety_critical=True),
        DeterministicTool(
            "evidence_validator",
            "Checks a step's handoff contract: FACT claims must carry a trace.",
            {"type": "object", "required": ["handoff"], "properties": {"handoff": {"type": "object"}}},
            evidence_validator),
    ]
}


def run_tool(name: str, arguments: dict) -> str:
    if name not in TOOLS:
        return json.dumps({"error": f"unknown tool '{name}'"})
    return json.dumps(TOOLS[name].run(arguments), default=str)
