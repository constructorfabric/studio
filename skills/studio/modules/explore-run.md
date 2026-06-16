# Explore Run

```pdsl
UNIT ExploreRun
PURPOSE: Explore the search scope read-only, then synthesize one resource_context.
STATE:
  SET PER_AGENT_BUDGET_MIN: integer (default 5..10, scope workflow_run)
  SET EXPLORE_PARALLELISM: integer (default auto, scope workflow_run)
DO:
  RUN ExploreExecutionContextPrep
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-synthesize.md
  SET task = ORIGINAL_INTENT (already captured by ExploreEntry)
  RUN scope estimation over search_roots (size, file and directory count, subtree breadth)
  CONTINUE ExploreRunSingleAgent WHEN the scope fits one agent within PER_AGENT_BUDGET_MIN
  CONTINUE ExploreRunPartitioned WHEN the scope is too large for one agent
RULES:
  ALWAYS estimate scope and choose single-agent vs parallel-partition dispatch before exploring
  ALWAYS partition a large scope into disjoint, non-overlapping partitions each sized to complete within PER_AGENT_BUDGET_MIN (target 5 to 10 minutes per agent)
  ALWAYS dispatch partition explorers in parallel bounded by EXPLORE_PARALLELISM, which defaults to the partition count capped at a safe max of 8 and MAY be overridden by the caller or user; run any overflow partitions in bounded waves
  ALWAYS synthesize and deduplicate every partition result into one resource_context before presenting, and reconcile exploration_status conservatively
  NEVER report sufficiency while any partition is unexplored or any wave is still pending
  ALWAYS in return-context mode (return_context == true), skip the save offer and the NextActionsOffer handoff and RETURN resource_context to the calling skill
  ALWAYS when ORIGINAL_INTENT asks to review, analyze, validate, audit, check, fix, write, or implement, treat that wording as the caller's downstream purpose and only discover relevant targets, context files, dependencies, conventions, and suggested slices
  NEVER emit review findings, validation verdicts, bug reports, severity ratings, fix recommendations, or authored content from ExploreRun; those belong to the caller's review, validation, brainstorm, or authoring loop
  NEVER put discovered source, docs, artifacts, diffs, or architecture files into the shared context pack — treat explorer output as resource_context only
  NEVER silently write files during an explore run
```

```pdsl
UNIT ExploreRunSingleAgent
PURPOSE: Dispatch one explorer for a small scope, then synthesize the result.
DO:
  RUN SubAgentDispatch for the single cf-explorer dispatch group
  DISPATCH a single cf-explorer with task, intent, known_paths, search_roots, and constraints
  CONTINUE ExploreRunSynthesize
```

```pdsl
UNIT ExploreRunPartitioned
PURPOSE: Partition a large search scope, dispatch bounded explorer waves, then synthesize the results.
DO:
  RUN partition search_roots into disjoint partitions, sizing each by file count, directory breadth, and total bytes so it finishes within PER_AGENT_BUDGET_MIN
  RUN SubAgentDispatch for the cf-explorer partition dispatch wave before each native partition wave
  DISPATCH one cf-explorer per partition in parallel, bounded by EXPLORE_PARALLELISM, each scoped to only its partition plus the per-agent budget, running overflow partitions in bounded waves
  CONTINUE ExploreRunSynthesize
```
