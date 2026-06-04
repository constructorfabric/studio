---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the iteration is mixed or judgmental-only (judgmental non-empty) and the user-approval gate must be presented before any author fix dispatch.
---

<!-- toc -->

- [Phase 5.4: User-Approval Gate (judgmental findings)](#phase-54-user-approval-gate-judgmental-findings)

<!-- /toc -->

### Phase 5.4: User-Approval Gate (judgmental findings)

```pdsl
UNIT Phase54UserApprovalGate

PURPOSE:
  Present user-approval gate for judgmental findings; parse reply; dispatch fix.

WHEN:
  - REQUIRE judgmental is non-empty (mixed or judgmental-only iterations)

DO:
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch
  - RUN NOTE: Pre-dispatch fail-stop and Mode B degradation rules in
    {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
  - RUN NOTE: Full findings list already rendered in `{cf-studio-path}/.core/workflows/generate/phase-5/phase-5.3-findings.md` § Findings display;
        - NEVER re-render it here

  - EMIT "Mixed iteration {N}/{MAX_ITER}: {m_count} mechanical queued for auto-fix when you proceed; {j_count} judgmental need your approval. Mechanical IDs: {comma-separated mechanical IDs}. Judgmental IDs: {comma-separated judgmental IDs}."
  - EMIT "Approve subset with `2:` to apply the mechanical batch only, or `2: <IDs>` to approve selected judgmental findings; un-approved judgmental findings are carried forward in session state."
  - EMIT_MENU Phase54ApprovalMenu
  - WAIT user.reply
  - STOP_TURN
```

```pdsl
UNIT Phase54ReplyParsing

PURPOSE:
  Parse user approval reply with canonical rules (case-insensitive throughout).

MENU Phase54ApprovalMenu:
  TITLE: Mixed iteration approval (canonical reply parsing)
  OPTIONS:
    1 ^1$ ->
      SET to_fix = mechanical + judgmental
      BUILD mode=fix payload WITH target_paths=target_paths (external entry) OR
        manifest.paths_written (normal entry) AND findings=to_fix
      INCLUDE git_commit_mode=GIT_COMMIT_MODE
      INCLUDE contributing_guide=CONTRIBUTING_GUIDE
      INCLUDE git_constraint block from phase-4-write.md § Git constraint blocks
      EXECUTE phase-4-write.md § Author Selection and Dispatch
      APPEND returned findings_not_fixable to carry_forward
      UPDATE manifest
      SET N = N + 1
      IF N > MAX_ITER: EMIT Phase5IterationCapPrompt; APPLY cap-reply rules
      ELSE: CONTINUE phase-5.1-det-gate.md

    ^2$ (no colon) ->
      EMIT "Reply 2 needs a colon: type `2:` for mechanical-only, or
            `2: <comma-separated judgmental IDs>` to also approve specific
            judgmental findings. Reply again."
      NEVER proceed
      WAIT user.reply
      STOP_TURN

    ^2:\s*$ (bare, no IDs) ->
      SET approved_judgmental = []
      SET unapproved_judgmental = judgmental
      ADD unapproved_judgmental to carry_forward
      SET to_fix = mechanical
      BUILD mode=fix payload WITH findings=to_fix (same git fields as option 1)
      EXECUTE phase-4-write.md § Author Selection and Dispatch
      APPEND returned findings_not_fixable to carry_forward
      UPDATE manifest
      SET N = N + 1
      IF N > MAX_ITER: EMIT Phase5IterationCapPrompt; APPLY cap-reply rules
      ELSE: CONTINUE phase-5.1-det-gate.md

    ^2:\s*[A-Za-z][A-Za-z0-9_-]*(\s*,\s*[A-Za-z][A-Za-z0-9_-]*)*\s*$ (with IDs) ->
      SPLIT on commas (whitespace around comma tolerated)
      UPPERCASE IDs
      INTERSECT with judgmental set
      DROP unknown IDs with one-line warning listing them
      SET approved_judgmental = intersection
      SET unapproved_judgmental = judgmental \ approved_judgmental
      ADD unapproved_judgmental to carry_forward
      SET to_fix = mechanical + approved_judgmental
      BUILD mode=fix payload WITH findings=to_fix (same git fields as option 1)
      EXECUTE phase-4-write.md § Author Selection and Dispatch
      APPEND returned findings_not_fixable to carry_forward
      UPDATE manifest
      SET N = N + 1
      IF N > MAX_ITER: EMIT Phase5IterationCapPrompt; APPLY cap-reply rules
      ELSE: CONTINUE phase-5.1-det-gate.md

    ^3$ ->
      SET loop_exit = "user-accepted"
      SET remaining_findings = all_findings ∪ carry_forward
      CONTINUE {cf-studio-path}/.core/workflows/generate/phase-6/index.md
      NOTE: remediation-handoff.md MANDATORY; post-write-handoff.md LOCKED
            until remediation clears

    ^4$ ->
      SET loop_exit = "manual-handoff"
      SET remaining_findings = all_findings ∪ carry_forward
      CONTINUE {cf-studio-path}/.core/workflows/generate/phase-6/index.md
      NOTE: remediation-handoff.md MANDATORY

    ^(stop|enough|done)$ ->
      TREAT as option 4
      LOAD {cf-studio-path}/.core/workflows/shared/stop-token-policy.md

  INVALID:
    EMIT "Reply not recognized. Expected `1`, `2:`, `2: <IDs>`, `3`, or `4`. Reply again."
    NEVER proceed
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT Phase54SessionCarryForward

PURPOSE:
  Define session-level carry_forward maintenance rules (canonical).

STATE:
  - SET carry_forward: set
    default: []
    scope: Phase 5 session
    initial: empty at Phase 5 entry (per phase-5/index.md § Dispatcher)

RULES:
  - ALWAYS union carry_forward after every author dispatch
    (from phase-5.3-findings.md § fast-path OR from this sub-file options 1/2/2:)
    with author's returned findings_not_fixable, deduplicating by finding id
  - ALWAYS FOR option 2: <IDs> and bare 2::
    ALWAYS union every un-approved judgmental finding into carry_forward
    BEFORE the next reviewer pass
  - ALWAYS A finding rejected across multiple iterations appears AT MOST ONCE in final set
  - ALWAYS union carry_forward into remaining_findings on every loop exit
    (author-rejected and user-unapproved judgmental findings NEVER be silently dropped)
```

```pdsl
UNIT Phase54CapPromptRules

PURPOSE:
  Define cap-prompt reply rules after an author write.

RULES:
  - ALWAYS extend: M ->
    SET MAX_ITER = M ONLY when M > current cap
    CONTINUE phase-5.1-det-gate.md
  - ALWAYS accept ->
    RUN post-fix deterministic gate FIRST
    IF gate PASS: SET loop_exit = "max-iter-stopped"
                  SET remaining_findings = carry_forward
    IF gate FAIL: SET loop_exit = "max-iter-stopped-with-failures"
                  CARRY failure into remaining_findings
    CONTINUE phase-5.5-final.md
    NOTE: NEVER reuse stale pre-fix PASS; must run post-fix gate
  - ALWAYS stop ->
    SET loop_exit = "manual-handoff"
    SET remaining_findings = carry_forward

  - ALWAYS AFTER any option that dispatches author worker:
    APPEND selected author dispatch evidence to phase5_dispatch_evidence
      BEFORE updating manifest or claiming files were written
```
