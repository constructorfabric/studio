# Kit Legacy Preview Menus
```pdsl
UNIT KitInitLegacySourcePreviewSuccess
PURPOSE: Render a successful legacy-source preview and wait for approval input.
DO:
  EMIT the migration report, public generated-name preview, and proposed canonical `.cf-studio-kit.toml`
  EMIT_MENU KitInitLegacyApprovalMenu
  WAIT user.reply
  STOP_TURN
UNIT KitInitLegacySourcePreviewFailure
PURPOSE: Render a failed legacy-source preview and wait for retry or cancel.
DO:
  EMIT the normalization findings and blocking error details
  EMIT_MENU KitInitPreviewFailureMenu
  WAIT user.reply
  STOP_TURN
MENU KitInitLegacyApprovalMenu
TITLE: Approve the legacy-source conversion?
OPTIONS:
  1 approve-default -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifest
  2 show-preview -> EMIT CURRENT_PREVIEW_TOML in a fenced `toml` block; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitLegacyApprovalMenu; WAIT user.reply; STOP_TURN
  3 edit -> SET PENDING_EDIT_BRANCH = legacy_manifest; EMIT "Reply with edit commands such as `set metadata.name=<name>`, `set metadata.version=<semver>`, `remove resource id=<id>`, `set resource <id>.kind=<kind>`, `set resource <id>.install_path=<path>`, `set resource <id>.prefix_generated_name=false`, or `preserve field=<field>`."; WAIT user.reply; STOP_TURN
  4 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-4." and EMIT_MENU KitInitLegacyApprovalMenu
MENU KitInitPreviewFailureMenu
TITLE: The manifest preview could not be produced. Fix the source input and retry, or cancel.
OPTIONS:
  1 retry -> CONTINUE KitInitLegacySourcePreviewStart
  2 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-2." and EMIT_MENU KitInitPreviewFailureMenu
```
