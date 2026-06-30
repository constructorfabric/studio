# Blocked Report

```pdsl
UNIT BlockedReportContract
PURPOSE: Define the canonical blocked result envelope for thin standalone skills.
DO:
  RUN BlockedReportEnvelopeContract
  RUN BlockedReportSuggestedNextSkillsContract
  RUN BlockedReportNextActionsContract
  STOP_TURN
RULES:
  ALWAYS reuse the canonical envelope fields and blocked semantics from ThinSkillRuntimeContracts
  NEVER replace the blocked result envelope with workflow-local status or ad-hoc prose
```

```pdsl
UNIT BlockedReportEnvelopeContract
PURPOSE: Render blocked results in the canonical SKILL_RESULT envelope shape.
RULES:
  ALWAYS emit type = SKILL_RESULT, skill, and status = blocked
  ALWAYS emit produced_artifacts = [], report_outputs = [], and assumptions = [] in a blocked result unless another canonical contract explicitly supplies non-empty collections
  ALWAYS emit missing_artifacts as a list of entries containing artifact_type, why_needed, accepted_shapes, suggested_producers, override_allowed, and override_summary when present
  ALWAYS emit suggested_next_skills as a top-level list even when it is empty
  ALWAYS keep override_allowed explicit for every missing_artifacts entry
  NEVER omit missing_artifacts or suggested_next_skills from a blocked result envelope
```

```pdsl
UNIT BlockedReportSuggestedNextSkillsContract
PURPOSE: Keep blocked next-step suggestions visible and machine-readable.
RULES:
  ALWAYS derive suggested_next_skills from the explicit next-step list chosen by the caller or from the union of missing_artifacts[].suggested_producers
  ALWAYS keep suggested_next_skills separate from missing_artifacts[].suggested_producers so callers can offer a curated subset when needed
  ALWAYS treat suggested_next_skills as suggestions only
  NEVER auto-route or auto-run a suggested next skill from blocked-report
```

```pdsl
UNIT BlockedReportNextActionsContract
PURPOSE: Require explicit blocked-state next actions before control returns to the user.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-next-actions.md WHEN BlockedNextActionsContract is not yet loaded
  RUN BlockedNextActionsContract
RULES:
  ALWAYS pair blocked envelopes with a clear next-actions menu when the blocked result is being returned to the user
  NEVER leave blocked recovery paths implied only by prose
  ALWAYS derive a primary_suggested_producer as the single top-level recommendation from the union of missing_artifacts[].suggested_producers that most efficiently resolves the most missing artifacts in one step; surface it as the first item in suggested_next_skills with a one-line description
```
