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

```pdsl
UNIT PostWriteHandoff

PURPOSE:
  Emit W1/W2/W3 handoff menu when files were written and remediation is not pending.

WHEN:
  - REQUIRE files were written AND remaining_findings is empty

DO:
  - EMIT "Changes written: {N} file(s). Suggested: {W1|W2|W3} because {scope/risk reason}."
  - EMIT_MENU PostWriteHandoffMenu
  - WAIT user.reply (next turn)

MENU PostWriteHandoffMenu:
  TITLE: Post-write review choice (next-turn reply)
  OPTIONS:
    1 W1 review here ->
      Invoke skill `cf-analyze` in this session
      WITH target_paths=manifest.paths_written, target_kinds, rules_mode,
           carried Validation Results, remaining_findings
      NOTE: no prompt block emitted
    2 W2 direct review prompt ->
      EMIT Direct Review Prompt template from prompt-template-direct-review.md
        as FINAL section that starts with Invoke skill `cf-analyze`,
        filled with changed paths, kind/target,
        verbatim Validation Results body, remaining_findings (when present)
    3 W3 plan review prompt ->
      EMIT Plan Review Prompt template from prompt-template-plan-review.md
        as FINAL section, filled the same way
  INVALID:
    EMIT "Reply with 1 for W1, 2 for W2, or 3 for W3."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS load this file ONLY when files were written AND remaining_findings is empty
  - NEVER emit W1/W2/W3 as actionable choices when remaining_findings is non-empty;
    emit Remediation Handoff as terminal reply contract instead
  - ALWAYS IF W-only reply arrives while remaining_findings is non-empty:
    REJECT W1, W2, W3
    ASK for a remediation choice
  - ALWAYS Post-write review remains LOCKED until remediation choice is processed
    and Phase 6 re-enters with no remaining findings
  - ALWAYS Re-emission contract: when Phase 6 R1 fix-loop exits cleanly back to Phase 6
    with remaining_findings empty, ALWAYS emit this single terminal handoff block
    before ending response; NEVER assume user scrolled back to a previous menu
```
