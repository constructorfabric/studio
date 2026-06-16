# Auto-Config Precheck

```pdsl
UNIT AutoConfigPrecheckGate
PURPOSE: Apply the canonical auto-config preconditions, then route into the scan (or a refresh-mode menu).
WHEN:
  REQUIRE entering auto-config
DO:
  RUN the canonical pre-checks defined by AutoConfigPreconditions in {cf-studio-path}/.core/requirements/auto-config.md — Studio initialized (RUN `{cfs_cmd} info` and expect FOUND), source code accessible, and {cf-studio-path}/config/ writable; RETURN a blocked AUTO_CONFIG_RESULT with reason="Studio not initialized" and next_action="run `cfs init`, then retry auto-config" and STOP_TURN WHEN the `{cfs_cmd} info` check errors or does not report FOUND
  RETURN a blocked AUTO_CONFIG_RESULT with reason="No source code found; the project appears greenfield" and next_action="add source code or run auto-config on a brownfield project, then retry" and STOP_TURN WHEN no source code is found or the project is greenfield
  LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-scan-docs.md
  EMIT_MENU ExistingRulesRefreshMenu WHEN existing generated rule files or auto-config managed blocks are present
  CONTINUE AutoConfigScan WHEN no existing generated rules or managed blocks are present
RULES:
  ALWAYS treat AutoConfigPreconditions in {cf-studio-path}/.core/requirements/auto-config.md as the authoritative pre-check definition; this gate only runs it and routes on the result
  NEVER begin the scan until pre-checks pass and, when rules already exist, a refresh mode is chosen
  NEVER overwrite user-authored rules
MENU ExistingRulesRefreshMenu
TITLE: Existing auto-config rules or navigation blocks were found. Choose how to refresh them.
OPTIONS:
  1 refresh -> regenerate generated rules + auto-config AGENTS blocks from a new scan, then CONTINUE AutoConfigScan
  2 selective | select -> choose files/sections to refresh after the scan, then CONTINUE AutoConfigScan
  3 report-only | report -> scan and report findings with writes to existing rule files disabled, then CONTINUE AutoConfigScan
  4 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the existing-rules refresh prompt" and next_action="re-run auto-config and choose a refresh mode to continue" and STOP_TURN
  INVALID -> EMIT_MENU ExistingRulesRefreshMenu
```
