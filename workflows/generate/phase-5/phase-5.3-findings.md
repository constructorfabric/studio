---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the merged findings list (det + semantic) must be displayed, partitioned, and (when all-mechanical) auto-fixed via the fast-path branch.
---

<!-- toc -->

- [Phase 5.3: Findings Display + Auto-Fix-Mechanical Fast Path](#phase-53-findings-display--auto-fix-mechanical-fast-path)

<!-- /toc -->

### Phase 5.3: Findings Display + Auto-Fix-Mechanical Fast Path

```text
UNIT Phase53ExternalEntry

PURPOSE:
  Initialize Phase 5 state on external entry from analyze.md Remediation Handoff option 1.

WHEN:
  external_entry from analyze.md Remediation Handoff option 1

DO:
  MUST RE-PROBE workflows/shared/inline-fallback-probe.md FIRST
    (analyze-side INLINE_FALLBACK does NOT carry across; SUB_AGENT_SESSION_APPROVED carries)
  SET all_findings = merged findings list from analyze (already namespaced per
    workflows/analyze/phase-3-semantic.md § Namespace rule)
  SET carried_validation_results = analyze-side deterministic results
  SET carried_semantic_reports = analyze-side semantic report blocks for Phase 6
    (used especially when MAX_ITER=0)
  SET external_target_paths = analyzed_paths
    MUST preserve until an author dispatch returns non-empty manifest.paths_written
    (downstream remediation re-entry uses it as fallback target set)
  SET target_paths = analyzed_paths (in-scope for every downstream dispatch)
  SET manifest.paths_written = [] until author dispatch returns actual write manifest
  RESOLVE MAX_ITER via workflows/generate/phase-5/index.md § Pre-Phase-Setup
    (default 5 on enter; 0 to skip loop and surface findings to phase-6)
  SET N = 1 (canonical, same as internal entry)
  SET carry_forward = [] (canonical, same as internal entry)

  FOR each unresolved context value (kind, rules_mode, system, kit_rules_path,
    template_path, example_path, checklist_path, name, design_artifact_path):
    IF cannot be inferred from analyze-side handoff:
      EMIT exactly:
---
One or more generate-context values could not be inferred from the analyze-side handoff. Please supply the following:

Why this input is needed: The generate-side author dispatch requires [{variable_name}] to select the correct template/rules/author tier.
Suggested: {inferred_value_from_artifacts_toml_or_N/A_if_not_available}
Reply with `{variable_name}: <value>`
---
      WAIT user.reply
      STOP_TURN

RULES:
  - MUST re-probe inline-fallback-probe.md FIRST before any other external-entry setup
  - MUST emit one prompt per unresolved variable in order:
    kind, rules_mode, system, kit_rules_path, template_path, example_path,
    checklist_path, name, design_artifact_path
  - MUST wait for user reply before proceeding to body of this phase

UNIT Phase53ExternalEntryGuard

PURPOSE:
  Enforce external-fix handoff guard before any file edit or inline patch.

RULES:
  - Before any file edit or inline patch, Phase 5 state MUST show:
    handoff_guard.inline_fallback_reprobed = true
    handoff_guard.max_iter_resolved = true
    handoff_guard.dispatch_evidence_required = true
  - Inline patching permitted ONLY when INLINE_FALLBACK=true OR MAX_ITER=0
  - When MAX_ITER > 0 AND INLINE_FALLBACK=false:
    missing phase5_dispatch_evidence for required validator/reviewer/author sequence
    MUST stop before editing files and repair dispatch state
    FORBID applying patches inline
```

```text
UNIT Phase53Body

PURPOSE:
  Display findings, partition mechanical/judgmental, and route to fast-path or
  approval gate.

DO:
  REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch

  IF MAX_ITER == 0:
    SKIP partition + auto-fix logic
    STILL render full findings list (audit trail in chat)
    IF external analyze→generate entry:
      EMIT "Iteration 1/1 (MAX_ITER=0): zero-iteration external entry;
            surfacing all carried findings to workflows/generate/phase-6/index.md."
      USE carried findings from analyze (no fresh Phase 5 validation/review)
    IF internal generate entry:
      EMIT "Iteration 1/1 (MAX_ITER=0): zero-iteration internal entry;
            surfacing the single-pass findings to workflows/generate/phase-6/index.md."
      USE findings from one fresh validator + semantic-reviewer pass
    SET remaining_findings = all_findings
    CONTINUE workflows/generate/phase-6/index.md
    NOTE: Remediation Handoff menu MANDATORY when remaining_findings non-empty

  SET remaining_findings = []  # before any branch executes

  PARTITION all_findings:
    mechanical = [f for f in all_findings if f.mechanical]
    judgmental = [f for f in all_findings if not f.mechanical]

  IF all_findings is empty AND carry_forward is empty:
    EMIT "Iteration {N}/{MAX_ITER}: clean — exiting review loop."
    SET loop_exit = "clean"
    SET remaining_findings = []
    CONTINUE workflows/generate/phase-5/phase-5.5-final.md

  IF all_findings is empty AND carry_forward non-empty:
    NOTE: loop is not clean; MUST NOT announce clean
    EXIT only as one of:
      loop_exit = "manual-handoff" when user stopped or chose handoff;
        SET remaining_findings = carry_forward
      loop_exit = "user-accepted" when user explicitly accepted carried findings
        after seeing their IDs; SET remaining_findings = carry_forward
    ELSE: STOP and surface protocol error (unresolved carry-forward findings
          cannot be hidden by clean validator pass)
```

#### Findings display (ALWAYS rendered — preserves audit history in the chat)

```text
UNIT Phase53FindingsDisplay

PURPOSE:
  Render every finding in a single ordered list before any fix proceeds.

DO:
  WHEN all_findings non-empty:
    FOR each finding:
      VERIFY finding has non-empty mechanical_rationale string
      IF missing: SUBSTITUTE "<no rationale provided by {agent_name}>"
        MUST NOT abort iteration

    EMIT exactly:
---
Iteration {N}/{MAX_ITER}. Det gate: {PASS|FAIL}. Findings: High {h} / Medium {m} / Low {l}; mechanical {m_count}, judgmental {j_count}.

[{id}] [{mech|judg}] [{severity}] `{path}`:{line} — {category}
       Evidence: "{evidence_quote}"
       Why {mechanical|judgmental}: {mechanical_rationale}
       Suggested fix: {suggested_fix}
[{next id}] ... (one block per finding, mechanical and judgmental interleaved by source order)
---

RULES:
  - MUST emit every finding before deciding next step
  - MUST NOT collapse, summarize, or truncate finding list before user approval
  - MUST ensure displayed list and full findings JSON identify same IDs
    (later fix, prompt, and plan handoffs MUST NOT reference unseen findings)
```

#### Branch — all-mechanical fast path

```text
UNIT Phase53MechanicalFastPath

PURPOSE:
  Auto-fix all findings when judgmental is empty; no user approval required.

WHEN:
  judgmental is EMPTY (every finding has mechanical=true)

DO:
  EMIT immediately after findings display:
---
All {m_count} findings are mechanical — deterministic fixes derivable from each
finding's `mechanical_rationale` alone. No user approval required. Auto-fixing now.
---

  IF user types stop_token BEFORE orchestrator dispatches auto-fix
    (while announcement is being read):
    TREAT as phase-5.4-approval.md § option 4 (manual-handoff)
    SKIP auto-fix dispatch
    SET remaining_findings = all_findings
    SET loop_exit = "manual-handoff"
    CONTINUE workflows/generate/phase-6/index.md

  BUILD mode=fix Inputs contract:
    mode = "fix"
    kind, name, system, rules_mode (carried from phase-4-write.md)
    target_paths = target_paths
    findings = mechanical
    template_path, example_path, kit_rules_path (resolved or null in RELAXED non-kit)
    checklist_path (ONLY when STRICT explicitly requires during fix)
    design_artifact_path (code mode only)
    git_commit_mode = GIT_COMMIT_MODE (MUST be included)
    contributing_guide = CONTRIBUTING_GUIDE (MUST be included; null when not found)
    git_constraint = mode-matched block from phase-4-write.md § Git constraint blocks

  IF INLINE_FALLBACK == true:
    SET CF_PHASE_GATE = released_for_inline_write IMMEDIATELY before inline write block
    RESET CF_PHASE_GATE = armed IMMEDIATELY after inline write block completes
      (both on success AND on failure)

  EXECUTE workflows/generate/phase-4-write.md § Author Selection and Dispatch
  APPEND returned findings_not_fixable to carry_forward
    (open, load, follow {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.4-approval.md § Session-level carry-forward)
  UPDATE manifest from returned manifest
  SET N = N + 1
  IF N > MAX_ITER:
    # NOTE: CF_PHASE_GATE is already armed at this point (reset above after inline write)
    EMIT_MENU Phase5IterationCapPrompt (from phase-5/index.md § Pre-Phase-Setup)
    APPLY cap-reply rules from phase-5.4-approval.md
  ELSE:
    CONTINUE workflows/generate/phase-5/phase-5.1-det-gate.md

RULES:
  - MUST set CF_PHASE_GATE = released_for_inline_write IMMEDIATELY before inline write
  - MUST reset CF_PHASE_GATE = armed IMMEDIATELY after inline write (success or failure)
```

#### Branch — mixed or judgmental-only

```text
UNIT Phase53MixedBranch

PURPOSE:
  Route to user-approval gate when judgmental findings are present.

WHEN:
  judgmental is non-empty

DO:
  CONTINUE workflows/generate/phase-5/phase-5.4-approval.md
    WITH mechanical and judgmental lists in scope
  NOTE: the full findings list above has already been rendered for audit;
        phase-5.4-approval.md menu governs which judgmental findings get
        fixed alongside the mechanical batch
```
