---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when files were written by Phase 4 (or any review iteration) and no remaining findings block post-write review.
---

<!-- toc -->

- [Post-Write Review Handoff (emitted when files were written and remediation is not pending)](#post-write-review-handoff-emitted-when-files-were-written-and-remediation-is-not-pending)

<!-- /toc -->

### Post-Write Review Handoff (emitted when files were written and remediation is not pending)

Load this file only when files were written and `remaining_findings` is empty.
When `remaining_findings` is non-empty, do not emit W1/W2/W3 as actionable
choices; emit the Remediation Handoff menu as the terminal reply contract
instead. If a W-only reply arrives while `remaining_findings is non-empty`,
reject `W1`, `W2`, and `W3` and ask for a remediation choice. Post-write review
remains locked until the remediation choice is processed and Phase 6 re-enters
with no remaining findings.

**Re-emission contract**: When a Phase 6 R1 fix-loop exits cleanly back to
Phase 6 with `remaining_findings` empty, the orchestrator MUST re-emit this
Post-Write Review Handoff menu before ending the response. Do NOT assume the
user has scrolled back to a previous menu.

Immediately after the informational next-step menu, emit this verbatim:

```text
Changes written: {N} file(s). How do you want to review them?

W1. Review here — load skill `cf` and route to `/cf-analyze` in this session on the written files
W2. Generate a Direct Review Prompt — emit a self-contained prompt that starts with `Invoke skill cf` and routes to `/cf-analyze` in a new chat
W3. Generate a Plan Review Prompt — emit a self-contained prompt that starts with `Invoke skill cf` and routes to `/cf-plan` in a new chat (for phased review on broad / multi-file / strict-coverage scope)

Suggested: {W1|W2|W3} because {scope/risk reason}.

Reply `W1`, `W2`, or `W3`.
```

On the user's next-turn reply:

- `W1` → load skill `cf` and route to `/cf-analyze` in this session with `target_paths = manifest.paths_written`, `target_kinds`, `rules_mode`, and the carried `Validation Results` + `remaining_findings`. No prompt block is emitted.
- `W2` → emit the `Direct Review Prompt` template (defined in `workflows/generate/phase-6/prompt-template-direct-review.md`) as the FINAL section, filled with changed paths, kind/target, the verbatim `Validation Results` body, and `remaining_findings` (when present).
- `W3` → emit the `Plan Review Prompt` template (defined in `workflows/generate/phase-6/prompt-template-plan-review.md`) as the FINAL section, filled the same way.
