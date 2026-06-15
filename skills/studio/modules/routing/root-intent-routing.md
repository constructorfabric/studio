# Root Intent Routing

```pdsl
UNIT RootActiveSessionGitCommitRequestGate
PURPOSE: Catch any git commit request typed during an active cf/cf-studio session before the current workflow or router continues.
WHEN:
  REQUIRE cf/cf-studio session rules are active
  REQUIRE the current user message, not only ORIGINAL_INTENT or the initial router prompt, explicitly asks Studio to create a git commit
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  RUN ActiveSessionGitCommitRequestGate from git-commit-mode before any workflow resumes, router matches intent, the main session modifies git state, or a sub-agent receives write-capable git policy
  CONTINUE the pending workflow/router step only after GitCommitModeGate resolves or STOP_TURNs
RULES:
  ALWAYS evaluate this gate on every new user message while cf/cf-studio session rules are active, including replies to menus, resumed workflow prompts, free-text follow-ups, and requests typed after a workflow has already started
  ALWAYS treat this as a session-level interrupt, not as part of ORIGINAL_INTENT capture and not as a root-router-only initial prompt check
  ALWAYS run this gate before honoring phrases such as `commit it`, `make a commit`, `commit these changes`, `git commit`, or `create a git commit`
  NEVER wait for workflow matching, companion routing, author dispatch, or sub-agent dispatch before resolving this gate when the current user message asks Studio to create a git commit
  NEVER treat ordinary references to commits for review/diff scope as commit-creation requests unless the user asks Studio to create a new git commit
```

```pdsl
UNIT IntentRouting
PURPOSE: Resolve available cf-* workflows, capture intent when needed, and present a companion-aware launch menu.
WHEN:
  REQUIRE cf root routing is active
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/session/shutdown.md WHEN the user intent is an unambiguous request to turn off, disable, or shut down Constructor Studio itself, not only an overlay/mode/debug feature
  CONTINUE StudioShutdown WHEN the user intent is an unambiguous request to turn off, disable, or shut down Constructor Studio itself, not only an overlay/mode/debug feature
  CONTINUE RootActiveSessionGitCommitRequestGate WHEN the current user message explicitly asks Studio to create a git commit
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md WHEN WorkflowResolution is not yet loaded
  RUN WorkflowResolution to resolve the available cf-* skills
  EMIT_MENU IntentSkillMenu WHEN the prompt contains no task intent
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/migrate-from-cypilot-offer.md WHEN the prompt intent is migrating from cypilot
  CONTINUE MigrateFromCypilotOffer WHEN the prompt intent is migrating from cypilot
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the prompt contains a task intent that spans more than one cf-* domain
  RUN matching of the intent against the resolved cf-* skill list to find relevant skill(s) and any loaded compatible companion groups WHEN the prompt contains a task intent
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
  ALWAYS populate MatchedIntentSkillMenu with relevant single skills and loaded compatible companion groups, tagging exactly one option `(suggested)`, when the prompt contains a task intent
  ALWAYS when returning a companion route, return an ordered launch list of every selected concrete workflow plus ORIGINAL_INTENT, not only the added companion names
  ALWAYS filter companion groups and comma-separated multi-selects so `cf`, `cf-analyze`, and `cf-generate` can never appear in a companion launch list
  NEVER tag a skill (suggested) when the prompt contains no task intent
  ALWAYS allow multi-select replies for compatible companion skills, formatted as comma-separated menu numbers
  NEVER load workflow-specific rules, ask sub-agent permission, or run explore/brainstorm/plan/validation from this root router
  ALWAYS treat migration from cypilot as a root-routed special case and offer the migrate-from-cypilot cleanup orchestrator before generic workflow matching
  ALWAYS treat unambiguous shutdown as a root-routed special case and run StudioShutdown before generic workflow matching
  NEVER route Brave New World off, debug off, autonomous-default mode off, or workflow-local mode disablement to StudioShutdown
  ALWAYS continue RootActiveSessionGitCommitRequestGate before routing, matching, executing, or delegating when the current user message explicitly asks Studio to create a git commit
  NEVER invoke, route, or delegate a requested git commit until GitCommitModeGate has resolved the session git policy and commit footer contract
MENU IntentSkillMenu
TITLE: Pick a cf-* workflow by number, or choose describe intent / help me choose so I can match the right workflow(s).
OPTIONS:
  1 skill -> SET SELECTED_WORKFLOW = selected cf-* skill; CONTINUE IntentDescribeCapture
  2 describe-intent | help-me-choose -> CONTINUE IntentDescribeCapture
  3 none -> STOP_TURN
  INVALID -> treat non-empty free text as ORIGINAL_INTENT, load companion-skills module when the text spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu; otherwise EMIT_MENU IntentSkillMenu
MENU MatchedIntentSkillMenu
TITLE: Matched cf-* workflow(s) for your intent — pick one to launch next, or pick a loaded companion group / comma-separated skills when the task spans domains.
OPTIONS:
  1 skill -> RETURN selected cf-* skill name plus ORIGINAL_INTENT for launch by the host/user; STOP_TURN
  2 companion-group -> RETURN ordered launch list of selected concrete companion cf-* workflow names plus ORIGINAL_INTENT for launch by the host/user in listed order; STOP_TURN
  3 other -> CONTINUE IntentAllSkillsMenu
  4 none -> STOP_TURN
  INVALID -> EMIT_MENU MatchedIntentSkillMenu
NOTES:
  The activation-only menu enumerates every available cf-* skill as `N <skill-name> — <what it does>`, includes `describe intent / help me choose`, and appends `none`. The matched menu enumerates matched skills or loaded companion groups as `N <skill-or-group> — <why it matches>`, tags exactly one `(suggested)`, allows comma-separated compatible multi-select, and appends `none`. Actual workflow execution belongs to the selected workflow, not to this router.
```

```pdsl
UNIT IntentDescribeCapture
PURPOSE: Capture free-text intent after activation-only cf without falling through the current turn.
STATE:
  SET SELECTED_WORKFLOW: unset | cf-* skill (default unset, scope workflow_run)
  SET SELECTED_COMPANION_SELECTION: unset | companion-selection (default unset, scope workflow_run)
DO:
  EMIT "Describe what you want to do. If you already picked a workflow, I will pass this intent into that workflow before any explore, brainstorm, plan, or substantive gate; otherwise I will match the relevant cf-* workflow(s), including companion skills when the task spans domains."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply
  ALWAYS when the resumed reply explicitly asks Studio to create a git commit, CONTINUE RootActiveSessionGitCommitRequestGate before returning, matching, or delegating the intent
  ALWAYS when SELECTED_WORKFLOW != unset, RETURN SELECTED_WORKFLOW plus ORIGINAL_INTENT for launch by the host/user and STOP_TURN
  ALWAYS when SELECTED_COMPANION_SELECTION != unset, filter out `cf`, `cf-analyze`, and `cf-generate`, then RETURN ordered launch list SELECTED_COMPANION_SELECTION plus ORIGINAL_INTENT for launch by the host/user and STOP_TURN
  ALWAYS when SELECTED_WORKFLOW == unset AND SELECTED_COMPANION_SELECTION == unset, load companion-skills module when the reply spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu
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
  2 companion-selection -> LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md; filter out `cf`, `cf-analyze`, and `cf-generate`; RETURN ordered launch list of selected compatible concrete cf-* workflow names plus ORIGINAL_INTENT for launch by the host/user WHEN ORIGINAL_INTENT is present; otherwise LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md; filter out `cf`, `cf-analyze`, and `cf-generate`; SET SELECTED_COMPANION_SELECTION = selected compatible concrete cf-* workflow names and CONTINUE IntentDescribeCapture
  3 none -> STOP_TURN
  INVALID -> treat non-empty free text as ORIGINAL_INTENT, load companion-skills module when the text spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu; otherwise EMIT_MENU AllCfSkillsMenu
```
