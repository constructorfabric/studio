# Explore Synthesize

```pdsl
UNIT ExploreRunSynthesize
PURPOSE: Merge explorer results, render the context summary, and route to return or save.
DO:
  RUN synthesis of all partition EXPLORER_RESULTs into one deduplicated resource_context (consolidate resources by path, merge summaries, union missing-context questions, reconcile exploration_status to the worst partition status)
  EMIT the rendered resource map and context summary
  RETURN resource_context to the calling skill and STOP_TURN WHEN return_context == true
  LOAD {cf-studio-path}/.core/skills/studio/modules/explore-save.md
  CONTINUE ExploreSaveOffer WHEN return_context != true
```
