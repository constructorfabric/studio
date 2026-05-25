---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the orchestrator needs the canonical generate-workflow validation checklist and Agent Self-Test (post-flight gate before ending the response).
---

<!-- toc -->

- [Validation Criteria](#validation-criteria)
- [Agent Self-Test (STRICT mode — AFTER completing work)](#agent-self-test-strict-mode--after-completing-work)

<!-- /toc -->

## Validation Criteria

- [ ] `{cf-studio-path}/.core/skills/studio/protocol.md` executed
- [ ] Phase-appropriate dependencies loaded (generation: template/example unless checklist explicitly required; validation/review: checklist when applicable)
- [ ] System context clarified (if using rules)
- [ ] Output destination clarified
- [ ] Parent references identified
- [ ] ID naming verified unique
- [ ] Information collected and confirmed
- [ ] `AUTHOR_PLAN_OFFER_RESOLVED` set before any Phase 3 / Phase 4 decision point, using only the canonical values from `workflows/generate/phase-1.5/state-contract.md`
- [ ] When `AUTHOR_PLAN_OFFER_RESOLVED=memory|disk`, `AUTHOR_EXECUTION_PLAN` parsed, validated, and used to drive Phase 4 task dispatch
- [ ] When `AUTHOR_PLAN_OFFER_RESOLVED=disk`, `AUTHOR_PLAN_CACHE_DIR` recorded and the plan cache contains `index.md`, `plan.json`, one `agents/{author}.md` file per involved author, and one task Markdown file per planned task
- [ ] When `AUTHOR_PLAN_OFFER_RESOLVED` is a terminal cancellation state (`cancelled_by_stop_token`, `cancelled_planner_failure`, `cancelled_partial_write`), Phase 3 and Phase 4 are skipped and no write-capable author is dispatched
- [ ] Content generated with no placeholders
- [ ] All IDs follow naming convention
- [ ] All cross-references valid
- [ ] File written after confirmation (if file output)
- [ ] Artifacts registry updated (if file output + rules)
- [ ] Validation executed
- [ ] Language content check executed (`{cfs_cmd} check-language`) when `allowed_content_languages` is configured
- [ ] Exact deterministic validator command(s), per-command validator results, and overall deterministic gate recorded
- [ ] `Validator availability proof` recorded when deterministic gate is `SKIPPED`
- [ ] `Semantic review basis` recorded
- [ ] `Skip reason` and `Validator-backed evidence note` recorded when deterministic gate is `SKIPPED`
- [ ] For file-writing output, the final-response gate self-check was completed before ending the response
- [ ] When files were written and `remaining_findings` is empty, `Post-Write Review Handoff` menu emitted as the FINAL section (including RELAXED explicitly unvalidated exits)
- [ ] When files were written and `remaining_findings` from Phase 5 is non-empty (manual-handoff, user-accepted with remaining, MAX_ITER=0 surfacing all findings, or RELAXED `Deterministic gate: FAIL`), `Remediation Handoff` menu emitted as the FINAL section and `W1`/`W2`/`W3` choices withheld until remediation clears
- [ ] The emitted terminal handoff menu lists exactly the three canonical options for the current state (Remediation: `R1`/`R2`/`R3`; Post-Write Review: `W1`/`W2`/`W3`) with actual counts filled in
- [ ] When the user picks `R2`/`R3`/`W2`/`W3` in their next turn, the corresponding emission template (`Fix Prompt`, `Plan Prompt`, `Direct Review Prompt`, or `Plan Review Prompt`) is emitted as the FINAL section of that next response; `R1`/`W1` are dispatched in-session without emitting any prompt block

## Agent Self-Test (STRICT mode — AFTER completing work)

Answer these AFTER doing the work and include evidence in the output.

| Question | Evidence required |
|----------|-------------------|
| Template loaded? | State the template path read this turn and confirm it was non-empty (`Read {template_path}: {N} lines`). |
| Example referenced? | State the example path read this turn, or explicitly record N/A when RELAXED non-kit with no example. |
| Placeholders absent? | Confirm no `{placeholder}` or `<!-- TODO -->` tokens remain in any written file; quote the written file's content line-count as evidence. |
| Explicit `yes` received before write? | Show the turn where the user's Phase 3 confirmation was received before any author dispatch or inline write. |
| CF_PHASE_GATE not left in any released_* state? | Confirm gate is `armed` at end of session; list every gate transition that occurred (`released_for_dispatch` / `released_for_inline_write` / `released_for_orchestrator_write`) and confirm each was reset. |
| Post-Write Review Handoff (or Remediation Handoff when remaining findings exist) emitted as the terminal section? | Final section of the response is the `Post-Write Review Handoff` menu (when `remaining_findings` is empty) or the `Remediation Handoff` menu (when `remaining_findings` is non-empty). Quote the heading emitted. |

Sample:
```markdown
### Agent Self-Test Results
| Question | Answer | Evidence |
|----------|--------|----------|
| Template loaded? | YES | Read workflows/templates/my-template.md: 85 lines |
| Example referenced? | YES | Read examples/example.md: 42 lines |
| Placeholders absent? | YES | Written file confirmed 120 lines, no {placeholder} tokens |
| Explicit yes received? | YES | User replied "yes" at Phase 3 approval turn |
| CF_PHASE_GATE not in released_*? | YES | Gate transitions: armed→released_for_dispatch→armed; no gate left open |
| Terminal handoff emitted? | YES | Final section is "Post-Write Review Handoff" (remaining_findings = []) |
```
**If ANY answer is NO or lacks evidence → Generate output is INVALID, must fix before ending the response**

RELAXED mode disclaimer:
```text
⚠️ Self-test skipped (RELAXED mode — no Constructor Studio rules)
```
