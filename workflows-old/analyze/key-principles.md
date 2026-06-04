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
  - ALWAYS treat deterministic gate PASS/FAIL as authoritative when it runs
  - ALWAYS run semantic review for any completed analysis; in STRICT mode semantic review also requires evidence-backed verification
  - NEVER label overall PASS when the deterministic gate cannot run; use semantic-only output and disclaim reduced rigor
  - ALWAYS output to chat only; NEVER create ANALYSIS_REPORT.md; ALWAYS keep analysis stateless
  - ALWAYS STOP and report issues immediately when deterministic gate fails
  - ALWAYS emit Remediation Handoff menu when actionable issues exist
  - ALWAYS emit Fix Prompt / Plan Prompt only on demand (user picks option 2 or 3 in the next turn)
```
