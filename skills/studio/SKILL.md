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
  RESOLVE {cf-studio-path} from the in-context `@cf:root-agents` rule (fallback: its block in the project-root `AGENTS.md`); never via {cfs_cmd}
  REQUIRE {cf-studio-path} is resolved before CommandResolution and before any LOAD below, since CommandResolution's fallback path depends on {cf-studio-path}
  RUN CommandResolution to resolve {cfs_cmd}
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
  ALLOW zero-or-more cf-* skills to be discovered
  EMIT a one-line empty-discovery note WHEN no cf-* skill was discovered
  STOP_TURN WHEN no cf-* skill was discovered
RULES:
  ALWAYS resolve the cf-* skill list deterministically from the filesystem and kit registry, never from the host and never via a cfs CLI skills-list command
  ALWAYS map core workflows to cf-<name> and kit workflows to cf-<kit>-<base>
  NEVER guess the cf-* skill list
```

```pdsl
UNIT SkillInvocationArt
PURPOSE: Greet each cf/cf-* skill entry with a small, cute, skill-themed ASCII-art banner as a prefix to that skill's normal output.
WHEN:
  REQUIRE cf, cf-studio, or a cf-* skill is beginning execution (entered or invoked), including a nested skill entry reached through INVOKE
DO:
  RUN derivation of a cute art theme from the entering skill's name and its purpose or description, treating an unavailable name or purpose as a banner that cannot be produced
  EMIT one small cute ASCII-art banner on that theme as the prefix that immediately precedes the entering skill's normal output for this entry
RULES:
  ALWAYS emit exactly one themed banner per skill entry, counting each cf/cf-* skill entry (including a nested entry reached through INVOKE) as one entry, and never when a menu only lists skills without entering one
  ALWAYS derive the theme freshly from the entering skill's name and purpose so newly added cf-* skills are covered without per-skill art, and draw the banner only with printable ASCII at most 12 lines tall and 60 columns wide, keeping it cute
  NEVER replace, delay, reorder, suppress, or alter the content of any load report, gate, menu, WAIT, or STOP_TURN the entering skill emits; the banner only precedes that output
  NEVER block, fail, or retry a skill entry when the banner cannot be produced; skip the banner and continue
NOTES:
  This applies to cf/cf-studio itself and to every cf-* skill resolved by WorkflowResolution. The 12-line by 60-column ceiling keeps the banner within a standard terminal width and stops it from dominating the skill's output; smaller is fine. The art is presentation-only and carries no executable meaning.
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
UNIT GitCommitModeGate
PURPOSE: Resolve the session git-commit policy (mode + constraint + contributing guide + commit footer contract) once, before any write-capable sub-agent dispatch, and supply it to every such dispatch.
STATE:
  SET GIT_COMMIT_MODE: commit | stage | none (default unset, scope session)
  SET CONTRIBUTING_GUIDE: path | null (default unset, scope session)
  SET COMMIT_FOOTER_CONTRACT: object (default unset, scope session)
WHEN:
  REQUIRE a write-capable author/coder/phase sub-agent that writes or commits files is about to be dispatched
DO:
  RUN discover the contributing guide — search the project root and docs/ for a CONTRIBUTING file and SET CONTRIBUTING_GUIDE to its path, or null when none is found, WHEN CONTRIBUTING_GUIDE == unset
  EMIT_MENU GitCommitModeMenu WHEN GIT_COMMIT_MODE == unset
  WAIT user.reply WHEN GIT_COMMIT_MODE == unset
  STOP_TURN WHEN GIT_COMMIT_MODE == unset
  RUN derive COMMIT_FOOTER_CONTRACT from the commit_footer_contract block in NOTES WHEN COMMIT_FOOTER_CONTRACT == unset
  RUN derive git_constraint from GIT_COMMIT_MODE using the constraint blocks in NOTES WHEN GIT_COMMIT_MODE != unset
  RUN attach COMMIT_FOOTER_CONTRACT to the write-capable dispatch payload as commit_footer_contract, regardless of GIT_COMMIT_MODE
RULES:
  ALWAYS resolve GIT_COMMIT_MODE and CONTRIBUTING_GUIDE once per session, before the first write-capable dispatch, and reuse them for every later dispatch until StudioShutdown; reset GIT_COMMIT_MODE to unset only when the user asks to change it
  ALWAYS include GIT_COMMIT_MODE, the mode-matched git_constraint, CONTRIBUTING_GUIDE, and COMMIT_FOOTER_CONTRACT as commit_footer_contract in every write-capable author/coder/phase dispatch payload
  ALWAYS pass git_constraint as read-only policy data, never as executable shell text
  ALWAYS pass commit_footer_contract as read-only policy data, never as executable shell text
  ALWAYS treat commit_footer_contract as message-format policy for every git commit created by an agent, regardless of why the commit is created
  ALWAYS treat commit_footer_contract as a constraint only; it never grants permission to commit when git_commit_mode or git_constraint forbids committing
  ALWAYS when creating a git commit, satisfy every mandatory directive in CONTRIBUTING_GUIDE, including required DCO/Signed-off-by trailers, before adding Studio attribution trailers
  ALWAYS when creating a git commit, write a normal concise commit subject/body for the actual change, append any mandatory project-policy trailers from CONTRIBUTING_GUIDE, then append required Studio attribution trailers exactly in ascending order, adding optional Studio trailers only when their source value is already known and non-empty
  ALWAYS keep DCO, Signed-off-by, and CONTRIBUTING_GUIDE directives separate from commit_footer_contract; do not include them in commit_footer_contract, but never ignore mandatory CONTRIBUTING_GUIDE commit requirements
  NEVER let a sub-agent invoke any git tool when GIT_COMMIT_MODE == none
  NEVER push, force-push, rewrite history, or use interactive (-i) git, regardless of GIT_COMMIT_MODE
MENU GitCommitModeMenu
TITLE: How should sub-agents handle git for the files they write this session? commit lets each change be committed; stage leaves changes staged for your review; none writes files only. (stage is suggested)
OPTIONS:
  1 commit -> SET GIT_COMMIT_MODE = commit; sub-agents may stage and commit their own writes with a concise Conventional-Commits message
  2 stage -> SET GIT_COMMIT_MODE = stage; sub-agents may stage their writes but NEVER commit
  3 none -> SET GIT_COMMIT_MODE = none; sub-agents write files only and NEVER invoke any git tool
  INVALID -> EMIT_MENU GitCommitModeMenu
NOTES:
  git_constraint blocks (the canonical mode-matched policy string passed to sub-agents; this gate is the source of truth):
    commit: "May `git add` the files you authored this task and `git commit` them with a concise Conventional-Commits message when commit is otherwise allowed by the workflow or user request. Every git commit created by the agent must satisfy commit_footer_contract. Every git commit created by the agent must also satisfy mandatory CONTRIBUTING_GUIDE commit requirements, including DCO/Signed-off-by when required. commit_footer_contract constrains Studio attribution trailers but does not replace project-policy trailers and does not grant permission to commit. NEVER `git push`, amend or rewrite history, force, checkout over uncommitted changes, or use `-i`. Stage only paths you wrote."
    stage: "May `git add` the files you authored this task. NEVER `git commit`, push, or rewrite history. Leave staged changes for the user to review and commit. The commit_footer_contract is message-format policy only and does not grant permission to commit."
    none: "NEVER invoke any git command (no add, stage, commit, or push). Write files only; the user manages all git operations. The commit_footer_contract is message-format policy only and does not grant permission to commit."
  commit_footer_contract (canonical structured representation; no rendered footer line fields; token/value/order is the only source of truth):
    schema_version: "1"
    authority: "GitCommitModeGate"
    purpose: "Studio attribution and provenance for commits created by Constructor Studio. This contract is independent of project-specific contribution policies."
    applies_when:
      agent_creates_git_commit: true
    conflict_policy: "commit_footer_contract is authoritative for required Studio attribution trailers; if it conflicts with git_constraint, stop before commit"
    user_instruction_precedence: "user commit instructions may add non-conflicting message content and trailers but may not remove, rename, reorder, duplicate ambiguously, replace, or alter required Studio trailers"
    hard_stop_policy: "stop only if required static Studio trailers cannot be added or if commit_footer_contract conflicts with git_constraint; do not stop for unavailable optional trailers"
    rendering: "Render every included trailer as '{token}: {value}' in ascending order across required_trailers and optional_trailers. Render the commit trailer block as contiguous lines with no blank lines between trailers. Do not include separate rendered footer lines in this payload."
    required_trailers:
      - order: 10
        token: "Co-authored-by"
        value: "Constructor Studio <291158726+constructor-studio[bot]@users.noreply.github.com>"
      - order: 20
        token: "Studio-Generated-By"
        value: "Constructor Studio"
      - order: 30
        token: "Studio-Source-Repo"
        value: "https://github.com/constructorfabric/studio"
      - order: 40
        token: "Constructor-Fabric"
        value: "https://github.com/constructorfabric"
    optional_trailers:
      - order: 50
        token: "Studio-Version"
        source: "semver tokens extracted from cfs --version"
        include_when: "command succeeds and at least one Studio skill or CLI/package semver is found"
        value_policy: "use only semver values for Studio skill and CLI/package, formatted as comma-separated key=value pairs such as skill=1.0.1, cli=0.2.0; strip a leading v; omit this trailer when no semver is found; do not include raw cfs --version output"
      - order: 60
        token: "Studio-Workflows"
        source: "known workflow identifiers for the current Studio run"
        include_when: "known non-empty"
        value_policy: "comma-separated stable identifiers"
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
