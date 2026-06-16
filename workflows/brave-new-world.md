---
cf: true
type: workflow
name: cf-brave-new-world
description: Invoke when the user wants Brave New World autonomous-default mode: a humorous self-contained overlay that autonomously chooses any non-destructive, reversible path.
version: 0.1
purpose: Reduce nuisance questions by choosing any path that does not risk project damage, data loss, irreversible side effects, dangerous git operations, or external commitments.
---

# Brave New World

This workflow is a self-contained session overlay, like `cf-debug-prompts`: it
does not require the `cf` skill to be loaded before activation. It only affects
later workflow choices whose own rules are available at the point of use. It is
not permission to ignore Constructor Studio control flow. It answers eligible
choices as the user would have answered them; it does not skip the underlying
workflow's required action.

## Activation

```pdsl
UNIT BraveNewWorldActivate
PURPOSE: Enable the autonomous-default overlay for the current session without starting task work.
STATE:
  - SET BRAVE_NEW_WORLD_ENABLED: true | false (default false, scope session)
  - SET BRAVE_NEW_WORLD_SCOPE: non-destructive-allow-by-default (default non-destructive-allow-by-default, scope session)
  - SET BRAVE_NEW_WORLD_DECISION_LOG: list (default empty, scope session)
  - SET BRAVE_NEW_WORLD_LAST_STATUS: enabled | disabled | autonomous-choice | fallback (default disabled, scope session)
WHEN:
  - REQUIRE user explicitly requests one of: cf-brave-new-world, brave-new-world, Brave New World, autonomous-default mode
  - NOT user requests disable, off, stop, turn off, or disable autonomous defaults
DO:
  - LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  - RUN WorkflowBootstrapRouterPrelude
  - RUN WorkflowBootstrapSimpleModeGate
  - RUN BraveNewWorldSessionEnable
RULES:
  - ALWAYS treat this workflow as an overlay on later workflow execution, not as a replacement workflow
  - ALWAYS remember git-commit-mode so any later commit request in this active overlay session runs GitCommitModeGate before routing, git use, or delegation
  - ALWAYS keep all current and future underlying rules, prerequisites, menus, waits, hard stops, validation gates, and terminal shapes active, while allowing this overlay to answer eligible menus and questions by selecting one valid original option
  - ALWAYS keep BRAVE_NEW_WORLD_DECISION_LOG append-only for the session across disable and re-enable cycles
  - NEVER start substantive task work merely because this overlay was enabled
  - NEVER require `cf` or `CFS_INIT == true` merely to enable or disable this overlay
```

```pdsl
UNIT BraveNewWorldSessionEnable
PURPOSE: Initialize Brave New World session state and announce the overlay.
DO:
  - SET BRAVE_NEW_WORLD_ENABLED = true
  - SET BRAVE_NEW_WORLD_SCOPE = non-destructive-allow-by-default
  - RUN initialize BRAVE_NEW_WORLD_DECISION_LOG as empty when it is unset
  - SET BRAVE_NEW_WORLD_LAST_STATUS = enabled
  - EMIT "Brave New World enabled: I will autonomously choose any non-destructive, reversible path. Say \"turn off Brave New World\" to disable it."
  - STOP_TURN
```

## Selection

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

```pdsl
UNIT BraveNewWorldEligibilityChecklist
PURPOSE: Produce the classification result that permits autonomous selection unless a destructive or irreversible risk is present.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a pending choice is being evaluated for autonomous selection
DO:
  - RUN inspect every original option's visible action path until the next fresh user input or terminal stop
  - RUN reject only options whose visible action path matches BraveNewWorldBlockedChoice or whose project-damage risk cannot be bounded from current context
  - RUN treat reversible, non-destructive options as eligible without requiring explicit autodefaultable marking
  - RUN prefer non-destructive progress options over terminal or no-op options
  - RUN set classification_status = eligible when at least one valid original option remains after blocked options are rejected
  - RUN set classification_status = ineligible when every option is blocked, every option's project-damage risk is unknown, or the menu/question requires fresh confidential, legal, financial, personal, or irreversible human judgment
RULES:
  - ALWAYS allow reversible, non-destructive workflow choices by default, including loading needed skills, selecting next steps, accepting default discovery/brainstorm/review scopes, answering brainstorm steering questions, choosing inline fallbacks, and continuing validation or review loops
  - ALWAYS require the selected option's visible action path to avoid data loss, destructive or irreversible file operations, unsafe git state changes, permission escalation, credential or secret exposure, deployment, publication, external commitments, payments, and security-impacting changes
  - ALWAYS require the choice to be reversible or correctable without losing user work, secrets, credentials, money, published state, deployment state, or git history
  - ALWAYS require the choice to be derived from visible current workflow state, not hidden user preference
  - ALWAYS require all original options and the chosen option action to be captured in the classification record before selection
  - NEVER require explicit autodefaultable marking for reversible, non-destructive options
  - NEVER prefer terminal or no-op options over non-destructive progress options
```

```pdsl
UNIT BraveNewWorldBlockedChoice
PURPOSE: Define prompts and options that this overlay must never answer.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a pending choice is being evaluated for autonomous selection
INVARIANTS:
  - NEVER auto-answer destructive-operation prompts, deletion prompts, overwrite prompts, shutdown confirmations, history-rewrite prompts, publish prompts, deployment prompts, or irreversible-operation prompts
  - NEVER auto-answer debugger prompts, breakpoint controls, step/continue approvals, debug-gate prompts, or cf-debug-skill console choices
  - NEVER auto-answer credential, secret, token, authentication, authorization, privacy, security, payment, billing, network-access, external-service, filesystem-permission, sandbox-escalation, install, update, or setup prompts
  - NEVER auto-answer prompts that authorize external delegation, deployment, publication, payments, account changes, cross-repository changes, or actions outside the current workspace
  - NEVER auto-answer git mode, staging, committing, pushing, force-pushing, branch deletion, checkout over uncommitted work, history rewrite, or any git-related permission prompt
  - NEVER auto-answer prompts that authorize deleting files, overwriting user changes, broad mechanical rewrites, dependency upgrades, migrations, generated artifact replacement, or edits whose blast radius is unknown
  - NEVER auto-answer ReviewFindingsNavigation, ReviewFixScope, partial review-fix finding-ID capture, or any prompt that selects which review findings may be fixed
  - NEVER auto-answer prompts that forget, unload, disable, or shut down rules or session state
  - NEVER auto-answer missing prerequisites, unresolved template variables, unavailable required context, failed validation recovery that needs human judgment, validation-result acceptance, or final human-review prompts
  - NEVER auto-answer explicit approvals granting destructive, irreversible, external, permission-escalating, secret-bearing, financial, git-mutating, or unknown-blast-radius authority
  - NEVER weaken REQUIRE, ALWAYS, NEVER, WAIT, STOP_TURN, INVARIANTS, approvals, dispatch gates, or terminal output shapes
```

```pdsl
UNIT BraveNewWorldFallback
PURPOSE: Preserve the original workflow behavior when autonomous selection is not allowed.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE classification_status != eligible OR every available option is blocked, destructive, irreversible, external, permission-escalating, secret-bearing, financial, git-mutating, unknown-blast-radius, not derivable from visible context, or otherwise fails BraveNewWorldEligibilityChecklist
DO:
  - SET BRAVE_NEW_WORLD_LAST_STATUS = fallback
  - EMIT "Brave New World needs your choice here because <blocked_or_ambiguous_reason>."
  - EMIT the original menu or question unchanged
  - WAIT user.reply when the underlying workflow requires WAIT
  - STOP_TURN when the underlying workflow requires STOP_TURN
RULES:
  - ALWAYS emit the original menu or question unchanged on fallback
  - ALWAYS preserve all underlying workflow handoff, logging, WAIT, STOP_TURN, terminal-shape, and output-contract behavior
  - NEVER continue past the original hard stop without user input
```

## Disable

```pdsl
UNIT BraveNewWorldDisable
PURPOSE: Turn off the autonomous-default overlay without shutting down Constructor Studio.
WHEN:
  - REQUIRE user requests disable, off, stop, turn off, stop autonomous-default mode, turn off autonomous defaults, or disable autonomous defaults for Brave New World
DO:
  - RUN resolve disable intent before activation intent WHEN a request contains both
  - SET BRAVE_NEW_WORLD_ENABLED = false
  - SET BRAVE_NEW_WORLD_LAST_STATUS = disabled
  - EMIT "Brave New World disabled: original menus and questions will be shown normally."
  - STOP_TURN
RULES:
  - ALWAYS give disable intent precedence over activation intent
  - ALWAYS disable only this overlay and leave Constructor Studio rules, loaded context, and session state intact
  - NEVER treat disabling this overlay as a Studio shutdown or session unload
```

## Verification Cases

```pdsl
UNIT BraveNewWorldVerificationCases
PURPOSE: Define regression cases for reviewing this overlay.
RULES:
  - ALWAYS verify destructive, irreversible, external-service, permission-escalation, secret, payment, deployment, publication, install/update, and git-mutating prompts emit BraveNewWorldFallback, preserve the original menu, and preserve required WAIT and STOP_TURN behavior
  - ALWAYS verify planning, routing, synthesized next-action, brainstorm-start, skill-loading, review-scope, and validation-retry menus can be auto-selected for non-destructive and reversible visible action paths
  - ALWAYS verify brainstorm steering questions can be answered from visible current workflow state without confidential, legal, financial, personal, or irreversible human judgment
  - ALWAYS verify an ambiguous menu with multiple safe progress options selects the least project-damaging option that best advances the user's current request and records the tie-break reason
  - ALWAYS verify one blocked case and one positive progress case both record all decision-log fields and announce the choice before continuation or fallback
```
