# Phase Close

```pdsl
UNIT PhaseCloseContract
PURPOSE: Define shared closure semantics for a phase after execution work is complete or intentionally skipped.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/phase-artifact-linking.md WHEN PhaseArtifactLinkingContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/phase-status-mark.md WHEN PhaseStatusMarkContract is not yet loaded
  RUN PhaseCloseChecklistContract
  RUN PhaseCloseSkipVisibilityContract
  RUN PhaseCloseStatusContract
RULES:
  ALWAYS use this module only for closure validation and closure-state recording
  ALWAYS require execution domains such as implementation, tests, CI, review, and git to be explicitly satisfied, skipped, or not-applicable before closure
  NEVER let this module own the full authoring, review, CI, or git workflow
```

```pdsl
UNIT PhaseCloseChecklistContract
PURPOSE: Keep phase closure prerequisites explicit and machine-readable.
RULES:
  ALWAYS require PHASE_CLOSE_CHECKLIST to be a list of entries with check_type, disposition, and summary
  ALWAYS allow check_type values implementation, tests, ci, review, git, or a narrower caller-declared subset
  ALWAYS allow disposition values satisfied, skipped, or not-applicable
  ALWAYS require every mandatory closure domain for the caller to appear exactly once in PHASE_CLOSE_CHECKLIST
  NEVER treat silence about a mandatory closure domain as implicit satisfaction
```

```pdsl
UNIT PhaseCloseSkipVisibilityContract
PURPOSE: Make intentional closure skips visible and reviewable.
RULES:
  ALWAYS require a visible rationale when any PHASE_CLOSE_CHECKLIST entry uses disposition = skipped
  ALWAYS keep skipped closure rationale attached to the corresponding checklist entry
  ALWAYS allow not-applicable without skip rationale when the caller declares the domain out of scope
  NEVER collapse skipped and not-applicable into the same meaning
```

```pdsl
UNIT PhaseCloseStatusContract
PURPOSE: Connect closure checklist results to shared phase-status reporting.
RULES:
  ALWAYS allow phase closure to mark PHASE_STATE as completed when every mandatory closure entry is satisfied or not-applicable
  ALWAYS allow phase closure to mark PHASE_STATE as blocked when a mandatory closure entry remains unresolved
  ALWAYS allow phase closure to mark PHASE_STATE as completed when one-or-more mandatory entries are skipped only if each skip has visible rationale
  ALWAYS keep closure outcome summary separate from any top-level skill result envelope
  NEVER emit a completed phase-close result while mandatory closure entries are absent from PHASE_CLOSE_CHECKLIST
```
