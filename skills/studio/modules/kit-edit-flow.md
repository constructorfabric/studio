# Kit Edit Flow
```pdsl
UNIT KitInitApplyUserEditsStart
PURPOSE: Apply user-supplied manifest edits, re-render the preview, and return to the correct approval gate.
WHEN:
  REQUIRE PENDING_EDIT_BRANCH != unset
DO:
  RUN KitInitApplyUserEditsValidate
  CONTINUE KitInitApplyUserEditsInvalid WHEN any requested edit is invalid
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-edit-render.md
  RUN KitInitApplyUserEditsApplyValid
  CONTINUE KitInitApplyUserEditsRender
RULES:
  ALWAYS return edited manifests to a preview approval menu before any write
  ALWAYS preserve top-level `manifest_version = "1.0"` after applying edits
  ALWAYS preserve artifact bindings as resource-ID references under the constraints resource, not as paths or naming-derived links
  ALWAYS recompute and show the public generated-name preview after applying edits and before returning to approval
  ALWAYS reject unsafe or unsupported edits instead of guessing
  NEVER write from an edit reply directly
UNIT KitInitApplyUserEditsValidate
PURPOSE: Parse the requested manifest edits and reject unsafe or unsupported changes.
DO:
  RUN parse the user reply as requested manifest edits: metadata changes, kit additions/removals for multi-kit manifests, resource additions/removals, kind changes, aliases, install paths, generated targets, artifact bindings, and fields to preserve
  RUN reject edits that would reference sources outside TARGET_DIR, introduce duplicate kit slugs, introduce duplicate resource IDs within the same kit, use unsupported resource kinds, set `prefix_generated_name = false` on a non-public resource, bind an artifact role to an unknown resource ID, put artifact bindings on a non-constraints resource, remove required `manifest_version = "1.0"`, set an unsupported `manifest_version`, or contradict canonical manifest shape
UNIT KitInitApplyUserEditsInvalid
PURPOSE: Present invalid edit reasons and wait for a revised edit choice.
DO:
  EMIT the rejected edits with reasons
  EMIT_MENU KitInitEditRetryMenu
  WAIT user.reply
  STOP_TURN
```
