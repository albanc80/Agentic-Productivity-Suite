# ADR 0001: Workflow-first orchestration, not agent group chat

Status: accepted · 2026-11-03

## Context
The source agents already used four patterns: a router with a strict handoff (Managerial OS), parallel specialists with synthesis (Investment Advisor), a gated engineering pipeline, and agents calling other agents. The suite needs repeatable results, traceability, evaluation and cost control across local and cloud models of very different capability.

## Decision
Playbooks are fixed step sequences in YAML, with six step kinds: agent, parallel, review, gate, tool and connector. A model only routes requests and does the specialist reasoning. Agents never choose the next agent. Tool use inside a step is bounded (allow-listed read-only tools, per-step call limit).

## Consequences
- Runs are reproducible in structure, resumable after gates or restarts, and testable with a scripted model.
- New workflows need a YAML file rather than prompt engineering of a coordinator.
- Open-ended exploration is limited to a single bounded step. If a real need appears, add a dedicated step kind rather than a free-form multi-agent loop.
