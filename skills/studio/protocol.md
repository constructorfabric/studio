---
description: "Invoke when loading Constructor Studio Protocol Guard, CLI resolution, logging, language, and write-confirmation rules."
---

# Constructor Studio Protocol

```pdsl
UNIT CliResolution

PURPOSE:
  Resolve the CLI command reference before any workflow work begins.

DO:
  - RUN WHEN cfs is available on PATH
       - SET {cfs_cmd} = cfs
  - RUN WHEN cfs is NOT available
       - SET {cfs_cmd} = python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py

RULES:
  - ALWAYS resolve {cfs_cmd} before any CLI invocation
  - ALWAYS use {cfs_cmd} for all subsequent CLI invocations in the session
```

```pdsl
UNIT ExecutionVisibility

PURPOSE:
  Produce consistent execution-visibility log entries whenever entering
  Constructor Studio prompt sections or completing checklist tasks.

RULES:
  - ALWAYS emit a log line in the format:  - [CONTEXT]: MESSAGE
    when entering any Constructor Studio prompt section
  - ALWAYS emit a log line in the format:  - [CONTEXT]: MESSAGE
    when completing any checklist task
```

```pdsl
UNIT ProtocolGuard

PURPOSE:
  Resolve all project configuration and controller-owned prompt assets before
  workflow work begins.

DO:
  - RUN Run {cfs_cmd} --json info
  - RUN Store the returned variables map
  - RUN WHEN {cf-studio-path}/.gen/AGENTS.md exists
       load or reuse it as a controller-owned SHARED_CONTEXT_PACK asset, then
       follow only the instruction slice selected for the top-level controller
  - RUN WHEN {cf-studio-path}/config/AGENTS.md exists
       load or reuse it as a controller-owned SHARED_CONTEXT_PACK asset, then
       follow only the instruction slice selected for the top-level controller
  - RUN WHEN {cf-studio-path}/.gen/SKILL.md exists
       load or reuse it as a controller-owned SHARED_CONTEXT_PACK asset, then
       follow only the instruction slice selected for the top-level controller
  - RUN WHEN {cf-studio-path}/config/SKILL.md exists
       load or reuse it as a controller-owned SHARED_CONTEXT_PACK asset, then
       follow only the instruction slice selected for the top-level controller
  - RUN Resolve registry, intent, target, rules, and matched WHEN-clause specs
  - RUN Load or reuse {cf-studio-path}/.core/requirements/language-complexity.md
     as a controller-owned SHARED_CONTEXT_PACK asset and follow the selected
     top-level controller slice

RULES:
  - ALWAYS execute steps 1-8 in order before any workflow work
  - ALWAYS store the variables map returned by step 1 for later substitution
  - NEVER instruct prompt-consuming sub-agents to reopen any ProtocolGuard
    prompt asset from disk; dispatches receive needed text via prompt_context_view
```

```pdsl
UNIT SharedContextPackProtocol

PURPOSE:
  Treat runtime instruction surfaces loaded during Protocol Guard as
  controller-owned prompt assets that populate or refresh the shared context
  pack before any downstream dispatch.

DO:
  - LOAD {cf-studio-path}/.core/workflows/shared/shared-context-pack-ownership.md
  - CONTINUE SharedContextPackOwnership

RULES:
  - ALWAYS ProtocolGuard resolves {cf-studio-path}/.gen/AGENTS.md,
    {cf-studio-path}/config/AGENTS.md, {cf-studio-path}/.gen/SKILL.md,
    {cf-studio-path}/config/SKILL.md, and
    {cf-studio-path}/.core/requirements/language-complexity.md on behalf of
    the top-level runtime controller only
  - ALWAYS The controller ALWAYS reuse matching SHARED_CONTEXT_PACK assets before
    re-reading disk, revalidate reused assets by etag, and refresh or replace
    stale assets before reuse
  - ALWAYS Mixed-content runtime assets loaded here ALWAYS contribute only their
    instruction-bearing sections to SHARED_CONTEXT_PACK
  - ALWAYS Missing or stale prompt assets that cannot be refreshed ALWAYS surface
    a deterministic controller-owned error before downstream dispatch
  - ALWAYS ExecutionVisibility logging ALWAYS include whether the controller
    reused, refreshed, or extended SHARED_CONTEXT_PACK during Protocol Guard
```

```pdsl
UNIT ConstructorStudioContextBlock

PURPOSE:
  Emit the required context header before any code edit.

DO:
  - REQUIRE ProtocolGuard has completed
  - EMIT:
    Constructor Studio Context:
    - Constructor Studio: {path}
    - Target: {artifact|codebase}
    - Specs loaded: {list paths or "none required"}

RULES:
  - ALWAYS emit this block before every code edit
```

```pdsl
UNIT AgentSafeInvocation

PURPOSE:
  Constrain all CLI invocations to agent-safe patterns and enforce the
  dual write-confirmation + phase-gate requirement.

STATE:
  - SET CF_PHASE_GATE:
    armed
    | released_for_dispatch
    | released_for_orchestrator_write
    | released_for_inline_write
    | user_bypass
    default: armed
    reset: per canonical PhaseSkipGate rules in SKILL.md

  - SET write_confirmation_obtained: unset | true
    default: unset
    scope: per_write_command

  - SET write_command:
    exact command or file-write operation being approved

  - SET write_target:
    exact target path, resource, or configuration key being changed

  - SET write_effect:
    concrete side effect, including created/modified files or external writes

RULES:
  - ALWAYS preserve the canonical CF_PHASE_GATE model and reset semantics from
    {cf-studio-path}/.core/skills/studio/SKILL.md
  - ALWAYS use {cfs_cmd} --json <subcommand> for all CLI invocations
    EXCEPT init, delegate, and update (run those without --json)
  - ALWAYS obtain explicit user confirmation before any write-capable command
  - ALWAYS populate write_command, write_target, and write_effect before emitting
    WriteConfirmationMenu
  - NEVER add --yes, -y, or --force to any command
    unless the user explicitly requested it
  - NEVER execute a write-capable command unless BOTH conditions hold:
      CF_PHASE_GATE is in a released_for_* state
      AND write_confirmation_obtained == true
  - NEVER treat gate-release as a substitute for write confirmation;
    both are independently required

INVARIANTS:
  - ALWAYS keep this unit aligned with the canonical Phase-Skip Gate model in
    SKILL.md and ALWAYS treat only released_for_* states as write-eligible here
  - NEVER write files while CF_PHASE_GATE == armed
  - NEVER write files while write_confirmation_obtained != true

ON_ERROR:
  write_attempted_while_gate_armed ->
    SET CF_PHASE_GATE = armed
    EMIT "Write blocked: Phase-Skip Gate is not released. Obtain gate release and explicit confirmation before retrying."
    STOP_TURN

  write_attempted_without_confirmation ->
    EMIT "Write blocked: explicit user confirmation is required before any write-capable command."
    EMIT_MENU WriteConfirmationMenu
    WAIT user.reply
    STOP_TURN

MENU WriteConfirmationMenu:
  TITLE: |
    Confirm write-capable action.

    Command/action: {write_command}
    Target: {write_target}
    Effect: {write_effect}
    Consequence:
      - Reply 1: run exactly this action against this target and apply the effect above.
      - Reply 2: do not run the action; no write is performed.

    Reply with exactly one number: 1 to approve this exact action, or 2 to cancel.
  OPTIONS:
    1 -> SET write_confirmation_obtained = true
         CONTINUE AgentSafeInvocation
    2 -> EMIT "Write cancelled."
         STOP_TURN
  INVALID:
    EMIT "Reply with exactly one number: 1 to confirm or 2 to cancel."
    WAIT user.reply
    STOP_TURN
```
