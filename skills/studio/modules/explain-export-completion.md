# Explain Completion

```pdsl
UNIT ExplainCompletion
PURPOSE: Return the explain completion envelope, then offer context-grounded next actions.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT the EXPLAIN_RESULT envelope
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after storytelling wrap completes and control is about to return to the user
  ALWAYS emit the EXPLAIN_RESULT envelope before offering next actions
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```

```pdsl
UNIT ExplainExport
PURPOSE: Write the finalized Markdown package when export mode is active.
WHEN:
  REQUIRE EXPLAIN_EXPORT == true
DO:
  RUN ExplainExportContextPrep
  RUN TemplateVarResolution before resolving the export package path
  RUN SubAgentDispatch for the storytelling-export dispatch group before launching export
  DISPATCH storytelling-export to write the finalized package under {cf-studio-path}/.cache/explain/packages/{slug}-{ISO}/ (index.md, per-portion files, navigation, mode extras)
  RETURN the EXPLAIN_RESULT envelope
  STOP_TURN
RULES:
  NEVER export a socratic session — refuse with the required message and write nothing
  ALWAYS in export mode keep navigation in file footers and chat to E0/E1 plus the final summary (no per-portion chat nav)
```

```pdsl
UNIT ExplainDispatch
PURPOSE: Name the storytelling sub-agents used per phase and guard the dispatch rails.
RULES:
  ALWAYS dispatch storytelling-preflight from {cf-studio-path}/.core/skills/studio/agents/storytelling-preflight.md (E0 input-access tier + session-discovery + size guards)
  ALWAYS dispatch storytelling-context-pack from {cf-studio-path}/.core/skills/studio/agents/storytelling-context-pack.md (E1.5 read-once content pack)
  ALWAYS dispatch the storytelling sub-agents from {cf-studio-path}/.core/skills/studio/agents/ per phase — storytelling-preflight (E0), storytelling-gate (each E1 gate plus context-pack-strategy/export-format gates), storytelling-context-pack (E1.5), storytelling-wrap (E5), storytelling-export (export)
  ALWAYS run SubAgentDispatch before every native storytelling dispatch group; preset gate resolution skips prompt dispatches only when the workflow explicitly resolves the gate without launching an agent
  ALWAYS dispatch cf-explorer via INVOKE skill `cf-explore` for non-explicit targets, never by dispatching cf-explorer directly
  ALWAYS pass ExplainExploreGate-resolved RESOURCE_CONTEXT to storytelling-preflight and storytelling-context-pack as read-only context references when provided
  ALWAYS deliver storytelling prompt content to sub-agents through prompt_context_view / pack handles
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
