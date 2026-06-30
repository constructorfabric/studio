# Handoff Suggestions

```pdsl
UNIT HandoffSuggestionsContract
PURPOSE: Convert missing-input or unresolved-question state into explicit next-step suggestions.
STATE:
  SET MISSING_INPUTS_REPORT: list | unset (default unset, scope unit_run)
  SET UNRESOLVED_QUESTIONS: list | unset (default unset, scope unit_run)
  SET HANDOFF_SUGGESTIONS: list | unset (default unset, scope unit_run)
  SET suggested_next_skills: list | unset (default unset, scope unit_run)
DO:
  RUN HandoffSuggestionsInputContract
  RUN HandoffSuggestionsBuildContract
  RUN HandoffSuggestionsCapabilityCollapseContract
  RUN HandoffSuggestionsOrderingContract
RULES:
  ALWAYS use this contract only to suggest producer or next skills
  ALWAYS keep suggestions machine-readable and non-binding
  NEVER auto-run, auto-route, or silently queue a suggested skill from this module
```

```pdsl
UNIT HandoffSuggestionsInputContract
PURPOSE: Define the accepted handoff sources.
RULES:
  ALWAYS require at least one of MISSING_INPUTS_REPORT or UNRESOLVED_QUESTIONS to be provided
  ALWAYS treat MISSING_INPUTS_REPORT as the authoritative producer-skill source when both are provided
  ALWAYS allow UNRESOLVED_QUESTIONS to contribute clarifying-skill suggestions even when no artifact is missing
  NEVER infer hidden producer skills that are absent from the input contracts
```

```pdsl
UNIT HandoffSuggestionsBuildContract
PURPOSE: Produce canonical next-step suggestion entries.
DO:
  RUN derive HANDOFF_SUGGESTIONS from the union of MISSING_INPUTS_REPORT[].suggested_producers and any caller-declared question-resolution skills
  SET suggested_next_skills = the stable ordered list of unique HANDOFF_SUGGESTIONS[].skill
RULES:
  ALWAYS represent each HANDOFF_SUGGESTIONS entry with skill, reason, resolves, and suggestion_rank
  ALWAYS set resolves to one-or-more input_key or question identifiers when such identifiers are available
  ALWAYS keep reason short and user-visible
  NEVER emit a suggestion entry without naming the target skill explicitly
```

```pdsl
UNIT HandoffSuggestionsCapabilityCollapseContract
PURPOSE: Prefer domain-specific producer skills over generic skills of the same capability class.
DO:
  RUN remove `planning` from suggested_next_skills WHEN suggested_next_skills contains `planning` and also contains one or more of `code-planning`, `documenting-planning`, or `prompting-planning`
  RUN remove every HANDOFF_SUGGESTIONS entry whose skill == `planning` WHEN suggested_next_skills contains one or more of `code-planning`, `documenting-planning`, or `prompting-planning`
RULES:
  ALWAYS prefer a domain-specific producer skill over a generic producer skill when both resolve the same missing capability class
  ALWAYS keep generic skills available as implicit fallback paths in documentation or routing, but not as equal-priority menu options when a domain-specific skill is already available
  NEVER present a generic and domain-specific planning skill as equal-ranked siblings in the same blocked next-actions menu
```

```pdsl
UNIT HandoffSuggestionsOrderingContract
PURPOSE: Keep suggestion order stable across repeated runs.
RULES:
  ALWAYS order suggestions by explicit caller priority when present, otherwise by first appearance in MISSING_INPUTS_REPORT, then by skill name
  ALWAYS deduplicate by skill plus resolves so one skill may appear more than once only when it resolves materially different blockers
  NEVER let suggestion ordering imply execution authority
```
