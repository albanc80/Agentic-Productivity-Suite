"""Every playbook runs end to end on a scripted model: inputs validate, steps run, gates approve, deliverable assembled."""

import json

import pytest

from tests.conftest import ROOT, agent_of, contract, run_to_rest

PLAYBOOK_IDS = sorted(p.stem.split("-", 1)[1] for p in (ROOT / "playbooks").glob("pb*.yaml"))


def minimal_inputs(pb) -> dict:
    out = {}
    for i in pb.inputs:
        if i.type == "documents":
            continue
        if i.type == "number":
            out[i.id] = 8
        elif i.type == "select":
            out[i.id] = i.default if i.default is not None else i.options[0]
        elif i.type == "multiselect":
            out[i.id] = i.default or i.options[:1]
        elif i.required:
            out[i.id] = f"Test value for {i.label}"
    return out


def test_catalog_is_complete(make_engine):
    eng, _, _ = make_engine()
    codes = sorted(p.code for p in eng.playbooks.values())
    assert codes == [f"PB-{n:02d}" for n in range(19)]
    for pb in eng.playbooks.values():
        assert pb.status == "mvp" and pb.triggers and pb.summary
        reviews = [s for s in pb.flat_steps() if s.kind == "review"]
        if pb.id not in ("quick-ask", "daily-plan", "status-update"):  # short single-author outputs
            assert reviews, f"{pb.id} has no independent review"
        if pb.safety_critical:
            assert any(s.kind == "gate" and s.required_role for s in pb.steps), pb.id


@pytest.mark.parametrize("pid", PLAYBOOK_IDS)
async def test_playbook_runs_end_to_end(make_engine, pid):
    eng, local, cloud = make_engine()
    pb = eng.playbooks[pid]
    rid = await eng.start(pb.id, minimal_inputs(pb))
    run = await run_to_rest(eng, rid)
    for _ in range(5):
        if run["status"] != "awaiting_approval":
            break
        apr = eng.store.approvals(status="pending", run_id=rid)[0]
        await eng.decide(apr["id"], "approved", "Tester")
        run = await run_to_rest(eng, rid)
    assert run["status"] == "completed", (pid, run["status"], run["notes"])
    assert run["outcome"] in ("COMPLETE", "COMPLETE_WITH_ACCEPTED_RISK"), (pid, run["outcome"], run["notes"])
    assert "Deliverable text." in run["deliverable"]
    assert local.calls or cloud.calls


# Side-by-side specialists that must always run: the playbook exists to produce them.
ALWAYS_ON = {
    "ai-opportunity-to-agent": {"evaluation", "security"},  # the evaluation plan and threat model are its controls
    "well-plan-review": {"npt_view", "field_view"},  # safety-critical: the NPT and field/HSE challenge is never optional
}


def test_every_playbook_with_side_by_side_specialists_lets_the_person_choose_the_views(make_engine):
    """The start form offers a checklist of views wherever specialists work side by side, so the person decides
    which agents run; a view that is not ticked is skipped and named to the later steps."""
    eng, _, _ = make_engine()
    for pb in eng.playbooks.values():
        for group in (s for s in pb.steps if s.kind == "parallel"):
            for c in group.steps:
                if c.id in ALWAYS_ON.get(pb.id, set()):
                    assert c.when is None, f"{pb.id}/{c.id} must always run"
                    continue
                assert c.when, f"{pb.id}: the person cannot leave out '{c.title}'"
                if c.when.contains is not None:
                    inp = pb.input(c.when.input)
                    assert inp.type == "multiselect" and c.when.contains in inp.options, f"{pb.id}/{c.id}"
                    if inp.id == "views":  # PB-03's six lenses keep their own lighter default (two ticked)
                        assert c.when.contains in (inp.default or []), f"{pb.id}/{c.id}: views start ticked"
        card = pb.card()
        assert all("when" in s and all("when" in c for c in s["children"]) for s in card["steps"]), pb.id


# ---------------------------------------------------------------- a run waits for one of three responses

MODEL_KINDS = ("agent", "review")  # tool and connector steps run code, not a model: they never ask


def asks_every_step_once():
    """Every step that calls a model asks the person one question the first time it runs, then does its work."""
    asked: set = set()

    def script(system, messages, tools):
        key = (agent_of(system), messages[0]["content"][:400])
        if key not in asked:
            asked.add(key)
            return "I need one thing.\n" + contract(status="NEEDS_INPUT", open_questions=[f"Question from {key[0]}?"])
        return "Deliverable text.\n\n" + contract()
    return script


async def drive(eng, rid: str, choice: str) -> tuple[dict, list[dict]]:
    """Run to the end, giving `choice` at every input pause and approving every approval gate."""
    pauses = []
    for _ in range(100):
        run = await run_to_rest(eng, rid)
        if run["status"] != "awaiting_approval":
            return run, pauses
        apr = eng.store.approvals(status="pending", run_id=rid)[0]
        if not apr["step_id"].startswith("input:"):
            await eng.decide(apr["id"], "approved", "Tester")
            continue
        steps_before = len(eng.store.steps(rid))
        await eng.wait(rid)  # with no response nothing moves: still waiting, nothing more ran
        assert eng.store.run(rid)["status"] == "awaiting_approval" and len(eng.store.steps(rid)) == steps_before
        pauses.append(apr)
        n = sum(len(x["questions"]) for x in json.loads(apr["payload"]))
        if choice == "answer":
            await eng.answer(apr["id"], ["The person's answer"] * n, "Tester")
        else:
            await eng.answer(apr["id"], [], "Tester", skip=choice == "ignore", stop=choice == "stop")
    raise AssertionError("run did not finish")


@pytest.mark.parametrize("choice", ["answer", "ignore", "stop"])
@pytest.mark.parametrize("pid", PLAYBOOK_IDS)
async def test_every_playbook_waits_for_one_of_three_responses_at_every_step_that_asks(make_engine, pid, choice):
    """All playbooks, every model step: a step that needs input pauses the run, the run does not go on until the
    person answers, ignores and continues, or stops it, and each response does what it says."""
    script = asks_every_step_once()
    eng, _l, _c = make_engine(local_script=script, cloud_script=script)
    pb = eng.playbooks[pid]
    rid = await eng.start(pb.id, minimal_inputs(pb))
    run, pauses = await drive(eng, rid, choice)
    assert pauses, f"{pid}: no step paused for input"
    if choice == "stop":
        assert run["status"] == "cancelled" and len(pauses) == 1, (pid, run["status"])
        assert eng.store.approval(pauses[0]["id"])["note"] == "stopped the playbook"
        return
    assert run["status"] == "completed", (pid, choice, run["status"], run["notes"])
    rows = eng.store.steps(rid)
    ran = {r["step_id"] for r in rows if r["kind"] in MODEL_KINDS and r["status"] != "skipped"}
    asked = {x["step"] for p in pauses for x in json.loads(p["payload"])}
    assert ran == asked, f"{pid}: steps that ran without pausing for their question: {sorted(ran - asked)}"
    for sid in asked:  # each asking step ran again after the response and finished its work
        statuses = [r["status"] for r in rows if r["step_id"] == sid]
        assert statuses[0] == "superseded" and statuses[-1] == "COMPLETE", (pid, sid, statuses)
    key = "answers" if choice == "answer" else "unanswered"
    assert len(run["options"][key]) == sum(len(json.loads(p["payload"])) for p in pauses), (pid, choice)
    assert "Deliverable text." in run["deliverable"]


async def test_a_step_revised_after_a_failed_review_that_asks_also_waits(make_engine):
    """A FAIL review sends the step back; if the revision needs input, the run pauses before reviewing again,
    and after the response the step runs again, then the review."""
    reviews = []

    def script(system, messages, tools):
        user = messages[0]["content"]
        if agent_of(system) == "Critical Mentor":
            reviews.append(user)
            verdict = "FAIL" if len(reviews) == 1 else "PASS"
            return "Review.\n" + contract(verdict=verdict, findings=["The plan has no budget."] if verdict == "FAIL" else [])
        if "The plan has no budget." in user and "The person answered" not in user:
            return "Need the budget.\n" + contract(status="NEEDS_INPUT", open_questions=["What is the budget?"])
        return "Deliverable text.\n\n" + contract()

    eng, *_ = make_engine(local_script=script, cloud_script=script)
    rid = await eng.start("idea-to-opportunity", {"idea": "Pet spa franchise"})
    run = await run_to_rest(eng, rid)
    [apr] = eng.store.approvals(status="pending", run_id=rid)
    assert run["status"] == "awaiting_approval" and apr["step_id"] == "input:challenge:1"
    assert json.loads(apr["payload"])[0]["step"] == "plan" and len(reviews) == 1, "paused before reviewing again"
    await eng.answer(apr["id"], ["$250k"], "Tester")
    run = await run_to_rest(eng, rid)
    assert run["status"] == "completed", run["notes"]
    plans = [r for r in eng.store.steps(rid) if r["step_id"] == "plan"]
    assert [r["status"] for r in plans][-1] == "COMPLETE" and len(plans) == 3  # first, revision that asked, rerun
    assert len(reviews) == 2 and "A: $250k" in reviews[-1]
