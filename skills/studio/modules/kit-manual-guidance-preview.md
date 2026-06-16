# Kit Manual Guidance Preview

```pdsl
UNIT KitInitManualGuidanceSynthesizePreview
PURPOSE: Build and render the manual-guidance proposal preview after validation succeeds.
DO:
  RUN synthesize a conservative canonical proposal from the accepted manual guidance using the same canonical shape and containment rules as KitInitDiscoveryProposal, including top-level `manifest_version = "1.0"`
  SET CURRENT_PREVIEW_TOML = the proposed `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the manual guidance classification and ambiguity report
  SET PENDING_MANUAL_GUIDANCE = unset
  CONTINUE KitInitManualGuidanceRenderPreview
RULES:
  ALWAYS produce a fresh proposal from manual guidance before entering the approval menu
  ALWAYS preserve user-provided artifact bindings as constraints-resource `artifacts.<KIND>.*` resource-ID references
  NEVER treat manual guidance as edits to a missing preview
  NEVER write from manual guidance directly
UNIT KitInitManualGuidanceRenderPreview
PURPOSE: Render the manual-guidance proposal preview and wait for approval input.
DO:
  EMIT the manual classification, proposal ambiguities, public generated-name preview, and proposed `.cf-studio-kit.toml` preview
  EMIT_MENU KitInitDiscoveryApprovalMenu
  WAIT user.reply
  STOP_TURN
MENU KitInitManualGuidanceRetryMenu
TITLE: Manual guidance could not produce a safe manifest proposal. Revise it, rerun discovery, or cancel.
OPTIONS:
  1 revise -> WAIT user.reply; STOP_TURN
  2 rerun-discovery -> SET PENDING_MANUAL_GUIDANCE = unset; CONTINUE KitInitDiscoveryRun
  3 cancel -> SET PENDING_MANUAL_GUIDANCE = unset; STOP_TURN
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitManualGuidanceRetryMenu
```
