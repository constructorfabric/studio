---
cf: true
type: workflow
name: cf-explain
description: "Invoke for requests to explain, walk through, teach, onboard, give a code tour, produce a source-grounded narrative, or summarize a decision."
version: 1.0
purpose: Standalone explain command; pass-through to analyze.md with EXPLAIN mode
---

```text
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
  - MUST follow routing.md § CanonicalRoutingPrecedenceState and require
    EXPLAIN_MODE=true before entering analyze mode.
  - If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```text
UNIT ExplainProxy

PURPOSE:
  Pass through to analyze.md with EXPLAIN mode active.

DO:
  REQUIRE EXPLAIN_MODE == true
  SET analyze.dispatch_state.EXPLAIN_MODE = true
  LOAD skill `cf` IN ANALYZE + EXPLAIN mode, EXPLAIN_MODE=true
  The target analyze workflow MUST apply
  {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md;
  cf-explore is required when explanation targets are not explicit.
  Completion signal from the target analyze/storytelling flow MUST include:
    { "type": "EXPLAIN_RESULT", "status": "complete|checkpointed|cancelled", "session_id": "<id|null>", "progress": "<X/N|null>", "resume_path": "<path|null>" }

ON_ERROR:
  load_failed -> EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set." STOP_TURN
```
