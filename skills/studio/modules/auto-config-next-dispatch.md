# Auto-Config Next

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
PURPOSE: Name how phases are driven and guard against substituting an update command for auto-config.
RULES:
  ALWAYS scan via INVOKE skill `cf-explore` (intent=analyze, return_context=true), never by dispatching cf-explorer directly
  ALWAYS drive rule generation, integration, and validation from the controller with a user confirmation gate at each phase
  NEVER satisfy auto-config by running `cfs update`, `make update`, bootstrap refresh, kit refresh, cache refresh, or generated-agent refresh unless the user explicitly switches to those commands
```
