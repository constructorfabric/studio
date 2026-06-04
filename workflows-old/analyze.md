---
cf: true
type: workflow
name: cf-analyze
description: Invoke when the user asks to analyze, validate, review, inspect, audit, check, or compare any artifact, code, or instruction document — read-only, tool invocations are validate-only.
version: 1.0
purpose: Universal workflow for analysing any Constructor Studio artifact or code
---

# Analyze

```pdsl
UNIT AnalyzeRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap and preserve analyze routing invariants.
DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
  - CONTINUE RootSkillEntrypointBootstrap
RULES:
  - ALWAYS follow {cf-studio-path}/.core/skills/studio/routing.md § CanonicalRoutingPrecedenceState for explain-mode
    entry, fallback dispatch state, and prompt-context ownership.
```

```pdsl
UNIT AnalyzeModeDirective
PURPOSE: Set cf skill mode and capture original intent before any phase work begins.
DO:
  - SET CF_MODE = "cf-analyze"
  - SET ORIGINAL_INTENT = user's triggering request (verbatim or shortest faithful summary)
RULES:
  - ALWAYS SET CF_MODE = "cf-analyze" as the first action after bootstrap
  - ALWAYS capture ORIGINAL_INTENT from the user's triggering message before any sub-agent dispatch
  - ALWAYS carry ORIGINAL_INTENT into Phase 0 dependencies as the task field
  - ALWAYS include ORIGINAL_INTENT in every reviewer and validator dispatch payload as task context
  - NEVER leave CF_MODE unset when entering this workflow
```

```pdsl
UNIT AnalyzePreambleLoader
PURPOSE: Load preamble before any other phase.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/preamble.md
NOTES: Performs route-only methodology selection and storytelling trigger handling; methodology implementations load only inside matched Phase 3 sub-agents.
```

```pdsl
UNIT AnalyzeRulesMode
PURPOSE: Load STRICT/RELAXED and stop-token behavior before any phase.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/shared/mode-resolution.md
  - CONTINUE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
```

```pdsl
UNIT AnalyzeSharedContextPack
PURPOSE: Keep analyze prompt loading controller-owned and pack-aware.
RULES:
  - ALWAYS Workflow fragments are controller-owned assets loaded from {cf-studio-path}/.core/workflows/...
  - ALWAYS Before reviewer dispatch ALWAYS reuse or extend SHARED_CONTEXT_PACK, load reviewer prompt source, and synthesize a final dispatch prompt with only task-relevant context
  - NEVER rely on sub-agents reopening workflow, requirement, spec, or AGENTS prompt files directly
```

```pdsl
UNIT AnalyzeRulesLoader
PURPOSE: Load completion contract and pre-output self-check.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/rules.md
RULES:
  - ALWAYS load rules.md unconditionally
```

```pdsl
UNIT AnalyzeChangeReviewFailClosed
PURPOSE: Keep change-review runs fail-closed until gate states resolve.
WHEN:
  - REQUIRE CHANGE_REVIEW == true
RULES:
  - ALWAYS Before gate resolution ALWAYS apply {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md § Change-Review Fail-Closed Sentinel
  - NEVER run local git status/diff, cfs validate, semantic review, findings, summaries, or remediation menus while sentinel is active
  - ALWAYS may emit only the missing gate menu or matching `Dispatch blocked: ...` error, then ALWAYS STOP_TURN
```

```pdsl
UNIT AnalyzeOverviewLoader
PURPOSE: Load mode resolution, command surface, prompt-review trigger semantics, and actionable-findings contract.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/overview.md
RULES:
  - ALWAYS load before any phase executes
```

```pdsl
UNIT AnalyzePhase0
PURPOSE: Resolve dependencies and run Mode Detection matrix.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-0-dependencies.md
NOTES: Phase 0 + 0.5 dependency resolution and Mode Detection matrix fully defined in phase-0-dependencies.md.
```

```pdsl
UNIT AnalyzeContextBudgetLoader
PURPOSE: Enforce context budget after dependencies are known and before Phase 0.1.
WHEN:
  - REQUIRE AnalyzePhase0 completed AND (large documents are about to load OR estimated total context > 1200 lines)
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/context-budget.md
```

```pdsl
UNIT AnalyzeExploreGate
PURPOSE: Decide whether discovery is needed before target validation and reviewer dispatch.
WHEN:
  - REQUIRE AnalyzePhase0 completed AND before Phase 0.5 / Phase 1
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md
RULES:
  - ALWAYS delegate explore applicability, replacement, and skip decisions to
    shared/explore-brainstorm-gate.md
  - NEVER run cf-brainstorm before findings; brainstorm is only a later remediation next step
  - ALWAYS pass RESOURCE_CONTEXT to semantic reviewers as resource context only, not prompt context
```

```pdsl
UNIT AnalyzePhase05
PURPOSE: Clarify scope when required by Phase 0 dependency resolution.
WHEN:
  - REQUIRE phase-0-dependencies.md routes scope clarification
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-0.5-scope.md
RULES:
  - NEVER load independently; load only when phase-0-dependencies.md triggers it
```

```pdsl
UNIT AnalyzePhase1
PURPOSE: Run existence check across {PATHS}.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-1-file-check.md
```

```pdsl
UNIT AnalyzePhase2
PURPOSE: Dispatch deterministic validators and enforce gate behavior.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2-det-gate.md
RULES:
  - ALWAYS skip when SEMANTIC_ONLY=true (sub-file enforces; router proceeds to Phase 3)
```

```pdsl
UNIT AnalyzePhase25
PURPOSE: Produce REVIEWER_EXECUTION_PLAN for parallel dispatch in Phase 3.
WHEN:
  - REQUIRE SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
RULES:
  - ALWAYS auto-skip when INLINE_FALLBACK=true, EXPLAIN_MODE=true, or no active methodology flag
NOTES: SUB_AGENT_SESSION_APPROVED and INLINE_FALLBACK declared in {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md § Session Sub-Agent Approval Gate.
```

```pdsl
UNIT AnalyzePhase3
PURPOSE: Run reviewer dispatch matrix, namespaced finding IDs, rules-mode behavior, and EXPLAIN_MODE boundary.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-semantic.md
```

```pdsl
UNIT AnalyzePhase3to4
PURPOSE: Run context-budget recovery checkpoint between semantic review and output.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md
```

```pdsl
UNIT AnalyzePhase4
PURPOSE: Emit output when semantic review or deterministic-gate FAIL is ready.
WHEN:
  - REQUIRE semantic review is complete OR deterministic gate returned FAIL
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-4-output/index.md
NOTES: Dispatcher selects schema sub-file by mode and routes Remediation Handoff menu when actionable findings exist.
```

```pdsl
UNIT AnalyzePhase5
PURPOSE: Offer next steps when overall result is PASS and not in EXPLAIN mode.
WHEN:
  - REQUIRE overall result == PASS AND EXPLAIN_MODE == false
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-5-next-steps.md
```

```pdsl
UNIT AnalyzeTerminal
PURPOSE: Enforce correct terminal block endings for final completion turns while
  permitting legal intermediate WAIT/STOP menus.
INVARIANTS:
  - ALWAYS Final completion turns ALWAYS end with exactly one terminal shape:
      Remediation Handoff menu (actionable findings exist or deterministic gate FAIL, EXPLAIN_MODE=false)
      Phase 5 next-steps menu (overall PASS, EXPLAIN_MODE=false, PARTIAL=false)
      Storytelling output terminal section (EXPLAIN_MODE=true)
      PARTIAL checkpoint + resume menu (review incomplete or context budget exhausted)
  - ALWAYS Legal intermediate WAIT/STOP menus are permitted and NEVER be treated as
    terminal-contract violations. This whitelist includes Phase 0.1
    plan-escalation, Phase 0.5 scope clarification, Phase 3 dispatch recovery,
    Phase 3→4 checkpoint/resume, and prompt-review partial-checkpoint menus.
  - ALWAYS Final completion turns NEVER fall through from PARTIAL or remediation
    states into Phase 5 in the same turn.
  - ALWAYS IF the required terminal file for the active end state is not loadable:
    STOP and surface the missing-file error before emitting that final turn.
```

```pdsl
UNIT AnalyzeStateSummaryLoader
PURPOSE: Load target-type x template / checklist / design matrix.
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/state-summary.md
```

```pdsl
UNIT AnalyzeKeyPrinciplesLoader
PURPOSE: Load key principles when finalizing the response.
WHEN:
  - REQUIRE finalizing the response
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/key-principles.md
```

```pdsl
UNIT AnalyzeSelfTest
PURPOSE: Answer canonical self-test questions in STRICT mode after completing work.
WHEN:
  - REQUIRE STRICT mode finalization requires self-test
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/agent-self-test.md
NOTES: Also referenced from Standard Analysis Output section 4.
```

```pdsl
UNIT AnalyzeValidation
PURPOSE: Verify post-flight checklist before ending the response.
WHEN:
  - REQUIRE post-flight checklist must be verified before ending the response
DO:
  - CONTINUE {cf-studio-path}/.core/workflows/analyze/validation-criteria.md
```
