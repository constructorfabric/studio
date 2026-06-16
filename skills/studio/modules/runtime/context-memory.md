# Context Memory

```pdsl
UNIT ContextCategories
PURPOSE: Classify every loaded context as exactly one of two categories.
RULES:
  ALWAYS classify every loaded context as either `rules` or `content`, where `rules` = instructions (skills, workflows, methodologies, pipelines, plans, templates, IO contracts, examples, schemas) and `content` = artifacts (checklists, codebase, generation targets, source materials, anything being transformed)
  NEVER classify a single loaded context as both `rules` and `content`
```

```pdsl
UNIT RulesMemory
PURPOSE: Govern the lifecycle of `rules` assets in the session.
RULES:
  ALWAYS load a `rules` asset at most once and then keep it for the entire session
  NEVER compact, reload, or mutate a `rules` asset once it is loaded
```

```pdsl
UNIT ContentMemory
PURPOSE: Govern the lifecycle of `content` in the session.
RULES:
  ALWAYS hold `content` in the session only while it is needed and unload/forget it once it stops being needed
  ALWAYS treat `content` as mutable and reloadable, tracked by absolute file path or, for web sources, by URL/reference
  NEVER compact `content`
```

```pdsl
UNIT ResourceContextMemory
PURPOSE: Govern resource_context returned by cf-explore or derived from local artifacts.
STATE:
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_REF: reference | unset (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_TASK_KEY: string | unset (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT_PROVENANCE: object | unset (default unset, scope workflow_run)
RULES:
  ALWAYS classify resource_context as `content`, never as `rules`
  ALWAYS store resource_context as a controller-owned map of absolute paths, URLs, references, short summaries, evidence pointers, and missing-context questions
  ALWAYS store the controller-owned resource_context reference in RESOURCE_CONTEXT_REF, the normalized task/scope key in RESOURCE_CONTEXT_TASK_KEY, and source/timestamp/provenance in RESOURCE_CONTEXT_PROVENANCE
  ALWAYS pass resource_context to downstream workflow, author, coder, panel, or reviewer steps as read-only context references
  ALWAYS reuse a stored resource_context only when RESOURCE_CONTEXT_TASK_KEY exactly matches the current normalized workflow-prep task key
  NEVER inline full source files, prompt files, instruction files, diffs, or generated artifacts into a dispatch payload merely because they appear in resource_context
  NEVER treat RESOURCE_CONTEXT == provided without RESOURCE_CONTEXT_REF and a matching RESOURCE_CONTEXT_TASK_KEY as reusable context
  NEVER let resource_context change a gate verdict; it is evidence/context, not authority
```
