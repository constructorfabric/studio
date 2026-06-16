# Explore Clarify

```pdsl
UNIT ExploreClarify
PURPOSE: Prevent an empty standalone explore from dispatching cf-explorer with no goal.
WHEN:
  REQUIRE the request is activation-only with no concrete topic, question, path, or decision
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-run.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-save.md
  EMIT "[Explore]: I need a topic before I search the project."
  EMIT "What should I explore?"
  EMIT_MENU ExploreClarifyMenu
  WAIT user.reply
  STOP_TURN
RULES:
  NEVER dispatch cf-explorer before a concrete topic, path, decision, or workflow purpose is given
  ALWAYS accept a free-text topic reply as the task for the explore run
  ALWAYS carry any user-provided extra context into constraints
MENU ExploreClarifyMenu
TITLE: What should I explore? Reply with a number or describe the topic directly.
OPTIONS:
  1 topic -> Topic/question — reply with the decision, feature, bug, or architecture question to explore, then CONTINUE ExploreRun
  2 path:<file-or-dir> | path -> Path-focused — reply `path: <file-or-dir>` plus what to understand, then CONTINUE ExploreRun
  3 workflow-prep -> Workflow prep — reply the calling workflow name and topic (e.g. `for coding|write-docs|write-skills|brainstorm|plan|generate|analyze: <topic>`), then CONTINUE ExploreRun
  4 saved-context -> Continue saved context — reply with a path to a saved exploration bundle (its result.json) or a prior session reference; LOAD it as resource_context, EMIT the rendered resource map and context summary, then RETURN resource_context and STOP_TURN WHEN return_context == true, else CONTINUE ExploreSaveOffer
  5 cancel -> Cancel — STOP_TURN
  INVALID -> treat non-empty free text as a topic and CONTINUE ExploreRun; else EMIT "Reply 1-5, or describe the topic directly, e.g. explore global install runtime resolution." and EMIT_MENU ExploreClarifyMenu
NOTES:
  Option labels of the form `name | alias` accept either word as the reply (e.g. `path` or `path: <file-or-dir>`); they are one option, not two.
```
