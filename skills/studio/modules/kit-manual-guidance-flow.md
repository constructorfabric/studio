# Kit Manual Guidance Flow
```pdsl
UNIT KitInitManualGuidanceProposalStart
PURPOSE: Turn user-provided manual resource guidance into a fresh manifest proposal when discovery returned no usable context.
WHEN:
  REQUIRE PENDING_MANUAL_GUIDANCE == true
DO:
  CONTINUE KitInitManualGuidanceParseAndValidate
  CONTINUE KitInitManualGuidanceHandleInvalid
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-manual-guidance-preview.md
  CONTINUE KitInitManualGuidanceSynthesizePreview
UNIT KitInitManualGuidanceParseAndValidate
PURPOSE: Parse manual guidance and determine whether it is valid enough to synthesize a proposal.
DO:
  RUN parse the user reply as manual candidate resources, optional multiple kit declarations, resource kinds, metadata defaults, aliases, install paths, generated targets, and exclusions
  RUN parse optional artifact binding guidance such as `bind artifact <KIND>.template=<resource-id>`, `bind artifact <KIND>.examples=<resource-id>`, `bind artifact <KIND>.rules=<resource-id>`, and `bind artifact <KIND>.checklist=<resource-id>`
  RUN reject guidance that references sources outside TARGET_DIR, uses unsupported resource kinds, creates duplicate IDs, proposes an unsupported `manifest_version`, binds an artifact role to an unknown resource ID, binds artifact metadata outside a constraints resource, or omits every candidate resource
UNIT KitInitManualGuidanceHandleInvalid
PURPOSE: Re-prompt for manual guidance when the supplied guidance is invalid.
DO:
  EMIT rejected guidance with reasons and EMIT_MENU KitInitManualGuidanceRetryMenu WHEN guidance is invalid
  WAIT user.reply WHEN guidance is invalid
  STOP_TURN WHEN guidance is invalid
```
