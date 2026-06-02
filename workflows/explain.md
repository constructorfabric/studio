---
cf: true
type: workflow
name: cf-explain
description: "Invoke for requests to explain, walk through, teach, onboard, give a code tour, produce a source-grounded narrative, or summarize a decision."
version: 1.0
purpose: Standalone explain command; pass-through to analyze.md with EXPLAIN mode
---

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
  - ALWAYS follow routing.md § CanonicalRoutingPrecedenceState and require
    EXPLAIN_MODE=true before entering analyze mode.
  - ALWAYS If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - ALWAYS This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```pdsl
UNIT ExplainProxy

PURPOSE:
  Pass through to analyze.md with EXPLAIN mode active.

DO:
  - REQUIRE EXPLAIN_MODE == true
  - SET analyze.dispatch_state.EXPLAIN_MODE = true
  - LOAD skill `cf` IN ANALYZE + EXPLAIN mode, EXPLAIN_MODE=true
  - RUN The target analyze workflow ALWAYS apply
  - RUN {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md;
  - RUN cf-explore is required when explanation targets are not explicit.
  - RUN Completion signal from the target analyze/storytelling flow ALWAYS include:
    { "type": "EXPLAIN_RESULT", "status": "complete|checkpointed|cancelled", "session_id": "<id|null>", "progress": "<X/N|null>", "resume_path": "<path|null>" }
  - RUN Every complete, checkpointed, cancelled, deterministic-failure, or wrap exit
  - RUN ALWAYS emit this EXPLAIN_RESULT envelope. When EXPLAIN_MODE owns the output,
  - RUN deterministic validation failure is represented as EXPLAIN_RESULT with
  - RUN status="checkpointed" and failure/resume metadata unless analyze.md explicitly
  - RUN overrides EXPLAIN_MODE into remediation output before storytelling begins.

ON_ERROR:
  load_failed ->
    EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set."
    EMIT_MENU ExplainLoadFailureMenu
    WAIT user.reply
    STOP_TURN

MENU ExplainLoadFailureMenu:
  TITLE: "Explain target workflow failed to load."
  OPTIONS:
    1 retry -> LOAD {cf-studio-path}/.core/workflows/analyze.md; CONTINUE ExplainProxy
    2 route -> SET EXPLAIN_MODE = false; CONTINUE {cf-studio-path}/.core/skills/studio/routing.md
    3 stop -> EMIT { "type": "EXPLAIN_RESULT", "status": "cancelled", "session_id": null, "progress": null, "resume_path": null }; STOP_TURN
  INVALID:
    EMIT "Reply `1`, `2`, or `3`."
    WAIT user.reply
    STOP_TURN
```
