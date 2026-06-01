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

```text
UNIT PostWriteHandoff

PURPOSE:
  Emit W1/W2/W3 handoff menu when files were written and remediation is not pending.

WHEN:
  files were written AND remaining_findings is empty

DO:
  EMIT one terminal post-write handoff block:
---
Changes written: {N} file(s). How do you want to review them?

W1. Review here — Invoke skill `cf-analyze` in this session on the written files
W2. Generate a Direct Review Prompt — emit a self-contained prompt that starts with Invoke skill `cf-analyze` in a new chat
W3. Generate a Plan Review Prompt — emit a self-contained prompt that starts with Invoke skill `cf-plan` in a new chat (for phased review on broad / multi-file / strict-coverage scope)

Suggested: {W1|W2|W3} because {scope/risk reason}.

Reply `W1`, `W2`, or `W3`.
---
  WAIT user.reply (next turn)

MENU PostWriteHandoffMenu:
  TITLE: Post-write review choice (next-turn reply)
  OPTIONS:
    W1 ->
      Invoke skill `cf-analyze` in this session
      WITH target_paths=manifest.paths_written, target_kinds, rules_mode,
           carried Validation Results, remaining_findings
      NOTE: no prompt block emitted
    W2 ->
      EMIT Direct Review Prompt template from prompt-template-direct-review.md
        as FINAL section, filled with changed paths, kind/target,
        verbatim Validation Results body, remaining_findings (when present)
    W3 ->
      EMIT Plan Review Prompt template from prompt-template-plan-review.md
        as FINAL section, filled the same way

RULES:
  - MUST load this file ONLY when files were written AND remaining_findings is empty
  - MUST NOT emit W1/W2/W3 as actionable choices when remaining_findings is non-empty;
    emit Remediation Handoff as terminal reply contract instead
  - IF W-only reply arrives while remaining_findings is non-empty:
    REJECT W1, W2, W3
    ASK for a remediation choice
  - Post-write review remains LOCKED until remediation choice is processed
    and Phase 6 re-enters with no remaining findings
  - Re-emission contract: when Phase 6 R1 fix-loop exits cleanly back to Phase 6
    with remaining_findings empty, MUST emit this single terminal handoff block
    before ending response; MUST NOT assume user scrolled back to a previous menu
```
