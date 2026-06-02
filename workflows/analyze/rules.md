---
name: analyze-rules
description: "Invoke when loading the analyze workflow rules covering MUST/MUST NOT scope, completion contract, anti-pattern reference list, and pre-output self-check."
purpose: Analyze workflow rules — MUST/MUST NOT scope, completion contract, anti-pattern reference list, pre-output self-check
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Next Steps](#next-steps)

<!-- /toc -->

```pdsl
UNIT AnalyzeRules

PURPOSE:
  Define mandatory analysis standards, completion contract, anti-pattern
  reference list, and pre-output self-check gate.

RULES:
  - MUST check EVERY SINGLE applicable criterion individually
  - MUST verify EACH ITEM; do not check categories in bulk
  - MUST read the COMPLETE artifact
  - MUST validate EVERY ID, reference, and section
  - MUST check for ALL placeholders, empty sections, and missing content
  - MUST cross-reference EVERY actor/capability/requirement ID
  - MUST report EVERY issue found
  - MUST_NOT skip checks
  - MUST_NOT assume sections are correct without verifying
  - MUST_NOT give benefit of doubt

INVARIANTS:
  - One missed issue = INVALID analysis
  - When actionable issues exist AND EXPLAIN_MODE=false: response MUST end with
    the Remediation Handoff menu (3 options: in-session fix continuation,
    Fix Prompt, Plan Prompt) as the FINAL section
  - An analysis summary alone is NOT completion
  - A validation report alone is NOT completion
  - A generic next-step menu without the three remediation handoff options is NOT completion
  - When EXPLAIN_MODE=true: completion contract does NOT apply; Storytelling Output
    schema (Phase 4) is the complete output; MUST_NOT emit handoff menu / Fix / Plan prompts

DO (pre-output self-check gate):
  Before emitting output, verify ALL of the following:
    - Did I report PASS without semantic review? -> IF yes: STOP and restart
    - Did I use a fresh Read tool call this turn? -> IF no: STOP and restart
    - Are N/A claims backed by quoted document lines? -> IF no: STOP and restart
    - Is per-category evidence present? -> IF no: STOP and restart
    - Did I show actual {cfs_cmd} validate output? -> IF no: STOP and restart
  IF any answer fails: STOP and restart with compliance

NOTES:
  Anti-pattern reference list (full list in
    {cf-studio-path}/.core/requirements/agent-compliance.md):
    AP-001 SKIP_SEMANTIC: reporting overall PASS from deterministic checks alone
    AP-002 MEMORY_VALIDATION: claiming review without a fresh Read tool call
    AP-003 ASSUMED_NA: marking a category N/A without document evidence
    AP-004 BULK_PASS: claiming "all pass" without per-category evidence
    AP-005 SELF_TEST_LIE: claiming the self-test passed when required evidence missing
    SIMULATED_VALIDATION: producing a validation summary without running {cfs_cmd} validate

  Post-PASS next steps (Phase 5 reads this):
    After a PASS result, present these options:
    - Deeper analysis — run a related analysis (consistency, code, or prompt-bug review)
      on the same or adjacent targets; reply "deeper".
    - Handoff to Invoke skill `cf-generate` — apply remediation for findings or improvements;
      reply "generate".
    - Handoff to Invoke skill `cf-plan` — decompose multi-phase remediation into a structured plan;
      reply "plan".
    - End session — no further action needed; reply "done".
```

## Next Steps

After a PASS result, present these options (Phase 5 reads this section):

- **Deeper analysis** — run a related analysis (consistency, code, or prompt-bug review) on the same or adjacent targets; reply `deeper`.
- **Handoff to Invoke skill `cf-generate`** — apply remediation for findings or improvements; reply `generate`.
- **Handoff to Invoke skill `cf-plan`** — decompose multi-phase remediation into a structured plan; reply `plan`.
- **End session** — no further action needed; reply `done`.
