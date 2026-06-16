# Brave New World Follow-Up

```pdsl
UNIT BraveNewWorldAutonomousPrepareSelection
PURPOSE: Resolve the eligible option that Brave New World will select.
DO:
  - RUN rank eligible options by current request advancement, project-damage risk, explicit defaults, and suggested labels WHEN multiple options are eligible
  - RUN select the exactly one eligible original option identified by the classification record
  - CONTINUE BraveNewWorldAutonomousRecordDecision
```

```pdsl
UNIT BraveNewWorldAutonomousRecordDecision
PURPOSE: Persist the autonomous-choice decision record before the workflow continues.
DO:
  - RUN append a decision record to BRAVE_NEW_WORLD_DECISION_LOG with menu_or_question, original_valid_options, chosen_option, chosen_option_action, criteria_results, blocked_match_result, rejected_option_summary, reason, source_context_summary, and next_stage
  - SET BRAVE_NEW_WORLD_LAST_STATUS = autonomous-choice
  - CONTINUE BraveNewWorldAutonomousAnnounce
```

```pdsl
UNIT BraveNewWorldAutonomousAnnounce
PURPOSE: Announce the autonomous choice and continue with the original workflow semantics.
DO:
  - EMIT "Brave New World: chose <chosen_option> (<chosen_option_action>) because <short reason>; continuing to <next_stage>."
  - CONTINUE the underlying workflow exactly as if the user had selected the chosen original option
```
