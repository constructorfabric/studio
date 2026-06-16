# Auto-Config Integrate


```pdsl
UNIT AutoConfigIntegrate
PURPOSE: Build AGENTS.md navigation rules and registry entries, writing only after explicit confirmation.
WHEN:
  REQUIRE the generated rule files are written
DO:
  RUN build AGENTS.md WHEN navigation rules — one whole-file rule per topic file; doc rules pointing at actionable headings — inside the managed blocks auto-config:rules and auto-config:docs
  RUN build detected-system entries for {cf-studio-path}/config/artifacts.toml
  EMIT the proposed AGENTS.md and registry changes for review
  EMIT_MENU IntegrateConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS restrict writes to {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/config/artifacts.toml
  ALWAYS preserve all user-authored content outside the auto-config managed blocks
  ALWAYS validate generated TOML and that every WHEN rule resolves to an accessible file or heading
MENU IntegrateConfirmMenu
TITLE: AGENTS.md and registry changes — write them and proceed to validation?
OPTIONS:
  1 proceed -> WRITE to {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/config/artifacts.toml, then CONTINUE AutoConfigValidate
  2 adjust -> revise the navigation rules / registry entries and EMIT_MENU IntegrateConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the AGENTS.md/registry review checkpoint; no integration written" and next_action="re-run auto-config to continue from rule generation" and STOP_TURN
  INVALID -> EMIT_MENU IntegrateConfirmMenu
```

```pdsl
UNIT AutoConfigValidate
PURPOSE: Validate the generated output and return the auto-config completion envelope.
WHEN:
  REQUIRE the AGENTS.md and registry changes are written
DO:
  RUN structural validation: all rule files exist, all WHEN rules resolve, registry entries point to existing directories, TOML valid
  RUN quality validation: prompt-engineering L2 no ambiguity, L5 no AP-VAGUE/AP-CONTEXT-BLOAT/AP-HALLUCINATION-PRONE, L6 compactness — each generated rule file within the 120-line generation target
  EMIT the validation report: systems detected, topic files generated, WHEN rules added, registry entries, per-check PASS/WARN/FAIL
  RETURN the AUTO_CONFIG_RESULT envelope
  LOAD {cf-studio-path}/.core/skills/studio/modules/auto-config-next-dispatch.md
  CONTINUE AutoConfigNextActions
RULES:
  ALWAYS emit the validation report and RETURN the AUTO_CONFIG_RESULT envelope on every terminal exit
  ALWAYS treat the terminal state as auto-config completion, not generation
NOTES:
  complete: { "type": "AUTO_CONFIG_RESULT", "status": "complete", "paths_written": [], "validation_status": "PASS|WARN|FAIL|SKIPPED" }
  blocked: { "type": "AUTO_CONFIG_RESULT", "status": "blocked", "reason": "<one-line>", "next_action": "<user action>" }
  failed: { "type": "AUTO_CONFIG_RESULT", "status": "failed", "reason": "<one-line>", "recovery": "<next action>" }
```
