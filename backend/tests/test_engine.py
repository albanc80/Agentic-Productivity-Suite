import json

import pytest

from app.connectors import ConnectorConfig, ConnectorManager
from app.contracts import Status
from app.engine import RunStopped
from app.playbooks import Playbook, PlaybookError, validate
from app.providers import ProviderError
from app.providers.base import ToolCall
from tests.conftest import agent_of, contract, run_to_rest

SCOPE_INPUTS = {"request": "Add SSO export", "effort_hours": 40, "project": "Portal", "requester": "Ops lead"}


async def test_scope_change_parallel_review_revise_and_gate(make_engine):
    reviews = {"n": 0}

    def script(system, messages, tools):
        who = agent_of(system)
        if who == "Critical Mentor":
            reviews["n"] += 1
            verdict = "FAIL" if reviews["n"] == 1 else "PASS"
            return "Review.\n" + contract(verdict=verdict, findings=["Baseline missing"] if verdict == "FAIL" else [])
        if who == "Management Counselor":
            user = messages[0]["content"]
            tag = "REVISED" if "Reviewer findings to address" in user else "FIRST"
            return f"Recommendation {tag}: DEFER to Q1.\n" + contract()
        return f"{who} analysis.\n" + contract()

    eng, _local, cloud = make_engine(cloud_script=script)
    rid = await eng.start("scope-change", SCOPE_INPUTS)
    run = await run_to_rest(eng, rid)
    assert run["status"] == "awaiting_approval"
    steps = eng.store.steps(rid)
    done = {s["step_id"] for s in steps}
    assert {"cost_of_delay", "stakeholders", "schedule", "recommendation", "challenge"} <= done
    assert reviews["n"] == 2, "failed review triggers one revision and one re-review"
    rec = [s for s in steps if s["step_id"] == "recommendation"]
    assert [s["attempt"] for s in rec] == [1, 2] and "REVISED" in rec[-1]["deliverable"]
    # parallel children received the request; the counselor saw all three analyses
    counselor_call = next(c for c in cloud.calls if agent_of(c["system"]) == "Management Counselor")
    for sid in ("cost_of_delay", "stakeholders", "schedule"):
        assert f"Prior step `{sid}`" in counselor_call["messages"][0]["content"]
    # approval payload is the revised recommendation
    apr = eng.store.approvals(status="pending", run_id=rid)[0]
    assert "REVISED" in apr["payload"]
    with pytest.raises(ValueError, match="named approver"):
        await eng.decide(apr["id"], "approved", "  ")
    await eng.decide(apr["id"], "approved", "Jordan", note="ok", edited="Recommendation EDITED by human")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed" and run["outcome"] == Status.COMPLETE.value
    md = run["deliverable"]
    assert "Recommendation EDITED by human" in md
    assert "Independent review: PASS (Critical Mentor)" in md and "approved** by Jordan" in md
    assert run["cost_usd"] > 0 and run["tokens"] > 0


async def test_rejected_gate_stops_run(make_engine):
    eng, *_ = make_engine()
    rid = await eng.start("scope-change", SCOPE_INPUTS)
    await run_to_rest(eng, rid)
    apr = eng.store.approvals(status="pending", run_id=rid)[0]
    await eng.decide(apr["id"], "rejected", "Jordan", note="not now")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed" and run["outcome"] == Status.REJECTED.value


async def test_restricted_data_stays_local(make_engine):
    eng, local, cloud = make_engine()
    rid = await eng.start("quick-ask", {"request": "Summarise this"}, data_class="restricted")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed"
    assert cloud.calls == [] and len(local.calls) == 1
    step = eng.store.steps(rid)[0]
    assert step["model"] == "local/small"


async def test_blocked_when_no_allowed_model(make_engine, settings):
    eng, local, cloud = make_engine(tiers={t: ["cloud/big"] for t in ("router", "specialist", "synthesis", "review")})
    rid = await eng.start("quick-ask", {"request": "x"}, data_class="restricted")
    run = await run_to_rest(eng, rid)
    assert run["outcome"] == Status.BLOCKED.value
    assert any("not allowed for 'restricted'" in n for n in run["notes"])
    assert cloud.calls == []


async def test_fallback_to_next_model_on_provider_error(make_engine):
    eng, local, cloud = make_engine(cloud_script=lambda *a: ProviderError("HTTP 529 overloaded"))
    rid = await eng.start("quick-ask", {"request": "x"})
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed"
    step = eng.store.steps(rid)[0]
    assert step["model"] == "local/small" and any("fallback after" in w for w in step["warnings"])


async def test_contract_repair_path(make_engine):
    def script(system, messages, tools):
        last = messages[-1]["content"] if isinstance(messages[-1].get("content"), str) else ""
        return contract(status="COMPLETE") if "Return only the JSON handoff block" in last else "Plain answer without contract."
    eng, *_ = make_engine(cloud_script=script)
    rid = await eng.start("quick-ask", {"request": "x"})
    await run_to_rest(eng, rid)
    step = eng.store.steps(rid)[0]
    assert step["status"] == "COMPLETE" and step["deliverable"] == "Plain answer without contract."
    assert any("repair" in w for w in step["warnings"])


async def test_mcp_tool_loop_read_only_and_injection_flag(make_engine, tracker_connector):
    seen_tools = {}

    def script(system, messages, tools):
        if tools and not any(m.get("role") == "tool" for m in messages):
            seen_tools["names"] = sorted(t.name for t in tools)
            return [ToolCall(id="c1", name="github__get_issue", arguments={"key": "DEMO-1"}),
                    ToolCall(id="c2", name="github__create_issue", arguments={"title": "x"})]
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        seen_tools["results"] = tool_msgs
        return "Answer using the issue.\n" + contract(evidence="EXECUTED",
                                                      claims=[{"text": "Login fails", "label": "FACT", "trace": "github.get_issue DEMO-1"}])

    eng, *_ = make_engine(cloud_script=script, connectors=tracker_connector)
    try:
        rid = await eng.start("quick-ask", {"request": "What is DEMO-1?"})
        await run_to_rest(eng, rid)
    finally:
        await tracker_connector.shutdown()
    assert "github__create_issue" not in seen_tools["names"] and "github__get_issue" in seen_tools["names"]
    results = {m["tool_call_id"]: m for m in seen_tools["results"]}
    assert results["c1"]["content"].startswith('<data source="github.get_issue" trust="untrusted">')
    assert results["c2"]["is_error"] is True and "unknown tool" in results["c2"]["content"]
    step = eng.store.steps(rid)[0]
    assert any("prompt injection" in w for w in step["warnings"])
    assert step["tool_calls"][0]["tool"] == "github__get_issue"
    assert json.loads(json.dumps(step["output"]))["handoff"]["evidence"] == "EXECUTED"


async def test_connected_accounts_are_named_in_the_task(make_engine):
    from tests.test_connectors import _mail_server
    seen = {}

    def script(system, messages, tools):
        seen["user"] = messages[0]["content"]
        return "Done.\n" + contract()

    conns = ConnectorManager([ConnectorConfig(id="microsoft365", name="Microsoft 365", transport="stdio",
                                              command="unused", accounts={"param": "account", "vars": ["MS365_ACCOUNTS"]})],
                             env={"MS365_ACCOUNTS": "work@corp.com,me@home.net"}, in_process={"microsoft365": _mail_server()})
    eng, *_ = make_engine(cloud_script=script, connectors=conns)
    try:
        rid = await eng.start("quick-ask", {"request": "What is in my inbox?"})
        await run_to_rest(eng, rid)
    finally:
        await conns.shutdown()
    assert "Connected accounts:" in seen["user"]
    assert "Microsoft 365: work@corp.com (default), me@home.net" in seen["user"] and "`account` argument" in seen["user"]


async def test_fact_without_trace_downgraded_and_false_evidence_corrected(make_engine):
    eng, *_ = make_engine(cloud_script=lambda *a: "x\n" + contract(evidence="EXECUTED",
                                                                    claims=[{"text": "Revenue up 40%", "label": "FACT"}]))
    rid = await eng.start("quick-ask", {"request": "x"})
    await run_to_rest(eng, rid)
    h = eng.store.steps(rid)[0]["output"]["handoff"]
    assert h["claims"][0]["label"] == "ASSUMPTION" and h["evidence"] == "NOT_EXECUTED"


async def test_kill_switch_blocks_new_runs(make_engine):
    eng, *_ = make_engine()
    eng.set_kill_switch(True, "admin")
    with pytest.raises(RunStopped):
        await eng.start("quick-ask", {"request": "x"})
    eng.set_kill_switch(False, "admin")
    assert await eng.start("quick-ask", {"request": "x"})


async def test_budget_gate(make_engine, settings):
    eng, *_ = make_engine(budgets=settings.budgets.model_copy(update={"max_run_tokens": 100}))
    rid = await eng.start("prd", {"opportunity": "Self-serve export"})
    run = await run_to_rest(eng, rid)
    apr = eng.store.approvals(status="pending", run_id=rid)
    assert run["status"] == "awaiting_approval" and apr[0]["title"] == "Budget limit reached"
    await eng.decide(apr[0]["id"], "rejected", "Jordan")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "cancelled"


async def test_input_validation(make_engine):
    eng, *_ = make_engine()
    with pytest.raises(ValueError, match="Effort estimate"):
        await eng.start("scope-change", {"request": "x", "project": "p"})
    with pytest.raises(ValueError, match="must be a number"):
        await eng.start("scope-change", {**SCOPE_INPUTS, "effort_hours": "lots"})


async def test_conditional_parallel_steps_and_persona_off_for_documents(make_engine):
    eng, _l, cloud = make_engine()
    rid = await eng.start("decision-brief", {"decision": "Build or buy the scheduler", "lenses": ["architecture"]})
    await run_to_rest(eng, rid)
    status = {s["step_id"]: s["status"] for s in eng.store.steps(rid)}
    assert status["view_business"] == "skipped" and status["view_architecture"] == "COMPLETE"
    cos_call = next(c for c in cloud.calls if agent_of(c["system"]) == "Chief of Staff")
    assert "FIXTURE PERSONA" not in cos_call["system"]  # documents are written without persona by default


def test_reviewer_cannot_review_own_work(make_engine):
    eng, *_ = make_engine()
    pb = Playbook.model_validate({
        "id": "bad", "code": "X", "name": "Bad", "area": "x", "desk": "command", "summary": "x", "inputs": [],
        "steps": [{"id": "a", "kind": "agent", "agent": "critical-mentor", "task": "t"},
                  {"id": "r", "kind": "review", "agent": "critical-mentor", "target": "a"}],
        "deliverable": "a"})
    with pytest.raises(PlaybookError, match="review its own work"):
        validate(pb, eng.registry)
