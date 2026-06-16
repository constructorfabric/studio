---
cf: true
type: workflow
name: cf-auto-config
description: "Invoke for requests to auto-config, initialize a project, discover config, set up a kit, set up agent integration, configure a workspace, or scan a brownfield project."
version: 0.1
purpose: Scan a brownfield project and generate per-topic rule files plus AGENTS.md navigation and registry entries, confirming at every checkpoint and never writing without approval.
---

# cf-auto-config

This skill scans a brownfield project — via the cf-explore skill — and generates per-topic rule files plus AGENTS.md WHEN navigation rules and registry entries, confirming at every checkpoint and never writing a file without explicit approval. It detects systems and semantic topics from scan evidence, drives rule generation, integration, and validation through controller-owned phases, and is never satisfied by `cfs update` or `make update`.

```pdsl
UNIT AutoConfigBootstrap
PURPOSE: Load the runtime rules and auto-config methodology before any auto-config work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapRouterPrelude
  RUN WorkflowBootstrapSimpleModeGate
  RUN WorkflowBootstrapStudioInstructionsMemory
  RUN WorkflowBootstrapCommandTemplateContext
  LOAD {cf-studio-path}/.core/requirements/auto-config.md as the phase-by-phase methodology reference
  RUN verify the methodology loaded; RETURN a failed AUTO_CONFIG_RESULT with reason="Auto-config methodology not found at {cf-studio-path}/.core/requirements/auto-config.md" and recovery="reinstall or sync the studio kit, then retry auto-config" and STOP_TURN WHEN the load fails
  SET ORIGINAL_INTENT = the user's triggering auto-config request (verbatim or shortest faithful summary)
  SET PLAN_FIRST_CONTINUE = AutoConfigPrecheckGate, SET CURRENT_WORKFLOW = cf-auto-config, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer
RULES:
  ALWAYS run StudioInstructionsMemoryGate before auto-config prechecks, routing, scanning, or writes
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` auto-config prechecks
  ALWAYS load template-vars before resolving config paths or unknown template variables
  ALWAYS load context-memory before storing scan output as resource_context
  ALWAYS load and follow the auto-config methodology for phase detail
  NEVER continue past bootstrap when the methodology reference fails to load
  NEVER require cf or CFS_INIT before auto-config; this workflow owns its prerequisite loads
```
```pdsl
UNIT AutoConfigPrecheckGate
PURPOSE: Apply the canonical auto-config preconditions, then route into the scan (or a refresh-mode menu).
WHEN:
  REQUIRE entering auto-config
DO:
  RUN the canonical pre-checks defined by AutoConfigPreconditions in {cf-studio-path}/.core/requirements/auto-config.md — Studio initialized (RUN `{cfs_cmd} info` and expect FOUND), source code accessible, and {cf-studio-path}/config/ writable; RETURN a blocked AUTO_CONFIG_RESULT with reason="Studio not initialized" and next_action="run `cfs init`, then retry auto-config" and STOP_TURN WHEN the `{cfs_cmd} info` check errors or does not report FOUND
  RETURN a blocked AUTO_CONFIG_RESULT with reason="No source code found; the project appears greenfield" and next_action="add source code or run auto-config on a brownfield project, then retry" and STOP_TURN WHEN no source code is found or the project is greenfield
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
  1 proceed -> CONTINUE AutoConfigDocs
  2 adjust -> re-run the scan or re-emit the summary, then EMIT_MENU ScanConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the scan summary checkpoint" and next_action="re-run auto-config to restart the scan" and STOP_TURN
  INVALID -> EMIT_MENU ScanConfirmMenu
```
```pdsl
UNIT AutoConfigDocs
PURPOSE: Discover project documentation, offer TOCs, and confirm doc navigation rules.
WHEN:
  REQUIRE the scan summary is confirmed
DO:
  RUN build a documentation inventory from resource_context (path, title, has-TOC, key headings, WHEN condition)
  RUN for each doc missing a TOC, EMIT a non-blocking suggestion "To add a TOC, run `{cfs_cmd} toc <doc>`"; never run the command or block discovery on it
  EMIT the Documentation Map and proposed navigation rules checkpoint
  EMIT_MENU DocsConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS present the documentation map and proposed navigation rules before detection
  NEVER add TOCs without confirmation
MENU DocsConfirmMenu
TITLE: Documentation map — proceed to system and topic detection?
OPTIONS:
  1 proceed -> CONTINUE AutoConfigDetect
  2 adjust -> re-emit the documentation map, then EMIT_MENU DocsConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the documentation map checkpoint" and next_action="re-run auto-config to continue from the scan" and STOP_TURN
  INVALID -> EMIT_MENU DocsConfirmMenu
```
```pdsl
UNIT AutoConfigDetect
PURPOSE: Detect systems and semantic topics, then confirm the system map and topic split before generating.
WHEN:
  REQUIRE the documentation map is confirmed
DO:
  RUN detect systems (Monolith | Monorepo | Microservices | Library) and semantic topics (conventions, architecture, patterns, testing, api-contracts, infrastructure, security, anti-patterns)
  EMIT the System Map and Topic/Rule-file map checkpoints
  EMIT_MENU DetectConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS propose only topics with at least 3 project-specific rules, merge topics with fewer, and split any topic over 120 lines
  ALWAYS confirm the system map and topic split before generating
  ALWAYS use activity-based WHEN conditions, never location-based
MENU DetectConfirmMenu
TITLE: System and topic map — proceed to rule generation?
OPTIONS:
  1 proceed -> CONTINUE AutoConfigGenerate
  2 adjust -> revise systems/topics per user feedback and EMIT_MENU DetectConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the system/topic map checkpoint" and next_action="re-run auto-config to continue" and STOP_TURN
  INVALID -> EMIT_MENU DetectConfirmMenu
```
```pdsl
UNIT AutoConfigGenerate
PURPOSE: Generate per-topic rule files from scan evidence and write them only after explicit confirmation.
WHEN:
  REQUIRE the topic map is confirmed
DO:
  RUN generate per-topic rule files from scan evidence — each rule grounded in `file:line` evidence, activity-based, passing prompt-engineering L2 clarity (no vague qualifiers, explicit activity-based WHEN) and L5 anti-pattern checks (no AP-VAGUE, AP-CONTEXT-BLOAT, AP-HALLUCINATION-PRONE), under 120 lines, no overlap, no boilerplate; one topic file includes a Critical Files table
  EMIT the generated rule-file batch for review
  EMIT_MENU GenerateConfirmMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS present generated rule files before writing any file
  NEVER write without explicit confirmation
  ALWAYS restrict rule-file writes to {cf-studio-path}/config/rules/
MENU GenerateConfirmMenu
TITLE: Generated rule files — write them and proceed to integration?
OPTIONS:
  1 proceed -> WRITE the rule files to {cf-studio-path}/config/rules/{topic}.md, RUN `{cfs_cmd} toc` on each, then CONTINUE AutoConfigIntegrate
  2 adjust -> revise the rule files per feedback and EMIT_MENU GenerateConfirmMenu
  3 cancel -> RETURN a blocked AUTO_CONFIG_RESULT with reason="auto-config cancelled at the rule-file review checkpoint; no files written" and next_action="re-run auto-config to regenerate and review the rule files" and STOP_TURN
  INVALID -> EMIT_MENU GenerateConfirmMenu
```
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
  CONTINUE AutoConfigNextActions
RULES:
  ALWAYS emit the validation report and RETURN the AUTO_CONFIG_RESULT envelope on every terminal exit
  ALWAYS treat the terminal state as auto-config completion, not generation
NOTES:
  complete: { "type": "AUTO_CONFIG_RESULT", "status": "complete", "paths_written": [], "validation_status": "PASS|WARN|FAIL|SKIPPED" }
  blocked: { "type": "AUTO_CONFIG_RESULT", "status": "blocked", "reason": "<one-line>", "next_action": "<user action>" }
  failed: { "type": "AUTO_CONFIG_RESULT", "status": "failed", "reason": "<one-line>", "recovery": "<next action>" }
```

```pdsl
UNIT AutoConfigNextActions
PURPOSE: Offer context-grounded next actions after auto-config completes and returns its completion envelope.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN NextActionsOffer
RULES:
  ALWAYS run only after AutoConfigValidate has emitted validation results and returned the AUTO_CONFIG_RESULT envelope
```
```pdsl
UNIT AutoConfigDispatch
PURPOSE: Name how the scan is delegated and guard against substituting an update command for auto-config.
RULES:
  ALWAYS scan via INVOKE skill `cf-explore` (intent=analyze, return_context=true), never by dispatching cf-explorer directly
  ALWAYS drive rule generation, integration, and validation from the controller with a user confirmation gate at each phase
  NEVER satisfy auto-config by running `cfs update`, `make update`, bootstrap refresh, kit refresh, cache refresh, or generated-agent refresh unless the user explicitly switches to those commands
```
