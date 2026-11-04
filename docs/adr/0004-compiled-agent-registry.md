# ADR 0004: Compile agent configurations into a neutral registry

Status: accepted · 2026-11-03 · partly superseded by ADR 0005 (the compiled agents are no longer committed)

## Context
Agent definitions are authored outside this repository and are not portable as written: they mix platform-specific content, presentation rules, user context and voice into one prompt.

## Decision
A private ingest tool reads the source archive directly and writes the registry:
- removes platform-specific content and presentation rules;
- keeps user context out of agent text (the profile is injected at runtime from `config/profile.yaml`);
- keeps persona text in its own layer;
- gives an agent several modes where one role serves several purposes;
- keeps skills as on-demand documents (inlined only when marked core).

The output is deterministic. Only the public catalog and skills are committed (ADR 0005). A test fails if any platform, brand or personal reference survives.

## Consequences
- The private sources remain the system of record. Improve an agent by editing its source and re-running the ingest, not by editing `registry/`.
- Sanitisation is rule-based: review the ingest report (private layer) after changing sources.
