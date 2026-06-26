# Root Intent Routing

```pdsl
UNIT RootActiveSessionGitCommitRequestGate
PURPOSE: Thin root wrapper for the canonical active-session git commit interrupt.
WHEN:
  REQUIRE cf/cf-studio session rules are active
  REQUIRE the current user message, not only ORIGINAL_INTENT or the initial router prompt, explicitly asks Studio to create a git commit
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN ActiveSessionGitCommitRequestGate from git-commit-mode before any workflow resumes, router matches intent, local menu INVALID handling runs, the main session modifies git state, or a sub-agent receives write-capable git policy
RULES:
  ALWAYS delegate the substantive interrupt behavior, pending-continuation preservation, local menu INVALID precedence, and resume handling to ActiveSessionGitCommitRequestGate in git-commit-mode
  NEVER duplicate or weaken ActiveSessionGitCommitRequestGate rules in this root wrapper
```

```pdsl
UNIT IntentRouting
PURPOSE: Resolve available cf-* workflows, capture intent when needed, and present a companion-aware launch menu.
WHEN:
  REQUIRE cf root routing is active
DO:
  RUN RootIntentSpecialCases
  RUN RootIntentMatchSetup
  EMIT_MENU IntentSkillMenu WHEN the prompt contains no task intent
  EMIT_MENU MatchedIntentSkillMenu WHEN the prompt contains a task intent
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS resolve the available cf-* skills via WorkflowResolution before populating IntentSkillMenu
  ALWAYS render IntentSkillMenu with every offered cf-* skill on its own numbered line so the user selects one by replying with the number
  ALWAYS for activation-only cf, show all available workflows first and include a `describe intent / help me choose` option
  NEVER invoke a cf-* workflow directly from this root router; only present the selected workflow(s) for launch
  ALWAYS when the user replies with free text instead of a listed workflow number, treat that reply as ORIGINAL_INTENT, run matching, and EMIT_MENU MatchedIntentSkillMenu
  ALWAYS prefer concrete non-router workflows over router entrypoints during intent matching; treat cf-analyze (backwards-compatible router name) and cf-generate (backwards-compatible router name) as router entrypoints only when explicitly selected or when no concrete workflow matches
  NEVER offer an already-selected cf-* workflow through cf-analyze or cf-generate when a concrete workflow can execute the intent
  ALWAYS when a companion route is returned, populate MatchedIntentSkillMenu with relevant single skills and compatible companion groups (tagging exactly one option (suggested)), return an ordered launch list of every selected concrete workflow plus ORIGINAL_INTENT, and filter companion groups and multi-selects so `cf`, `cf-analyze`, and `cf-generate` never appear in a companion launch list
  NEVER load workflow-specific rules, ask sub-agent permission, or run explore/brainstorm/plan/validation from this root router
  ALWAYS treat migration from cypilot as a root-routed special case and offer the migrate-from-cypilot cleanup orchestrator before generic workflow matching
  ALWAYS treat unambiguous shutdown as a root-routed special case and run StudioShutdown before generic workflow matching
  NEVER route Brave New World off, debug off, autonomous-default mode off, or workflow-local mode disablement to StudioShutdown
INVARIANTS:
  ALWAYS continue RootActiveSessionGitCommitRequestGate before routing, matching, executing, or delegating when the current user message explicitly asks Studio to create a git commit
  NEVER invoke, route, or delegate a requested git commit until GitCommitModeGate has resolved the session git policy and commit footer contract
MENU IntentSkillMenu
TITLE: Pick a cf-* workflow by number, or choose describe intent / help me choose so I can match the right workflow(s).
OPTIONS:
  1 skill -> SET SELECTED_WORKFLOW = selected cf-* skill; CONTINUE IntentDescribeCapture
  2 describe-intent | help-me-choose -> CONTINUE IntentDescribeCapture
  3 none -> EMIT "No workflow was selected. Control is returning to free mode."; STOP_TURN
  INVALID -> treat non-empty free text as ORIGINAL_INTENT, load companion-skills module when the text spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu; otherwise EMIT_MENU IntentSkillMenu
MENU MatchedIntentSkillMenu
TITLE: Matched cf-* workflow(s) for your intent — pick one to launch next, or pick a loaded companion group / comma-separated skills when the task spans domains.
OPTIONS:
  1 skill -> RETURN selected cf-* skill name plus ORIGINAL_INTENT for launch by the host/user; STOP_TURN
  2 companion-group -> RETURN ordered launch list of selected concrete companion cf-* workflow names plus ORIGINAL_INTENT for launch by the host/user in listed order; STOP_TURN
  3 other -> CONTINUE IntentAllSkillsMenu
  4 none -> EMIT "No workflow was launched. Control is returning to free mode."; STOP_TURN
  INVALID -> EMIT_MENU MatchedIntentSkillMenu
NOTES:
  The activation-only menu enumerates every available cf-* skill as `N <skill-name> — <what it does>`, includes `describe intent / help me choose`, and appends `none`. The matched menu enumerates matched skills or loaded companion groups as `N <skill-or-group> — <why it matches>`, tags exactly one `(suggested)`, allows comma-separated compatible multi-select, and appends `none`. Actual workflow execution belongs to the selected workflow, not to this router.
```

```pdsl
UNIT RootIntentSpecialCases
PURPOSE: Resolve shutdown, commit-request, and cypilot-migration exceptions before generic workflow matching.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/session/shutdown.md WHEN the user intent is an unambiguous request to turn off, disable, or shut down Constructor Studio itself, not only an overlay/mode/debug feature
  CONTINUE StudioShutdown WHEN the user intent is an unambiguous request to turn off, disable, or shut down Constructor Studio itself, not only an overlay/mode/debug feature
  CONTINUE RootActiveSessionGitCommitRequestGate WHEN the current user message explicitly asks Studio to create a git commit
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/migrate-from-cypilot-offer.md WHEN the prompt intent is migrating from cypilot
  CONTINUE MigrateFromCypilotOffer WHEN the prompt intent is migrating from cypilot
```

```pdsl
UNIT RootIntentMatchSetup
PURPOSE: Resolve the available workflow registry and any companion candidates before a root router menu is emitted.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md WHEN WorkflowResolution is not yet loaded
  RUN WorkflowResolution to resolve the available cf-* skills
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the prompt contains a task intent that spans more than one cf-* domain
  RUN CompanionSkillResolutionSetup WHEN the prompt contains a task intent that spans more than one cf-* domain
  RUN matching of the intent against the resolved cf-* skill list to find relevant skill(s) and any loaded compatible companion groups WHEN the prompt contains a task intent
```

```pdsl
UNIT IntentDescribeCapture
PURPOSE: Capture free-text intent after activation-only cf without falling through the current turn.
STATE:
  SET SELECTED_WORKFLOW: unset | cf-* skill (default unset, scope workflow_run)
  SET SELECTED_COMPANION_SELECTION: unset | companion-selection (default unset, scope workflow_run)
  SET INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  EMIT "Describe what you want to do. If you already picked a workflow, I will pass this intent into that workflow before any explore, brainstorm, plan, or substantive gate; otherwise I will match the relevant cf-* workflow(s), including companion skills when the task spans domains."
  SET INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS stop the turn after capturing the free-text prompt so resumed intent routing runs explicitly
```

```pdsl
UNIT IntentDescribeResume
PURPOSE: Route the resumed free-text intent through git gating, deferred workflow returns, or fresh matching.
STATE:
  SET SELECTED_WORKFLOW: unset | cf-* skill (default unset, scope workflow_run)
  SET SELECTED_COMPANION_SELECTION: unset | companion-selection (default unset, scope workflow_run)
  SET INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET INTENT_CAPTURE_STATE = unset
  CONTINUE RootActiveSessionGitCommitRequestGate WHEN user.reply explicitly asks Studio to create a git commit
  CONTINUE IntentDescribeReturnSelectedWorkflow WHEN SELECTED_WORKFLOW != unset
  CONTINUE IntentDescribeReturnSelectedCompanions WHEN SELECTED_COMPANION_SELECTION != unset
  CONTINUE IntentDescribeMatchReply WHEN SELECTED_WORKFLOW == unset AND SELECTED_COMPANION_SELECTION == unset
```

```pdsl
UNIT IntentDescribeReturnSelectedWorkflow
PURPOSE: Return the deferred single-workflow launch after free-text intent capture completes.
WHEN:
  REQUIRE SELECTED_WORKFLOW != unset
DO:
  RETURN SELECTED_WORKFLOW plus ORIGINAL_INTENT for launch by the host/user
  STOP_TURN
```

```pdsl
UNIT IntentDescribeReturnSelectedCompanions
PURPOSE: Return the deferred companion workflow launch after free-text intent capture completes.
STATE:
  SET SELECTED_COMPANION_SELECTION: unset | companion-selection (default unset, scope workflow_run)
WHEN:
  REQUIRE SELECTED_COMPANION_SELECTION != unset
DO:
  RETURN ordered launch list of SELECTED_COMPANION_SELECTION excluding `cf`, `cf-analyze`, and `cf-generate`, plus ORIGINAL_INTENT for launch by the host/user
  STOP_TURN
```

```pdsl
UNIT IntentDescribeMatchReply
PURPOSE: Match the resumed free-text intent when no deferred workflow selection is waiting.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the reply spans domains
  RUN CompanionSkillResolutionSetup WHEN the reply spans domains
  RUN matching of the intent against the resolved cf-* skill list to find relevant skill(s) and any loaded compatible companion groups
  EMIT_MENU MatchedIntentSkillMenu
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT IntentAllSkillsMenu
PURPOSE: Let the user choose from every available cf-* skill after rejecting the matched suggestion.
DO:
  EMIT_MENU AllCfSkillsMenu
  WAIT user.reply
  STOP_TURN
MENU AllCfSkillsMenu
TITLE: All available cf-* workflow(s) — pick one, or enter comma-separated compatible skills for a companion route.
OPTIONS:
  1 skill -> RETURN selected cf-* skill name plus ORIGINAL_INTENT for launch by the host/user WHEN ORIGINAL_INTENT is present; otherwise SET SELECTED_WORKFLOW = selected cf-* skill and CONTINUE IntentDescribeCapture
  2 companion-selection -> filter out `cf`, `cf-analyze`, and `cf-generate`; RETURN ordered launch list of selected compatible concrete cf-* workflow names plus ORIGINAL_INTENT for launch by the host/user WHEN ORIGINAL_INTENT is present; otherwise filter out `cf`, `cf-analyze`, and `cf-generate`; SET SELECTED_COMPANION_SELECTION = selected compatible concrete cf-* workflow names and CONTINUE IntentDescribeCapture
  3 none -> EMIT "No workflow was selected. Control is returning to free mode."; STOP_TURN
  INVALID -> treat non-empty free text as ORIGINAL_INTENT, load companion-skills module when the text spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu; otherwise EMIT_MENU AllCfSkillsMenu
```
