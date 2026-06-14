---
cf: true
type: workflow
name: cf-explore
description: "Invoke for requests to explore, discover context, find relevant files, locate architecture docs, locate artifacts, search code references, or gather task-relevant resource context."
version: 0.1
purpose: Discover task-relevant project resource context via a read-only sub-agent and return a controller-owned resource map without polluting the shared context pack.
---

# cf-explore

This skill discovers task-relevant project resource context via one or more cf-explorer sub-agents — a single agent for small scope, or N parallel partition agents (each budgeted ~5-10 minutes) for large folders and repos, whose findings are then synthesized — running read-only over allowed search roots. It returns a controller-owned resource map plus a context summary that is kept as resource_context and never loaded into the shared context pack. After showing the map it optionally saves an exploration bundle; next-step choices are then offered by the studio's global Next Actions rule.

```pdsl
UNIT ExploreBootstrap
PURPOSE: Ensure the cf skill is loaded before any explore work.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  STOP_TURN WHEN CFS_INIT != true
  CONTINUE ExploreEntry WHEN CFS_INIT == true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before any explore work
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past ExploreBootstrap unless CFS_INIT == true is positively confirmed
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so explore cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE ExploreBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
```

```pdsl
UNIT ExploreEntry
PURPOSE: Capture the original intent and route to clarify or directly to the explorer.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET intent: standalone | brainstorm | generate | analyze | plan (default standalone, scope workflow_run)
  SET return_context: true | false (default false, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering request (verbatim or shortest faithful summary)
  SET intent = standalone WHEN invoked directly; otherwise the intent supplied by the calling workflow
  SET return_context = true WHEN the caller invoked cf-explore in return-context mode (e.g. cf-brainstorm before round 1); else false
  CONTINUE ExploreClarify WHEN the request is activation-only with no concrete topic, question, path, or decision
  CONTINUE ExploreRun WHEN a concrete topic, path, decision, or workflow purpose is already present
RULES:
  ALWAYS capture ORIGINAL_INTENT before any cf-explorer dispatch
  ALWAYS default intent to standalone and return_context to false when explore is invoked on its own
  ALWAYS set return_context = true only when a calling skill/workflow requested resource_context back
  ALWAYS route an activation-only request to ExploreClarify and a concrete request straight to ExploreRun
```

```pdsl
UNIT ExploreClarify
PURPOSE: Prevent an empty standalone explore from dispatching cf-explorer with no goal.
WHEN:
  REQUIRE the request is activation-only with no concrete topic, question, path, or decision
DO:
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
  3 workflow-prep -> Workflow prep — reply `for brainstorm|plan|generate|analyze: <topic>`, then CONTINUE ExploreRun
  4 saved-context -> Continue saved context — reply with a path to a saved exploration bundle (its result.json) or a prior session reference; LOAD it as resource_context, EMIT the rendered resource map and context summary, then RETURN resource_context and STOP_TURN WHEN return_context == true, else CONTINUE ExploreSaveOffer
  5 cancel -> Cancel — STOP_TURN
  INVALID -> treat non-empty free text as a topic and CONTINUE ExploreRun; else EMIT "Reply 1-5, or describe the topic directly, e.g. explore global install runtime resolution." and EMIT_MENU ExploreClarifyMenu
NOTES:
  Option labels of the form `name | alias` accept either word as the reply (e.g. `path` or `path: <file-or-dir>`); they are one option, not two.
```

```pdsl
UNIT ExploreRun
PURPOSE: Explore the search scope read-only — single agent for small scope, or N parallel partition agents for large scope — then synthesize one resource_context.
STATE:
  SET PER_AGENT_BUDGET_MIN: integer (default 5..10, scope workflow_run)
  SET EXPLORE_PARALLELISM: integer (default auto, scope workflow_run)
DO:
  SET task = ORIGINAL_INTENT (already captured by ExploreEntry)
  RUN scope estimation over search_roots (size, file and directory count, subtree breadth)
  DISPATCH a single cf-explorer with task, intent, known_paths, search_roots, and constraints WHEN the scope fits one agent within PER_AGENT_BUDGET_MIN
  RUN partition search_roots into disjoint partitions, sizing each by file count, directory breadth, and total bytes so it finishes within PER_AGENT_BUDGET_MIN, WHEN the scope is too large for one agent
  DISPATCH one cf-explorer per partition in parallel, bounded by EXPLORE_PARALLELISM, each scoped to only its partition plus the per-agent budget, running overflow partitions in bounded waves, WHEN partitions exist
  RUN synthesis of all partition EXPLORER_RESULTs into one deduplicated resource_context (consolidate resources by path, merge summaries, union missing-context questions, reconcile exploration_status to the worst partition status)
  EMIT the rendered resource map and context summary
  RETURN resource_context to the calling skill and STOP_TURN WHEN return_context == true
  CONTINUE ExploreSaveOffer WHEN return_context != true
RULES:
  ALWAYS estimate scope and choose single-agent vs parallel-partition dispatch before exploring
  ALWAYS partition a large scope into disjoint, non-overlapping partitions each sized to complete within PER_AGENT_BUDGET_MIN (target 5 to 10 minutes per agent)
  ALWAYS dispatch partition explorers in parallel bounded by EXPLORE_PARALLELISM, which defaults to the partition count capped at a safe max of 8 and MAY be overridden by the caller or user; run any overflow partitions in bounded waves
  ALWAYS synthesize and deduplicate every partition result into one resource_context before presenting, and reconcile exploration_status conservatively
  NEVER report sufficiency while any partition is unexplored or any wave is still pending
  ALWAYS in return-context mode (return_context == true), skip the save offer and the global next-actions offer and RETURN resource_context to the calling skill
  NEVER put discovered source, docs, artifacts, diffs, or architecture files into the shared context pack — treat explorer output as resource_context only
  NEVER silently write files during an explore run
  ALWAYS keep every cf-explorer read-only
  ALWAYS carry task / ORIGINAL_INTENT into every explorer dispatch and the downstream handoff
  ALWAYS pass known_paths = paths already resolved by a parent workflow, else empty
  ALWAYS pass search_roots = the project roots (or the partition subtree) allowed for read-only discovery
  ALWAYS pass constraints = relevant scope, system, KIND, the per-agent time budget (constraints.max_time_minutes, 5 to 10), and user-provided limits
NOTES:
  Waves: overflow partitions run in sequential waves; each wave dispatches up to EXPLORE_PARALLELISM partitions in parallel, and wave N+1 starts only after every agent in wave N has returned.
  Synthesis: for each unique resource path keep one entry, merging duplicate partitions' summaries and taking the union of their suggested_slices (dropping identical slices); union all partitions' missing_context_questions; set merged exploration_status = insufficient if any partition is insufficient, else partial if any is partial, else sufficient.
```

```pdsl
UNIT ExploreSaveOffer
PURPOSE: Offer orchestrator-owned persistence after the resource map is shown.
WHEN:
  REQUIRE the synthesized resource_context has been received and summarized
DO:
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
  3 skip -> write nothing, then STOP_TURN
  4 cancel -> write nothing and STOP_TURN
  INVALID -> EMIT "Reply with 1-4, save, skip, or folder: <path> (e.g., folder: /tmp/explore)." and EMIT_MENU ExploreSaveMenu
NOTES:
  After this gate resolves and control returns to the user, ConditionalModuleLoading loads {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md so NextActionsOffer can synthesize next-step choices (e.g. brainstorm, plan, generate, analyze, or explore again) from the current resource_context.
```

```pdsl
UNIT ExploreDispatch
PURPOSE: Name the sub-agent used for read-only discovery, single or fanned out across partitions.
RULES:
  ALWAYS dispatch cf-explorer from {cf-studio-path}/.core/skills/studio/agents/cf-explorer.md for read-only discovery
  ALWAYS dispatch cf-explorer as a single instance for small scope, or as N parallel partition-scoped instances (bounded by EXPLORE_PARALLELISM, in waves if needed) for large scope
  ALWAYS pass each cf-explorer only its task + (partition) paths + constraints including the per-agent time budget, never prompt or instruction files
  NEVER let cf-explorer load prompt or instruction files from disk
  ALWAYS treat every cf-explorer output as resource_context to be synthesized, never the shared context pack
```
