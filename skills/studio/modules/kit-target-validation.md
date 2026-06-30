# Kit Target Validation
```pdsl
UNIT KitInitValidateWrittenManifestRun
PURPOSE: Validate the canonical manifest after it has been written and report deterministic status.
WHEN:
  REQUIRE TARGET_SOURCE == legacy_manifest OR TARGET_SOURCE == discovery
DO:
  RUN `{cfs_cmd} kit normalize <target> --dry-run`
  RUN inspect the normalized manifest report for constraints resources with artifact kinds but no explicit template/example bindings; report these as actionable warnings because `validate-kits` will skip self-check for unknown relationships
  EMIT the validation report, manifest summary, and any warnings WHEN the dry-run passes
  EMIT the validation findings and the path that needs revision WHEN the dry-run reports fail or error
  CONTINUE KitInitNextActions WHEN the dry-run passes
  EMIT_MENU KitInitValidationFailureMenu WHEN the dry-run reports fail or error
  WAIT user.reply WHEN the dry-run reports fail or error
  STOP_TURN WHEN the dry-run reports fail or error
MENU KitInitValidationFailureMenu
TITLE: Kit manifest validation failed. How would you like to proceed?
OPTIONS:
  1 retry — I have fixed the manifest, re-run validation -> CONTINUE KitInitValidateWrittenManifestRun
  2 edit — open the manifest for review and editing -> LOAD {cf-studio-path}/.core/skills/studio/modules/kit-edit-flow.md; SET PENDING_EDIT_BRANCH = canonical; CONTINUE KitInitApplyUserEditsStart
  3 stop — return to free mode -> LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer
  INVALID -> EMIT_MENU KitInitValidationFailureMenu
RULES:
  ALWAYS validate a newly written `.cf-studio-kit.toml` through dry-run normalization before reporting completion
  NEVER skip validation after a write
  NEVER report success when the dry-run reports fail or error
UNIT KitInitNextActions
PURPOSE: Offer context-grounded next actions after a kit manifest write validates successfully.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded
  RUN NextActionsOffer
RULES:
  ALWAYS run only after KitInitValidateWrittenManifest reports a passing dry-run validation
```
