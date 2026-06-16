# Brave New World Choice

```pdsl
UNIT BraveNewWorldAutonomousChoice
PURPOSE: Decide whether the controller may answer a pending menu or question without asking the user.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a workflow menu or user-choice question is about to be emitted
DO:
  - REQUIRE BRAVE_NEW_WORLD_DECISION_LOG exists
  - RUN classify the pending choice with BraveNewWorldEligibilityChecklist
  - CONTINUE BraveNewWorldFallback WHEN classification_status != eligible
  - CONTINUE BraveNewWorldAutonomousPrepareSelection
RULES:
  - ALWAYS require classification_status == eligible before autonomous selection
  - ALWAYS choose exactly one valid original option
  - ALWAYS use explicit defaults or suggested labels only as tiebreakers during option ranking
  - ALWAYS require the chosen option to be one of the original menu or question's valid options
  - ALWAYS preserve the original option's exact action semantics after selection
  - ALWAYS record and announce every autonomous choice before continuing
  - NEVER invent a new option, rewrite a menu, suppress a required menu, or change the underlying workflow's action
  - NEVER treat humor, convenience, prior activation, or a suggested label as sufficient reason to select an option that fails the non-destructive eligibility check
ON_ERROR:
  classification_failed -> CONTINUE BraveNewWorldFallback
  conflicting_classification -> CONTINUE BraveNewWorldFallback
  no_valid_option -> CONTINUE BraveNewWorldFallback
  decision_log_unavailable -> CONTINUE BraveNewWorldFallback
```
