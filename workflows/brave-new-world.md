---
cf: true
type: workflow
name: cf-brave-new-world
description: Invoke when the user wants Brave New World autonomous-default mode: a humorous self-contained overlay that chooses only explicitly safe defaults.
version: 0.1
purpose: Reduce nuisance questions without bypassing Constructor Studio prerequisites, approvals, WAIT/STOP_TURN gates, dispatch gates, terminal shapes, or user-review checkpoints.
---

# Brave New World

This workflow is a self-contained session overlay, like `cf-debug-prompts`: it
does not require the `cf` skill to be loaded before activation. It only affects
later workflow choices whose own rules are available at the point of use. It is
not permission to ignore Constructor Studio control flow.

## Activation

```pdsl
UNIT BraveNewWorldActivate
PURPOSE: Enable the autonomous-default overlay for the current session without starting task work.
STATE:
  - SET BRAVE_NEW_WORLD_ENABLED: true | false (default false, scope session)
  - SET BRAVE_NEW_WORLD_SCOPE: explicit-autodefaults-only (default explicit-autodefaults-only, scope session)
  - SET BRAVE_NEW_WORLD_DECISION_LOG: list (default empty, scope session)
  - SET BRAVE_NEW_WORLD_LAST_STATUS: enabled | disabled | autonomous-choice | fallback (default disabled, scope session)
WHEN:
  - REQUIRE user explicitly requests one of: cf-brave-new-world, brave-new-world, Brave New World, autonomous-default mode
  - NOT user requests disable, off, stop, turn off, or disable autonomous defaults
DO:
  - SET BRAVE_NEW_WORLD_ENABLED = true
  - SET BRAVE_NEW_WORLD_SCOPE = explicit-autodefaults-only
  - RUN initialize BRAVE_NEW_WORLD_DECISION_LOG as empty when it is unset
  - SET BRAVE_NEW_WORLD_LAST_STATUS = enabled
  - EMIT "Brave New World enabled: I will only choose explicitly safe autonomous defaults. Say \"turn off Brave New World\" to disable it."
  - STOP_TURN
RULES:
  - ALWAYS treat this workflow as an overlay on later workflow execution, not as a replacement workflow
  - ALWAYS keep all current and future underlying rules, prerequisites, menus, approvals, waits, hard stops, dispatch gates, validation gates, user-review checkpoints, and terminal shapes active
  - ALWAYS keep BRAVE_NEW_WORLD_DECISION_LOG append-only for the session across disable and re-enable cycles
  - NEVER start substantive task work merely because this overlay was enabled
  - NEVER require `cf` or `CFS_INIT == true` merely to enable or disable this overlay
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
  - RUN select the exactly one eligible original option identified by the classification record
  - RUN append a decision record to BRAVE_NEW_WORLD_DECISION_LOG with menu_or_question, original_valid_options, chosen_option, chosen_option_action, criteria_results, blocked_match_result, rejected_option_summary, reason, source_context_summary, and next_stage
  - SET BRAVE_NEW_WORLD_LAST_STATUS = autonomous-choice
  - EMIT "Brave New World: chose <chosen_option> (<chosen_option_action>) because <short reason>; continuing to <next_stage>."
  - CONTINUE the underlying workflow exactly as if the user had selected the chosen original option
RULES:
  - ALWAYS require classification_status == eligible before autonomous selection
  - ALWAYS require exactly one eligible original option; zero eligible options, ties, multiple recommended options, hidden preferences, missing evidence, or incomplete context route to BraveNewWorldFallback
  - ALWAYS require the chosen option to be one of the original menu or question's valid options
  - ALWAYS preserve the original option's exact action semantics after selection
  - ALWAYS record and announce every autonomous choice before continuing
  - NEVER invent a new option, rewrite a menu, suppress a required menu, or change the underlying workflow's action
  - NEVER treat humor, convenience, prior activation, or a suggested label as sufficient reason to answer a gate
ON_ERROR:
  classification_failed -> CONTINUE BraveNewWorldFallback
  conflicting_classification -> CONTINUE BraveNewWorldFallback
  no_valid_option -> CONTINUE BraveNewWorldFallback
  decision_log_unavailable -> CONTINUE BraveNewWorldFallback
```

```pdsl
UNIT BraveNewWorldEligibilityChecklist
PURPOSE: Produce the only classification result that can permit autonomous selection.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a pending choice is being evaluated for autonomous selection
DO:
  - RUN set classification_status = eligible only when every allowed criterion is proven PASS and every blocked criterion is proven absent
  - RUN set classification_status = ineligible when any allowed criterion is FAIL or unknown, any blocked criterion is present, or the selected option's action path cannot be inspected until the next fresh user input
RULES:
  - ALWAYS require the originating workflow to explicitly mark the pending choice or option as autodefaultable, OR require the selected option to be an explicitly terminal no-op such as done, stop, decline, cancel, skip optional continuation, or session-only wrap
  - ALWAYS require the option action path until the next fresh user input to avoid invoking another skill or workflow, dispatching work, writing or editing files, executing shell commands, requesting network or external-service access, changing git state, installing or updating software, publishing, deploying, or spending money
  - ALWAYS require the choice to be reversible in the same session without data loss, security impact, permission escalation, or user-control loss
  - ALWAYS require the choice to be derived from visible current workflow state, not hidden user preference
  - ALWAYS require all original options and the chosen option action to be captured in the classification record before selection
  - NEVER auto-select router targets, planning gates, plan-storage gates, synthesized next actions, next-route actions, brainstorm/start actions, review-fix scopes, validation recovery choices, permission-denial recovery choices, or any option that starts new substantive work before fresh user input
```

```pdsl
UNIT BraveNewWorldBlockedChoice
PURPOSE: Define prompts that this overlay must never answer.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE a pending choice is being evaluated for autonomous selection
INVARIANTS:
  - NEVER auto-answer, satisfy, skip, weaken, or bypass explicit approvals
  - NEVER auto-answer any Constructor Studio hard stop: WAIT, STOP_TURN, menu, gate, opener, approval, dispatch_gate, terminal_shape, or user.review checkpoint, unless the originating workflow explicitly marks that exact choice autodefaultable
  - NEVER auto-answer destructive-operation prompts, deletion prompts, overwrite prompts, shutdown confirmations, history-rewrite prompts, publish prompts, deployment prompts, or irreversible-operation prompts
  - NEVER auto-answer credential, secret, token, authentication, authorization, privacy, security, payment, billing, network-access, external-service, filesystem-permission, sandbox-escalation, install, update, or setup prompts
  - NEVER auto-answer external delegation approvals, sub-agent approval, native-dispatch approval, fallback approval, or retry-vs-inline fallback prompts
  - NEVER auto-answer git mode, staging, committing, pushing, or any git-related permission prompt
  - NEVER auto-answer review-fix approval, issue-fix scope, or any prompt that authorizes edits after findings
  - NEVER auto-answer prompts that forget, unload, disable, or shut down rules or session state
  - NEVER auto-answer missing prerequisites, unresolved template variables, unavailable required context, failed validation recovery, validation-result review, retry/continue after validation findings, or human-review prompts
  - NEVER auto-select optional continuation routes, synthesized next actions, brainstorm starts, generated next routes, or any option that chains into new task work; choose only an explicitly terminal no-op when that no-op is eligible, otherwise fall back
  - NEVER weaken REQUIRE, ALWAYS, NEVER, WAIT, STOP_TURN, INVARIANTS, approvals, dispatch gates, or terminal output shapes
```

```pdsl
UNIT BraveNewWorldFallback
PURPOSE: Preserve the original workflow behavior when autonomous selection is not allowed.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE classification_status != eligible OR a pending choice is ambiguous, blocked, non-reversible, not explicitly autodefaultable, not terminal/no-op, not derivable from visible context, or otherwise fails BraveNewWorldEligibilityChecklist
DO:
  - SET BRAVE_NEW_WORLD_LAST_STATUS = fallback
  - EMIT "Brave New World needs your choice here because <blocked_or_ambiguous_reason>."
  - EMIT the original menu or question unchanged
  - WAIT user.reply when the underlying workflow requires WAIT
  - STOP_TURN when the underlying workflow requires STOP_TURN
RULES:
  - ALWAYS fall back to the original menu or question unchanged when any eligibility criterion is missing
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
  - SET BRAVE_NEW_WORLD_ENABLED = false
  - SET BRAVE_NEW_WORLD_LAST_STATUS = disabled
  - EMIT "Brave New World disabled: original menus and questions will be shown normally."
  - STOP_TURN
RULES:
  - ALWAYS give disable intent precedence over activation intent when a request contains both
  - ALWAYS disable only this overlay and leave Constructor Studio rules, loaded context, and session state intact
  - NEVER treat disabling this overlay as a Studio shutdown or session unload
```

## Verification Cases

```pdsl
UNIT BraveNewWorldVerificationCases
PURPOSE: Define regression cases for reviewing this overlay.
RULES:
  - ALWAYS verify an explicit approval prompt emits BraveNewWorldFallback, the original menu unchanged, WAIT when required, and STOP_TURN when required
  - ALWAYS verify planning, plan-storage, routing, synthesized next-action, brainstorm-start, and validation-recovery menus fall back unless the originating workflow explicitly marks the exact option autodefaultable
  - ALWAYS verify a suggested optional route that starts new work is never auto-selected; an eligible terminal no-op may be selected only when it is exactly one eligible option
  - ALWAYS verify an ambiguous menu with two plausible non-mutating options falls back
  - ALWAYS verify one positive case where the originating workflow explicitly marks a single terminal no-op as autodefaultable records all decision-log fields and announces the choice before continuation
```
