---
name: cf
aliases: [cf-studio, cf-init, cf-enable]
description: Invoke when user asks to initiate a Constructor Studio session and loads the core rules.
---

# cf / cf-studio — Constructor Studio Session Initiator

`cf` (and `cf-studio`) initializes the Constructor Studio session, loads the
core rules in this file, and routes to cf-* workflows. Task-specific rules live
in conditional modules and MUST be loaded by `ConditionalModuleLoading` before
their behavior is used.

```pdsl
UNIT SessionInit
PURPOSE: Establish cf/cf-studio as the session initiator that only loads core rules and routes.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
WHEN:
  REQUIRE activation of cf OR activation of cf-studio
DO:
  RESOLVE {cf-studio-path} from the in-context `@cf:root-agents` rule (fallback: its block in the project-root `AGENTS.md`); never via {cfs_cmd}
  REQUIRE {cf-studio-path} is resolved before CommandResolution and before any LOAD below, since CommandResolution's fallback path depends on {cf-studio-path}
  RUN CommandResolution to resolve {cfs_cmd}
  LOAD and REMEMBER rules from {cf-studio-path}/.gen/AGENTS.md
  LOAD and REMEMBER rules from {cf-studio-path}/config/AGENTS.md WHEN that file exists; SKIP it without error WHEN it is absent
  LOAD and REMEMBER rules from {cf-studio-path}/config/SKILL.md WHEN that file exists; SKIP it without error WHEN it is absent
  LOAD and REMEMBER rules from {cf-studio-path}/.core/requirements/pdsl-execution-card.md
  LOAD and REMEMBER core UNIT rules defined in this file, including ConditionalModuleLoading
  SET CFS_INIT = true
  RUN CliCapabilities to discover and remember the available {cfs_cmd} commands
  EMIT a load report naming loaded always-on sources, then EMIT a conditional-module report that lists every module path in ConditionalModuleLoading and the trigger that will load it before use
  CONTINUE IntentRouting
RULES:
  ALWAYS treat cf and cf-studio as the same skill, where cf-studio is a proxy alias to cf
  ALWAYS limit cf/cf-studio to initiating the session, loading core rules, and routing
  ALWAYS run CommandResolution then CliCapabilities on every cf/cf-studio activation, before routing
  ALWAYS load the {cf-studio-path}/.gen/AGENTS.md rule source as mandatory
  ALWAYS treat the {cf-studio-path}/config/AGENTS.md and {cf-studio-path}/config/SKILL.md rule sources as optional, loading each when it exists and skipping it without error when it is absent
  ALWAYS report the loaded always-on rule sources and confirm conditional modules are enforced before routing
  ALWAYS include the conditional-module trigger table in the cf load report so the user can see which modules will be loaded when their conditions fire
NOTES:
  Loading {cf-studio-path}/.core/requirements/pdsl-execution-card.md here is intentional: per the PDSL spec the root studio SKILL owns loading that runtime semantics card once into the shared context pack; the agent already executes PDSL from inherent understanding, and the card reinforces it. This is not a circular dependency.
```

```pdsl
UNIT ConditionalModuleLoading
PURPOSE: Fail closed for all optional rule modules so task-specific instructions are never skipped.
RULES:
  ALWAYS load and follow the module named by this table before executing the matching behavior
  ALWAYS STOP_TURN with the missing module path when a required conditional module cannot be loaded
  ALWAYS load the module rather than skip it when the trigger may apply and cannot be disproved from the current intent/state
  NEVER move a rule out of this root skill unless its trigger can be expressed as one stable BEFORE/WHEN rule in this table
  BEFORE companion skill grouping or multi-skill recommendation -> LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md
  BEFORE any creative or ambiguous what/how task -> LOAD {cf-studio-path}/.core/skills/studio/modules/gates/creative-brainstorm-offer.md
  WHEN intent is cypilot migration -> LOAD {cf-studio-path}/.core/skills/studio/modules/gates/migrate-from-cypilot-offer.md
  BEFORE producing document, guide, report, README, onboarding, training, or explanatory write-up content -> LOAD {cf-studio-path}/.core/skills/studio/modules/gates/language-complexity.md
  BEFORE substantive multi-step task work when no accepted plan is already active -> LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md
  BEFORE choosing or launching cf-* sub-agents -> LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/dispatch.md
  BEFORE any cf workflow, main session, or sub-agent invokes git or prepares git policy -> LOAD {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  WHEN an unknown `{...}` template variable is encountered -> LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  BEFORE any review operation emits findings -> LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md
  BEFORE applying fixes from review findings -> LOAD {cf-studio-path}/.core/skills/studio/modules/review/fix-approval.md
  BEFORE returning control to the user after task completion -> LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  WHEN user intent unambiguously requests disabling/shutdown of Studio -> LOAD {cf-studio-path}/.core/skills/studio/modules/session/shutdown.md
```

```pdsl
UNIT IntentRouting
PURPOSE: After cf loads core rules, resolve the available cf-* skills via WorkflowResolution and route by intent, showing all workflows first when no intent is known.
WHEN:
  REQUIRE cf has loaded core rules
DO:
  RUN WorkflowResolution to resolve the available cf-* skills
  EMIT_MENU IntentSkillMenu WHEN the prompt contains no task intent
  LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md WHEN the prompt contains a task intent that spans more than one cf-* domain
  RUN matching of the intent against the resolved cf-* skill list to find relevant skill(s) and any loaded compatible companion groups WHEN the prompt contains a task intent
  EMIT_MENU MatchedIntentSkillMenu WHEN the prompt contains a task intent
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS resolve the available cf-* skills via WorkflowResolution before populating IntentSkillMenu
  ALWAYS render IntentSkillMenu with every offered cf-* skill on its own numbered line so the user selects one by replying with the number
  ALWAYS for activation-only cf, show all available workflows first and include a `describe intent / help me choose` option before asking for intent or entering explore, brainstorm, plan, or any substantive workflow gate
  ALWAYS when the user replies with free text instead of a listed workflow number, treat that reply as ORIGINAL_INTENT, run matching, and emit MatchedIntentSkillMenu
  ALWAYS populate MatchedIntentSkillMenu with relevant single skills and loaded compatible companion groups, tagging exactly one option `(suggested)`, when the prompt contains a task intent
  NEVER tag a skill (suggested) when the prompt contains no task intent
  ALWAYS allow multi-select replies for compatible companion skills, formatted as comma-separated menu numbers, and invoke selected skills sequentially so each selected skill loads its prerequisites and gates in order
  NEVER let multi-select bypass any selected skill's WAIT, STOP_TURN, approval, brainstorm, plan, validation, or sub-agent gate
MENU IntentSkillMenu
TITLE: Pick a cf-* workflow by number, or choose describe intent / help me choose so I can match the right workflow(s).
OPTIONS:
  1 skill -> INVOKE the selected cf-* skill with no intent so the skill prompts for its own input
  2 describe-intent | help-me-choose -> CONTINUE IntentDescribeCapture
  3 none -> STOP_TURN
  INVALID -> treat non-empty free text as ORIGINAL_INTENT, load companion-skills module when the text spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu; otherwise EMIT_MENU IntentSkillMenu
MENU MatchedIntentSkillMenu
TITLE: Matched cf-* workflow(s) for your intent — pick one, or pick a loaded companion group / comma-separated skills when the task spans domains.
OPTIONS:
  1 skill -> INVOKE the selected cf-* skill, passing ORIGINAL_INTENT
  2 companion-group -> INVOKE each listed companion cf-* skill sequentially, passing ORIGINAL_INTENT and preserving every selected skill's prerequisites and gates
  3 other -> CONTINUE IntentAllSkillsMenu
  4 none -> STOP_TURN
  INVALID -> EMIT_MENU MatchedIntentSkillMenu
NOTES:
  The activation-only menu enumerates every available cf-* skill as `N <skill-name> — <what it does>`, includes `describe intent / help me choose`, and appends `none`. The matched menu enumerates matched skills or loaded companion groups as `N <skill-or-group> — <why it matches>`, tags exactly one `(suggested)`, allows comma-separated compatible multi-select, and appends `none`.
```

```pdsl
UNIT IntentDescribeCapture
PURPOSE: Capture free-text intent after activation-only cf without falling through the current turn.
DO:
  EMIT "Describe what you want to do. I will match the relevant cf-* workflow(s), including companion skills when the task spans domains."
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS on the resumed reply set ORIGINAL_INTENT = user.reply, load companion-skills module when the reply spans domains, run matching, EMIT_MENU MatchedIntentSkillMenu, WAIT user.reply, and STOP_TURN
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
  1 skill -> INVOKE the selected cf-* skill, passing ORIGINAL_INTENT when present else load only
  2 companion-selection -> LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, then INVOKE each selected compatible cf-* skill sequentially, passing ORIGINAL_INTENT when present else load only
  3 none -> STOP_TURN
  INVALID -> treat non-empty free text as ORIGINAL_INTENT, load companion-skills module when the text spans domains, run matching, and EMIT_MENU MatchedIntentSkillMenu; otherwise EMIT_MENU AllCfSkillsMenu
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
