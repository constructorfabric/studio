---
cf: true
type: workflow
name: cf-analyze
description: Invoke when the user or another skill or workflow explicitly asks for `cf-analyze` or `analyze`, asks for help choosing the right analysis skill, or needs a generic analysis router because no concrete review, validation, or inspection workflow has been chosen yet.
version: 2.0
purpose: Backward-compatible generic analysis router that selects the most relevant concrete cf-* skill or companion skill group available in the session, or helps clarify analysis intent when none is given.
---

# cf-analyze

This workflow is kept as a stable, backwards-compatible entry point for the
`analyze` verb. It performs no analysis itself. Instead it discovers the cf-*
skills available to the current session (via the shared WorkflowResolution
rule), matches the user's analyze intent against them, and offers the most
relevant skill or companion skill group for invocation — passing the user's
intent into it. When no intent is present it lists the available cf-* skills
plus a `describe intent / help me choose` option. The legacy
multi-phase analyze workflow has been retired; routing is the only behavior here.

```pdsl
UNIT AnalyzeBootstrap
PURPOSE: Load the runtime routing rules needed before any analyze routing work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapCommandWorkflowResolution
  CONTINUE AnalyzeRoute
RULES:
  ALWAYS load command-resolution and workflow-resolution before AnalyzeRoute
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing or delegation
  NEVER require cf or CFS_INIT before routing; this workflow owns its prerequisite loads
```

```pdsl
UNIT AnalyzeRoute
PURPOSE: Capture the analyze intent, resolve cf-* skills via WorkflowResolution, and route to the chosen skill.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET AVAILABLE_SKILLS: list (default unset, scope workflow_run)
  SET ANALYZE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE WorkflowResolution is loaded
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-intent-capture.md WHEN ANALYZE_INTENT_CAPTURE_STATE == resume
  CONTINUE AnalyzeDescribeIntentResume WHEN ANALYZE_INTENT_CAPTURE_STATE == resume
  SET ORIGINAL_INTENT = the user's triggering analyze request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowResolution to resolve the available cf-* skills
  SET AVAILABLE_SKILLS = the resolved cf-* skills (name + its workflow description), excluding `cf`, `cf-analyze`, and `cf-generate`
  LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-skill-fallbacks.md WHEN AVAILABLE_SKILLS is empty
  CONTINUE AnalyzeNoMatch WHEN AVAILABLE_SKILLS is empty
  LOAD {cf-studio-path}/.core/skills/studio/modules/analyze-routing-menus.md
  CONTINUE AnalyzeRouteIntentFlow WHEN ORIGINAL_INTENT != unset
  CONTINUE AnalyzeRouteLoadFlow WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS preserve ORIGINAL_INTENT when it was already set by AnalyzeDescribeIntent
  ALWAYS resolve cf-* skills via WorkflowResolution, never by guessing and never via a CLI skills-list command
  ALWAYS exclude `cf`, `cf-analyze`, and `cf-generate` from AVAILABLE_SKILLS and companion groups; these are routers/entrypoints and must never be offered as companions
  ALWAYS pass ORIGINAL_INTENT into every invoked skill and render each offered skill as `<skill-name> — <short description>` from AVAILABLE_SKILLS
  ALWAYS support compatible companion multi-select, invoking selected skills sequentially so each skill's prerequisites and gates run in order
INVARIANTS:
  NEVER let a companion or multi-select route bypass any selected skill's WAIT, STOP_TURN, approval, brainstorm, plan, validation, or sub-agent gate
  NEVER load or run any legacy analyze phase logic; routing is the only behavior
NOTES:
  Empty-state ownership: WorkflowResolution STOP_TURNs when zero cf-* skills are discovered (a broken install), so that case never reaches this router; the CONTINUE AnalyzeNoMatch WHEN AVAILABLE_SKILLS is empty branch handles the distinct case where resolution succeeds but excluding this router (cf-analyze) leaves no other skill.
```
