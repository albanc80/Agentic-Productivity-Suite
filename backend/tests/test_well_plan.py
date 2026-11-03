"""PB-15 Well Plan Review: deterministic calculations feed the engineering review; engineer gate."""

import yaml

from app.contracts import Status
from tests.conftest import ROOT, agent_of, run_to_rest

PB = yaml.safe_load((ROOT / "playbooks" / "pb15-well-plan-review.yaml").read_text())
EXAMPLES = {i["id"]: i["example"] for i in PB["inputs"] if i.get("example")}
BASE = {"well": "Demo-1H lateral", "plan_summary": "9-5/8 in intermediate to 10,000 ft TVD; 8-1/2 in lateral to 15,500 ft MD."}


async def test_calculations_feed_review_and_engineer_gate(make_engine):
    eng, _local, cloud = make_engine()
    rid = await eng.start("well-plan-review", {**BASE, **EXAMPLES})
    run = await run_to_rest(eng, rid)
    assert run["status"] == "awaiting_approval"
    steps = {s["step_id"]: s for s in eng.store.steps(rid)}
    for sid in ("casing_check", "hydraulics_check", "td_check"):
        assert steps[sid]["status"] == "COMPLETE", steps[sid]
    review_call = next(c for c in cloud.calls if agent_of(c["system"]) == "Well Planning Advisor")
    user = review_call["messages"][0]["content"]
    assert '<data source="step:casing_check"' in user and '"burst"' in user and "suite_notice" in user
    assert "Safety-critical domain rules" in review_call["system"]
    tool_names = {t.name for t in review_call["tools"]}
    assert {"casing_design_checker", "hydraulics_solver", "torque_drag_simulator", "risk_matrix_generator"} <= tool_names
    apr = eng.store.approvals(status="pending", run_id=rid)[0]
    assert apr["required_role"] == "Qualified drilling engineer"
    await eng.decide(apr["id"], "approved", "R. Engineer, PE")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed" and "approved** by R. Engineer, PE" in run["deliverable"]


async def test_invalid_json_blocks_only_that_calculation(make_engine):
    eng, *_ = make_engine()
    rid = await eng.start("well-plan-review", {**BASE, "casing_json": "{not json", "hydraulics_json": EXAMPLES["hydraulics_json"]})
    await run_to_rest(eng, rid)
    steps = {s["step_id"]: s for s in eng.store.steps(rid)}
    assert steps["casing_check"]["status"] == "BLOCKED" and "not valid JSON" in steps["casing_check"]["warnings"][0]
    assert steps["hydraulics_check"]["status"] == "COMPLETE"
    assert steps["td_check"]["status"] == "skipped"
    apr = eng.store.approvals(status="pending", run_id=rid)[0]
    await eng.decide(apr["id"], "approved", "R. Engineer")
    run = await run_to_rest(eng, rid)
    assert run["outcome"] == Status.PARTIAL.value
    assert any("not valid JSON" in n for n in run["notes"])


async def test_wrong_calculator_fields_are_reported(make_engine):
    eng, *_ = make_engine()
    rid = await eng.start("well-plan-review", {**BASE, "casing_json": '{"casing_size_in": 9.625}'})
    await run_to_rest(eng, rid)
    step = next(s for s in eng.store.steps(rid) if s["step_id"] == "casing_check")
    assert step["status"] == "BLOCKED" and "invalid arguments" in step["warnings"][0]
