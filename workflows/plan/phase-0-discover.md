---
cf: true
type: workflow-phase
name: plan-phase-0-discover
description: "Invoke when cf-plan enters Phase 0 to resolve runtime variables and build a dynamic tool map from the CLISPEC."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 0: Resolve Variables & Discover Tools

```pdsl
UNIT Phase0ResolveVariables

PURPOSE:
  Resolve runtime variables and persist them for later phases and context recovery.

DO:
  EXECUTE {cfs_cmd} --json info
  SET {cf-studio-path} = returned value
  SET {project_root} = returned value
  SET {variables} = returned variables dict
  CONTINUE Phase0VariableCheckpoint

NOTES:
  Resolved values must be carried forward to Phase 3.1, where they MUST be
  written into the [meta] TOML table of plan.toml.
```

```pdsl
UNIT Phase0VariableCheckpoint

PURPOSE:
  Ensure resolved variables survive context compaction and resume.

RULES:
  - MUST write {cfs_cmd}, {cf-studio-path}, and {project_root} into plan.toml [meta]
    table in Phase 3.1 so the runtime can read them on resume
  - MUST re-run {cfs_cmd} --json info on context loss or new-chat resume to verify
    or refresh resolved values before any path-dependent step
  - MUST parse plan.toml [meta] table first on resume, then re-run {cfs_cmd} --json info

DO:
  CONTINUE Phase0DiscoverTools

ON_ERROR:
  {cfs_cmd} --json info failure ->
    EMIT "Failed to resolve runtime variables from `{cfs_cmd} --json info`. Verify that {cfs_cmd} is on PATH and the studio is initialised, then retry."
    STOP_TURN
```

## 0.1 Discover Available Tools

```pdsl
UNIT Phase0DiscoverTools

PURPOSE:
  Build a dynamic tool map from the CLISPEC and kit scripts.

DO:
  READ {cf-studio-path}/.core/skills/studio/studio.clispec
  FOR each COMMAND block:
    ADD to tool_map: {command_name} — {DESCRIPTION line} [outputs: {OUTPUT format}]
  FOR each script directory in {variables} (e.g. {scripts} when present):
    SCAN for *.py and *.sh files
    ADD each kit script to tool_map with inferred purpose
```
