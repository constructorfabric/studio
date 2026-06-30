# Kit Edit Render

```pdsl
UNIT KitInitApplyUserEditsApplyValid
PURPOSE: Apply valid edits and store the revised manifest preview artifacts.
DO:
  RUN apply valid edits to CURRENT_PREVIEW_TOML
  RUN re-render the proposed `.cf-studio-kit.toml`
  SET CURRENT_PREVIEW_TOML = the revised `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the revised preview report and remaining ambiguities

UNIT KitInitApplyUserEditsRender
PURPOSE: Render the revised preview and route back to the matching approval menu.
DO:
  EMIT the revised public generated-name preview, revised manifest preview, and remaining ambiguities
  CONTINUE KitInitApplyUserEditsRenderLegacy WHEN PENDING_EDIT_BRANCH == legacy_manifest
  CONTINUE KitInitApplyUserEditsRenderDiscovery WHEN PENDING_EDIT_BRANCH == discovery
  CONTINUE KitInitApplyUserEditsRenderCanonical WHEN PENDING_EDIT_BRANCH == canonical
UNIT KitInitApplyUserEditsRenderLegacy
PURPOSE: Return an edited legacy-source preview to its approval menu.
DO:
  EMIT_MENU KitInitLegacyApprovalMenu
  SET PENDING_EDIT_BRANCH = unset
  WAIT user.reply
  STOP_TURN
UNIT KitInitApplyUserEditsRenderDiscovery
PURPOSE: Return an edited discovery preview to its approval menu.
DO:
  EMIT_MENU KitInitDiscoveryApprovalMenu
  SET PENDING_EDIT_BRANCH = unset
  WAIT user.reply
  STOP_TURN
UNIT KitInitApplyUserEditsRenderCanonical
PURPOSE: Return an edited canonical manifest preview to the existing-manifest menu.
DO:
  EMIT_MENU KitInitExistingManifestMenu
  SET PENDING_EDIT_BRANCH = unset
  WAIT user.reply
  STOP_TURN
MENU KitInitEditRetryMenu
TITLE: Some edits cannot be applied safely. Revise the edit request, keep the previous preview, or cancel.
OPTIONS:
  1 revise -> WAIT user.reply; STOP_TURN
  2 keep-preview -> EMIT CURRENT_PREVIEW_TOML; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitLegacyApprovalMenu WHEN PENDING_EDIT_BRANCH == legacy_manifest; EMIT_MENU KitInitDiscoveryApprovalMenu WHEN PENDING_EDIT_BRANCH == discovery; EMIT_MENU KitInitExistingManifestMenu WHEN PENDING_EDIT_BRANCH == canonical; WAIT user.reply; STOP_TURN
  3 cancel -> SET PENDING_EDIT_BRANCH = unset; STOP_TURN
  INVALID -> EMIT "Reply 1-3."; EMIT_MENU KitInitEditRetryMenu; WAIT user.reply; STOP_TURN
```
