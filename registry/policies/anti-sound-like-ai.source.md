# Anti-Sound-Like-AI v4.0

## Purpose

Produce writing that sounds like the user realistically wrote it for the stated audience.

The objective is credible authorship, not fake imperfection, casualization, random sentence variation, slang insertion, typo injection, or detector gaming.

Preserve:
- verified facts
- dates, names, figures, and citations
- technical meaning
- uncertainty
- required legal, safety, compliance, or contractual language
- audience
- requested format
- the user's actual judgment

AI-detector scores are noisy. Do not optimize directly for a detector score. Treat repeated high-AI results across multiple detectors as a regression signal that the composition process is still too model-shaped.

## Core principle

Do not write the full analysis the model is capable of producing.

Write only what this author would realistically bother saying.

Select. Omit. State the point. Stop.

---

## When NOT to Use

- Net-new factual research or fact-finding — use the deep-research agent for that instead.
- Translating third-party text into another language, or reproducing copyrighted source material.
- Pure formatting or layout cleanup with no voice change — use the docx, pptx, or xlsx skill instead.
- Text that must stay verbatim: legal clauses, contractual language, safety notices, approved disclosures, quoted statements.
- Code, structured data, configuration files, or machine-read output.
- Any request to disguise authorship, evade an AI-detection policy, or misrepresent who wrote something.

## Quick Start

```
User: "rewrite this update so it sounds like me, not a bot"
→ extract facts → decide what this author would bother saying
→ drop the rest → draft rough → run the geometry + voice checks → stop

User: "translate this article into Spanish"
→ NOT this skill (translation / third-party source)
```

## Inputs and Tools

Voice evidence beats guesswork. When the user's own writing is available, sample it before drafting:

- `ListChatMessages` — shorter, less formal register for chat and chat replies.
- `ReadFileContent` — read an attached or referenced document the rewrite is based on.

If no voice sample is reachable, say so and draft from the request's stated audience and channel rather than inventing a style.

---

# 1. Operating Model

The drafting process MUST follow this sequence:

SOURCE / REQUEST
↓
FACT EXTRACTION
↓
AUTHOR JUDGMENT
↓
CONTENT SELECTION
↓
VOICE FINGERPRINT
↓
CHANNEL MODE
↓
ROUGH COMPOSITION
↓
RHETORICAL GEOMETRY CHECK
↓
IMPLICATION SUPPRESSION
↓
SYNTHESIS REMOVAL
↓
VOICE CHECK
↓
STOP

Do not skip directly from source to polished prose unless the task is trivial.

Do not write a generic draft and "humanize" it afterward.

---

# 2. Phase 1 — Extract Facts Before Prose

When source material exists:

1. Extract facts into short notes.
2. Separate:
   - verified facts
   - claims from the source
   - the user's judgment
   - unresolved uncertainty
3. Ignore the source's sentence order.
4. Ignore the source's paragraph order.
5. Do not copy the source's narrative arc.
6. Do not begin composing prose yet.

If there is no source material, extract the factual requirements and constraints from the user's request instead.

### Required behavior

A summary that preserves the source's sequence is not acceptable merely because the wording changed.

Do not paraphrase paragraph-by-paragraph.

---

# 3. Phase 2 — Identify the Author's Actual Judgment

Before drafting, determine privately:

- What does the author actually think?
- What would they emphasize?
- What would they ignore?
- What decision, concern, observation, or request is driving the message?
- What would they consider too obvious to explain?
- What would they realistically say in this channel?

Reduce this to one internal sentence:

> "The author mainly wants to say: ________."

If no defensible author judgment exists, remain factual and do not invent one.

---

# 4. Phase 3 — Select Aggressively

For normal prose, choose the one or two points the author would most likely mention.

Add more only when the task explicitly requires broader coverage.

Prefer omission over completeness.

Do not add:
- background merely for completeness
- balance merely to appear thoughtful
- generic recommendations
- implications the reader can already infer
- a second or third point merely to create symmetry
- a concluding lesson merely to make the piece feel finished

### Coverage rule

The correct amount of content is determined by:
- audience
- channel
- purpose
- required completeness

Not by how much analysis is available.

---

# 5. Phase 4 — Build a Voice Fingerprint

Use actual voice evidence whenever available.

Priority order:

1. User-supplied writing samples.
2. Accepted prior revisions.
3. Recurrent wording and sentence habits.
4. Domain vocabulary used naturally by the user.
5. Plain professional English when evidence is limited.

Do not invent:
- slang
- quirks
- personal anecdotes
- misspellings
- grammatical errors
- punctuation habits unsupported by evidence

## Voice Fingerprint Schema

Privately estimate only the features supported by available evidence.

### Sentence behavior
- typical sentence length: short / medium / long / mixed
- fragments: rare / occasional / frequent
- compound sentences: rare / moderate / frequent
- contractions: rare / moderate / frequent
- rhetorical questions: rare / moderate / frequent
- parenthetical remarks: rare / moderate / frequent
- direct assertions: weak / moderate / strong

### Paragraph behavior
- typical paragraph length
- one-sentence paragraphs: rare / occasional / frequent
- dense technical paragraphs: rare / moderate / frequent
- tolerance for abrupt topic shifts
- preference for bullets vs prose

### Vocabulary
- recurring verbs
- recurring nouns
- preferred domain terminology
- preferred plain alternatives
- phrases the user actually uses
- words the user tends not to use

### Reasoning behavior
- starts with judgment or context
- explains implications fully or partially
- uses examples or abstractions
- qualifies aggressively or minimally
- challenges assumptions or accepts them
- states recommendations directly or indirectly
- prefers operational, technical, commercial, strategic, or personal framing

### Closure behavior
- explicit conclusion
- action/request ending
- unresolved issue ending
- abrupt stop after practical point
- recap tendency

The draft should match this fingerprint where evidence exists.

Do not force generic "human" variability.

---

# 6. Phase 5 — Choose a Channel Mode

Apply the mode that best matches the requested artifact.

## WORKING_NOTE

Use for:
- quick internal updates
- manager notes
- informal professional comments
- short working observations

Behavior:
- low structure
- high omission
- direct opinion
- limited context
- minimal synthesis
- stop early

## EMAIL

Use for:
- professional email
- reply
- stakeholder note

Default composition:
1. purpose or answer
2. only necessary context
3. ask, decision, or next action if needed

Do not:
- build a miniature report
- summarize everything again at the end
- add a "broader implication" paragraph

## EXECUTIVE

Use for:
- executive summaries
- leadership notes
- decision memos
- senior stakeholder communication

Behavior:
- compressed
- decision-centered
- selective evidence
- explicit risk when material
- minimal exposition
- no ornamental synthesis

## TECHNICAL

Use for:
- architecture
- engineering
- operations
- scientific or domain-specific documentation

Behavior:
- accuracy overrides stylistic variation
- preserve necessary definitions and causal explanation
- use domain terminology naturally
- do not remove explanation required for technical correctness
- avoid generic executive polish unless requested

## SOCIAL

Use for:
- LinkedIn
- public professional posts
- comments
- short-form thought leadership

Behavior:
- author judgment dominates
- incomplete coverage is acceptable
- one useful example is better than three generic examples
- avoid packaged "lesson learned" endings
- avoid formulaic hooks unless they match the user's actual style

## LONG_FORM

Use for:
- articles
- essays
- reports
- longer opinion pieces

Behavior:
- allow development over time
- vary section depth according to importance
- do not give every section equal weight
- do not force each section into claim → evidence → implication
- conclusions are optional unless the format requires one

## FORMAL / CONTROLLED

Use for:
- legal
- contractual
- compliance
- policy
- safety-critical
- regulated documentation

Behavior:
- preserve required wording and completeness
- detector avoidance is secondary to accuracy and compliance
- do not introduce stylistic irregularity that creates ambiguity

---

# 7. Phase 6 — Compose Roughly, Not Editorially

Write the first usable version from:
- selected facts
- author judgment
- voice fingerprint
- channel mode

Do not consult the source's narrative order.

Do not attempt to make every sentence elegant.

Use three sentence roles consciously:

## A. Functional sentence

Example:
> I don't think this is ready.

Use when a plain statement is sufficient.

## B. Working explanation

Example:
> We tested two workflows and both failed once the agent had to recover from incomplete data.

Use when evidence or context is needed.

## C. Polished synthesis

Example:
> These findings underscore the importance of establishing robust recovery mechanisms before expanding autonomous execution.

Treat this sentence type as suspicious.

Delete or rewrite it unless:
- the format explicitly requires synthesis, AND
- it adds information the reader cannot infer.

---

# 8. Rhetorical Geometry Control

This is a hard gate.

AI-shaped writing often repeats the same paragraph logic even when vocabulary changes.

Reject repeated rhetorical geometry.

## Common AI geometries

### Pattern A
claim → explanation → implication

### Pattern B
fact → caveat → takeaway

### Pattern C
context → analysis → recommendation

### Pattern D
option → benefit → limitation

### Pattern E
event → significance → broader meaning

### Pattern F
problem → solution → strategic implication

One occurrence may be natural.

Repeated use across adjacent paragraphs or list items is a rejection condition unless the content genuinely requires it.

## Geometry test

Inspect paragraph function, not only paragraph length.

Reject when two or more adjacent units have substantially the same internal role sequence.

Example:

Paragraph 1:
- event
- caveat
- significance

Paragraph 2:
- event
- caveat
- significance

Paragraph 3:
- event
- caveat
- significance

→ REBUILD.

Do not repair by changing transition words.

---

# 9. Composition Entropy Check

Human writing usually allocates attention unevenly.

Check for excessive regularity in:

- paragraph length
- sentence count per paragraph
- list-item length
- rhetorical sequence
- qualification placement
- repeated sentence openings
- repeated transition structure

### Reject examples

Paragraph lengths:
52 / 55 / 49 / 56 words

Sentence pattern:
long / medium / short
long / medium / short
long / medium / short

List items:
each contains one benefit, one caveat, one recommendation

These patterns are mechanically balanced.

### Important

Do NOT randomize text merely to create irregularity.

The goal is not randomness.

The goal is to let importance determine space.

---

# 10. Implication Suppression

After each factual or analytical statement, ask privately:

> Would the intended reader already understand why this matters?

If yes:
- do not explain the implication

If partially:
- add only the missing operational meaning

If no:
- explain it directly

Avoid automatic phrases such as:
- this highlights
- this underscores
- this demonstrates
- this is significant because
- the broader implication is
- this points to
- this suggests a larger shift

Use them only when the sentence adds non-obvious meaning.

---

# 11. Explanation Completion Suppression

LLMs tend to close every semantic loop.

Do not.

A human author may:
- state an observation without unpacking it
- leave a familiar implication unstated
- mention one risk and ignore lower-priority risks
- stop after the decision
- move on without summarizing

Do not explain everything the model understands.

---

# 12. Uneven Emphasis

Allocate text according to author priority.

One issue may receive:
- 100 words

Another:
- one sentence

Another:
- nothing

This is acceptable.

Do not:
- equalize paragraph size
- give each option identical treatment
- provide three examples because the first two sections had three examples
- create symmetry that the content does not require

---

# 13. Concrete Language

Prefer:
- named actors
- systems
- actions
- dates
- dependencies
- failure modes
- controls
- measurable effects
- specific operational consequences

Examples:

"improve visibility"
→
"show data age and missing channels on the same screen"

"strengthen governance"
→
"require an owner, approval record, and retirement date"

"increase efficiency"
→
name the manual step removed or time reduced

Do not invent operational detail merely to make writing sound specific.

---

# 14. Language Controls

Avoid reflexive use of:

- it is important to note
- it is worth noting
- at its core
- that being said
- key takeaway
- my takeaway
- the broader point
- this highlights the importance of
- success will depend on
- ultimately
- overall
- furthermore
- moreover
- additionally
- leverage
- utilize
- facilitate
- streamline

Use a plain verb when a plain verb works.

Avoid synthetic contrast patterns such as:
- not X, but Y
- this is not about X; it is about Y

Use only when the distinction is genuinely necessary.

Avoid repeated groups of three.

Keep a triad only when the content actually contains three required items.

Avoid inflated terms unless supported:
- transformative
- groundbreaking
- revolutionary
- pivotal
- unparalleled
- seamless
- game-changing

---

# 15. Transition Suppression

Do not use transitions to manufacture coherence.

Delete transitions when facts already establish the relationship.

Suspicious transition density includes:
- however
- therefore
- meanwhile
- additionally
- more importantly
- in contrast
- as a result
- at the same time
- on the other hand

Transitions are permitted when they express a real logical relationship.

Do not use them merely because a new paragraph begins.

---

# 16. Summary-Specific Rules

When summarizing:

1. Write the author's judgment privately in one sentence.
2. Select only the facts needed to support it.
3. Separate unrelated developments.
4. Break the source order.
5. Do not reproduce the source's narrative arc.
6. Add a recommendation only when specific and supported.
7. Stop before the summary becomes a consulting mini-report.

## Reject this default structure

Paragraph 1:
event → caveat → significance

Paragraph 2:
context → pressure → opportunity

Paragraph 3:
second trend → evidence → implication

Paragraph 4:
broad recommendation

Rebuild from facts and author priority.

---

# 17. Source Deconstruction Rules

When rewriting or summarizing a source:

- extract before drafting
- reorder facts
- group around author judgment
- remove source transitions
- do not mimic source paragraph count
- do not preserve source emphasis automatically
- use original sentence construction
- quote only when necessary and properly attributed

If the source structure is still recognizable, the rewrite is not sufficiently independent.

---

# 18. Synthetic Professionalism Check

Reject or rewrite prose that sounds like it could have been produced unchanged by:

- a generic consulting analyst
- a corporate communications team
- a LinkedIn ghostwriter
- an executive-summary generator
- a competent general-purpose LLM

This is a hard rejection condition.

Do not edit such a draft.

Discard its composition and reconstruct it from:
- facts
- author judgment
- voice fingerprint
- channel purpose

---

# 19. Hard Reset Protocol

Trigger a hard reset when:

- several detectors or reviewers strongly flag the text
- repeated rhetorical geometry appears
- the draft reads like a compact consulting report
- the source sequence remains visible
- the text explains every implication
- every paragraph feels equally polished
- the conclusion packages the entire message
- the user's actual judgment is hard to see

## Reset procedure

1. Keep only verified facts.
2. Keep the user's actual judgment.
3. Delete the draft.
4. Re-select the one or two points worth mentioning.
5. Change the order of facts.
6. Rebuild using the correct channel mode.
7. Remove at least one nonessential point.
8. Remove implications the audience can infer.
9. Delete the final synthesis paragraph unless it contains a real action, risk, decision, request, or unresolved dependency.
10. Recheck rhetorical geometry.
11. Stop.

Do not repair a failed draft with synonyms.

Do not run a generic "humanizer" pass.

---

# 20. No-Final-Polish Rule

After the draft passes the structural checks:

DO NOT perform another general stylistic improvement pass.

Allowed final corrections:
- factual error
- grammar that changes meaning
- ambiguity
- broken syntax
- citation issue
- required format compliance

Disallowed final behavior:
- making transitions smoother
- making the ending stronger
- making all sentences more elegant
- balancing paragraph lengths
- adding a recap
- replacing plain sentences with more sophisticated ones
- adding rhetorical flourish

Once the practical point is clear and correct, stop.

---

# 21. Final Quality Gate

Use this gate to reject structural failures, not to polish prose.

Confirm:

- facts remain accurate
- uncertainty is preserved
- user judgment is visible when supported
- source order has been broken when applicable
- rhetorical geometry is not repetitive
- attention is uneven where importance is uneven
- no generic conclusion was added
- no obvious implication is redundantly explained
- channel mode is appropriate
- language is concrete where evidence allows
- the piece stops at the practical point
- the draft does not sound interchangeable with generic corporate prose

If a failure requires more than a local factual or grammatical correction:

REBUILD.

Do not cosmetically optimize.

---

# 22. Regression Test Suite

Before accepting a new version of this skill, test it against multiple artifact types.

Minimum recommended suite:

1. Short internal manager note
2. Executive summary
3. LinkedIn post
4. Technical architecture explanation
5. Article summary
6. Email to a stakeholder
7. Opinionated industry commentary
8. Rewrite of polished AI-generated prose
9. Rewrite from a source article
10. Short recommendation with only one major point

For each test, evaluate:

## Structural
- repeated paragraph logic
- source-order retention
- excessive completeness
- symmetrical paragraph/list construction
- packaged conclusion
- over-explanation
- transition density

## Voice
- resembles known author samples
- natural vocabulary
- realistic level of formality
- realistic omission
- realistic emphasis

## Accuracy
- facts preserved
- technical meaning preserved
- no invented specificity
- caveats preserved

## Detector signal
Use detector scores only as one regression indicator.

Prefer:
- multiple detectors
- repeated runs
- comparison against genuine human samples from the same author and genre

Do not set a detector score as the sole acceptance criterion.

---

# 23. Output Behavior

When creating or rewriting text:

- return the finished text first
- explain material changes only when useful or requested
- do not mention this skill
- do not mention detector tactics
- do not describe the hidden drafting process
- do not claim a detector score unless actually tested
- do not add a conclusion after the practical point

---

# Guardrails

- Never fabricate facts, figures, dates, names, quotes, or citations to make prose flow better — a gap stays a gap, marked for the user to fill.
- Never alter the meaning of a fact, a number, or a stated uncertainty in the name of voice.
- Never touch text that must stay verbatim: legal, contractual, safety, compliance, or approved-disclosure language.
- Do not inject fake imperfection — no typos, invented slang, forced casualness, or random sentence-length jitter.
- Do not optimize for an AI-detector score, and never claim a detector result that was not actually measured.
- Do not imitate a real person's voice other than the user's own, and never help disguise authorship or misrepresent who wrote something.
- Always preserve the requested format, length limit, and audience — voice work is not license to restructure a deliverable.
- If the source material is missing, unreadable, or thinner than the request assumes, say so plainly rather than filling the space.
- If no sample of the user's writing is available, draft from channel and audience and tell the user the voice is inferred.
- Confirm before sending anything — produce the text and let the user review it; never auto-send a rewritten message on the user's behalf.
- Do not mention this skill, its checks, or the drafting process in the delivered text.

---

# 24. Final Rule

Human writing is selective.

It reflects what the author cares about, not everything the model knows.

It gives unequal space to unequal priorities.

It leaves familiar implications unstated.

It does not close every loop.

It stops when the message has done its job.
