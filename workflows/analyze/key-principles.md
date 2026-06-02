---
name: analyze-key-principles
description: "Invoke when loading the analyze workflow Key Principles covering deterministic-vs-semantic authority, chat-only output, and remediation-prompt conditions."
purpose: Analyze workflow Key Principles — deterministic-vs-semantic authority, chat-only output, remediation-prompt conditions
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzeKeyPrinciples

PURPOSE:
  Define authority boundaries and output constraints for the analyze workflow.

RULES:
  - MUST treat deterministic gate PASS/FAIL as authoritative when it runs
  - MUST run semantic review for any completed analysis; in STRICT mode semantic review also requires evidence-backed verification
  - MUST_NOT label overall PASS when the deterministic gate cannot run; use semantic-only output and disclaim reduced rigor
  - MUST output to chat only; MUST_NOT create ANALYSIS_REPORT.md; MUST keep analysis stateless
  - MUST STOP and report issues immediately when deterministic gate fails
  - MUST emit Remediation Handoff menu when actionable issues exist
  - MUST emit Fix Prompt / Plan Prompt only on demand (user picks option 2 or 3 in the next turn)
```

## Key Principles

- Deterministic gate PASS/FAIL is authoritative when it runs.
- Semantic review is mandatory for any completed analysis; in STRICT mode it also requires evidence-backed verification.
- If the deterministic gate cannot run, do not label overall PASS; use semantic-only output and disclaim reduced rigor.
- Output is chat-only; never create `ANALYSIS_REPORT.md`; keep analysis stateless.
- If deterministic gate fails, STOP and report issues immediately.
- Remediation Handoff menu emitted when actionable issues exist; Fix Prompt / Plan Prompt are on-demand emissions for the next user turn (options 2 or 3).
