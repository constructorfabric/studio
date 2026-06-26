# Kit Existing Manifest

```pdsl
UNIT KitInitExistingManifestOffer
PURPOSE: Avoid silent overwrite when a canonical manifest already exists in the target folder.
WHEN:
  REQUIRE TARGET_SOURCE == canonical
DO:
  EMIT "A canonical manifest already exists at <target>/.cf-studio-kit.toml."
  EMIT_MENU KitInitExistingManifestMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer read-only validation or cancel when the canonical manifest already exists
  NEVER overwrite an existing canonical manifest silently
MENU KitInitExistingManifestMenu
TITLE: `.cf-studio-kit.toml` already exists. What should happen?
OPTIONS:
  1 validate -> RUN `{cfs_cmd} kit normalize <target> --dry-run` to load and validate the current canonical manifest without writing; EMIT the validation report and manifest summary; STOP_TURN
  2 cancel -> STOP_TURN
  3 edit — open the existing manifest for review and edit -> LOAD {cf-studio-path}/.core/skills/studio/modules/kit-edit-flow.md; SET PENDING_EDIT_BRANCH = canonical; CONTINUE KitInitApplyUserEditsStart
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitExistingManifestMenu
NOTE: To add, remove, or revise resources, choose 3 to open the manifest in edit mode.
```
