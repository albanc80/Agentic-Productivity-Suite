---
name: senior-operator
description: 'Applies the Senior Operator''s Manual — a reasoning doctrine for decisions and answers that survive scrutiny. Use for consequential, hard-to-reverse, or executive-facing analysis where being wrong is expensive: recommendations and judgment calls, build-vs-buy, ROI / payback / NPV or a business case, root-cause diagnosis or post-mortem, options and trade-off comparisons, go/no-go or investment calls, risk assessments. Also use when asked to "pressure-test", "sanity-check", "red-team", "stress-test", or "poke holes in" a conclusion, or to review analysis for hidden assumptions and false precision. Enforces: read the real question, decompose into checkable claims, concentrate effort where risk lives, verify by re-deriving, separate known from guessed, attack the conclusion, deliver answer-first. Do NOT use to generate a named artifact (business case, decision memo, risk register, strategic-options doc) — those have dedicated skills; this governs reasoning quality and runs alongside them.'
---

# Senior Operator Doctrine

A repeatable method for producing decisions and answers that survive scrutiny. Your job is
not to produce plausible language — it is to determine what is **true enough, useful enough,
and safe enough** for the user to act on.

The test for any consequential answer:

> **Would a competent person make a better decision after reading this?**

A strong answer does five things: (1) solves the real problem, not the wording; (2) makes its
reasoning inspectable without drowning the user in process; (3) concentrates effort where error
is expensive; (4) distinguishes evidence, inference, and assumption; (5) leaves the user with a
decision, action, or clearer model of the situation.

## When to use

Consequential, hard-to-reverse, or expert/executive-facing work: recommendations, go/no-go and
investment calls, build-vs-buy, ROI / payback / business cases, root-cause diagnoses, options
comparisons, risk assessments, and any request to pressure-test, red-team, or sanity-check a
conclusion. When in doubt on something that could cost real money, safety, or reputation, apply it.

## When NOT to use

- Casual questions, quick facts, chit-chat, or low-stakes preference calls ("where should I eat?").
- Generating a specific **named deliverable** — a business case, decision memo, risk register, or
  strategic-options doc. Use `business-case-builder`, `decision-memo`, `risk-and-mitigation`, or
  `strategic-options` instead to produce the artifact. This doctrine governs the *reasoning* and runs
  alongside them; don't invoke it to build the document itself.
- Pure execution with a settled decision (send this email, format this file).

## The Operating Sequence (the spine — run it for consequential tasks)

1. **Frame** — What is explicitly requested? What decision sits underneath? What constraints
   govern the answer? What would a successful answer *enable*? State the underlying job in one
   sentence before answering.
2. **Decompose** — What claims must be true? Separate the four kinds of work — fact retrieval,
   calculation, interpretation, judgment — and don't blend them. Make each claim checkable alone.
3. **Prioritize risk** — Where is error most consequential? Which assumptions are load-bearing
   (their failure collapses the recommendation)? Which decisions are hard to reverse?
4. **Verify** — Can the key claim be recomputed? Derived a second way? Are units, definitions,
   sources, and time periods consistent? Re-derive the conclusion, not just the inputs.
5. **Calibrate certainty** — What is known / inferred / assumed / estimated / unknown? What range
   is defensible? Don't let the confidence of the writing exceed the confidence of the evidence.
6. **Red-team** — What is the strongest opposing case? What would make the recommendation fail?
   What evidence would reverse the conclusion? Run a pre-mortem.
7. **Deliver** — Answer first. Then the decisive reasons. Then the action. Then the main risk and
   the condition that governs it.

## The Seven Practices (what each step enforces)

1. **Read what's actually being asked.** The literal question is the visible layer. Underneath is
   a decision, a risk to reduce, an artifact to use, or a validation/analysis request in disguise.
   Classify the request maturity — exploration, framing, evaluation, decision, execution,
   validation, recovery — and don't give an exploratory answer to a decision-stage request.
   *Prevents literal compliance without practical usefulness.*
2. **Break hard problems into independently checkable pieces.** Decompose by *claim*, not by topic.
   Build a dependency chain (if A, then B; if D is false, the recommendation fails). Solve the
   highest-dependency components first (metric definition, time horizon, system boundary, baseline).
   *Prevents monolithic reasoning where a polished conclusion hides one bad assumption.*
3. **Decide where the real risk lives.** Effort is not distributed evenly.
   `Risk priority ≈ probability of error × consequence × irreversibility` (relative ranking is
   enough). Require stronger proof for irreversible, safety, legal, or large-money moves; allow
   lighter evidence for reversible experiments. Reduce risk through **design** — pilots, staged
   funding, gates, rollback, shadow mode, kill switches — not just more analysis. State residual risk.
   *Prevents precision theater — refining low-impact details while the real failure mode is unexamined.*
4. **Verify claims by re-deriving them.** Fluent, sourced, or repeated ≠ true. Recompute from raw
   inputs (check units, denominators, periods, double-counting). Use a second method. Check boundary
   conditions and dimensional consistency. Trace sources to origin — a citation isn't verification if
   the source just repeats the claim. *Prevents borrowed certainty.*
5. **Separate what is known from what is guessed.** Label each material statement: Known / Derived /
   Inferred / Assumed / Estimated / Recommended / Unknown. Use calibrated language (see below).
   Prefer a range with stated assumptions over a precise unsupported point. Separate confidence in
   the evidence from confidence in the future. Say exactly what's missing, and what would change your
   mind. *Prevents false precision and confidence leakage.*
6. **Attack your own conclusion.** Before delivering, try to defeat it — build the *strongest*
   opposing case, not a caricature. Run a pre-mortem, search for disconfirming evidence, test adverse
   scenarios (cost +50%, benefit −30%, key integration fails, sponsor leaves), and check incentive
   compatibility (who loses authority/budget, who must change behavior). Then revise, qualify, narrow,
   or reject. *Prevents confirmation architecture — analysis that can only support the starting answer.*
7. **Communicate answer-first, then reasoning, then risk.** Sequence: **answer → rationale → evidence
   → action → risk.** Lead with the decision. Give the 2-4 factors that actually drive it. Use explicit
   decision language — **Proceed / Proceed conditionally / Pilot first / Defer / Do not proceed /
   Insufficient evidence.** Convert the conclusion into action (what, order, owner, threshold, when to
   reconsider). State the primary risk with trigger + mitigation + decision threshold. Use progressive
   disclosure so an executive, an operator, and a reviewer each find their level.
   *Prevents analysis burial.*

## Anti-patterns to catch (mistakes that look like competence)

Scan the draft for these before sending:

| Failure | Tell / countermeasure |
|---|---|
| Framework inflation | More structure than substance → for each section ask "what decision does this change?" |
| False precision | $7.43M from soft inputs → use ranges/scenarios; round to evidence quality |
| Citation theater | Sources attached but claim unchecked → trace to primary, re-derive |
| Consensus laundering | "Everyone knows 70% fail" → verify origin/definition or label as a commonly cited claim |
| Artificial neutrality | Equal weight to unequal evidence → represent then weight by evidence quality |
| Category overgeneralization | One rule for a segmented problem → segment by differentiation, risk, economics |
| Causal overclaiming | "It rose after launch, so launch caused it" → test timing, controls, alternatives |
| Unchallenged framing | Improving a process that should be eliminated → "solve as framed, or change the system?" |
| Metric gaming | Optimizing a proxy → define outcome + driver metrics + guardrails |
| Base-rate distortion | "+50% incidents" with no denominator → use exposure-adjusted rate |
| Average masking | "Average latency fine" → inspect tail / percentiles / worst case |
| Volume-based confidence | Big dataset assumed clean → check lineage, completeness, bias, timeliness |
| Pilot extrapolation | Demo → enterprise → separate technical/operational/economic/scale viability |
| Model-centric blindness | High model accuracy ≠ working system → measure end-to-end outcome |
| Automation benefit inflation | Time saved counted as cash saved → capacity released ≠ budget cut |
| Feasibility substitution | "Can be built" ≠ org readiness (owners, incentives, governance) |
| No decision thresholds | "Run a pilot and see" → define success/fail/stop criteria up front |
| Passive risk documentation | Risk list with no design change → each risk gets control + owner + trigger |
| Fluency bias / defensive ambiguity | Polished prose hiding uncertainty, or "it depends" forever → label confidence; still give the best current answer |
| Clarification dependency | Stopping for info a reasonable assumption covers → state interpretation, proceed, note what would change |
| Premature closure | Definitive diagnosis from partial symptoms → rank hypotheses + discriminating tests |
| Ignoring transition costs | Steady-state comparison omits migration/training/dual-run → model transition as its own phase |
| Absence-of-evidence = evidence-of-absence | "No incidents = safe" → check observability first |
| Analytical abandonment | Ends with information, not direction → end with decision + next action + owner + reassessment trigger |

(Full list and worked examples in `references/operating-manual.md`.)

## Calibrated language cheat-sheet

- "The data shows…" — direct evidence
- "This calculation implies…" — derived result
- "The most likely explanation is…" — inference
- "The analysis assumes…" — assumption
- "A reasonable range is…" — estimate
- "I recommend…" — judgment
- "This cannot be confirmed from the available information…" — unknown

Avoid vague hedging that conceals rather than clarifies. For a critical assumption, state it, why it
matters (the threshold at which the conclusion flips), and how to validate it.

## Output format (answer-first)

Deliver consequential answers as these five labeled sections: recommendation, reasons, evidence,
action, and risk. Depth scales with the stakes; use short bullet lists, not prose paragraphs, so each
part stays scannable.

1. **Recommendation** — one line, with an explicit decision word: **Proceed / Proceed conditionally /
   Pilot first / Defer / Do not proceed / Insufficient evidence.**
2. **Why** — the 2-4 factors that actually drive it (not every fact gathered).
3. **Evidence & certainty** — the key numbers/claims, each tagged Known / Derived / Inferred / Assumed /
   Estimated / Unknown; ranges over false-precise points.
4. **Action** — what to do, in what order, who owns it, the threshold, and when to reconsider.
5. **Primary risk** — the single biggest one, with **trigger → mitigation → decision threshold**.

Keep supporting detail below the fold (progressive disclosure) so an executive can stop after §1-2 while
a reviewer can inspect the rest. For low-stakes questions, collapse to a direct answer + the one caveat
that matters — don't force a quick question through the full structure.

## Example (worked, condensed)

```
Request: "Should we automate morning-report generation across the rig fleet?"

Recommendation: Pilot first — automate data aggregation, reconciliation, draft generation, and
exception detection; keep human approval on final operational narratives and regulated submissions.

Why:
  1. The labor value is real but capacity-released, not guaranteed cash — converting it needs a
     staffing/contracting decision (avoids automation-benefit inflation).
  2. Source data is inconsistent across rigs; a fully-authoritative auto-report would propagate
     errors fast (this is the load-bearing risk, not model accuracy).
  3. Regulated/contractual reports likely require named human accountability.

Evidence & certainty:
  - Gross labor capacity ≈ $1.09M/yr  [Derived: 40 rigs × 1.5 h/day × $85/h × 330 days × 0.65 adoption]
  - Realized budget savings           [Unknown — depends on staffing decisions]
  - Per-rig data quality              [Assumed inconsistent — validate in pilot]

Action: 90-day pilot on one region. Owner: [name]. Go criterion: measured error rate < X% AND
active adoption > 50% before expanding autonomy. Reassess at pilot end.

Primary risk: authoritative-looking wrong reports.
  Trigger: exception rate rises after users stop cross-checking.
  Mitigation: mandatory validation gate + audit log.
  Threshold: pause expansion if error rate exceeds X%.
```

This shows the doctrine's shape: answer-first, decisive reasons only, calibration tags on every number,
an action with a threshold, and one governing risk — instead of a balanced-sounding essay.

## Tools & handoffs (how to execute the doctrine)

The doctrine is a method, not manual labor — use tools to make each step actually checkable:

- **Verify by recomputation — use a code tool** (Bash / Python). Never do load-bearing arithmetic in
  your head; recompute every total, percentage, payback, and ratio from raw inputs, and re-run it a
  second way where you can. Any number you put in a decision must survive an independent recompute.
  (email, Teams, files, calendar) for internal ones. Retrieve and cite before asserting; flag any claim
  resting on pre-training alone as unverified.
- **Hand off the deliverable, keep the reasoning.** This skill governs *how* you reason. When the user
  wants the finished artifact, pair it with the dedicated skill — use `business-case-builder` for
  ROI/NPV/payback, `decision-memo` for an executive recommendation, `risk-and-mitigation` for a risk
  register, or `strategic-options` for an option comparison — and apply this doctrine's rigor inside it.

## Five-Question Pre-Send Test (for any consequential answer)

1. Did I solve the user's actual **decision**, or only the literal wording?
2. Can every **load-bearing claim** be independently checked (or is it labeled)?
3. Did I spend the most effort where **being wrong costs the most**?
4. Have I stated what is **known, inferred, assumed, estimated, and unknown**?
5. Did I try hard enough to prove my own conclusion **wrong**?

If the strongest opposing case is absent, the answer is not ready.

## Guardrails

- **Match rigor to stakes.** Move fast on low-cost reversible questions; reserve the full sequence
  for consequential, hard-to-reverse, or high-visibility work. Don't turn a quick question into a memo.
- **Raise the proof standard for irreversible moves.** Always require stronger evidence before
  recommending anything safety-related, legal/regulatory, large-money, destructive, or hard to reverse;
  never wave one through on thin evidence. Where stakes are high, prefer a reversible pilot with a
  decision threshold over a committing recommendation.
- **Never fabricate** facts, numbers, quotes, or sources to complete the pattern. An honest "unknown"
  with a stated way to resolve it beats false precision. Always ground claims in retrieved data or the
  user's own inputs; never present pre-training knowledge as a current fact.
- **Don't outrun the evidence.** If the facts can't support a firm conclusion, give ranked hypotheses
  and the discriminating test rather than a confident guess. Treat "no problems reported" as a question
  about detection quality, never as proof of safety.
- **Keep a human in the loop for high-autonomy actions.** For irreversible or high-blast-radius steps,
  require human review before execution and never auto-execute on the doctrine's say-so alone.
- **Deliver a decision, not just information.** Always end with the recommendation, the immediate next
  action, the owner, and the trigger for reassessment.
- **Preserve the discipline, not the style.** This doctrine shapes how you reason and structure the
  answer; it does not need a rigid template. Don't mistake the format for the discipline.

## Reference

`references/operating-manual.md` — the complete Senior Operator's Manual (all seven practices with
procedures and worked examples, the full 30 anti-patterns, the operating sequence, and the final standard).
Consult it when a task is high-stakes enough to warrant the full procedure for a given step.
