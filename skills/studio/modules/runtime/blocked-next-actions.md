# Blocked Next Actions

```pdsl
UNIT BlockedNextActionsContract
PURPOSE: Require a clear blocked-state next-actions menu before control returns to the user.
STATE:
  SET BLOCKED_NEXT_ACTION_OVERRIDE_AVAILABLE: true | false | unset (default unset, scope unit_run)
WHEN:
  REQUIRE status == blocked OR PREREQUISITE_STATUS == blocked OR missing_artifacts is non-empty OR MISSING_ARTIFACTS is non-empty
DO:
  RUN BlockedNextActionsResolveContract
  RUN BlockedNextActionsMenuContract
RULES:
  ALWAYS offer explicit numbered next actions from a blocked state before returning control to the user
  ALWAYS keep the menu aligned to missing_artifacts and suggested_next_skills from the current blocked result
  NEVER return a blocked result to the user as envelope-plus-prose only when an interactive menu can be offered
```

```pdsl
UNIT BlockedNextActionsResolveContract
PURPOSE: Resolve the blocked next-action menu inputs from the current blocked result.
DO:
  SET BLOCKED_NEXT_ACTION_OVERRIDE_AVAILABLE = true WHEN one or more missing_artifacts entries declare override_allowed == true
  SET BLOCKED_NEXT_ACTION_OVERRIDE_AVAILABLE = false WHEN no missing_artifacts entry declares override_allowed == true
RULES:
  ALWAYS derive menu options from the current blocked payload rather than workflow-local guesses
  ALWAYS preserve declaration order for missing_artifacts and suggested_next_skills when rendering menu choices
```

```pdsl
UNIT BlockedNextActionsMenuContract
PURPOSE: Present the blocked-state next-actions menu and stop on a clear user-facing choice boundary.
DO:
  EMIT_MENU BlockedNextActionsMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS include a provide-inputs path
  ALWAYS include each suggested next skill as its own numbered option when suggested_next_skills is non-empty
  ALWAYS include an override option when BLOCKED_NEXT_ACTION_OVERRIDE_AVAILABLE == true
  ALWAYS include a back option
  ALWAYS include a stop option
  NEVER hide override behind prose when override is legal
  ALWAYS assign each suggested_next_skills entry its own top-level integer option number (2, 3, 4, ...); override, back, and stop always occupy the last slots after all skill entries
  ALWAYS mark the first suggested_next_skills entry as (suggested) unless a higher-priority producer is identified from missing_artifacts context
MENU BlockedNextActionsMenu
TITLE: This skill is blocked. Choose the next step. Reply with a number.
OPTIONS:
  1 provide-inputs -> WAIT for the user to provide the missing artifact references, paths, or descriptors called out in missing_artifacts, then STOP_TURN
  2 suggested-skill -> the rendered menu lists each suggested_next_skills entry on its own numbered line as `N <skill> - resolves <artifact types>`; selecting one explicitly chooses that producer skill as the next step and returns control at the handoff boundary
  3 override -> WAIT for explicit override approval naming the missing artifacts to bypass, then STOP_TURN WHEN BLOCKED_NEXT_ACTION_OVERRIDE_AVAILABLE == true
  4 back -> STOP_TURN and return to the nearest previous workflow-owned decision point when one exists, otherwise STOP_TURN as a safe terminal return
  5 stop -> STOP_TURN
  INVALID -> EMIT_MENU BlockedNextActionsMenu
NOTES:
  The rendered menu must enumerate every suggested_next_skills entry on its own line after `provide-inputs`, preserve stable order, append `override` only when legal, then append `back` and a final `stop` option.
```
