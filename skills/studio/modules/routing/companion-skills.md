# Companion Skill Routing
```pdsl
UNIT CompanionSkillRouting
PURPOSE: Let routers and workflows offer multiple compatible cf-* companion skills for cross-domain tasks without weakening each selected skill's protocol.
WHEN:
  REQUIRE a task intent clearly spans more than one cf-* skill domain
DO:
  RUN identify compatible companion skills from the resolved cf-* skill list by matching the task domains, required artifacts, and requested operations against each skill name and description
  RUN rank companion groups by relevance, protocol compatibility, and minimal necessary scope
  EMIT_MENU CompanionRoutingMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS prefer the smallest companion group that covers the task domains
  ALWAYS include concrete write-docs/write-skills/coding companions when the user request explicitly spans documentation, prompt/workflow authoring, source code, review, or implementation
  ALWAYS use companion routing visibly when an active workflow cannot absorb the current user message into one of its reachable states but another cf-* workflow clearly can
  NEVER include `cf`, `cf-analyze`, or `cf-generate` in a companion group; they are routers/entrypoints, not companion workflows
  ALWAYS invoke selected companion skills sequentially, not as a merged prompt, so each skill entry loads and follows its own prerequisites
  NEVER load a companion skill silently; companion loading is always visible in a numbered menu or explicit user reply
  NEVER let companion routing skip or reorder hard gates emitted by any selected skill
```

```pdsl
UNIT CompanionSkillOffer
PURPOSE: At any workflow intent-analysis point, look for probable companion cf-* skills and offer to add them before continuing the current workflow.
STATE:
  SET COMPANION_CONTINUE: unit-name (default unset, scope workflow_run)
  SET CURRENT_WORKFLOW: cf-workflow-name (default unset, scope workflow_run)
  SET COMPANION_OFFER_RESOLVED: true | false (default false, scope workflow_run)
  SET COMPANION_SELECTION_APPLIED: true | false (default false, scope workflow_run)
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  CONTINUE COMPANION_CONTINUE WHEN COMPANION_OFFER_RESOLVED == true OR COMPANION_SELECTION_APPLIED == true
  RUN CompanionSkillResolutionSetup
  RUN identify probable companion skills from ORIGINAL_INTENT, excluding `cf`, `cf-analyze`, `cf-generate`, and CURRENT_WORKFLOW, and rank minimal compatible groups
  CONTINUE COMPANION_CONTINUE WHEN no probable companion group is found
  EMIT_MENU CompanionSkillOfferMenu WHEN one or more probable companion groups are found
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS run this offer immediately after a workflow captures or derives ORIGINAL_INTENT and before explore, brainstorm, planning, validation, authoring, review, or dispatch work
  ALWAYS when reused from an active workflow boundary, offer likely companions visibly before any free-mode exit when the current user message fits another workflow domain better than the current workflow state machine
  ALWAYS offer likely companions visibly when ORIGINAL_INTENT spans multiple workflow domains
  ALWAYS require the caller to set CURRENT_WORKFLOW to its concrete cf-* workflow name before calling CompanionSkillOffer
  ALWAYS filter companion candidates so `cf`, `cf-analyze`, and `cf-generate` can never appear in companion groups, companion-selection, or add-companions output
  ALWAYS exclude CURRENT_WORKFLOW from companion candidates but include it first in the returned launch list when companions are selected
  ALWAYS mark exactly one option as suggested: the smallest group that covers the detected domains, or continue-single when no companion materially improves coverage
  ALWAYS return an ordered launch list containing CURRENT_WORKFLOW followed by selected companion workflow names plus ORIGINAL_INTENT to the host/user for launch, and mark COMPANION_SELECTION_APPLIED before returning; NEVER silently invoke companions from inside this offer
  ALWAYS set COMPANION_OFFER_RESOLVED before continuing the single-workflow path so a resumed caller does not re-offer the same companions for the same ORIGINAL_INTENT
  NEVER block a single-workflow path when the user chooses continue-single
  NEVER run without CURRENT_WORKFLOW set by the caller
  NEVER run without COMPANION_CONTINUE set by the caller
MENU CompanionSkillOfferMenu
TITLE: This request spans multiple workflows. How do you want to proceed?
OPTIONS:
  1 run in sequence — start [CURRENT_WORKFLOW] now, then I'll list the companion workflows to run after; this turn ends with the ordered list (suggested when cross-domain) -> SET COMPANION_SELECTION_APPLIED = true; EMIT the ordered launch list [CURRENT_WORKFLOW, resolved companion workflow names] with ORIGINAL_INTENT and a note that the user should invoke each in order after the previous completes; STOP_TURN
  2 continue with [CURRENT_WORKFLOW] only (suggested when no companion materially improves coverage) -> SET COMPANION_OFFER_RESOLVED = true; CONTINUE COMPANION_CONTINUE
  3 cancel — stop without running any workflow -> STOP_TURN
  INVALID -> EMIT_MENU CompanionSkillOfferMenu
```

```pdsl
UNIT CompanionRoutingMenu
PURPOSE: Offer a concrete single-skill or companion-group choice with named options and a cancel escape.
STATE:
  SET COMPANION_ROUTING_SINGLE_TARGET: cf-workflow-name | unset (default unset, scope workflow_run)
  SET COMPANION_ROUTING_GROUP_TARGETS: list | unset (default unset, scope workflow_run)
DO:
  CONTINUE COMPANION_CONTINUE WHEN ranked companion candidates is empty
  SET COMPANION_ROUTING_SINGLE_TARGET = the best single resolved skill name from ranked companion candidates
  SET COMPANION_ROUTING_GROUP_TARGETS = the best companion group resolved skill names from ranked companion candidates
  EMIT_MENU CompanionRoutingMenuOptions
MENU CompanionRoutingMenuOptions
TITLE: Choose how to proceed — pick a number.
OPTIONS:
  1 [COMPANION_ROUTING_SINGLE_TARGET] — [one-line description] (suggested when single domain) -> SET COMPANION_OFFER_RESOLVED = true; CONTINUE COMPANION_ROUTING_SINGLE_TARGET with ORIGINAL_INTENT
  2 [COMPANION_ROUTING_GROUP_TARGETS joined] — run in sequence for full coverage (suggested when cross-domain) -> SET COMPANION_SELECTION_APPLIED = true; EMIT ordered launch list [COMPANION_ROUTING_GROUP_TARGETS] with ORIGINAL_INTENT and instruction to invoke each in order; STOP_TURN
  3 cancel — stop and return control to the user -> STOP_TURN
  INVALID -> EMIT_MENU CompanionRoutingMenuOptions
RULES:
  ALWAYS resolve COMPANION_ROUTING_SINGLE_TARGET and COMPANION_ROUTING_GROUP_TARGETS before emitting; never emit placeholder text as visible option labels
  ALWAYS mark exactly one option as suggested based on whether the task spans one or multiple domains
  ALWAYS include option 3 cancel so the user can exit without committing
  ALWAYS set COMPANION_SELECTION_APPLIED = true when option 2 is chosen, mirroring CompanionSkillOfferMenu
  ALWAYS set COMPANION_OFFER_RESOLVED = true when option 1 is chosen, so callers do not re-offer for the same intent
```

```pdsl
UNIT CompanionSkillResolutionSetup
PURPOSE: Resolve `{cfs_cmd}` and the available cf-* workflow registry before companion candidates are ranked.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md WHEN CommandResolution is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md WHEN WorkflowResolution is not yet loaded
  RUN CommandResolution to resolve {cfs_cmd} WHEN {cfs_cmd} is unset
  RUN WorkflowResolution to resolve the available cf-* skills
```
