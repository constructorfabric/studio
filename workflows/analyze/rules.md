---
name: analyze-rules
description: "Invoke when loading the analyze workflow rules covering MUST/MUST NOT scope, completion contract, anti-pattern reference list, and pre-output self-check."
purpose: Analyze workflow rules — MUST/MUST NOT scope, completion contract, anti-pattern reference list, pre-output self-check
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Rules](#rules)
- [Next Steps](#next-steps)

<!-- /toc -->


## Rules

**MUST** check **EVERY SINGLE** applicable criterion; verify **EACH ITEM** individually; read the **COMPLETE** artifact; validate **EVERY** ID, reference, and section; check for **ALL** placeholders, empty sections, and missing content; cross-reference **EVERY** actor/capability/requirement ID; report **EVERY** issue found.

**MUST NOT** skip checks, assume sections are correct without verifying, or give benefit of doubt.

**One missed issue = INVALID analysis**

**Completion contract** (enforced at response finalization): when actionable issues exist (`FAIL`, `PARTIAL`, blocking validator errors, or any recommendation requiring artifact/code/workflow changes) AND `EXPLAIN_MODE=false`, the response MUST end with the `Remediation Handoff` menu (3 options: in-session fix continuation, Fix Prompt, Plan Prompt) as the final section. An analysis summary alone is not completion. A validation report alone is not completion. A generic next-step menu without the three remediation handoff options is not completion. See Phase 4 `enforceRemediationPrompts` for full rules. **Exception**: when `EXPLAIN_MODE=true`, this completion contract does NOT apply — storytelling output is pedagogical, not a validation report; the Storytelling Output schema (Phase 4) is the complete output and the handoff menu / Fix / Plan prompts MUST NOT be emitted.

**Reference**: `{cf-studio-path}/.core/requirements/agent-compliance.md` for the full anti-pattern list.
- `AP-001 SKIP_SEMANTIC`: reporting overall PASS from deterministic checks alone.
- `AP-002 MEMORY_VALIDATION`: claiming review without a fresh Read tool call.
- `AP-003 ASSUMED_NA`: marking a category N/A without document evidence.
- `AP-004 BULK_PASS`: claiming "all pass" without per-category evidence.
- `AP-005 SELF_TEST_LIE`: claiming the self-test passed when required evidence is missing.
- `SIMULATED_VALIDATION`: producing a validation summary without running `{cfs_cmd} validate`.
Before output, self-check: PASS without semantic review? fresh Read this turn? N/A claims quoted? per-category evidence present? actual `{cfs_cmd} validate` output shown? If any answer is no → STOP and restart with compliance.

## Next Steps

After a PASS result, present these options (Phase 5 reads this section):

- **Deeper analysis** — run a related analysis (consistency, code, or prompt-bug review) on the same or adjacent targets; reply `deeper`.
- **Handoff to `/cf-generate`** — apply remediation for findings or improvements; reply `generate`.
- **Handoff to `/cf-plan`** — decompose multi-phase remediation into a structured plan; reply `plan`.
- **End session** — no further action needed; reply `done`.
