# Auto-Config Scan

```pdsl
UNIT AutoConfigScan
PURPOSE: Scan the project read-only via cf-explore and confirm the scan summary before detection.
STATE:
  SET resource_context: object (default empty, scope workflow_run)
DO:
  RUN ResourceContextMemory
  INVOKE skill `cf-explore` with intent=analyze and return_context=true to scan the project read-only and return resource_context (it handles large repos via parallel partitioning)
  SET resource_context = the resource_context returned by cf-explore
  RUN extract project surface, entry points, structure, conventions, and a documentation inventory from the returned resource_context
  EMIT the Scan Summary checkpoint: project, languages, architecture, entry points, modules, key conventions, and systems detected
  EMIT_MENU ScanConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS scan via cf-explore in return-context mode and never write during the scan
  ALWAYS present the scan summary and confirm before detection
  ALWAYS keep scan output as resource_context, not the shared context pack
MENU ScanConfirmMenu
TITLE: Scan summary — proceed to documentation discovery?
OPTIONS:
  1 proceed -> LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-docs.md; CONTINUE AutoConfigDocs
  2 adjust -> re-run the scan or re-emit the summary, then EMIT_MENU ScanConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the scan summary checkpoint" and next_action="re-run auto-config to restart the scan" and STOP_TURN
  INVALID -> EMIT_MENU ScanConfirmMenu
```
