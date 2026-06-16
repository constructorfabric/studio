# Explore Save

```pdsl
UNIT ExploreSaveOffer
PURPOSE: Offer orchestrator-owned persistence after the resource map is shown.
WHEN:
  REQUIRE the synthesized resource_context has been received and summarized
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-next-dispatch.md
  RUN TemplateVarResolution before resolving default_save_dir
  SET default_save_dir = {cf-studio-path}/.cache/explore/{slug}-{ISO}/
  EMIT "Save this exploration bundle?"
  EMIT "Bundle files: result.json, resource-map.md, summary.md. Default folder: {default_save_dir}"
  EMIT_MENU ExploreSaveMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS persist the synthesized explorer result JSON as result.json
  ALWAYS render the resource map and context summary into resource-map.md
  ALWAYS write summary.md with task summary, exploration status, resource count, and missing-context questions
  ALWAYS allow a user-selected folder instead of the default cache path
  NEVER write any files unless the user chooses save or folder
  ALWAYS keep results in resource_context, not the shared context pack
MENU ExploreSaveMenu
TITLE: Save this exploration bundle?
OPTIONS:
  1 save -> WRITE the bundle to default_save_dir, then STOP_TURN
  2 folder:<path> | folder -> WRITE the bundle to the user path, then STOP_TURN
  3 skip -> write nothing, then CONTINUE ExploreNextActions
  4 cancel -> write nothing and STOP_TURN
  INVALID -> EMIT "Reply with 1-4, save, skip, or folder: <path> (e.g., folder: /tmp/explore)." and EMIT_MENU ExploreSaveMenu
NOTES:
  Save and folder options write the bundle then stop because persistence is the selected terminal action. Skip continues to next actions because no file write is pending.
```
