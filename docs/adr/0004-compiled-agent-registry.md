# ADR 0004: Compile agent configurations into a neutral registry

Status: accepted · 2026-11-03

## Context
The 38 source agents were written for one platform and one person. They contain platform-specific sections, branding rules, a personal profile and persona voice mixed into instructions, and several roles are duplicated.

## Decision
`scripts/ingest_agents.py` reads the source archive directly and writes `registry/`:
- drops platform-specific sections and lines, branding instructions and skills;
- replaces personal references with "the user" (the profile is injected from `config/profile.yaml`);
- moves persona text into a separate field;
- merges duplicate roles into one agent with modes;
- keeps skills as on-demand documents (inlined only when marked core).

The output is deterministic and committed. A test fails if any platform, brand or personal reference survives.

## Consequences
- The source archive remains the system of record. Improve an agent by editing the source and re-running ingest, not by editing `registry/`.
- Sanitisation is rule-based: review `registry/INGEST_REPORT.md` after changing sources.
