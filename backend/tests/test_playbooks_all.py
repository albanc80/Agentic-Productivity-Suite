"""Every playbook runs end to end on a scripted model: inputs validate, steps run, gates approve, deliverable assembled."""

import pytest

from tests.conftest import ROOT, run_to_rest

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
