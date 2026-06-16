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
  STOP_TURN WHEN the dry-run reports fail or error
RULES:
  ALWAYS validate a newly written `.cf-studio-kit.toml` through dry-run normalization before reporting completion
  NEVER skip validation after a write
  NEVER report success when the dry-run reports fail or error
UNIT KitInitNextActions
PURPOSE: Offer context-grounded next actions after a kit manifest write validates successfully.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN NextActionsOffer
RULES:
  ALWAYS run only after KitInitValidateWrittenManifest reports a passing dry-run validation
```
