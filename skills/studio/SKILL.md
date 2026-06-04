---
name: cf
aliases: [cf-studio, cf-init, cf-enable]
description: Invoke when user asks to initiate a Constructor Studio session and loads the core rules.
---

# cf / cf-studio — Constructor Studio Session Initiator

`cf` (and its proxy alias `cf-studio`, which behaves identically) is the Constructor Studio session initiator. Its sole responsibility is to load the core rules defined in this file at the start of a session. It performs no task work itself — all actual work is governed by the rules below and carried out elsewhere.

```pdsl
UNIT SessionInit
PURPOSE: Establish cf/cf-studio as the session initiator that only loads the core rules and does no work itself.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
WHEN:
  REQUIRE activation of cf OR activation of cf-studio
DO:
  RUN CommandResolution to resolve {cfs_cmd}
  RUN TemplateVarResolution to resolve {cf-studio-path}
  REQUIRE {cf-studio-path} is resolved before any LOAD below
  LOAD and REMEMBER rules from {cf-studio-path}/.gen/AGENTS.md
  LOAD and REMEMBER rules from {cf-studio-path}/.gen/SKILL.md
  LOAD and REMEMBER rules from {cf-studio-path}/config/AGENTS.md WHEN that file exists; SKIP it without error WHEN it is absent
  LOAD and REMEMBER rules from {cf-studio-path}/config/SKILL.md WHEN that file exists; SKIP it without error WHEN it is absent
  LOAD and REMEMBER rules from {cf-studio-path}/.core/requirements/pdsl-execution-card.md
  LOAD and REMEMBER all UNIT rules defined in this file
  SET CFS_INIT = true
  RUN CliCapabilities to discover and remember the available {cfs_cmd} commands
  EMIT a load report that names each loaded rule source ({cf-studio-path}/.gen/AGENTS.md, {cf-studio-path}/.gen/SKILL.md, {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/config/SKILL.md when present, {cf-studio-path}/.core/requirements/pdsl-execution-card.md, and the UNIT rules in this file) and confirms cf is ready to follow them
  CONTINUE IntentRouting
RULES:
  ALWAYS treat cf and cf-studio as the same skill, where cf-studio is a proxy alias to cf
  ALWAYS limit cf/cf-studio to initiating the session and loading core rules
  ALWAYS run CommandResolution then CliCapabilities on every cf/cf-studio activation, before routing
  ALWAYS load the {cf-studio-path}/.gen/AGENTS.md and {cf-studio-path}/.gen/SKILL.md rule sources as mandatory
  ALWAYS treat the {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/config/SKILL.md rule sources as optional, loading each when it exists and skipping it without error when it is absent
  ALWAYS report the loaded rule sources and confirm readiness to follow them before routing
NOTES:
  Loading {cf-studio-path}/.core/requirements/pdsl-execution-card.md here is intentional: per the PDSL spec the root studio SKILL owns loading that runtime semantics card once into the shared context pack; the agent already executes PDSL from inherent understanding, and the card reinforces it. This is not a circular dependency.
```

```pdsl
UNIT IntentRouting
PURPOSE: After cf loads core rules, resolve the available cf-* skills via WorkflowResolution and present them as one numbered, directly selectable menu — the matched skill(s) when the prompt has a task intent, or all cf-* skills when it has none.
WHEN:
  REQUIRE cf has loaded core rules
DO:
  RUN WorkflowResolution to resolve the available cf-* skills
  RUN matching of the intent against the resolved cf-* skill list to find the relevant skill(s) WHEN the prompt contains a task intent
  EMIT_MENU IntentSkillMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS resolve the available cf-* skills via WorkflowResolution before populating IntentSkillMenu
  ALWAYS render IntentSkillMenu with every offered cf-* skill on its own numbered line so the user selects one by replying with the number
  ALWAYS populate IntentSkillMenu with the matched skill(s) when the prompt contains a task intent and with all available cf-* skills when it contains none
  ALWAYS tag exactly one skill (suggested) when the prompt contains a task intent
  NEVER tag a skill (suggested) when the prompt contains no task intent
MENU IntentSkillMenu
TITLE: Pick a cf-* skill by number to run it (when matched to a request, the best match is tagged suggested).
OPTIONS:
  1 skill -> INVOKE the selected cf-* skill, passing the original intent
  2 none -> STOP_TURN
  INVALID -> EMIT_MENU IntentSkillMenu
NOTES:
  The rendered menu enumerates every offered cf-* skill on its own line as `N <skill-name> — <why it matches or what it does>`, tags exactly one `(suggested)` when there is a task intent, and appends a final `none` option; option `1 skill` above is the representative template for those numbered skill options.
```

```pdsl
UNIT WorkflowResolution
PURPOSE: Resolve the available cf-* skills deterministically by discovering core and kit workflows, never from the host, for any unit that needs the skill list.
WHEN:
  REQUIRE the available cf-* skill list is needed
DO:
  RUN enumeration of core workflows at {cf-studio-path}/.core/workflows/*.md
  RUN enumeration of kit workflows from `{cfs_cmd} info --json` at kit_details.<kit>.workflows
  RUN mapping of each discovered workflow to its cf-* skill name: a core workflow file <name>.md maps to cf-<name>; a kit workflow <base> under kit <kit> maps to cf-<kit>-<base>
  REQUIRE at least one cf-* skill was discovered
  EMIT a one-line empty-discovery note WHEN no cf-* skill was discovered
  STOP_TURN WHEN no cf-* skill was discovered
RULES:
  ALWAYS resolve the cf-* skill list deterministically from the filesystem and kit registry, never from the host and never via a cfs CLI skills-list command
  ALWAYS map core workflows to cf-<name> and kit workflows to cf-<kit>-<base>
  NEVER guess the cf-* skill list
```

```pdsl
UNIT CreativeIntentBrainstormOffer
PURPOSE: Always offer cf-brainstorm before any creative task, and respect the user's decline.
WHEN:
  REQUIRE the prompt contains a creative intent (brainstorm, ideate, explore options, explore or shape a design, discover requirements, map options, compare decision tradeoffs, or design a new artifact or feature)
DO:
  EMIT_MENU CreativeBrainstormOffer
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer to Invoke cf-brainstorm before starting any creative task
  ALWAYS let the user decline the cf-brainstorm offer
  ALWAYS evaluate this offer after IntentRouting has routed, and before PlanFirstGate when a single request is both creative and substantive
  NEVER load or invoke cf-brainstorm when the user declines; continue with the requested task instead
MENU CreativeBrainstormOffer
TITLE: This looks like a creative task — run a cf-brainstorm panel first? (recommended)
OPTIONS:
  1 brainstorm -> INVOKE skill `cf-brainstorm`
  2 skip -> NEVER load cf-brainstorm; CONTINUE the requested task without it
  INVALID -> EMIT_MENU CreativeBrainstormOffer
```

```pdsl
UNIT MigrateFromCypilotOffer
PURPOSE: Offer the migrate-from-cypilot orchestrator when the prompt intent is a cypilot migration, and respect the user's decline.
WHEN:
  REQUIRE the prompt intent is migrating from cypilot (migrate from cypilot, migrate-from-cypilot, or cleaning up residual cypilot/cpt/Cypilot/Cyber Pilot references after the deterministic migration)
DO:
  EMIT_MENU MigrateFromCypilotConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer the migrate-from-cypilot orchestrator when the prompt intent is a cypilot migration
  ALWAYS let the user decline the offer
  NEVER open or run the migrate-from-cypilot orchestrator when the user declines; continue with the requested task instead
MENU MigrateFromCypilotConfirm
TITLE: This looks like a cypilot to Constructor Studio migration — run the migrate-from-cypilot cleanup orchestrator? It checks the deterministic-migration preconditions first and gates every sub-agent step.
OPTIONS:
  1 migrate -> open and follow {cf-studio-path}/.core/skills/studio/migrate-from-cypilot.md
  2 skip -> NEVER open the orchestrator; CONTINUE the requested task without it
  INVALID -> EMIT_MENU MigrateFromCypilotConfirm
```

```pdsl
UNIT LanguageComplexityLoad
PURPOSE: Always load and apply the language-complexity rule when the intent is creating documents, guides, or reports.
WHEN:
  REQUIRE the prompt intent is creating or writing documents, guides, reports, READMEs, documentation, onboarding/training material, or explanatory write-ups
DO:
  LOAD {cf-studio-path}/.core/requirements/language-complexity.md and follow it
RULES:
  ALWAYS load {cf-studio-path}/.core/requirements/language-complexity.md before producing any document, guide, or report content
  ALWAYS self-check every chat message and artifact write against the resolved language-complexity level and rewrite before emitting when a draft breaches it
  ALWAYS keep source quotes verbatim (exempt from the complexity rewrite)
```

```pdsl
UNIT PlanFirstGate
PURPOSE: Before any substantive operation, ask whether to plan the work first, and respect the user's decline.
WHEN:
  REQUIRE a substantive task is about to start (validation, review, editing, prompts, skills, code, artifacts, analytical tasks, or any other task work)
DO:
  EMIT_MENU PlanFirstConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS ask whether a plan is needed before starting any substantive task
  ALWAYS let the user decline and proceed without a plan
  ALWAYS resolve a co-triggering CreativeIntentBrainstormOffer before this gate when both apply to the same request
  NEVER start the substantive operation before this gate resolves
MENU PlanFirstConfirm
TITLE: Plan this work before starting? (recommended for multi-step or sub-agent work)
OPTIONS:
  1 plan -> CONTINUE PlanBuild
  2 no-plan -> proceed without a plan and CONTINUE the requested task
  INVALID -> EMIT_MENU PlanFirstConfirm
```

```pdsl
UNIT PlanBuild
PURPOSE: Build the execution plan, present it for review, and let the user choose where it is kept.
WHEN:
  REQUIRE the user chose to plan in PlanFirstGate
DO:
  RUN draft the plan: define the sub-agent intent for each task, group tasks into parallel, sequential, and inline execution, and order them
  EMIT the drafted plan for user review
  EMIT_MENU PlanStorageChoice
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS define the sub-agent intent for the planned work before execution
  ALWAYS classify each task as a parallel sub-agent, a sequential sub-agent, or an inline task
  ALWAYS present the plan for user review before executing it
  ALWAYS offer to save the plan to disk or keep it in session memory
  NEVER execute the planned work before the user has reviewed the plan and chosen its storage
MENU PlanStorageChoice
TITLE: Plan ready — review it, then choose how to keep it before I start.
OPTIONS:
  1 memory -> keep the plan in session memory and CONTINUE the planned work (suggested for quick iteration)
  2 disk -> WRITE the plan to disk, then CONTINUE the planned work (for persistence)
  3 revise -> revise the plan per user feedback and EMIT_MENU PlanStorageChoice
  4 stop -> STOP_TURN
  INVALID -> EMIT_MENU PlanStorageChoice
```

```pdsl
UNIT ContextCategories
PURPOSE: Classify every loaded context as exactly one of two categories.
RULES:
  ALWAYS classify every loaded context as either `rules` or `content`, where `rules` = instructions (skills, workflows, methodologies, pipelines, plans, templates, IO contracts, examples, schemas) and `content` = artifacts (checklists, codebase, generation targets, source materials, anything being transformed)
  NEVER classify a single loaded context as both `rules` and `content`
```

```pdsl
UNIT RulesMemory
PURPOSE: Govern the lifecycle of `rules` assets in the session.
RULES:
  ALWAYS load a `rules` asset at most once and then keep it for the entire session
  NEVER compact, reload, or mutate a `rules` asset once it is loaded
```

```pdsl
UNIT ContentMemory
PURPOSE: Govern the lifecycle of `content` in the session.
RULES:
  ALWAYS hold `content` in the session only while it is needed and unload/forget it once it stops being needed
  ALWAYS treat `content` as mutable and reloadable, tracked by absolute file path or, for web sources, by URL/reference
  NEVER compact `content`
```

```pdsl
UNIT SubAgentDispatch
PURPOSE: Synthesize and dispatch cf-* sub-agents from `rules` plus a contract while gating on approval and providing a fallback.
STATE:
  SET SUB_AGENTS_APPROVED: unset | true | false (default unset, scope session)
  SET SUB_AGENTS_INLINE: unset | true (default unset, scope session)
WHEN:
  REQUIRE a cf-* sub-agent must be launched
DO:
  LOAD sub-agent contract from {cf-studio-path}/.core/skills/studio/agents/{sub-agent-name}.md
  EMIT_MENU SubAgentApprovalRequest WHEN SUB_AGENTS_APPROVED == unset
  WAIT user.reply WHEN SUB_AGENTS_APPROVED == unset
  REQUIRE SUB_AGENTS_APPROVED == true
  RUN synthesis of the initial prompt from the controller-selected `rules` plus the sub-agent contract
  DISPATCH the sub-agent natively
RULES:
  ALWAYS synthesize the initial prompt from `rules` plus the sub-agent contract, with the controller deciding which `rules` the sub-agent needs and which it does not
  ALWAYS pass any needed `content` to the sub-agent as an absolute path or web reference/link, never inline
  ALWAYS allow the sub-agent to load any `content` it needs
  ALWAYS treat SUB_AGENTS_APPROVED as a session-wide approval that applies to every later dispatch until StudioShutdown, and reset it to unset when the user asks to revoke it
  NEVER allow the sub-agent to load any instructions (`rules`)
  NEVER dispatch a sub-agent unless SUB_AGENTS_APPROVED == true
ON_ERROR:
  EMIT_MENU SubAgentApprovalRequest WHEN SUB_AGENTS_APPROVED == unset
  EMIT_MENU SubAgentFallbackRequest WHEN SUB_AGENTS_APPROVED == false OR native dispatch fails
MENU SubAgentApprovalRequest
TITLE: Approve dispatching cf-* sub-agents this session? Approve runs them natively (parallel, isolated); deny offers an inline fallback. (approve is suggested)
OPTIONS:
  1 approve -> SET SUB_AGENTS_APPROVED = true; CONTINUE dispatch
  2 deny -> SET SUB_AGENTS_APPROVED = false; EMIT_MENU SubAgentFallbackRequest
  INVALID -> EMIT_MENU SubAgentApprovalRequest
MENU SubAgentFallbackRequest
TITLE: The sub-agent could not run natively — how should I proceed? (inline is suggested)
OPTIONS:
  1 inline -> SET SUB_AGENTS_INLINE = true; RUN the contract inline
  2 retry -> DISPATCH the sub-agent natively, at most 2 retries before this menu re-offers only inline or stop
  3 stop -> STOP_TURN
  INVALID -> EMIT_MENU SubAgentFallbackRequest
```

```pdsl
UNIT CommandResolution
PURPOSE: Resolve the {cfs_cmd} command before invoking any cfs command.
WHEN:
  REQUIRE a {cfs_cmd} invocation is needed
DO:
  SET {cfs_cmd} = cfs WHEN cfs is available on PATH
  SET {cfs_cmd} = python {cf-studio-path}/.core/skills/studio/scripts/studio.py WHEN cfs is not available on PATH
RULES:
  ALWAYS resolve {cfs_cmd} before invoking any cfs command
```

```pdsl
UNIT CliCapabilities
PURPOSE: Discover and remember the tool's available commands and prefer them for relevant tasks.
DO:
  RUN {cfs_cmd} --help to obtain the list of available commands and capabilities
  SET remembered tool commands = the commands returned by {cfs_cmd} --help
RULES:
  ALWAYS run {cfs_cmd} --help to discover available commands and remember them for the session
  ALWAYS prefer a remembered {cfs_cmd} command over an ad-hoc approach when one fits the task
```

```pdsl
UNIT TemplateVarResolution
PURPOSE: Resolve unknown template variables before asking the user.
WHEN:
  REQUIRE an unknown `{...}` template variable is encountered
DO:
  RUN {cfs_cmd} resolve-vars
  WAIT for the user to provide the value WHEN the variable still cannot be found
  CONTINUE once the value is provided
RULES:
  ALWAYS try `{cfs_cmd} resolve-vars` before asking the user for a template variable value
```

```pdsl
UNIT ReviewFindingContract
PURPOSE: Define the fields every review finding must report, for all review operations.
RULES:
  ALWAYS report each finding of any review operation with SEVERITY, LOCATION (path plus line or range), EVIDENCE, ROOT_CAUSE, IMPACT, SUGGESTED_FIX, VERIFICATION (how to confirm the fix resolves it), and CONFIDENCE
  ALWAYS apply this finding contract to every review operation, regardless of which skill or workflow runs it
  NEVER emit a review finding that is missing any of the required fields
```

```pdsl
UNIT ReviewFixApprovalGate
PURPOSE: Gate every review-fix loop on explicit user approval and let the user choose the fix scope.
WHEN:
  REQUIRE a review-fix loop has produced findings and is about to apply fixes
DO:
  EMIT_MENU ReviewFixScope
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS request user confirmation before applying any fixes in a review-fix loop
  ALWAYS offer the fix-scope options: only CRITICAL and MAJOR findings, all findings, or a user-selected partial subset
  NEVER apply review fixes without explicit user approval of the chosen scope
MENU ReviewFixScope
TITLE: Review found issues — what should I fix? (nothing is changed until you choose)
OPTIONS:
  1 crit-major -> fix only CRITICAL and MAJOR findings, then re-review (suggested)
  2 all -> fix all findings, then re-review
  3 partial -> ask which specific findings to fix, fix only those, then re-review
  4 none -> STOP_TURN
  INVALID -> EMIT_MENU ReviewFixScope
```

```pdsl
UNIT NextActionsOffer
PURPOSE: After completing a task or operation, always offer next actions synthesized from the current context and the available cf-* skills.
WHEN:
  REQUIRE a task or operation has just completed and control is about to return to the user
DO:
  RUN WorkflowResolution to resolve the available cf-* skills
  RUN synthesis of 3 to 5 next actions from the current context and the available cf-* skills
  EMIT_MENU NextActionsMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer next actions when a task or operation completes and control returns to the user
  ALWAYS synthesize 3 to 5 next actions from the current context and the available cf-* skills, never a fixed or guessed list
  ALWAYS explain why each offered action is relevant to the current context and mark exactly one as suggested
  ALWAYS let the user pick an offered action or decline
  NEVER offer next actions when the operation returns control to a calling skill or workflow rather than the user (for example a skill invoked in return-context mode)
MENU NextActionsMenu
TITLE: Next actions for this context — pick a number or reply done. (one action is marked suggested)
OPTIONS:
  1 action -> run the chosen synthesized next action; the menu lists each of the 3 to 5 synthesized actions as its own number with its why, and exactly one is tagged (suggested)
  2 done -> STOP_TURN
  INVALID -> EMIT_MENU NextActionsMenu
NOTES:
  The rendered menu enumerates every synthesized action (3 to 5) on its own line as `N <action> — <why>`, tags exactly one `(suggested)`, and appends a final `done` option; option `1 action` above is the representative template for those numbered actions.
```

```pdsl
UNIT StudioShutdown
PURPOSE: Turn the studio off only after explicit user confirmation, then forget all loaded `content` and `rules` for the session.
WHEN:
  REQUIRE the user intent can be interpreted as a request to turn off, disable, or shut down the studio
DO:
  EMIT_MENU StudioShutdownConfirm
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS require explicit user confirmation via the menu before turning the studio off
  ALWAYS give StudioShutdown precedence only when shutdown is the unambiguous intent; otherwise resolve the task intent first and confirm the shutdown separately
  ALWAYS set CFS_INIT = false and forget all `content` and all `rules` on confirmation
  ALWAYS make the user aware that confirming forgets all loaded `content` and `rules`
  NEVER turn the studio off or forget `content`/`rules` without confirmation
MENU StudioShutdownConfirm
TITLE: Confirm: turning the studio off will FORGET all loaded `content` and `rules` for this session.
OPTIONS:
  1 confirm -> SET CFS_INIT = false; forget/unload all `content` and all `rules` from the session
  2 cancel -> STOP_TURN
  INVALID -> EMIT_MENU StudioShutdownConfirm
```