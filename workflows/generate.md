---
cf: true
type: workflow
name: cf-generate
description: Invoke when the user asks to create, update, edit, fix, implement, refactor, add, set up, configure, or build any artifact or code — universal create-or-modify workflow.
version: 1.0
purpose: Universal workflow for creating or updating any artifact or code
---

# Generate

```pdsl
UNIT RootSkillEntrypointBootstrap
PURPOSE: Prevent direct workflow entry from bypassing the root cf skill.
DO:
  - REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded completely
     and followed FIRST.
  - REQUIRE CfSkillInit, Bootstrap, HardRules, and
     WorkflowProtocolNonSubstitution from SKILL.md have completed.
  - CONTINUE this workflow only after the root cf skill routing/entrypoint
     selects it.
RULES:
  - ALWAYS execute before any workflow-specific unit in this file.
  - NEVER treat protocol.md, routing.md, or a thin proxy skill as a
    substitute for loading and following SKILL.md.
  - ALWAYS follow routing.md § CanonicalRoutingPrecedenceState for workflow
    entry, fallback dispatch state, and prompt-context ownership.
  - ALWAYS If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - ALWAYS This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```pdsl
UNIT Generate

PURPOSE: Universal create-or-modify workflow for any artifact or code.

STATE:
  - SET TARGET_TYPE:                 artifact | code | config      default: artifact
  - SET MODE:                        create | update               default: create
  - SET GIT_COMMIT_MODE:             set | unset                   default: unset   scope: session
  - SET SUB_AGENT_SESSION_APPROVED:  unset | true                  default: unset   scope: session
  - SET INLINE_FALLBACK:             unset | true | false          default: unset   scope: workflow_run
  - SET INLINE_FALLBACK_PROBED:      false | true                  default: false   scope: workflow_run
  - SET AUTHOR_PLAN_OFFER_RESOLVED:  unresolved | memory | disk | auto_skipped_no_author_plan_flag | auto_skipped_rules_disabled | cancelled_by_stop_token | cancelled_planner_failure
                               default: unresolved
  - SET RESOURCE_CONTEXT:            present | absent              default: absent
  - SET SHARED_CONTEXT_PACK:         present | absent              default: absent

RULES:
  - ALWAYS Artifact mode: use template + example by default; load checklist only when current rules require it before writing
  - ALWAYS Code mode: use design/spec context first; defer checklist to validation/review unless rules require earlier
  - ALWAYS Config mode: create/update config files
  - ALWAYS After protocol.md: TARGET_TYPE, RULES, KIND, PATH, MODE, and phase-appropriate deps are known
  - ALWAYS Key vars: {cf-studio-path}/config/, {ARTIFACTS_REGISTRY}, {KITS_PATH}, {PATH}
  - ALWAYS Use {KITS_PATH}/artifacts/{KIND}/examples/ for style/quality guidance
  - ALWAYS Workflow fragments are controller-owned; loaded from {cf-studio-path}/.core/workflows/...
  - ALWAYS Before any downstream author/reviewer dispatch: controller ALWAYS reuse or extend SHARED_CONTEXT_PACK,
    load the agent prompt source, and synthesize a final dispatch prompt with only task-relevant context
  - NEVER rely on sub-agents reopening workflow, requirement, spec, or AGENTS prompt files directly
  - ALWAYS Late phases and prompt-consuming sub-agents ALWAYS consume only controller-supplied
    prompt_context_view slices from SHARED_CONTEXT_PACK; they NEVER reopen prompt assets from disk
  - ALWAYS estimate size before loading large docs and state the budget for this turn
  - ALWAYS load only generation-phase sections required for current KIND
  - ALWAYS defer checklist loading to validation/review unless rules require earlier
  - ALWAYS The controller ALWAYS lazy-load Phase 1.5 only at the first post-approval branch
    after Phase 1 inputs approved where author-plan applicability, storage mode,
    author-plan-derived dispatch, or author-plan-derived menu behavior must be resolved
  - ALWAYS Eager Phase 1.5 applicability is limited to instruction-file classification,
    explicit auto-skip conditions, and the boundary that author-plan resolution
    ALWAYS happen before Phase 3 summary or disk/write-path selection where applicable
  - ALWAYS The controller ALWAYS load the minimal validation manifest eagerly and defer the
    detailed post-flight checklist and STRICT self-test until the final validation gate
  - ALWAYS use read_file ranges, summarize each chunk, keep only extracted criteria
  - ALWAYS stop and output a checkpoint in chat (do not write files) if required steps cannot fit in context
  - ALWAYS WHEN SUB_AGENT_SESSION_APPROVED=true AND INLINE_FALLBACK=false AND INLINE_FALLBACK_PROBED=true:
      gate logs estimate and proceeds without proposing Invoke skill `cf-plan`;
      decomposition handled in-workflow by Phase 1.5 (mandatory in that branch)
  - ALWAYS WHEN INLINE_FALLBACK_PROBED=false:
      run shared/inline-fallback-probe.md before reading INLINE_FALLBACK or
      entering any fallback-gated branch
  - ALWAYS WHEN INLINE_FALLBACK_PROBED=true:
      fallback-gated branches may read INLINE_FALLBACK only as resolved by
      shared/inline-fallback-probe.md for the active workflow run
  - ALWAYS OTHERWISE: plan-escalation gate offers Invoke skill `cf-plan` or stop when native
    sub-agent dispatch is not active; estimate is informational and local
    single-context continuation is not the default fallback
  - ALWAYS Critical anti-pattern failures (STRICT mode): SKIP_TEMPLATE, SKIP_EXAMPLE, SKIP_CHECKLIST,
    PLACEHOLDER_SHIP, NO_CONFIRMATION, SIMULATED_VALIDATION
  - ALWAYS self-check before writing files (STRICT mode): template loaded, example referenced,
    no placeholders, explicit `yes` received
  - ALWAYS stop and fix before proceeding if any self-check answer fails
  - ALWAYS include self-check results in Phase 3 Summary output (STRICT mode)
  - ALWAYS Reference: {cf-studio-path}/.core/requirements/agent-compliance.md for full anti-pattern list

DO:
  // Rules mode
  - REQUIRE {cf-studio-path}/.core/skills/studio/protocol.md
  - REQUIRE {cf-studio-path}/.core/workflows/shared/mode-resolution.md
  - REQUIRE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md

  // BROWNFIELD gate
  - REQUIRE project is BROWNFIELD:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/reverse-engineering.md

  // Phase 0: dependencies (delegates INLINE_FALLBACK probe to shared/inline-fallback-probe.md)
  - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0-dependencies.md

  // Phase 0.a: explore/brainstorm gate
  - REQUIRE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md

  // Phase 0.1: plan escalation gate (mandatory after deps load)
  - REQUIRE {cf-studio-path}/.core/workflows/shared/plan-escalation-gate.md

  // Phase 0.2: review-loop config (MAX_ITER)
  - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0.2-review-loop-cfg.md

  // Eager validation boundary: minimal validation manifest only
  - REQUIRE entering Generate eager validation boundary to load the minimal validation manifest before any late validation fragments:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/validation-criteria.md § Minimal Validation Manifest

  // Phase 0.x: GIT_COMMIT_MODE probe
  - REQUIRE GIT_COMMIT_MODE == unset:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0-git-commit-mode.md

  // Phase 0.5: clarify output/context
  - REQUIRE system context or output destination is unclear:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0.5-clarify.md

  // Phase 0.7: brainstorm
  - REQUIRE NOT --no-brainstorm AND NOT KIND.rules.brainstorm == "disabled":
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-0.7/index.md

  // Phase 1: collect inputs
  - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-1-collect.md

  // Phase 1.5: lazy-load after Phase 1 inputs approved at the first post-approval branch
  - REQUIRE Phase 1 inputs approved AND current branch is the first post-approval branch that must resolve author-plan applicability, storage mode, author-plan-derived dispatch, or author-plan-derived menu behavior before Phase 3 summary or disk/write-path selection where applicable:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-1.5-author-plan.md

  // Phase 2 / 2.5: no-op or checkpoint
  - REQUIRE artifact >10 sections OR expected multi-turn OR resumable section/state bookkeeping is required:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-2-checkpoint.md

  // Phase 3: summary + confirmation gate (no files written until explicit yes)
  - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-3-summary.md

  // Phase 4: write files atomically
  - REQUIRE Phase3 == yes:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-4-write.md

  // Phase 5: bounded review loop
  - REQUIRE Phase 4 writes complete OR entering from external analyze remediation entry with analyze-side accepted payload predicates, payload shaping/mapping onto the Phase 5 contract, and branch mapping already resolved:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-5/index.md

  // Phase 6: next-steps and handoff menus
  - REQUIRE Phase 5 exit requires validation results, validation/waiver state, files changed, findings, waivers, or unresolved validation state reporting
     OR Phase 5 was entered from external analyze remediation handoff:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/phase-6/index.md

  // Post-flight validation: lazy-load detailed checklist only when ending the run
  - REQUIRE preparing post-flight validation, terminal handoff, or final response output:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/validation-criteria.md § Detailed Post-Flight Checklist

  - REQUIRE STRICT_MODE AND preparing final response gate:
    - REQUIRE {cf-studio-path}/.core/workflows/generate/validation-criteria.md § Agent Self-Test (STRICT mode — post-flight lazy)

RULES:
  // Phase 0.a
  - ALWAYS delegate explore/brainstorm applicability and ordering to
    shared/explore-brainstorm-gate.md
  - ALWAYS carry RESOURCE_CONTEXT into Phase 0.7 and Phase 1 when exploration ran
  - NEVER put resource files into SHARED_CONTEXT_PACK
  // Phase 0.x
  - ALWAYS skip GIT_COMMIT_MODE probe if already set from an earlier run in this session
  // Phase 1.5
  - ALWAYS Author plan is mandatory unless an explicit auto-skip condition applies
  - ALWAYS User chooses storage mode (memory or disk), not whether planning runs
  - ALWAYS Phase 1.5 entry predicates are evaluated eagerly after Phase 1 inputs approved,
    but the full phase body is lazy-loaded only at the first post-approval branch
    that needs author-plan resolution before Phase 3 summary or disk/write-path
    selection where applicable
  - ALWAYS Phase 2 checkpoint loading is lazy; load it only for artifact >10 sections,
    expected multi-turn execution, or resumable section/state bookkeeping
  - ALWAYS Phase 5 review-loop loading is lazy; load it only after Phase 4 writes complete
    or when analyze.md hands remediation into the external entry with accepted
    payload predicates, payload shaping/mapping onto the Phase 5 contract, and
    branch mapping already resolved
  // Phase 6
  - ALWAYS Phase 6 menu loading is lazy; load it only when Phase 5 exit must report
    validation results, validation/waiver state, files changed, findings, waivers,
    or unresolved validation state, OR when Phase 5 was entered from external
    analyze remediation handoff
  - ALWAYS External analyze remediation entry ALWAYS end with an explicit Phase 6
    terminal handoff/return menu even when no files were written and no
    remaining findings exist
  - ALWAYS Remediation Handoff: conditional on non-empty remaining_findings
  - ALWAYS Post-Write Review Handoff: mandatory when files were written

ON_ERROR:
  tool/dispatch failure        -> REQUIRE {cf-studio-path}/.core/workflows/generate/error-handling.md
  user abandonment             -> REQUIRE {cf-studio-path}/.core/workflows/generate/error-handling.md
  validation-failure >= 3 iter -> REQUIRE {cf-studio-path}/.core/workflows/generate/error-handling.md

NOTES:
  phase-0-dependencies.md delegates INLINE_FALLBACK probe to shared/inline-fallback-probe.md
  (same canonical block reused by analyze.md).
  MAX_ITER prompt + parser live in phase-5/index.md § Pre-Phase-Setup (also analyze.md external-entry point).
  Phase 5 also accepts external entry from analyze.md Remediation Handoff option 1 into
  Phase 5.3 only after analyze-side accepted payload predicates, payload shaping/mapping
  onto the Phase 5 contract, and branch mapping are already resolved.
```
