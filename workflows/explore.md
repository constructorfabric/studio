---
cf: true
type: workflow
name: cf-explore
description: "Invoke for requests to explore, discover context, find relevant files, locate architecture docs, locate artifacts, search code references, or gather task-relevant resource context."
version: 1.0
purpose: Standalone explore command; discovers resource context and returns a controller-owned resource map
---

# Explore Workflow

```pdsl
UNIT ExploreRootSkillEntrypointBootstrap
PURPOSE: Load the shared root cf skill entrypoint bootstrap.
DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/root-skill-entrypoint-bootstrap.md
```

```pdsl
UNIT ExploreWorkflow

PURPOSE:
  Discover project/resource context relevant to a task without loading those
  resources into SHARED_CONTEXT_PACK.

DO:
  - REQUIRE ExploreClarifyGate resolved before any cf-explorer dispatch
  - REQUIRE `{cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md` loaded before cf-explorer dispatch
  - LOAD {cf-studio-path}/.core/skills/studio/agents/cf-explorer.md
    as the explorer source contract
  - RUN SYNTHESIZE final dispatch prompt from the loaded explorer contract plus
    SHARED_CONTEXT_PACK and the payload below
  - REQUIRE explorer source contract is not loaded, unreadable, ambiguous, or not
     reflected in the final dispatch prompt:
    FAIL per sub-agent-dispatch.md § SubAgentContractReadGate
    - NEVER dispatch
  - DISPATCH cf-explorer with the synthesized final prompt including:
    task = user's explore request or parent workflow task
    intent = "standalone" | "brainstorm" | "generate" | "analyze" | "plan" | "workspace" | "PDSL"
    panel = null unless called from brainstorm after panel selection
    known_paths = paths already resolved by parent workflow
    search_roots = project roots allowed for read-only discovery
    constraints = relevant scope, system, KIND, and user-provided limits

  - RUN RECEIVE explorer result JSON
  - RUN VALIDATE explorer result JSON has:
    {
      "type": "EXPLORER_RESULT",
      "exploration_status": "sufficient|insufficient|blocked",
      "resource_context": {
        "resources": [{"path": "<path-or-id>", "kind": "<kind>", "reason": "<why relevant>", "summary": "<bounded summary>"}],
        "missing_context_questions": [],
        "searches_run": []
      }
    }
  - EMIT resource map and context summary
  - RUN ExploreSaveOffer

RULES:
  - NEVER put source code, docs, artifacts, diffs, or architecture files into
    SHARED_CONTEXT_PACK
  - ALWAYS apply sub-agent-dispatch.md § SubAgentContractReadGate before
    dispatching cf-explorer
  - ALWAYS treat explorer output as resource_context, not prompt_context
  - NEVER silently write files
  - NEVER dispatch prompt-consuming sub-agents with resource paths only when
    the task requires resolved resource summaries or excerpts
  - ALWAYS Parent workflows may skip this gate only when they supply a non-empty
    parent workflow task or known_paths
```

```pdsl
UNIT ExploreSaveOffer

PURPOSE:
  Offer explicit orchestrator-owned persistence for exploration results after
  the resource map/context summary is shown.

WHEN:
  - REQUIRE explorer result JSON has been received and summarized

DO:
  - SET default_save_dir = `{cf-studio-path}/.cache/explore/{slug}-{ISO}/`
  - EMIT "Save this exploration bundle?"
  - EMIT `Default folder: {cf-studio-path}/.cache/explore/{slug}-{ISO}/`
  - EMIT "Saved bundle files are `result.json`, `resource-map.md`, and `summary.md`."
  - EMIT_MENU ExploreSaveMenu
  - WAIT user.reply

MENU ExploreSaveMenu:
  OPTIONS:
    1 | save | save default ->
      SAVE_BUNDLE folder=default_save_dir
        result.json = exact explorer result JSON
        resource-map.md = rendered resource map and context summary
        summary.md = task summary, exploration status, resource count, and missing-context questions
      EMIT "Saved exploration bundle to {default_save_dir}."
      CONTINUE ExploreNextActions
    2 ->
      EMIT "Reply with `folder: <path>` for the save location."
      WAIT user.reply
      STOP_TURN
    3 folder: <path> ->
      SAVE_BUNDLE folder=<user path>
        result.json = exact explorer result JSON
        resource-map.md = rendered resource map and context summary
        summary.md = task summary, exploration status, resource count, and missing-context questions
      EMIT "Saved exploration bundle to <user path>."
      CONTINUE ExploreNextActions
    3 | skip | no ->
      EMIT "Skipped saving. No files were written."
      CONTINUE ExploreNextActions
    4 | cancel ->
      EMIT "Explore save canceled. No files were written."
      STOP_TURN
  INVALID:
    EMIT "Reply with 1-4, `save`, `skip`, or `folder: <path>`."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS keep saving orchestrator-owned; cf-explorer remains read-only
  - ALWAYS persist the exact explorer result JSON as `result.json`
  - ALWAYS render the resource map/context summary into `resource-map.md`
  - ALWAYS write `summary.md` with task summary, exploration status, resource count,
    and missing-context questions
  - NEVER silently write exploration results from running explore alone
  - ALWAYS allow a user-selected folder instead of the default cache path
  - ALWAYS keep explorer output in `resource_context`, not `SHARED_CONTEXT_PACK`
```

```pdsl
UNIT ExploreNextActions

PURPOSE:
  Present post-exploration next-action options after the save offer resolves.

WHEN:
  - REQUIRE ExploreSaveOffer has resolved (saved, skipped, or custom path saved)

DO:
  - EMIT_MENU ExploreNextActionsMenu

MENU ExploreNextActionsMenu:
  TITLE: What would you like to do with this context?
  OPTIONS:
    1 | brainstorm ->
      CONTINUE {cf-studio-path}/.core/workflows/generate.md WITH intent="brainstorm"
        resource_context = state.resource_context
    2 | plan ->
      CONTINUE {cf-studio-path}/.core/workflows/plan.md
        resource_context = state.resource_context
    3 | generate ->
      CONTINUE {cf-studio-path}/.core/workflows/generate.md
        resource_context = state.resource_context
    4 | analyze | review ->
      CONTINUE {cf-studio-path}/.core/workflows/analyze.md
        resource_context = state.resource_context
    5 | refine | explore again ->
      CONTINUE ExploreWorkflow
    6 | stop | done ->
      EMIT "Exploration complete."
      STOP_TURN
  INVALID:
    EMIT "Reply with 1-6 or one of: brainstorm, plan, generate, analyze, refine, stop."
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS pass resource_context forward to whichever workflow is chosen
  - NEVER re-run ExploreSaveOffer when looping back via refine
  - ALWAYS stop cleanly when user replies stop or done
```

```pdsl
UNIT ExploreClarifyGate

PURPOSE:
  Prevent empty standalone explore invocations from dispatching cf-explorer
  without a user goal.

WHEN:
  - REQUIRE intent == "standalone"
  - AND request is activation-only / no-task explore intent:
    explore | cf-explore | /cf-explore | skill explorer | explorer |
    find context | discover context
  - AND no concrete topic/question/path/decision is present

DO:
  - EMIT "[Explore]: I need a topic before I search the project."
  - EMIT "What should I explore?"
  - EMIT_MENU ExploreClarifyMenu
  - WAIT user.reply
  - STOP_TURN

MENU ExploreClarifyMenu:
  OPTIONS:
    1 -> Topic/question — user replies with the decision, feature, bug, or architecture question to explore
    2 -> Path-focused — user replies `path: <file-or-dir>` plus what they want to understand
    3 -> Workflow prep — user replies `for brainstorm|plan|generate|analyze: <topic>`
    4 -> Continue saved context — user replies with a previous RESOURCE_CONTEXT/session reference if available
    5 -> Cancel
  INVALID:
    EMIT "Reply with 1-5, or describe the topic directly, e.g. `explore global install runtime resolution`."
    WAIT user.reply
    STOP_TURN

RULES:
  - NEVER dispatch cf-explorer before this gate resolves for standalone
    empty explore requests
  - ALWAYS ask for at least one concrete topic, question, path, decision, or
    downstream workflow purpose
  - ALWAYS accept free-text topic replies as the task for the next explore turn
  - ALWAYS carry any user-provided extra context into `constraints`
  - ALWAYS Parent workflows may skip this clarify gate only when they supply a non-empty
    parent workflow task or known_paths
```
