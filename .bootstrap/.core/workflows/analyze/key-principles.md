---
name: analyze-key-principles
description: "Invoke when loading the analyze workflow Key Principles covering deterministic-vs-semantic authority, chat-only output, and remediation-prompt conditions."
purpose: Analyze workflow Key Principles — deterministic-vs-semantic authority, chat-only output, remediation-prompt conditions
loaded_by: workflows/analyze.md
version: 1.0
---

## Key Principles

- Deterministic gate PASS/FAIL is authoritative when it runs.
- Semantic review is mandatory for any completed analysis; in STRICT mode it also requires evidence-backed verification.
- If the deterministic gate cannot run, do not label overall PASS; use semantic-only output and disclaim reduced rigor.
- Output is chat-only; never create `ANALYSIS_REPORT.md`; keep analysis stateless.
- If deterministic gate fails, STOP and report issues immediately.
- Remediation Handoff menu emitted when actionable issues exist; Fix Prompt / Plan Prompt are on-demand emissions for the next user turn (options 2 or 3).
