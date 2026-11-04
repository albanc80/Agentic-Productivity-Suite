# ADR 0004: Compile agent configurations into a neutral registry

Status: accepted · 2026-11-03 · partly superseded by ADR 0005 (the compiled agents are no longer committed)

## Context
The source agents were written for one platform and one person. They contain platform-specific sections, branding rules, a personal profile and persona voice mixed into instructions.

## Decision
A private ingest tool reads the source archive directly and writes the registry:
- drops platform-specific sections and lines, branding instructions and skills;
- replaces personal references with "the user" (the profile is injected from `config/profile.yaml`);
- moves persona text into a separate field;
- gives an agent several modes where one role serves several purposes;
- keeps skills as on-demand documents (inlined only when marked core).

The output is deterministic. Only the public catalog and skills are committed (ADR 0005). A test fails if any platform, brand or personal reference survives.

## Consequences
- The source archive remains the system of record. Improve an agent by editing the source and re-running ingest, not by editing `registry/`.
- Sanitisation is rule-based: review the ingest report (private layer) after changing sources.
