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

```pdsl
UNIT Phase53ExternalEntry

PURPOSE:
  Initialize Phase 5 state on external entry from analyze.md Remediation Handoff option 1.

WHEN:
  - REQUIRE external_entry from analyze.md Remediation Handoff option 1

DO:
  - RUN ALWAYS RE-PROBE workflows/shared/inline-fallback-probe.md FIRST
    (analyze-side INLINE_FALLBACK does NOT carry across; SUB_AGENT_SESSION_APPROVED carries)
  - SET all_findings = merged findings list from analyze (already namespaced per
    workflows/analyze/phase-3-semantic.md § Namespace rule)
  - SET carried_validation_results = analyze-side deterministic results
  - SET carried_semantic_reports = analyze-side semantic report blocks for Phase 6
    (used especially when MAX_ITER=0)
  - SET external_target_paths = analyzed_paths
    ALWAYS preserve until an author dispatch returns non-empty manifest.paths_written
    (downstream remediation re-entry uses it as fallback target set)
  - SET target_paths = analyzed_paths (in-scope for every downstream dispatch)
  - SET manifest.paths_written = [] until author dispatch returns actual write manifest
  - RUN RESOLVE MAX_ITER via workflows/generate/phase-5/index.md § Pre-Phase-Setup
    (default 5 on enter; 0 to skip loop and surface findings to phase-6)
  - SET N = 1 (canonical, same as internal entry)
  - SET carry_forward = [] (canonical, same as internal entry)

  - RUN FOR each unresolved context value (kind, rules_mode, system, kit_rules_path,
    template_path, example_path, checklist_path, name, design_artifact_path):
    IF cannot be inferred from analyze-side handoff:
      - EMIT exactly:
- RUN ---
- RUN One or more generate-context values could not be inferred from the analyze-side handoff. Please supply the following:

- RUN Why this input is needed: The generate-side author dispatch requires [{variable_name}] to select the correct template/rules/author tier.
- RUN Suggested: {inferred_value_from_artifacts_toml_or_N/A_if_not_available}
- RUN Reply with `{variable_name}: <value>`
- RUN ---
      - WAIT user.reply
      - STOP_TURN

RULES:
  - ALWAYS re-probe inline-fallback-probe.md FIRST before any other external-entry setup
  - ALWAYS emit one prompt per unresolved variable in order:
    kind, rules_mode, system, kit_rules_path, template_path, example_path,
    checklist_path, name, design_artifact_path
  - ALWAYS wait for user reply before proceeding to body of this phase

UNIT Phase53ExternalEntryGuard

PURPOSE:
  Enforce external-fix handoff guard before any file edit or inline patch.

RULES:
  - ALWAYS Before any file edit or inline patch, Phase 5 state ALWAYS show:
    handoff_guard.inline_fallback_reprobed = true
    handoff_guard.max_iter_resolved = true
    handoff_guard.dispatch_evidence_required = true
  - ALWAYS Inline patching permitted ONLY when INLINE_FALLBACK=true OR MAX_ITER=0
  - ALWAYS When MAX_ITER > 0 AND INLINE_FALLBACK=false:
    before the first external-entry author dispatch, missing author dispatch
    evidence ALWAYS stop before editing files and repair dispatch state
  - ALWAYS When MAX_ITER > 0 AND INLINE_FALLBACK=false:
    after the first external-entry author dispatch, missing validator/reviewer
    dispatch evidence for any post-author iteration that reached Phase 5.1/5.2
    ALWAYS stop before any further edit and repair dispatch state
    NEVER applying patches inline
```

```pdsl
UNIT Phase53Body

PURPOSE:
  Display findings, partition mechanical/judgmental, and route to fast-path or
  approval gate.

DO:
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before dispatch

  - REQUIRE MAX_ITER == 0:
    SKIP partition + auto-fix logic
    STILL render full findings list (audit trail in chat)
    IF external analyze→generate entry:
      - EMIT "Iteration 1/1 (MAX_ITER=0): zero-iteration external entry;
            surfacing all carried findings to workflows/generate/phase-6/index.md."
      USE carried findings from analyze (no fresh Phase 5 validation/review)
    IF internal generate entry:
      - EMIT "Iteration 1/1 (MAX_ITER=0): zero-iteration internal entry;
            surfacing the single-pass findings to workflows/generate/phase-6/index.md."
      USE findings from one fresh validator + semantic-reviewer pass
    - SET remaining_findings = all_findings
    - CONTINUE workflows/generate/phase-6/index.md
    NOTE: Remediation Handoff menu MANDATORY when remaining_findings non-empty

  - SET remaining_findings = []  # before any branch executes

  - REQUIRE external analyze→generate entry AND N == 1 AND MAX_ITER >= 1:
    USE carried analyze findings as all_findings
    SKIP fresh Phase 5.1 / Phase 5.2 before this first Phase 5.3 pass
    NOTE: the first author dispatch fixes already-reviewed analyze findings;
          Phase 5.1 / Phase 5.2 run after that write to verify the result

  - RUN PARTITION all_findings:
    mechanical = [f for f in all_findings if f.mechanical]
    judgmental = [f for f in all_findings if not f.mechanical]

  - REQUIRE all_findings is empty AND carry_forward is empty:
    - EMIT "Iteration {N}/{MAX_ITER}: clean — exiting review loop."
    - SET loop_exit = "clean"
    - SET remaining_findings = []
    - CONTINUE workflows/generate/phase-5/phase-5.5-final.md

  - REQUIRE all_findings is empty AND carry_forward non-empty:
    NOTE: loop is not clean; NEVER announce clean
    EXIT only as one of:
      loop_exit = "manual-handoff" when user stopped or chose handoff;
        - SET remaining_findings = carry_forward
      loop_exit = "user-accepted" when user explicitly accepted carried findings
        after seeing their IDs; SET remaining_findings = carry_forward
    ELSE: STOP and surface protocol error (unresolved carry-forward findings
          cannot be hidden by clean validator pass)
```

#### Findings display (ALWAYS rendered — preserves audit history in the chat)

```pdsl
UNIT Phase53FindingsDisplay

PURPOSE:
  Render every finding in a single ordered list before any fix proceeds.

DO:
  - RUN WHEN all_findings non-empty:
    FOR each finding:
      VERIFY finding has non-empty mechanical_rationale string
      IF missing: SUBSTITUTE "<no rationale provided by {agent_name}>"
        - NEVER abort iteration

    - EMIT exactly:
- RUN ---
- RUN Iteration {N}/{MAX_ITER}. Det gate: {PASS|FAIL}. Findings: High {h} / Medium {m} / Low {l}; mechanical {m_count}, judgmental {j_count}.

- RUN [{id}] [{mech|judg}] [{severity}] `{path}`:{line} — {category}
       Evidence: "{evidence_quote}"
       Why {mechanical|judgmental}: {mechanical_rationale}
       Suggested fix: {suggested_fix}
- RUN [{next id}] ... (one block per finding, mechanical and judgmental interleaved by source order)
- RUN ---

RULES:
  - ALWAYS emit every finding before deciding next step
  - NEVER collapse, summarize, or truncate finding list before user approval
  - ALWAYS ensure displayed list and full findings JSON identify same IDs
    (later fix, prompt, and plan handoffs NEVER reference unseen findings)
```

#### Branch — all-mechanical fast path

```pdsl
UNIT Phase53MechanicalFastPath

PURPOSE:
  Auto-fix all findings when judgmental is empty; no user approval required.

WHEN:
  - REQUIRE judgmental is EMPTY (every finding has mechanical=true)

DO:
  - EMIT immediately after findings display:
- RUN ---
- RUN All {m_count} findings are mechanical — deterministic fixes derivable from each
- RUN finding's `mechanical_rationale` alone. No user approval required. Auto-fixing now.
- RUN ---

  - RUN NOTE: This fast path has no user-input WAIT point after the announcement.
        Stop tokens are observable only at explicit menus/WAIT states such as
        Phase 5.4 approval or the iteration-cap menu; they NEVER be modeled
        as an interruptible announcement-read branch.

  - RUN BUILD mode=fix Inputs contract:
    mode = "fix"
    kind, name, system, rules_mode (carried from phase-4-write.md)
    target_paths = target_paths
    findings = mechanical
    template_path, example_path, kit_rules_path (resolved or null in RELAXED non-kit)
    checklist_path (ONLY when STRICT explicitly requires during fix)
    design_artifact_path (code mode only)
    git_commit_mode = GIT_COMMIT_MODE (ALWAYS be included)
    contributing_guide = CONTRIBUTING_GUIDE (ALWAYS be included; null when not found)
    git_constraint = mode-matched block from phase-4-write.md § Git constraint blocks

  - REQUIRE INLINE_FALLBACK == true:
    - SET CF_PHASE_GATE = released_for_inline_write IMMEDIATELY before inline write block
    RESET CF_PHASE_GATE = armed IMMEDIATELY after inline write block completes
      (both on success AND on failure)

  - RUN EXECUTE workflows/generate/phase-4-write.md § Author Selection and Dispatch
  - RUN APPEND phase5_dispatch_evidence record:
    phase = "5.3"
    agent_id = selected_author
    target_paths = target_paths
    result_marker = returned Written block or manifest marker
    iteration = N
  - RUN APPEND returned findings_not_fixable to carry_forward
    (open, load, follow {cf-studio-path}/.core/workflows/generate/phase-5/phase-5.4-approval.md § Session-level carry-forward)
  - RUN UPDATE manifest from returned manifest
  - SET N = N + 1
  - REQUIRE N > MAX_ITER:
    # NOTE: CF_PHASE_GATE is already armed at this point (reset above after inline write)
    - EMIT_MENU Phase5IterationCapPrompt (from phase-5/index.md § Pre-Phase-Setup)
    APPLY cap-reply rules from phase-5.4-approval.md
  - RUN otherwise
    - CONTINUE workflows/generate/phase-5/phase-5.1-det-gate.md

RULES:
  - ALWAYS set CF_PHASE_GATE = released_for_inline_write IMMEDIATELY before inline write
  - ALWAYS reset CF_PHASE_GATE = armed IMMEDIATELY after inline write (success or failure)
```

#### Branch — mixed or judgmental-only

```pdsl
UNIT Phase53MixedBranch

PURPOSE:
  Route to user-approval gate when judgmental findings are present.

WHEN:
  - REQUIRE judgmental is non-empty

DO:
  - CONTINUE workflows/generate/phase-5/phase-5.4-approval.md
    WITH mechanical and judgmental lists in scope
  - RUN NOTE: the full findings list above has already been rendered for audit;
        phase-5.4-approval.md menu governs which judgmental findings get
        fixed alongside the mechanical batch
```
