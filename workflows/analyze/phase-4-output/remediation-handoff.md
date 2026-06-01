---
name: analyze-phase-4-remediation-handoff
description: "Invoke when the analyze result contains actionable issues to append the terminal Remediation Handoff menu offering fix, plan, or next-step options."
purpose: Terminal Remediation Handoff menu for actionable analyze findings
loaded_by: workflows/analyze.md
version: 1.0
---

# Analyze Phase 4 — Remediation Handoff

```text
UNIT AnalyzeRemediationHandoff

PURPOSE:
  Emit the mandatory Remediation Handoff menu when actionable findings exist,
  and route the next turn to the selected remediation path.

WHEN:
  actionable findings exist
  AND EXPLAIN_MODE == false

DO:
  EMIT_MENU RemediationHandoffMenu
  WAIT user.reply
  STOP_TURN

MENU RemediationHandoffMenu:
  TITLE: |
    Actionable findings: High {h} / Medium {m} / Low {l}. How do you want to proceed?
    Suggested: {1|2|3} because {scope/risk reason}.
  OPTIONS:
    1 -> Continue here in fix mode:
           Re-probe INLINE_FALLBACK via workflows/shared/inline-fallback-probe.md
           EMIT canonical MAX_ITER resolution prompt from
             workflows/generate/phase-5/index.md § Pre-Phase-Setup (default 5; 0 skips loop)
           WAIT user.reply for MAX_ITER
           Initialize Phase 5 state internally:
             all_findings = merged findings
             analyzed_paths = analyzed paths
             external_target_paths = analyzed_paths
             target_paths = analyzed_paths
             manifest.paths_written = []
             carry deterministic results and semantic report blocks
           SET handoff_guard.inline_fallback_reprobed = true
           SET handoff_guard.max_iter_resolved = true
           SET handoff_guard.dispatch_evidence_required = true
           IF MAX_ITER == 0:
             CONTINUE workflows/generate/phase-5/phase-5.3-findings.md
               (sets remaining_findings = all_findings; routes to phase-6/index.md
                with mandatory remediation-handoff.md menu)
           IF MAX_ITER > 0:
             CONTINUE workflows/generate/phase-5/phase-5.3-findings.md
             using carried analyze findings as the first iteration's findings
             BEFORE any fresh Phase 5.1 / 5.2 review
             First author dispatch fixes the already-reviewed analyze findings.
             After author dispatch, every subsequent iteration MUST dispatch
               cf-deterministic-validator (5.1) and matched semantic reviewer
               sub-agent set (5.2) on the written files before any further
               author dispatch
             FORBID re-running validator/reviewer before the first author
               dispatch merely to refresh findings already produced by analyze
    2 -> EMIT fix-prompt-template.md as the FINAL section
    3 -> EMIT plan-prompt-template.md as the FINAL section
  INVALID:
    EMIT "Reply `1`, `2`, or `3`."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST emit this menu as the FINAL section of the current response when
    actionable findings exist AND EXPLAIN_MODE=false
  - MUST_NOT defer the menu to a later user turn
  - MUST_NOT ask whether the menu should be generated
  - MUST_NOT replace this menu with a generic next-step menu
  - MUST_NOT emit Fix Prompt or Plan Prompt unless user picks option 2 or 3
    in the NEXT turn; both MUST be self-contained with all findings, paths,
    and context embedded inline
  - MUST re-probe INLINE_FALLBACK before any Phase 5 dispatch after option 1
  - MUST_NOT shortcut the fix loop with inline review, inline fix, or
    single-pass summary when MAX_ITER > 0
  - MUST produce phase5_dispatch_evidence for author dispatch before the first
    external-entry edit when MAX_ITER > 0 AND INLINE_FALLBACK=false; validator
    and semantic reviewer dispatch evidence is required for every post-author
    iteration that reaches Phase 5.1 / 5.2
  - EXPLAIN_MODE=true disables this menu entirely

NOTES:
  "Actionable findings" = any FAIL, PARTIAL, blocking validator error, or
  recommendation requiring artifact, code, or instruction changes.
  Prompt templates are on-demand only: self-contained, start with
  "Invoke skill `cf`", include full findings inline, include target path/kind
  and deterministic gate status, state the route, ask the next agent to
  fix root causes plus tests/validation.
```
