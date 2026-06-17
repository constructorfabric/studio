# Companion Skill Routing
```pdsl
UNIT CompanionSkillRouting
PURPOSE: Let routers and workflows offer multiple compatible cf-* companion skills for cross-domain tasks without weakening each selected skill's protocol.
WHEN:
  REQUIRE a task intent clearly spans more than one cf-* skill domain
DO:
  RUN identify compatible companion skills from the resolved cf-* skill list by matching the task domains, required artifacts, and requested operations against each skill name and description
  RUN rank companion groups by relevance, protocol compatibility, and minimal necessary scope
  EMIT a menu that includes the best single skill and the best companion group, marking exactly one suggested option
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
TITLE: This intent may benefit from companion cf-* workflow(s). Return a launch list for the host/user to run in order, or keep this workflow only?
OPTIONS:
  1 add-companions (suggested when cross-domain) -> SET COMPANION_SELECTION_APPLIED = true; RETURN ordered launch list [CURRENT_WORKFLOW, selected companion cf-* workflow names] plus ORIGINAL_INTENT for launch by the host/user; STOP_TURN
  2 continue-single -> SET COMPANION_OFFER_RESOLVED = true; CONTINUE COMPANION_CONTINUE
  INVALID -> EMIT_MENU CompanionSkillOfferMenu
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
