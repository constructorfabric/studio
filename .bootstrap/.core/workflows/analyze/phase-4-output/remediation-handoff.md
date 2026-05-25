---
name: analyze-phase-4-remediation-handoff
description: "Invoke when the analyze result contains actionable issues to append the terminal Remediation Handoff menu offering fix, plan, or next-step options."
purpose: Terminal Remediation Handoff menu for actionable analyze findings
loaded_by: workflows/analyze.md
version: 1.0
---

## Mandatory Remediation Handoff Policy

The Remediation Handoff menu is mandatory when actionable findings exist, except when EXPLAIN_MODE=true. "Actionable findings" means any `FAIL`, `PARTIAL`, blocking validator error, or recommendation requiring artifact, code, or instruction changes. When the policy is active, the menu MUST be emitted as the final section of the current response — do not defer it to a later user turn, do not ask whether it should be generated, and do not replace it with a generic next-step menu.

If the result contains any actionable issue (`FAIL`, `PARTIAL`, blocking
validator errors, or recommendations requiring artifact, code, or instruction
changes), append this menu as the final section. `EXPLAIN_MODE=true` disables
this menu because storytelling open questions are author-routed.

### Remediation Handoff

```text
Actionable findings: High {h} / Medium {m} / Low {l}. How do you want to proceed?

1. Continue here in fix mode — load skill `cf` and route to `/cf-generate` with these findings in this session
2. Generate a Fix Prompt — emit a self-contained prompt that starts with `Invoke skill cf` and routes to `/cf-generate` in a new chat
3. Generate a Plan Prompt — emit a self-contained prompt that starts with `Invoke skill cf` and routes to `/cf-plan` in a new chat

Suggested: {1|2|3} because {scope/risk reason}.

Reply `1`, `2`, or `3`.
```

Next-turn routing:
- `1` → load skill `cf` and enter fix mode. The orchestrator MUST: (a) re-probe `INLINE_FALLBACK` through `workflows/shared/inline-fallback-probe.md` before any other generate Phase 5 prompt or dispatch; (b) emit the canonical `MAX_ITER` resolution prompt from `workflows/generate/phase-5/index.md` § Pre-Phase-Setup (default `5`; `0` skips the loop) and wait for the reply; (c) initialize Phase 5 state: `all_findings = merged findings`, `analyzed_paths = analyzed paths`, `external_target_paths = analyzed_paths`, `target_paths = analyzed_paths` (in-scope target set for every downstream sub-agent dispatch), `manifest.paths_written = []` (no files have been written yet on external entry), carried deterministic results and carried semantic report blocks; (d) when `MAX_ITER = 0`, enter `workflows/generate/phase-5/phase-5.3-findings.md` and let `workflows/generate/phase-6/index.md` consume the carried blocks; (e) when `MAX_ITER > 0`, route `MAX_ITER > 0` external entries to `workflows/generate/phase-5/phase-5.1-det-gate.md`, then Phase 5.2, before `workflows/generate/phase-5/phase-5.3-findings.md` and before any author dispatch. Each executed iteration MUST dispatch `cf-deterministic-validator` (Phase 5.1) and the matched semantic reviewer sub-agent set (Phase 5.2) on `target_paths` BEFORE the author dispatch. MUST NOT shortcut the loop with an inline review, inline fix, or single-pass summary; sub-agent dispatch required every iteration (subject to `INLINE_FALLBACK` per `workflows/shared/inline-fallback-probe.md`). Loop iterates until clean or `MAX_ITER` is hit. No prompt block is emitted by this step.
- `2` → emit the On-demand Fix Prompt Template from `workflows/analyze/phase-4-output/fix-prompt-template.md` as the final section.
- `3` → emit the On-demand Plan Prompt Template from `workflows/analyze/phase-4-output/plan-prompt-template.md` as the final section.

External-fix handoff guard: after option `1` is selected and before any file edit
or inline patch attempt, set and preserve this guard in Phase 5 state:
`handoff_guard.inline_fallback_reprobed = true`,
`handoff_guard.max_iter_resolved = true`, and
`handoff_guard.dispatch_evidence_required = true`. If `MAX_ITER > 0` and
`INLINE_FALLBACK=false`, the downstream generate Phase 5 loop MUST produce
`phase5_dispatch_evidence` for the validator, semantic reviewer(s), and author
dispatches. Missing guard state or missing dispatch evidence is a protocol
violation; stop and repair the workflow state instead of editing files inline.

Prompt templates are on-demand only. They must be self-contained, start with `Invoke skill cf`, include full findings inline, include target path/kind and deterministic gate status, state the route, and ask the next agent to fix root causes plus tests/validation.
