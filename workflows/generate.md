---
cf: true
type: workflow
name: cf-generate
description: Invoke when the user or another skill or workflow explicitly asks for `cf-generate` or `generate`, asks for help choosing the right authoring skill, or needs a generic create-or-update router because no concrete coding, documenting, prompting, or kit workflow has been chosen yet.
version: 2.0
purpose: Backward-compatible generic authoring router that selects the most relevant concrete cf-* skill or companion skill group available in the session, or helps clarify create-or-update intent when none is given.
---

# cf-generate

This workflow is kept as a stable, backwards-compatible entry point for the
`generate` verb. It performs no create-or-modify work itself. Instead it
discovers the `cf-*` skills available to the current session (via the shared
WorkflowResolution rule), matches the user's generate intent against them, and
offers the most relevant skill or companion skill group for invocation —
passing the user's intent into it. When no intent is present it lists the
available `cf-*` skills plus a `describe intent / help me choose` option. The
legacy multi-phase generate workflow has been retired; routing is the only behavior here.

```pdsl
UNIT GenerateBootstrap
PURPOSE: Load the runtime routing rules needed before any generate routing work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapCommandWorkflowResolution
  CONTINUE GenerateRoute
RULES:
  ALWAYS load command-resolution and workflow-resolution before GenerateRoute
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing or delegation
  NEVER require cf or CFS_INIT before routing; this workflow owns its prerequisite loads
```

```pdsl
UNIT GenerateRoute
PURPOSE: Capture the generate intent, resolve cf-* skills via WorkflowResolution, and route to the chosen skill.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET AVAILABLE_SKILLS: list (default unset, scope workflow_run)
  SET GENERATE_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE WorkflowResolution is loaded
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/generate-intent-capture.md WHEN GENERATE_INTENT_CAPTURE_STATE == resume
  CONTINUE GenerateDescribeIntentResume WHEN GENERATE_INTENT_CAPTURE_STATE == resume
  SET ORIGINAL_INTENT = the user's triggering generate request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowResolution to resolve the available cf-* skills
  SET AVAILABLE_SKILLS = the resolved cf-* skills (name + its workflow description), excluding `cf`, `cf-analyze`, and `cf-generate`
  LOAD {cf-studio-path}/.core/skills/studio/modules/generate-skill-fallbacks.md WHEN AVAILABLE_SKILLS is empty
  CONTINUE GenerateNoMatch WHEN AVAILABLE_SKILLS is empty
  LOAD {cf-studio-path}/.core/skills/studio/modules/generate-routing-menus.md
  CONTINUE GenerateRouteIntentFlow WHEN ORIGINAL_INTENT != unset
  CONTINUE GenerateRouteLoadFlow WHEN ORIGINAL_INTENT == unset
RULES:
  ALWAYS preserve ORIGINAL_INTENT when it was already set by GenerateDescribeIntent
  ALWAYS resolve cf-* skills via WorkflowResolution, never by guessing and never via a CLI skills-list command
  ALWAYS exclude `cf`, `cf-analyze`, and `cf-generate` from AVAILABLE_SKILLS and companion groups; these are routers/entrypoints and must never be offered as companions
  ALWAYS pass ORIGINAL_INTENT into every invoked skill when an intent is present
  ALWAYS render each offered skill as `<skill-name> — <short description>` from AVAILABLE_SKILLS
  ALWAYS support compatible companion multi-select, invoking selected skills sequentially so each skill's prerequisites and gates run in order
  NEVER let a companion or multi-select route bypass any selected skill's WAIT, STOP_TURN, approval, brainstorm, plan, validation, or sub-agent gate
  NEVER load or run any legacy generate phase logic; routing is the only behavior
NOTES:
  Empty-state ownership: WorkflowResolution STOP_TURNs when zero cf-* skills are discovered (a broken install), so that case never reaches this router; the CONTINUE GenerateNoMatch WHEN AVAILABLE_SKILLS is empty branch handles the distinct case where resolution succeeds but excluding this router (cf-generate) leaves no other skill.
```
