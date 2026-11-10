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

    conns = ConnectorManager([ConnectorConfig(id="microsoft365", name="Microsoft 365", transport="stdio", enabled=True,
                                              command="unused", accounts={"param": "account", "vars": ["MS365_ACCOUNTS"]})],
                             env={"MS365_ACCOUNTS": "work@corp.com,me@home.net"}, in_process={"microsoft365": _mail_server()})
    eng, *_ = make_engine(cloud_script=script, connectors=conns)
    try:
        rid = await eng.start("quick-ask", {"request": "What is in my inbox?"})
        await run_to_rest(eng, rid)
    finally:
        await conns.shutdown()
    assert "Connected accounts and scope:" in seen["user"]
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
    eng, *_ = make_engine(budgets=settings.budgets.model_copy(update={"enabled": True, "max_run_tokens": 100}))
    rid = await eng.start("prd", {"opportunity": "Self-serve export"})
    run = await run_to_rest(eng, rid)
    apr = eng.store.approvals(status="pending", run_id=rid)
    assert run["status"] == "awaiting_approval" and apr[0]["title"] == "Budget limit reached"
    executed = len(eng.store.steps(rid))
    await eng.decide(apr[0]["id"], "rejected", "Jordan")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "cancelled"
    assert len(eng.store.steps(rid)) == executed, "a rejected budget stops the run before another step runs"


async def test_budget_approval_doubles_the_limit_and_asks_again(make_engine, settings):
    eng, *_ = make_engine(budgets=settings.budgets.model_copy(update={"enabled": True, "max_run_tokens": 100}))
    rid = await eng.start("prd", {"opportunity": "Self-serve export"})
    await run_to_rest(eng, rid)
    first = eng.store.approvals(status="pending", run_id=rid)[0]
    await eng.decide(first["id"], "approved", "Jordan")
    run = await run_to_rest(eng, rid)
    # one step uses 150 tokens: still over at 200, so the run asks again instead of running on
    pending = eng.store.approvals(status="pending", run_id=rid)
    assert run["status"] == "awaiting_approval" and pending[0]["step_id"] != first["step_id"]
    assert eng.store.run(rid)["options"]["budget_multiplier"] >= 2


async def test_spending_limits_are_off_by_default(make_engine, settings):
    assert settings.budgets.enabled is False
    eng, *_ = make_engine(budgets=settings.budgets.model_copy(update={"max_run_tokens": 100, "max_run_cost_usd": 0}))
    rid = await eng.start("prd", {"opportunity": "Self-serve export"})
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed" and not eng.store.approvals(run_id=rid)


async def test_spending_limit_stops_tool_calls_inside_a_step(make_engine, settings, tracker_connector):
    seen = []

    def script(system, messages, tools):
        if tools:
            return [ToolCall(id=f"c{len(seen)}", name="github__get_issue", arguments={"key": "DEMO-1"})]
        seen.append([m for m in messages if m.get("role") == "tool"])
        return "Answer.\n" + contract()

    eng, *_ = make_engine(cloud_script=script, connectors=tracker_connector,
                          budgets=settings.budgets.model_copy(update={"enabled": True, "max_run_tokens": 250}))
    try:
        rid = await eng.start("quick-ask", {"request": "What is DEMO-1?"})
        await run_to_rest(eng, rid)
    finally:
        await tracker_connector.shutdown()
    step = eng.store.steps(rid)[0]
    # 110 tokens per tool round: the third round crosses 250, so its call is not run and the model finishes
    assert len(step["tool_calls"]) == 2
    assert any("spending limit reached during this step" in w for w in step["warnings"])
    assert "spending limit for this run is reached" in seen[0][-1]["content"]


async def test_step_limit_is_enforced(make_engine, settings):
    eng, *_ = make_engine(budgets=settings.budgets.model_copy(update={"max_steps": 2}))
    with pytest.raises(ValueError, match="more than the step limit of 2"):
        await eng.start("prd", {"opportunity": "Self-serve export"})


async def test_step_limit_counts_revisions(make_engine, settings):
    reviews = {"n": 0}

    def script(system, messages, tools):
        if agent_of(system) == "Critical Mentor":
            reviews["n"] += 1
            return "Review.\n" + contract(verdict="FAIL", findings=["Baseline missing"])
        return "Work.\n" + contract()

    eng, *_ = make_engine(cloud_script=script)
    pb = eng.playbooks["scope-change"]
    n = sum(1 for s in pb.flat_steps() if s.kind != "gate")
    eng.s.budgets = settings.budgets.model_copy(update={"max_steps": n})  # fits, but not with the revision
    rid = await eng.start("scope-change", SCOPE_INPUTS)
    run = await run_to_rest(eng, rid)
    assert run["status"] == "cancelled"
    assert any("step limit reached" in note for note in run["notes"])


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


DECISION = {"decision": "Build or buy the scheduler", "options": "Buy Vendor X, or build in-house", "lenses": ["business"]}


def asks_once(system, messages, tools):
    user = messages[0]["content"]
    if agent_of(system) == "Chief of Staff" and "The person answered" not in user and "Frame the decision" in user:
        return "I need the budget.\n" + contract(status="NEEDS_INPUT", open_questions=["What is the budget ceiling?",
                                                                                     "Who owns the decision?"])
    return f"{agent_of(system)} work.\n" + contract()


async def test_a_step_that_needs_input_pauses_asks_and_runs_again_with_the_answers(make_engine):
    eng, _l, cloud = make_engine(cloud_script=asks_once)
    rid = await eng.start("decision-brief", DECISION)
    run = await run_to_rest(eng, rid)
    [apr] = eng.store.approvals(status="pending", run_id=rid)
    assert run["status"] == "awaiting_approval" and apr["title"] == "Your input is needed" and apr["step_id"] == "input:frame:1"
    need = json.loads(apr["payload"])
    assert need[0]["step"] == "frame" and need[0]["questions"] == ["What is the budget ceiling?", "Who owns the decision?"]
    assert not any(s["step_id"] == "view_business" for s in eng.store.steps(rid)), "nothing more is spent before the answer"
    await eng.answer(apr["id"], ["$250k", "The COO"], "Jordan")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed", run["notes"]
    frames = [s for s in eng.store.steps(rid) if s["step_id"] == "frame"]
    assert [s["status"] for s in frames] == ["superseded", "COMPLETE"] and frames[-1]["attempt"] == 2
    later = next(c for c in cloud.calls if agent_of(c["system"]) == "Business Analyst")
    assert "A: $250k" in later["messages"][0]["content"] and "A: The COO" in later["messages"][0]["content"]
    assert run["options"]["answers"][0] == {"step": "frame", "question": "What is the budget ceiling?", "answer": "$250k"}
    events = [e["event"] for e in eng.store.audit_log(rid)]
    assert "input_requested" in events and "input_given" in events


async def test_ignore_and_continue_reruns_the_step_without_the_answers_and_never_asks_again(make_engine):
    eng, _l, cloud = make_engine(cloud_script=asks_once)
    rid = await eng.start("decision-brief", DECISION)
    await run_to_rest(eng, rid)
    [apr] = eng.store.approvals(status="pending", run_id=rid)
    cloud.calls.clear()
    await eng.answer(apr["id"], [], "Jordan", skip=True)
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed" and any("Ignored the questions" in n for n in run["notes"])
    assert eng.store.approval(apr["id"])["note"] == "continued without answering"
    assert not eng.store.approvals(status="pending", run_id=rid), "a step the person chose to ignore never asks again"
    frames = [s for s in eng.store.steps(rid) if s["step_id"] == "frame"]
    assert [s["status"] for s in frames][0] == "superseded" and len(frames) == 2  # the asking step ran again
    rerun = next(c for c in cloud.calls if "Frame the decision" in c["messages"][0]["content"])["messages"][0]["content"]
    later = next(c for c in cloud.calls if agent_of(c["system"]) == "Business Analyst")["messages"][0]["content"]
    for text in (rerun, later):  # the step that asked, and every later step, adjust to what is missing
        assert "chose to go on without answering" in text and "- What is the budget ceiling?" in text
    assert run["options"]["unanswered"][0] == {"step": "frame", "question": "What is the budget ceiling?"}
    with pytest.raises(ValueError, match="already approved"):
        await eng.answer(apr["id"], ["x"], "Jordan")


async def test_stop_the_playbook_cancels_the_run(make_engine):
    eng, *_ = make_engine(cloud_script=asks_once)
    rid = await eng.start("decision-brief", DECISION)
    await run_to_rest(eng, rid)
    [apr] = eng.store.approvals(status="pending", run_id=rid)
    await eng.answer(apr["id"], [], "Jordan", stop=True)
    run = eng.store.run(rid)
    a = eng.store.approval(apr["id"])
    assert run["status"] == "cancelled" and a["status"] == "rejected" and a["note"] == "stopped the playbook"
    assert not any(s["step_id"] == "view_business" for s in eng.store.steps(rid)), "nothing more ran"
    assert any(e["event"] == "run_cancelled" for e in eng.store.audit_log(rid))


async def test_the_run_never_goes_on_by_itself(make_engine):
    """No answer, no going on: an empty reply is refused, and an agent that keeps asking keeps the run waiting
    (there used to be an automatic continue after two rounds)."""
    eng, *_ = make_engine(cloud_script=asks_once)
    rid = await eng.start("decision-brief", DECISION)
    await run_to_rest(eng, rid)
    [apr] = eng.store.approvals(status="pending", run_id=rid)
    with pytest.raises(ValueError, match="Ignore and continue, or Stop the playbook"):
        await eng.answer(apr["id"], ["", "  "], "Jordan")
    assert eng.store.approval(apr["id"])["status"] == "pending" and eng.store.run(rid)["status"] == "awaiting_approval"
    always = lambda system, messages, tools: "Need more.\n" + contract(status="NEEDS_INPUT", open_questions=["More?"])  # noqa: E731
    eng, *_ = make_engine(cloud_script=always)
    rid = await eng.start("quick-ask", {"request": "x"})
    for _ in range(3):
        run = await run_to_rest(eng, rid)
        assert run["status"] == "awaiting_approval"
        [apr] = eng.store.approvals(status="pending", run_id=rid)
        await eng.answer(apr["id"], ["answer"], "Jordan")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "awaiting_approval", "still waiting for the person"


async def test_unticked_views_and_blank_inputs_are_named_to_the_agents(make_engine):
    eng, _l, cloud = make_engine()
    rid = await eng.start("idea-to-opportunity", {"idea": "Pet spa franchise", "views": ["Value and sizing"]})
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed", run["notes"]
    steps = {s["step_id"]: s["status"] for s in eng.store.steps(rid)}
    assert steps["feasibility"] == "skipped" and steps["value"] != "skipped"
    assert not any(agent_of(c["system"]) == "Enterprise Architect" for c in cloud.calls)
    last = cloud.calls[-1]["messages"][0]["content"]
    assert "Not part of this run" in last and "Feasibility check" in last
    assert "Left blank by the person:" in cloud.calls[0]["messages"][0]["content"]


async def test_every_input_reaches_the_agents(make_engine):
    eng, _l, cloud = make_engine()
    rid = await eng.start("decision-brief", {**DECISION, "criteria": "cost and time", "deadline": "Friday"})
    await run_to_rest(eng, rid)
    first = cloud.calls[0]["messages"][0]["content"]
    # "Options" used to be dropped: it is neither named in a task nor treated as data.
    assert "Options you are considering (optional): Buy Vendor X, or build in-house" in first
    assert "Specialist views: business" in first and "Inputs from the person:" in first


async def test_a_playbook_step_gets_only_the_connectors_its_playbook_requires(make_engine):
    """Chat offers every connector that is on; a playbook step only the ones its playbook lists. quick-ask lists
    github (here the fake tracker server) but not 'mail', which is on and must not be offered."""
    from tests.fake_mcp_server import server
    seen = {}

    def script(system, messages, tools):
        seen.setdefault("names", sorted(t.name for t in tools or []))
        seen.setdefault("user", messages[0]["content"])
        return "Done.\n" + contract()

    conns = ConnectorManager([
        ConnectorConfig(id="github", name="GitHub", transport="stdio", command="unused", enabled=True,
                        context={"GITHUB_REPOS": "Repositories the person works in: {value}."}),
        ConnectorConfig(id="mail", name="Mail", transport="stdio", command="unused", enabled=True,
                        accounts={"param": "account", "vars": ["MAIL_ACCOUNTS"]}),
    ], env={"GITHUB_REPOS": "acme/app", "MAIL_ACCOUNTS": "me@corp.com"}, in_process={"github": server, "mail": server})
    eng, *_ = make_engine(cloud_script=script, connectors=conns)
    try:
        rid = await eng.start("quick-ask", {"request": "What is open?"})
        await run_to_rest(eng, rid)
    finally:
        await conns.shutdown()
    assert "github__list_issues" in seen["names"] and not any(n.startswith("mail__") for n in seen["names"])
    assert "GitHub: Repositories the person works in: acme/app." in seen["user"] and "me@corp.com" not in seen["user"]
    assert eng.store.steps(rid)[0]["status"] == "COMPLETE"
