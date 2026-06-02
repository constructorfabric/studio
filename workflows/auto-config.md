---
cf: true
type: workflow
name: cf-auto-config
description: "Invoke for requests to auto-config, initialize a project, discover config, set up a kit, set up agent integration, configure a workspace, or scan a brownfield project."
version: 1.0
purpose: Standalone auto-config command; pass-through to generate.md with AUTO_CONFIG mode
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
  - ALWAYS If this workflow file is opened directly, STOP workflow phases until
    SKILL.md has been loaded completely and followed.
  - ALWAYS This gate applies to the top-level controller only; dispatched sub-agents
    consume the synthesized final prompt and supplied context slices.
```

```pdsl
UNIT AutoConfigProxy

PURPOSE:
  Pass through to generate.md with AUTO_CONFIG mode active.

DO:
  - RUN INTERPRET user intent as auto-config methodology execution:
    - "auto-config", "auto-config update", "update auto-config",
      "rescan", "refresh rules", and equivalents mean scan/rescan the
      project and generate or update inferred config/rules.
    - They NEVER be satisfied by `cfs update`, `make update`, bootstrap
      refresh, kit refresh, cache refresh, or generated-agent refresh unless
      the user explicitly asks for those update commands instead of
      auto-config.
  - LOAD skill `cf` IN GENERATE + AUTO_CONFIG mode, AUTO_CONFIG=true
  - RUN The target generate workflow ALWAYS apply
  - RUN {cf-studio-path}/.core/workflows/shared/explore-brainstorm-gate.md;
  - RUN cf-explore is required for auto-config before config writes.
  - RUN The target generate workflow ALWAYS enter the AUTO_CONFIG fast path before
  - RUN normal generate update/write routing, author-planning for arbitrary config
  - RUN updates, or CLI update suggestions from `{cfs_cmd} --json info`.
  - RUN Completion signal from the generate side ALWAYS be one of:
    { "type": "AUTO_CONFIG_RESULT", "status": "complete", "paths_written": [], "validation_status": "PASS|WARN|FAIL|SKIPPED" }
    { "type": "AUTO_CONFIG_RESULT", "status": "blocked", "reason": "<one-line>", "next_action": "<user action>" }
    { "type": "AUTO_CONFIG_RESULT", "status": "failed", "reason": "<one-line>", "recovery": "<next action>" }

ON_ERROR:
  load_failed -> EMIT "Cannot load target workflow — check that {cf-studio-path} is correctly set." STOP_TURN
```
