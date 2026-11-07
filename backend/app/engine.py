"""Playbook execution engine.

Lifecycle of a run:  queued -> running -> (awaiting_approval -> running)* -> completed
                     with side exits: failed, cancelled, interrupted (server restart)

The run's cursor points at the next top-level step. Every step result is
persisted before the cursor moves, so a run can resume after a gate or a
restart without repeating finished work.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .connectors import MAX_AGENT_TOOLS, ConnectorError, ConnectorManager, setup_hints
from .contracts import HandoffIn, HandoffOut, Label, Status, parse_handoff, worst
from .guards import redact, scan_people_eval, wrap_data
from .outputs import Outputs
from .playbooks import Playbook, Step, render, render_args, resolve_window
from .prompts import build_system, build_user, fit
from .providers import ModelRouter, ProviderError, Resolved, ToolSpec, Usage
from .registry import Registry
from .settings import Settings
from .store import Store
from .tools import TOOLS, run_tool

log = logging.getLogger("suite.engine")

SKILL_TOOL = "suite__read_skill"
REPAIR_PROMPT = ("Return only the JSON handoff block for your answer above, in a ```json fence, following the "
                 "schema you were given. No other text.")


EDITED_ATTEMPT = 99  # step row recording an approver's edit; not an execution
INPUT_ROUNDS = 2  # times one step may stop to ask the person before the run goes on without
INPUT_PREFIX = "input:"  # approval step ids for "your input is needed"
SUPERSEDED = "superseded"  # a step result replaced by a rerun with the person's answers
BUDGET_NOTE = "The spending limit for this run is reached. Do not call tools. Finish now with what you have."


class RunStopped(Exception):
    """Raised to stop driving a run (cancel, kill switch, budget gate)."""


@dataclass
class StepResult:
    status: Status
    handoff: dict | None = None
    deliverable: str = ""
    data: str | None = None  # tool/connector output made available to later steps
    warnings: list[str] = field(default_factory=list)


@dataclass
class RunCtx:
    run: dict
    pb: Playbook
    inputs: dict
    outputs: dict[str, dict] = field(default_factory=dict)  # step_id -> {agent, handoff, deliverable, data, status}

    @property
    def id(self) -> str:
        return self.run["id"]

    @property
    def data_class(self) -> str:
        return self.run["data_class"]

    def template_ctx(self) -> dict:
        return {"inputs": self.inputs, "today": date.today().isoformat()}


class Engine:
    def __init__(self, settings: Settings, registry: Registry, playbooks: dict[str, Playbook], router: ModelRouter,
                 connectors: ConnectorManager, store: Store, profile: dict, outputs: Outputs | None = None):
        self.s = settings
        self.outputs = outputs or Outputs(None)
        self.registry = registry
        self.playbooks = playbooks
        self.router = router
        self.connectors = connectors
        self.store = store
        self.profile = profile
        self._tasks: dict[str, asyncio.Task] = {}

    # ================================================================ public API

    @property
    def killed(self) -> bool:
        return bool(self.store.get_setting("kill_switch", False))

    def set_kill_switch(self, on: bool, by: str) -> None:
        self.store.set_setting("kill_switch", on)
        self.store.audit("kill_switch", None, on=on, by=by)
        if on:
            for rid, t in list(self._tasks.items()):
                if not t.done():
                    t.cancel()
                    self.store.update_run(rid, status="cancelled")
                    self.store.add_note(rid, "Stopped by the kill switch.")

    def validate_inputs(self, pb: Playbook, raw: dict) -> tuple[dict, list[str]]:
        clean, errors = {}, []
        for inp in pb.inputs:
            v = raw.get(inp.id, inp.default)
            if isinstance(v, str):
                v = v.strip()
            if inp.required and v in (None, "", []):
                errors.append(f"'{inp.label}' is required")
                continue
            if v in (None, ""):
                clean[inp.id] = [] if inp.type in ("multiselect", "documents") else ""
                continue
            if inp.type == "number":
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    errors.append(f"'{inp.label}' must be a number")
                    continue
            if inp.type == "select" and inp.options and v not in inp.options:
                errors.append(f"'{inp.label}' must be one of {inp.options}")
                continue
            if inp.type in ("multiselect", "documents") and not isinstance(v, list):
                v = [v]
            if inp.type == "multiselect" and inp.options:
                bad = [x for x in v if x not in inp.options]
                if bad:
                    errors.append(f"'{inp.label}' has unknown options {bad}")
                    continue
            clean[inp.id] = v
        return clean, errors

    async def start(self, playbook_id: str, raw_inputs: dict, data_class: str | None = None,
                    options: dict | None = None) -> str:
        if self.killed:
            raise RunStopped("The kill switch is on. Turn it off in Settings to start runs.")
        pb = self.playbooks[playbook_id]
        inputs, errors = self.validate_inputs(pb, raw_inputs)
        if errors:
            raise ValueError("; ".join(errors))
        n_steps = sum(1 for s in pb.flat_steps() if s.kind != "gate")
        if n_steps > self.s.budgets.max_steps:
            raise ValueError(f"{pb.name} has {n_steps} steps, more than the step limit of {self.s.budgets.max_steps}. "
                             "Raise Max steps in Settings > Policies & budgets.")
        dc = data_class or self.s.default_data_class
        if dc not in self.s.data_classes:
            raise ValueError(f"unknown data class '{dc}'")
        opts = {"persona": self.s.persona.chat if pb.style == "chat" else self.s.persona.exports, **(options or {})}
        first = next((str(inputs.get(i.id)) for i in pb.inputs if i.required and i.type in ("text", "longtext")), pb.name)
        title = first[:90] + ("..." if len(first) > 90 else "")
        rid = self.store.create_run(pb.id, title, dc, inputs, opts)
        self.store.audit("run_started", rid, playbook=pb.id, data_class=dc, persona=opts["persona"])
        self._spawn(rid)
        return rid

    def _spawn(self, run_id: str) -> None:
        t = asyncio.create_task(self._drive(run_id), name=f"run:{run_id}")
        self._tasks[run_id] = t
        t.add_done_callback(lambda _t, rid=run_id: self._tasks.pop(rid, None))

    async def wait(self, run_id: str) -> None:
        t = self._tasks.get(run_id)
        if t:
            await asyncio.gather(t, return_exceptions=True)

    def cancel(self, run_id: str, by: str = "user") -> None:
        t = self._tasks.get(run_id)
        if t and not t.done():
            t.cancel()
        run = self.store.run(run_id)
        if run and run["status"] in ("queued", "running", "awaiting_approval", "interrupted"):
            self.store.update_run(run_id, status="cancelled")
            for a in self.store.approvals(status="pending", run_id=run_id):
                self.store.decide_approval(a["id"], "cancelled", by, "run cancelled", None)
            self.store.add_note(run_id, f"Cancelled by {by}.")
            self.store.audit("run_cancelled", run_id, by=by)

    async def decide(self, approval_id: str, decision: str, decided_by: str, note: str = "",
                     edited: str | None = None) -> dict:
        a = self.store.approval(approval_id)
        if not a:
            raise KeyError("approval not found")
        if a["status"] != "pending":
            raise ValueError(f"approval already {a['status']}")
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        if not decided_by.strip():
            raise ValueError("a named approver is required")
        self.store.decide_approval(approval_id, decision, decided_by.strip(), note, edited)
        self.store.audit("approval_decided", a["run_id"], approval=approval_id, step=a["step_id"],
                         decision=decision, by=decided_by.strip(), edited=bool(edited))
        run = self.store.run(a["run_id"])
        if run and run["status"] == "awaiting_approval":
            self.store.update_run(run["id"], status="running")
            self._spawn(run["id"])
        return self.store.approval(approval_id)

    def resume(self, run_id: str) -> None:
        run = self.store.run(run_id)
        if not run or run["status"] not in ("interrupted", "failed"):
            raise ValueError("only interrupted or failed runs can be resumed")
        if self.killed:
            raise RunStopped("The kill switch is on.")
        self.store.update_run(run_id, status="running")
        self.store.audit("run_resumed", run_id)
        self._spawn(run_id)

    def recover(self) -> None:
        """Mark runs that were executing when the server stopped."""
        for r in self.store.runs(limit=1000):
            if r["status"] in ("running", "queued"):
                self.store.update_run(r["id"], status="interrupted")
                self.store.add_note(r["id"], "The server stopped while this run was executing. Resume to continue.")

    # ================================================================ driver

    def _ctx(self, run_id: str) -> RunCtx:
        run = self.store.run(run_id)
        pb = self.playbooks[run["playbook_id"]]
        ctx = RunCtx(run=run, pb=pb, inputs=run["inputs"])
        for s in pb.flat_steps():
            row = self.store.latest_step(run_id, s.id)
            if row and row["status"] not in ("running", "error", SUPERSEDED):
                ctx.outputs[s.id] = {"agent": row["agent"], "status": row["status"], "deliverable": row["deliverable"] or "",
                                     "handoff": (row["output"] or {}).get("handoff"),
                                     "data": (row["output"] or {}).get("data"), "warnings": row["warnings"]}
        return ctx

    async def _drive(self, run_id: str) -> None:
        try:
            self.store.update_run(run_id, status="running")
            while True:
                ctx = self._ctx(run_id)
                cursor = ctx.run["cursor"]
                if cursor >= len(ctx.pb.steps):
                    break
                if self.killed:
                    raise RunStopped("kill switch")
                step = ctx.pb.steps[cursor]
                if self._budget_gate(ctx):  # before every step, so a rejection stops the run before more is spent
                    return
                paused = await self._top_step(ctx, step)
                if paused:
                    return
                self.store.update_run(run_id, cursor=cursor + 1)
            self._finish(run_id)
        except asyncio.CancelledError:
            raise
        except RunStopped as e:
            self.store.add_note(run_id, f"Run stopped: {e}")
            if self.store.run(run_id)["status"] == "running":
                self.store.update_run(run_id, status="cancelled")
        except Exception as e:  # noqa: BLE001 - a run must never take the server down
            log.exception("run %s failed", run_id)
            self.store.update_run(run_id, status="failed", outcome=Status.BLOCKED.value)
            self.store.add_note(run_id, f"Run failed: {type(e).__name__}: {redact(str(e))[:500]}")
            self.store.audit("run_failed", run_id, error=redact(str(e))[:500])

    async def _top_step(self, ctx: RunCtx, step: Step) -> bool:
        """Execute one top-level step. Returns True if the run paused at a gate."""
        if step.when and not step.when.holds(ctx.inputs):
            self._record_skip(ctx, step, "condition not met")
            return False
        if step.kind == "gate":
            return self._gate(ctx, step)
        if step.kind == "parallel":
            children = [c for c in step.steps if not c.when or c.when.holds(ctx.inputs)]
            for c in step.steps:
                if c not in children:
                    self._record_skip(ctx, c, "condition not met", parent=step.id)
            pending = [c for c in children if c.id not in ctx.outputs]
            if not pending:
                return False
            await asyncio.gather(*(self._run_step(ctx, c, parent=step.id) for c in pending))
            return self._input_gate(ctx, step, pending)
        if step.id in ctx.outputs:
            return False
        await self._run_step(ctx, step)
        if step.kind == "review":
            await self._maybe_revise(ctx, step)
        return self._input_gate(ctx, step, [step])

    # ================================================================ the person's input

    def _input_gate(self, ctx: RunCtx, top: Step, ran: list[Step]) -> bool:
        """Pause when a step says it needs the person's input. The run page asks the questions; the answers
        rerun those steps and are given to every later step. Continuing without answering is always possible."""
        need = []
        for s in ran:
            o = ctx.outputs.get(s.id) or {}
            if o.get("status") != Status.NEEDS_INPUT.value:
                continue
            qs = [str(q).strip() for q in (o.get("handoff") or {}).get("open_questions") or [] if str(q).strip()]
            need.append({"step": s.id, "title": s.title or s.id, "agent": s.agent,
                         "questions": qs[:5] or ["What information is missing for this step? (the agent named none)"]})
        if not need:
            return False
        rounds = [a for a in self.store.approvals(run_id=ctx.id) if a["step_id"].startswith(f"{INPUT_PREFIX}{top.id}:")]
        if len(rounds) >= INPUT_ROUNDS:
            self.store.add_note(ctx.id, f"'{top.title or top.id}' still needs input after {INPUT_ROUNDS} rounds of "
                                        "questions; the run continued with what it has.")
            return False
        names = ", ".join(self.registry.agents[n["agent"]].name for n in need if n.get("agent") in self.registry.agents)
        self.store.create_approval(
            ctx.id, f"{INPUT_PREFIX}{top.id}:{len(rounds) + 1}", "Your input is needed",
            f"{names or 'An agent'} needs more information to do this step well. Answer what you can and continue; "
            "the step runs again with your answers, and later steps see them too. You can also continue without answering.",
            None, json.dumps(need))
        self.store.update_run(ctx.id, status="awaiting_approval")
        self.store.audit("input_requested", ctx.id, step=top.id, questions=sum(len(n["questions"]) for n in need))
        return True

    async def answer(self, approval_id: str, answers: list[str], by: str, skip: bool = False) -> dict:
        """The person answered the questions of an input pause (or chose to continue without answering)."""
        a = self.store.approval(approval_id)
        if not a or not a["step_id"].startswith(INPUT_PREFIX):
            raise KeyError("input request not found")
        if a["status"] != "pending":
            raise ValueError(f"input request already {a['status']}")
        if self.killed:
            raise RunStopped("The kill switch is on.")
        need = json.loads(a["payload"] or "[]")
        questions = [(n, q) for n in need for q in n["questions"]]
        given = [(n, q, (answers[i] if i < len(answers) else "").strip()) for i, (n, q) in enumerate(questions)]
        answered = [g for g in given if g[2]]
        run = self.store.run(a["run_id"])
        if skip or not answered:
            self.store.decide_approval(approval_id, "approved", by or "you", "continued without answering", None)
            self.store.add_note(run["id"], "Continued without answering the questions.")
        else:
            prior = list(run["options"].get("answers") or [])
            prior += [{"step": n["step"], "question": q[:500], "answer": ans[:4000]} for n, q, ans in answered]
            self.store.update_run(run["id"], options={**run["options"], "answers": prior})
            for n in {n["step"] for n, _q, _a in answered}:  # rerun the steps that asked, now with the answers
                row = self.store.latest_step(run["id"], n)
                if row:
                    self.store.finish_step(row["id"], status=SUPERSEDED)
            self.store.decide_approval(approval_id, "approved", by or "you", f"{len(answered)} answer(s) given", None)
        self.store.audit("input_given", run["id"], approval=approval_id, answers=len(answered), skipped=bool(skip or not answered))
        if self.store.run(run["id"])["status"] == "awaiting_approval":
            self.store.update_run(run["id"], status="running")
            self._spawn(run["id"])
        return self.store.approval(approval_id)

    def _given_inputs(self, ctx: RunCtx) -> str:
        """Every input the person filled in, and every answer they gave, for the agent's task.
        Long text and files go in as untrusted data blocks instead (see _priors)."""
        lines = []
        for inp in ctx.pb.inputs:
            v = ctx.inputs.get(inp.id)
            if inp.is_data or v in (None, "", []):
                continue
            v = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
            lines.append(f"- {inp.label}: {v[:600]}")
        out = "Inputs from the person:\n" + "\n".join(lines) if lines else ""
        answers = ctx.run["options"].get("answers") or []
        if answers:
            out += ("\n\n" if out else "") + "The person answered these questions during the run (use them; they override assumptions):\n" + \
                "\n".join(f"- Q: {x['question']}\n  A: {x['answer']}" for x in answers)
        return out

    def _record_skip(self, ctx: RunCtx, step: Step, reason: str, parent: str | None = None) -> None:
        if step.id in ctx.outputs:
            return
        sid = self.store.start_step(ctx.id, step.id, step.kind, parent=parent, agent=step.agent, title=step.title)
        self.store.finish_step(sid, status="skipped", warnings=[reason])
        ctx.outputs[step.id] = {"status": "skipped", "deliverable": "", "handoff": None, "data": None, "agent": step.agent}

    # ================================================================ step kinds

    async def _run_step(self, ctx: RunCtx, step: Step, *, parent: str | None = None, attempt: int = 1,
                        feedback: list[str] | None = None) -> None:
        prev = self.store.latest_step(ctx.id, step.id)
        if attempt == 1 and prev and prev["status"] == SUPERSEDED:
            attempt = prev["attempt"] + 1  # rerun with the person's answers
        # Guardrail, always on: revisions and resumed steps count, so a run cannot loop without end.
        limit = self.s.budgets.max_steps
        done = sum(1 for r in self.store.steps(ctx.id)
                   if r["kind"] != "gate" and r["status"] != "skipped" and r["attempt"] != EDITED_ATTEMPT)
        if done >= limit:
            raise RunStopped(f"step limit reached ({limit} steps; Max steps in Settings > Policies & budgets)")
        sid = self.store.start_step(ctx.id, step.id, step.kind, parent=parent, agent=step.agent,
                                    title=step.title or step.id, attempt=attempt)
        try:
            if step.kind in ("agent", "review"):
                res = await self._agent(ctx, step, sid, feedback=feedback)
            elif step.kind == "tool":
                res = self._tool(ctx, step)
                self.store.finish_step(sid, status=res.status.value, output={"data": res.data, "handoff": res.handoff},
                                       warnings=res.warnings)
            elif step.kind == "connector":
                res = await self._connector(ctx, step)
                self.store.finish_step(sid, status=("skipped" if res.data is None else res.status.value),
                                       output={"data": res.data}, warnings=res.warnings)
            else:
                raise ValueError(f"unexpected step kind {step.kind}")
        except RunStopped:
            self.store.finish_step(sid, status="error", error="stopped")
            raise
        except Exception as e:  # noqa: BLE001
            self.store.finish_step(sid, status="error", error=redact(f"{type(e).__name__}: {e}")[:800])
            raise
        ctx.outputs[step.id] = {"agent": step.agent, "status": res.status.value, "deliverable": res.deliverable,
                                "handoff": res.handoff, "data": res.data, "warnings": res.warnings}

    def _tool(self, ctx: RunCtx, step: Step) -> StepResult:
        args = render_args(step.args, ctx.template_ctx(), ctx.outputs)
        if step.args_from_input:
            raw = ctx.inputs.get(step.args_from_input)
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError as e:
                parsed, err = None, f"line {e.lineno}, column {e.colno}: {e.msg}"
            else:
                err = None if isinstance(parsed, dict) else "expected a JSON object"
            if err:
                msg = f"'{step.args_from_input}' is not valid JSON ({err}); calculation not run"
                self.store.add_note(ctx.id, msg)
                return StepResult(status=Status.BLOCKED, data=json.dumps({"error": msg}), warnings=[msg],
                                  deliverable=msg)
            args = {**parsed, **args}
        out = json.loads(run_tool(step.tool, args))
        warnings = []
        status = Status.COMPLETE
        if "error" in out:
            status, warnings = Status.BLOCKED, [out["error"]]
        if step.tool == "evidence_validator" and out.get("facts_without_trace"):
            warnings.append(f"{len(out['facts_without_trace'])} FACT claim(s) had no trace and were downgraded to ASSUMPTION")
        return StepResult(status=status, data=json.dumps(out, indent=2), warnings=warnings,
                          deliverable=f"```json\n{json.dumps(out, indent=2)}\n```")

    async def _connector(self, ctx: RunCtx, step: Step) -> StepResult:
        cid = step.connector
        if not self.connectors.configured(cid):
            msg = f"Connector '{cid}' is not configured; step skipped."
            if not step.optional:
                raise ConnectorError(msg)
            self.store.add_note(ctx.id, msg)
            return StepResult(status=Status.PARTIAL, data=None, warnings=[msg])
        args = render_args(step.args, ctx.template_ctx(), ctx.outputs)
        text, is_error = await self.connectors.call(cid, step.tool, args)
        self.store.audit("connector_call", ctx.id, connector=cid, tool=step.tool, error=is_error)
        return StepResult(status=Status.PARTIAL if is_error else Status.COMPLETE, data=text,
                          warnings=[f"{cid}.{step.tool} returned an error"] if is_error else [])

    def _gate(self, ctx: RunCtx, step: Step) -> bool:
        existing = [a for a in self.store.approvals(run_id=ctx.id) if a["step_id"] == step.id]
        decided = next((a for a in existing if a["status"] in ("approved", "rejected")), None)
        if decided:
            sid = self.store.start_step(ctx.id, step.id, "gate", title=step.title)
            status = Status.COMPLETE if decided["status"] == "approved" else Status.REJECTED
            self.store.finish_step(sid, status=status.value, deliverable=decided.get("edited") or "",
                                   output={"handoff": {"status": status.value, "summary":
                                           f"{decided['status']} by {decided['decided_by']}" +
                                           (f": {decided['note']}" if decided.get("note") else "")}},
                                   warnings=[])
            if decided["status"] == "approved" and decided.get("edited") and step.payload_from:
                # The human edit becomes the authoritative version of that step's output.
                psid = self.store.start_step(ctx.id, step.payload_from, "agent", title="Edited by approver",
                                             agent=ctx.outputs.get(step.payload_from, {}).get("agent"), attempt=EDITED_ATTEMPT)
                prev = ctx.outputs.get(step.payload_from, {})
                self.store.finish_step(psid, status=prev.get("status", "COMPLETE"), deliverable=decided["edited"],
                                       output={"handoff": prev.get("handoff")},
                                       warnings=[f"edited by {decided['decided_by']} at approval"])
            if decided["status"] == "rejected":
                self.store.update_run(ctx.id, cursor=len(ctx.pb.steps))
                self.store.add_note(ctx.id, f"Rejected at gate '{step.title}' by {decided['decided_by']}.")
            return False
        if any(a["status"] == "pending" for a in existing):
            self.store.update_run(ctx.id, status="awaiting_approval")
            return True
        payload_step = step.payload_from or ctx.pb.deliverable
        payload = ctx.outputs.get(payload_step, {}).get("deliverable", "")
        instructions = render(step.instructions, ctx.template_ctx())
        self.store.create_approval(ctx.id, step.id, step.title, instructions, step.required_role, payload)
        self.store.update_run(ctx.id, status="awaiting_approval")
        self.store.audit("approval_requested", ctx.id, step=step.id, role=step.required_role)
        return True

    def _over_budget(self, run: dict, tokens: int = 0, cost: float = 0.0) -> list[str]:
        """What a run is over, counting ``tokens``/``cost`` not yet recorded. Empty when spending limits are off."""
        b = self.s.budgets
        if not b.enabled:
            return []
        mult = float(run["options"].get("budget_multiplier", 1))
        over = []
        if run["cost_usd"] + cost > b.max_run_cost_usd * mult:
            over.append(f"cost ${run['cost_usd'] + cost:.2f} > ${b.max_run_cost_usd * mult:.2f}")
        if run["tokens"] + tokens > b.max_run_tokens * mult:
            over.append(f"tokens {run['tokens'] + tokens} > {int(b.max_run_tokens * mult)}")
        return over

    def _budget_gate(self, ctx: RunCtx) -> bool:
        """Checked before every step. Over the limit, the run pauses: approve doubles the limit, reject stops it."""
        while True:
            run = self.store.run(ctx.id)
            over = self._over_budget(run)
            if not over:
                return False
            mult = float(run["options"].get("budget_multiplier", 1))
            gate_id = f"budget-{int(mult)}"
            existing = [a for a in self.store.approvals(run_id=ctx.id) if a["step_id"] == gate_id]
            if existing and existing[0]["status"] == "approved":
                self.store.update_run(ctx.id, options={**run["options"], "budget_multiplier": mult * 2})
                continue  # still over at the doubled limit: ask again
            if existing and existing[0]["status"] == "rejected":
                raise RunStopped("budget limit reached and continuation was rejected")
            if not existing:
                self.store.create_approval(ctx.id, gate_id, "Budget limit reached",
                                           "This run has used more than its budget (" + ", ".join(over) +
                                           "). Approve to double the limit and continue, or reject to stop.", None, "")
                self.store.audit("budget_gate", ctx.id, over=over)
            self.store.update_run(ctx.id, status="awaiting_approval")
            return True

    async def _maybe_revise(self, ctx: RunCtx, review: Step) -> None:
        out = ctx.outputs.get(review.id) or {}
        verdict = (out.get("handoff") or {}).get("verdict")
        if verdict != "FAIL" or review.on_fail != "revise":
            return
        if self.store.latest_step(ctx.id, review.target)["attempt"] > 1:
            return  # one revision only
        findings = (out.get("handoff") or {}).get("findings") or ["Reviewer marked the work FAIL; see review step."]
        self.store.add_note(ctx.id, f"Review '{review.id}' failed; '{review.target}' was revised once.")
        target = ctx.pb.step(review.target)
        await self._run_step(ctx, target, attempt=2, feedback=findings)
        await self._run_step(ctx, review, attempt=2)

    # ================================================================ agent steps

    def _priors(self, ctx: RunCtx, step: Step) -> tuple[list[tuple[str, str]], list[str], list[str]]:
        """Prior step deliverables, plus data blocks from inputs and tool/connector steps."""
        order = [s.id for s in ctx.pb.flat_steps()]
        here = order.index(step.id)
        refs = step.context_from if step.context_from is not None else [
            sid for sid in order[:here] if sid in ctx.outputs and ctx.pb.step(sid).kind in ("agent", "review", "tool", "connector")
        ]
        if step.kind == "review" and step.target not in refs:
            refs = [*refs, step.target]
        priors, data_blocks, flags = [], [], []
        for sid in refs:
            o = ctx.outputs.get(sid)
            if not o or o["status"] == "skipped":
                continue
            kind = ctx.pb.step(sid).kind
            if kind in ("tool", "connector"):
                if o.get("data"):
                    block, f, _ = wrap_data(f"step:{sid}", o["data"], self.s.budgets.max_tool_result_chars)
                    data_blocks.append(block)
                    flags += [f"step {sid}: {x}" for x in f]
                continue
            h = o.get("handoff") or {}
            claims = "\n".join(f"- [{c.get('label')}] {c.get('text')} (trace: {c.get('trace') or 'none'})"
                               for c in h.get("claims", [])[:20])
            extra = ""
            if h.get("verdict"):
                extra = f"\nReview verdict: {h['verdict']}\nFindings:\n" + "\n".join(f"- {f}" for f in h.get("findings", []))
            priors.append((sid, f"Agent: {o.get('agent')} | status: {o.get('status')}\n\n{o.get('deliverable', '')}"
                                f"\n\nKey claims:\n{claims or '- none'}{extra}"))
        for inp in ctx.pb.inputs:
            v = ctx.inputs.get(inp.id)
            if not inp.is_data or v in (None, "", []):
                continue
            if inp.type == "documents":
                for fid in v:
                    f = self.store.file(fid) if isinstance(fid, str) and fid.startswith("file_") else None
                    content = f["text"] if f else str(fid)
                    name = f"input:{inp.id}/{f['name']}" if f else f"input:{inp.id}"
                    block, fl, _ = wrap_data(name, content, 60_000)
                    data_blocks.append(block)
                    flags += [f"{name}: {x}" for x in fl]
            else:
                block, fl, _ = wrap_data(f"input:{inp.id}", str(v), 60_000)
                data_blocks.append(block)
                flags += [f"input {inp.id}: {x}" for x in fl]
        return priors, data_blocks, flags

    def _handoff(self, ctx: RunCtx) -> HandoffOut:
        i = ctx.inputs
        req = next((str(i[x.id]) for x in ctx.pb.inputs if x.required and i.get(x.id) not in (None, "", [])
                    and x.type in ("text", "longtext")), ctx.pb.name)
        constraints = i.get("constraints") or "NONE"
        return HandoffOut(request=req[:2000], scope=str(i.get("scope") or i.get("project") or "UNKNOWN"),
                          window=resolve_window(i.get("window") or i.get("date") or None, date.today()),
                          constraints=str(constraints)[:1000])

    async def _tool_specs(self, ctx: RunCtx, step: Step, agent_tools: list[str],
                          has_skills: bool) -> tuple[list[ToolSpec], dict, list[str], list[str]]:
        specs: list[ToolSpec] = []
        routes: dict[str, tuple[str, Any]] = {}
        notes: list[str] = []
        account_lines: list[str] = []
        # Only the connectors this playbook requires (chat offers every connector that is on): read-only, audited.
        room = MAX_AGENT_TOOLS - len(dict.fromkeys(step.tools + agent_tools)) - (1 if has_skills else 0)
        chosen = [c for c in step.connectors if c not in step.connector_when or step.connector_when[c].holds(ctx.inputs)]
        notes += [f"connector {c} not looked up: left out on the start form" for c in step.connectors if c not in chosen]
        found = await self.connectors.tools_for_agent(chosen, only=True, room=room)
        notes += found.notes
        account_lines += found.lines
        for t in found.tools:
            specs.append(ToolSpec(t.qualified, f"[{t.connector}, read-only] {t.description}", t.input_schema or {"type": "object"}))
            routes[t.qualified] = ("mcp", (t.connector, t.name))
        for name in dict.fromkeys(step.tools + agent_tools):
            t = TOOLS[name]
            specs.append(ToolSpec(name, t.description, t.parameters))
            routes[name] = ("tool", name)
        if has_skills:
            specs.append(ToolSpec(SKILL_TOOL, "Load the full text of a skill (or one of its resource files) listed in your instructions.",
                                  {"type": "object", "required": ["skill"],
                                   "properties": {"skill": {"type": "string"}, "resource": {"type": "string"}}}))
            routes[SKILL_TOOL] = ("skill", None)
        return specs, routes, notes, account_lines

    async def _exec_tool(self, ctx: RunCtx, routes: dict, name: str, args: dict, agent_skills: list[str]) -> tuple[str, bool, list[str]]:
        kind, target = routes.get(name, (None, None))
        if kind == "mcp":
            cid, tool = target
            try:
                text, is_error = await self.connectors.call(cid, tool, args)
            except ConnectorError as e:
                return str(e), True, []
            except Exception as e:  # noqa: BLE001 - one failing lookup never breaks the step
                return f"{cid}.{tool} failed: {type(e).__name__}: {e}"[:2000], True, []
            self.store.audit("connector_call", ctx.id, connector=cid, tool=tool, error=is_error)
            for hint in setup_hints(text):
                self.store.add_note(ctx.id, hint)
            block, flags, _ = wrap_data(f"{cid}.{tool}", text, self.s.budgets.max_tool_result_chars)
            return block, is_error, flags
        if kind == "tool":
            return run_tool(target, args), False, []
        if kind == "skill":
            sk = str(args.get("skill", ""))
            if sk not in agent_skills:
                return f"skill '{sk}' is not available to this agent", True, []
            try:
                return self.registry.skill_text(sk, args.get("resource") or None)[:40_000], False, []
            except (KeyError, PermissionError) as e:
                return str(e), True, []
        return f"unknown tool '{name}'", True, []

    async def _agent(self, ctx: RunCtx, step: Step, sid: str, feedback: list[str] | None) -> StepResult:
        agent = self.registry.agent(step.agent)
        review = step.kind == "review"
        tier = step.tier or ("review" if review else agent.default_tier)
        candidates, skipped = self.router.candidates(tier, ctx.data_class, agent_id=agent.id, override=step.models)
        if not candidates:
            msg = (f"No model configured for this step (tier '{tier}', data class '{ctx.data_class}'). "
                   "Add or switch on a model in Settings, then run again."
                   + (" Checked: " + "; ".join(skipped) if skipped else ""))
            self.store.finish_step(sid, status=Status.BLOCKED.value, error=msg, warnings=skipped)
            self.store.add_note(ctx.id, msg)
            return StepResult(status=Status.BLOCKED, handoff={"status": "BLOCKED", "summary": msg}, deliverable=msg, warnings=[msg])

        priors, data_blocks, inj_flags = self._priors(ctx, step)
        task = render(step.task or "Review the target step's output against its task and the inputs.", ctx.template_ctx())
        given = self._given_inputs(ctx)
        if given:
            task = task.rstrip() + "\n\n" + given
        task += ("\n\nIf you cannot do this step well without an answer only the person can give, set status NEEDS_INPUT "
                 "and put up to five short, specific questions in open_questions; the run pauses, asks them, and runs this "
                 "step again with the answers. Otherwise do the step and list remaining questions as usual.")
        handoff = self._handoff(ctx)
        warnings: list[str] = [f"possible prompt injection in {f}" for f in inj_flags]
        errors: list[str] = []
        for cand in candidates:
            if self.killed:
                raise RunStopped("kill switch")
            try:
                pre = warnings + [f"fallback after: {e}" for e in errors]
                return await self._converse(ctx, step, agent, cand, task, handoff, priors, data_blocks, review,
                                            feedback, sid, pre)
            except ProviderError as e:
                errors.append(f"{cand.ref}: {redact(str(e))[:300]}")
                log.warning("step %s provider error: %s", step.id, e)
        msg = "All candidate models failed: " + " | ".join(errors)
        self.store.finish_step(sid, status=Status.BLOCKED.value, error=msg, warnings=warnings)
        return StepResult(status=Status.BLOCKED, handoff={"status": "BLOCKED", "summary": msg}, deliverable=msg, warnings=[msg])

    async def _converse(self, ctx: RunCtx, step: Step, agent, cand: Resolved, task: str, handoff: HandoffOut,
                        priors, data_blocks, review: bool, feedback, sid: str, pre_warnings: list[str]) -> StepResult:
        use_tools = cand.model.tools
        agent_tools = agent.tools if use_tools else []
        specs, routes, tool_notes, account_lines = ([], {}, [], [])
        on_demand = [s for s in agent.skills if s not in agent.core_skills + step.skills]
        if use_tools:
            specs, routes, tool_notes, account_lines = await self._tool_specs(ctx, step, agent_tools, bool(on_demand))
        elif step.connectors or step.tools:
            tool_notes.append(f"{cand.ref} has no tool calling; connectors and tools were not used in this step")

        persona = bool(ctx.run["options"].get("persona"))
        system = build_system(agent=agent, mode=step.mode, registry=self.registry, policies=self.s.output_policies,
                              profile=self.profile, persona=persona, extra_skills=step.skills,
                              has_skill_tool=SKILL_TOOL in routes, review=review)
        if account_lines:
            task = task.rstrip() + "\n\nConnected accounts and scope:\n" + "\n".join(account_lines)
        user = build_user(handoff=handoff, task=task, priors=priors, data_blocks=data_blocks,
                          review_target=step.target if review else None, feedback=feedback)
        tool_tokens = sum(len(json.dumps(t.parameters)) + len(t.description) for t in specs) // 3
        budget = int(cand.model.context_tokens * self.s.budgets.max_context_fraction) - cand.model.max_output_tokens - tool_tokens
        parts = fit(system, user, budget_tokens=max(budget, 1500))
        warnings = list(pre_warnings) + list(tool_notes) + [f"context fit for {cand.ref}: {c}" for c in parts.cuts]

        provider = cand.provider
        conv = provider.start(parts.system, parts.user)
        usage = Usage()
        tool_log: list[dict] = []
        calls_made = 0
        latency = 0
        max_calls = self.s.budgets.max_tool_calls_per_step
        result = None
        out_of_budget = False
        for _round in range(max_calls + 2):
            if self.killed:
                raise RunStopped("kill switch")
            offer = specs if (specs and calls_made < max_calls and not out_of_budget) else None
            result = await provider.chat(conv, model=cand.model.model, tools=offer,
                                         max_tokens=cand.model.max_output_tokens, effort=cand.model.effort)
            usage += result.usage
            latency += result.latency_ms
            if not result.tool_calls or not offer:
                break
            provider.add_assistant(conv, result)
            # Spending limit, checked before every further model call: once over, the model finishes without tools.
            over = self._over_budget(self.store.run(ctx.id), usage.input_tokens + usage.output_tokens + usage.cache_read_tokens,
                                     cand.cost(usage))
            if over:
                out_of_budget = True
                warnings.append("spending limit reached during this step (" + ", ".join(over) +
                                "); the model was asked to finish without more tool calls")
                provider.add_tool_results(conv, [(c.id, BUDGET_NOTE, True) for c in result.tool_calls])
                continue
            outputs = []
            for call in result.tool_calls[: max_calls - calls_made]:
                content, is_err, flags = await self._exec_tool(ctx, routes, call.name, call.arguments, agent.skills)
                calls_made += 1
                warnings += [f"possible prompt injection in {call.name} result: {f}" for f in flags]
                tool_log.append({"tool": call.name, "arguments": json.loads(redact(json.dumps(call.arguments))),
                                 "error": is_err, "chars": len(content)})
                outputs.append((call.id, content, is_err))
            for call in result.tool_calls[len(outputs):]:
                outputs.append((call.id, "Tool budget for this step is used up. Finish with what you have.", True))
            provider.add_tool_results(conv, outputs)
            if calls_made >= max_calls:
                warnings.append(f"tool-call limit ({max_calls}) reached")

        text = result.text if result else ""
        h, deliverable = parse_handoff(text)
        if h is None:
            warnings.append("response had no valid contract block; asked the model to repair it")
            provider.add_assistant(conv, result)
            provider.add_user(conv, REPAIR_PROMPT)
            fix = await provider.chat(conv, model=cand.model.model, tools=None, max_tokens=2000, effort=cand.model.effort)
            usage += fix.usage
            h2, _ = parse_handoff(fix.text)
            h = h2 or HandoffIn(status=Status.PARTIAL, summary="The model did not return a structured contract.")
            if h2 is None:
                warnings.append("contract repair failed; step marked PARTIAL")
            h.deliverable = deliverable

        # Evidence discipline: FACT needs a trace.
        downgraded = 0
        for c in h.claims:
            if c.label == Label.FACT and not (c.trace and c.trace.strip().lower() not in {"", "null", "none", "n/a"}):
                c.label, downgraded = Label.ASSUMPTION, downgraded + 1
        if downgraded:
            warnings.append(f"{downgraded} FACT claim(s) without a trace downgraded to ASSUMPTION")
        if not calls_made and h.evidence == "EXECUTED":
            h.evidence = "NOT_EXECUTED"
            warnings.append("model claimed executed evidence without any tool call; corrected to NOT_EXECUTED")
        people = scan_people_eval(deliverable)
        if people:
            warnings.append("deliverable contains language that characterises people (" + ", ".join(people) +
                            "); review before sharing")
            self.store.add_note(ctx.id, f"People-evaluation language flagged in step '{step.id}'.")
        if review and h.verdict is None:
            h.verdict = "PASS_WITH_CHANGES"
            warnings.append("review returned no verdict; recorded as PASS_WITH_CHANGES")
        cost = cand.cost(usage)
        self.store.add_run_usage(ctx.id, usage.input_tokens + usage.output_tokens + usage.cache_read_tokens, cost)
        prompt_text = parts.system + "\n\n-----\n\n" + parts.user
        hd = h.model_dump(mode="json", exclude={"deliverable"})
        self.store.finish_step(
            sid, status=h.status.value, provider=cand.config.type + ":" + cand.ref.split("/", 1)[0], model=cand.ref,
            tokens_in=usage.input_tokens + usage.cache_read_tokens, tokens_out=usage.output_tokens, cost_usd=cost,
            latency_ms=latency, prompt_chars=parts.chars,
            prompt=prompt_text if self.s.store_prompts else "sha256:" + hashlib.sha256(prompt_text.encode()).hexdigest(),
            output={"handoff": hd}, deliverable=deliverable, warnings=warnings, tool_calls=tool_log,
        )
        self.store.audit("model_call", ctx.id, step=step.id, model=cand.ref, locality=cand.config.locality,
                         tokens=usage.input_tokens + usage.output_tokens, tools=calls_made)
        return StepResult(status=h.status, handoff=hd, deliverable=deliverable, warnings=warnings)

    # ================================================================ assembly

    def _finish(self, run_id: str) -> None:
        ctx = self._ctx(run_id)
        statuses: list[Status] = []
        for s in ctx.pb.flat_steps():
            o = ctx.outputs.get(s.id)
            if not o or o["status"] in ("skipped",) or s.kind == "parallel":
                continue
            if s.kind in ("tool", "connector"):
                if o["status"] == Status.BLOCKED.value:
                    statuses.append(Status.PARTIAL)  # a failed calculation or fetch weakens the result
                continue
            try:
                statuses.append(Status(o["status"]))
            except ValueError:
                continue
        outcome = worst(statuses)
        reviews = [o for s in ctx.pb.flat_steps() if s.kind == "review" and (o := ctx.outputs.get(s.id))]
        if any((r.get("handoff") or {}).get("verdict") == "FAIL" for r in reviews) and outcome in (
                Status.COMPLETE, Status.COMPLETE_WITH_ACCEPTED_RISK):
            outcome = Status.PARTIAL
        md = self.assemble(ctx, outcome)
        self.store.update_run(run_id, status="completed", outcome=outcome.value, deliverable=md)
        self.store.audit("run_completed", run_id, outcome=outcome.value)
        self.outputs.save_run(self.store.run(run_id))

    def assemble(self, ctx: RunCtx, outcome: Status) -> str:
        run = self.store.run(ctx.id)
        main = ctx.outputs.get(ctx.pb.deliverable) or {}
        h = main.get("handoff") or {}
        steps = self.store.steps(ctx.id)
        models = sorted({s["model"] for s in steps if s.get("model")})
        lines = [f"# {ctx.pb.name}", "", f"**{run['title']}**", "",
                 f"> Outcome: **{outcome.value}** · Data class: {run['data_class']} · Models: {', '.join(models) or 'none'}"
                 f" · Tokens: {run['tokens']:,}", ""]
        if h.get("summary"):
            lines += ["## Summary", "", h["summary"], ""]
        lines += [main.get("deliverable") or "_No deliverable was produced._", ""]
        for s in ctx.pb.flat_steps():
            if s.kind != "review":
                continue
            o = ctx.outputs.get(s.id)
            if not o or o["status"] == "skipped":
                continue
            rh = o.get("handoff") or {}
            reviewer = self.registry.agents.get(o.get("agent") or "")
            lines += [f"## Independent review: {(rh.get('verdict') or 'n/a').replace('_', ' ')} "
                      f"({reviewer.name if reviewer else o.get('agent')})", ""]
            lines += [f"- {f}" for f in rh.get("findings", [])] or ["- No findings recorded."]
            lines.append("")
        claims = h.get("claims") or []
        if claims:
            lines += ["## Claims and evidence", "", "| Label | Claim | Trace |", "|---|---|---|"]
            lines += [f"| {c.get('label')} | {_cell(c.get('text'))} | {_cell(c.get('trace') or '-')} |" for c in claims]
            lines.append("")
        risks = h.get("risks") or []
        if risks:
            lines += ["## Risks", "", "| Severity | Risk | Mitigation |", "|---|---|---|"]
            lines += [f"| {r.get('severity')} | {_cell(r.get('risk'))} | {_cell(r.get('mitigation') or '-')} |" for r in risks]
            lines.append("")
        if h.get("open_questions"):
            lines += ["## Open questions", ""] + [f"- {q}" for q in h["open_questions"]] + [""]
        na = h.get("next_action") or {}
        if na.get("action"):
            lines += ["## Next action", "", f"{na['action']} (owner: {na.get('owner') or 'UNKNOWN'}"
                      + (f"; gate: {na['gate']}" if na.get("gate") else "") + ")", ""]
        approvals = self.store.approvals(run_id=ctx.id)
        if approvals:
            lines += ["## Approvals", ""]
            lines += [f"- {a['title']}: **{a['status']}**" + (f" by {a['decided_by']}" if a.get("decided_by") else "")
                      + (f" ({a['decided_at']})" if a.get("decided_at") else "") + (f": {a['note']}" if a.get("note") else "")
                      for a in approvals]
            lines.append("")
        notes = list(run["notes"])
        for s in steps:
            for w in s.get("warnings") or []:
                notes.append(f"{s['step_id']}: {w}")
        if notes:
            lines += ["## Run notes", ""] + [f"- {n}" for n in dict.fromkeys(notes)] + [""]
        return "\n".join(lines)


def _cell(text: Any) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")[:400]
