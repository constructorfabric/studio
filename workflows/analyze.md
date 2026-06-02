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
UNIT RootSkillEntrypointBootstrap
PURPOSE: Prevent direct workflow entry from bypassing the root cf skill.
DO:
  1. REQUIRE {cf-studio-path}/.core/skills/studio/SKILL.md is loaded completely
     and followed FIRST.
  2. REQUIRE CfSkillInit, Bootstrap, HardRules, and
     WorkflowProtocolNonSubstitution from SKILL.md have completed.
  3. CONTINUE this workflow only after the root cf skill routing/entrypoint
     selects it.
RULES:
  - MUST execute before any workflow-specific unit in this file.
  - MUST_NOT treat protocol.md, routing.md, or a thin proxy skill as a
    substitute for loading and following SKILL.md.
  - MUST follow routing.md § CanonicalRoutingPrecedenceState for explain-mode
    entry, fallback dispatch state, and prompt-context ownership.
  - If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```pdsl
UNIT AnalyzePreamble
PURPOSE: Load preamble before any other phase.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/preamble.md
NOTES: Performs route-only methodology selection and storytelling trigger handling; methodology implementations load only inside matched Phase 3 sub-agents.
```

```pdsl
UNIT AnalyzeRulesMode
PURPOSE: Load STRICT/RELAXED and stop-token behavior before any phase.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/shared/mode-resolution.md
  CONTINUE {cf-studio-path}/.core/workflows/shared/stop-token-policy.md
```

```pdsl
UNIT AnalyzeSharedContextPack
PURPOSE: Keep analyze prompt loading controller-owned and pack-aware.
RULES:
  - Workflow fragments are controller-owned assets loaded from {cf-studio-path}/.core/workflows/...
  - Before reviewer dispatch MUST reuse or extend SHARED_CONTEXT_PACK, load reviewer prompt source, and synthesize a final dispatch prompt with only task-relevant context
  - MUST_NOT rely on sub-agents reopening workflow, requirement, spec, or AGENTS prompt files directly
```

```pdsl
UNIT AnalyzeRules
PURPOSE: Load completion contract and pre-output self-check.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/rules.md
RULES:
  - MUST load rules.md unconditionally
```

```pdsl
UNIT AnalyzeChangeReviewFailClosed
PURPOSE: Keep change-review runs fail-closed until gate states resolve.
WHEN: CHANGE_REVIEW == true
RULES:
  - Before gate resolution MUST apply {cf-studio-path}/.core/skills/studio/SKILL.md § Change-Review Fail-Closed Sentinel
  - MUST_NOT run local git status/diff, cfs validate, semantic review, findings, summaries, or remediation menus while sentinel is active
  - MAY emit only the missing gate menu or matching `Dispatch blocked: ...` error, then MUST STOP_TURN
```

```pdsl
UNIT AnalyzeOverview
PURPOSE: Load mode resolution, command surface, prompt-review trigger semantics, and actionable-findings contract.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/overview.md
RULES:
  - MUST load before any phase executes
```

```pdsl
UNIT AnalyzePhase0
PURPOSE: Resolve dependencies and run Mode Detection matrix.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-0-dependencies.md
NOTES: Phase 0 + 0.5 dependency resolution and Mode Detection matrix fully defined in phase-0-dependencies.md.
```

```pdsl
UNIT AnalyzeContextBudget
PURPOSE: Enforce context budget after dependencies are known and before Phase 0.1.
WHEN: AnalyzePhase0 completed AND (large documents are about to load OR estimated total context > 1200 lines)
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/context-budget.md
```

```pdsl
UNIT AnalyzeExploreGate
PURPOSE: Decide whether discovery is needed before target validation and reviewer dispatch.
WHEN: AnalyzePhase0 completed AND before Phase 0.5 / Phase 1
DO:
  CONTINUE {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md
RULES:
  - MUST delegate explore applicability, replacement, and skip decisions to
    shared/explore-brainstorm-gate.md
  - MUST NOT run cf-brainstorm before findings; brainstorm is only a later remediation next step
  - MUST pass RESOURCE_CONTEXT to semantic reviewers as resource context only, not prompt context
```

```pdsl
UNIT AnalyzePhase05
PURPOSE: Clarify scope when required by Phase 0 dependency resolution.
WHEN: phase-0-dependencies.md routes scope clarification
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-0.5-scope.md
RULES:
  - MUST NOT load independently; load only when phase-0-dependencies.md triggers it
```

```pdsl
UNIT AnalyzePhase1
PURPOSE: Run existence check across {PATHS}.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-1-file-check.md
```

```pdsl
UNIT AnalyzePhase2
PURPOSE: Dispatch deterministic validators and enforce gate behavior.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2-det-gate.md
RULES:
  - MUST skip when SEMANTIC_ONLY=true (sub-file enforces; router proceeds to Phase 3)
```

```pdsl
UNIT AnalyzePhase25
PURPOSE: Produce REVIEWER_EXECUTION_PLAN for parallel dispatch in Phase 3.
WHEN: SUB_AGENT_SESSION_APPROVED == true AND INLINE_FALLBACK == false
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-2.5-reviewer-plan.md
RULES:
  - MUST auto-skip when INLINE_FALLBACK=true, EXPLAIN_MODE=true, or no active methodology flag
NOTES: SUB_AGENT_SESSION_APPROVED and INLINE_FALLBACK declared in SKILL.md § Session Sub-Agent Approval Gate.
```

```pdsl
UNIT AnalyzePhase3
PURPOSE: Run reviewer dispatch matrix, namespaced finding IDs, rules-mode behavior, and EXPLAIN_MODE boundary.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-semantic.md
```

```pdsl
UNIT AnalyzePhase3to4
PURPOSE: Run context-budget recovery checkpoint between semantic review and output.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-3-to-4-checkpoint.md
```

```pdsl
UNIT AnalyzePhase4
PURPOSE: Emit output when semantic review or deterministic-gate FAIL is ready.
WHEN: semantic review is complete OR deterministic gate returned FAIL
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-4-output/index.md
NOTES: Dispatcher selects schema sub-file by mode and routes Remediation Handoff menu when actionable findings exist.
```

```pdsl
UNIT AnalyzePhase5
PURPOSE: Offer next steps when overall result is PASS and not in EXPLAIN mode.
WHEN: overall result == PASS AND EXPLAIN_MODE == false
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/phase-5-next-steps.md
```

```pdsl
UNIT AnalyzeTerminal
PURPOSE: Enforce correct terminal block endings for final completion turns while
  permitting legal intermediate WAIT/STOP menus.
INVARIANTS:
  - Final completion turns MUST end with exactly one terminal shape:
      Remediation Handoff menu (actionable findings exist or deterministic gate FAIL, EXPLAIN_MODE=false)
      Phase 5 next-steps menu (overall PASS, EXPLAIN_MODE=false, PARTIAL=false)
      Storytelling output terminal section (EXPLAIN_MODE=true)
      PARTIAL checkpoint + resume menu (review incomplete or context budget exhausted)
  - Legal intermediate WAIT/STOP menus are permitted and MUST_NOT be treated as
    terminal-contract violations. This whitelist includes Phase 0.1
    plan-escalation, Phase 0.5 scope clarification, Phase 3 dispatch recovery,
    Phase 3→4 checkpoint/resume, and prompt-review partial-checkpoint menus.
  - Final completion turns MUST_NOT fall through from PARTIAL or remediation
    states into Phase 5 in the same turn.
  - IF the required terminal file for the active end state is not loadable:
    STOP and surface the missing-file error before emitting that final turn.
```

```pdsl
UNIT AnalyzeStateSummary
PURPOSE: Load target-type x template / checklist / design matrix.
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/state-summary.md
```

```pdsl
UNIT AnalyzeKeyPrinciples
PURPOSE: Load key principles when finalizing the response.
WHEN: finalizing the response
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/key-principles.md
```

```pdsl
UNIT AnalyzeSelfTest
PURPOSE: Answer canonical self-test questions in STRICT mode after completing work.
WHEN: STRICT mode finalization requires self-test
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/agent-self-test.md
NOTES: Also referenced from Standard Analysis Output section 4.
```

```pdsl
UNIT AnalyzeValidation
PURPOSE: Verify post-flight checklist before ending the response.
WHEN: post-flight checklist must be verified before ending the response
DO:
  CONTINUE {cf-studio-path}/.core/workflows/analyze/validation-criteria.md
```
