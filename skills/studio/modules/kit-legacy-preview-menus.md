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
TITLE: Approve the legacy-source conversion? The proposed .cf-studio-kit.toml is shown above. Approve to write it, or review/edit first.
OPTIONS:
  1 approve — write the manifest shown above -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifestRun
  2 re-show manifest — display the proposed manifest again -> EMIT CURRENT_PREVIEW_TOML in a fenced `toml` block; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitLegacyApprovalMenu; WAIT user.reply; STOP_TURN
  3 edit -> SET PENDING_EDIT_BRANCH = legacy_manifest; EMIT "You are editing the proposed canonical manifest shown above. Send one field edit at a time. When you are finished, reply `done` to see the updated preview and return to this menu. Examples:\n- Change kit name: `set metadata.name = My Kit`\n- Change version: `set metadata.version = 1.2.0`\n- Remove a resource: `remove resource id = <id>`\n- Change a resource field: `set resource <id>.kind = skill`"; WAIT user.reply; STOP_TURN
  4 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-4." and EMIT_MENU KitInitLegacyApprovalMenu
RULES:
  ALWAYS when PENDING_EDIT_BRANCH == legacy_manifest and user.reply == "done": apply all pending edits, EMIT the updated preview TOML, reset PENDING_EDIT_BRANCH = unset, and EMIT_MENU KitInitLegacyApprovalMenu; WAIT user.reply; STOP_TURN
  ALWAYS when PENDING_EDIT_BRANCH == legacy_manifest and user.reply is a field edit command: apply the edit, update CURRENT_PREVIEW_TOML, and EMIT "Edit applied. Send another edit or reply `done` to finish."
MENU KitInitPreviewFailureMenu
TITLE: Preview failed — see the findings above. Fix the source file shown then retry, or cancel.
OPTIONS:
  1 retry -> CONTINUE KitInitLegacySourcePreviewStart
  2 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-2." and EMIT_MENU KitInitPreviewFailureMenu
RULES:
  ALWAYS differentiate retry behavior by PREVIEW_STATUS: when PREVIEW_STATUS == error (parse failure), show the exact error output and suggest checking TOML syntax; when PREVIEW_STATUS == fail (validation findings), list the specific blocking findings the user must address
```
