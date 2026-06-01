---
cf: true
type: workflow
name: cf-auto-config
description: "Invoke for requests to auto-config, initialize a project, discover config, set up a kit, set up agent integration, configure a workspace, or scan a brownfield project."
version: 1.0
purpose: Standalone auto-config command; pass-through to generate.md with AUTO_CONFIG mode
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
  - If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```text
UNIT AutoConfigProxy

PURPOSE:
  Pass through to generate.md with AUTO_CONFIG mode active.

DO:
  LOAD skill `cf` IN GENERATE + AUTO_CONFIG mode, AUTO_CONFIG=true
  The target generate workflow MUST apply
  {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md;
  cf-explore is required for auto-config before config writes.
  Completion signal from the generate side MUST be one of:
    { "type": "AUTO_CONFIG_RESULT", "status": "complete", "paths_written": [], "validation_status": "PASS|WARN|FAIL|SKIPPED" }
    { "type": "AUTO_CONFIG_RESULT", "status": "blocked", "reason": "<one-line>", "next_action": "<user action>" }
    { "type": "AUTO_CONFIG_RESULT", "status": "failed", "reason": "<one-line>", "recovery": "<next action>" }

ON_ERROR:
  load_failed -> EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set." STOP_TURN
```
