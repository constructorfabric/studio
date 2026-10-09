# Explore Save

```pdsl
UNIT ExploreSaveOffer
PURPOSE: Offer orchestrator-owned persistence after the resource map is shown.
WHEN:
  REQUIRE the synthesized resource_context has been received and summarized
DO:
  RUN CommandResolution to resolve {cfs_cmd} WHEN {cfs_cmd} is unset, loading {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md first when it is not yet loaded: the option branches below record the user's answer through {cfs_cmd}, and most bootstraps reach this gate before any command has been resolved
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-next-dispatch.md
  RUN ExploreSaveContextPrep
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
TYPE: decision
KEY: explore_save
OPTIONS:
  1 save -> RUN `{cfs_cmd} gate-log --kind exception-asked --gate ExploreSaveMenu --declared-type decision --decision-key explore_save --value save --status resolved --why <why the plan did not answer it>` WHEN this gate was emitted and the user chose this option, then WRITE the bundle to default_save_dir, then CONTINUE ExploreNextActions
  2 folder:<path> | folder -> RUN `{cfs_cmd} gate-log --kind exception-asked --gate ExploreSaveMenu --declared-type decision --decision-key explore_save --value folder --status resolved --why <why the plan did not answer it>` WHEN this gate was emitted and the user chose this option, then WRITE the bundle to the user path, then CONTINUE ExploreNextActions
  3 skip -> RUN `{cfs_cmd} gate-log --kind exception-asked --gate ExploreSaveMenu --declared-type decision --decision-key explore_save --value skip --status resolved --why <why the plan did not answer it>` WHEN this gate was emitted and the user chose this option, then write nothing, then CONTINUE ExploreNextActions
  4 cancel -> RUN `{cfs_cmd} gate-log --kind exception-asked --gate ExploreSaveMenu --declared-type decision --decision-key explore_save --value cancel --status resolved --why <why the plan did not answer it>` WHEN this gate was emitted and the user chose this option, then write nothing, then CONTINUE ExploreNextActions
  INVALID -> EMIT "Reply with 1-4, save, skip, or folder: <path> (e.g., folder: /tmp/explore)." and EMIT_MENU ExploreSaveMenu
```
