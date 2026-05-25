---
description: "Invoke when loading Constructor Studio Protocol Guard, CLI resolution, logging, language, and write-confirmation rules."
---

# Constructor Studio Protocol

```text
UNIT CliResolution

PURPOSE:
  Resolve the CLI command reference before any workflow work begins.

DO:
  1. WHEN cfs is available on PATH
       SET {cfs_cmd} = cfs
  2. WHEN cfs is NOT available
       SET {cfs_cmd} = python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py

RULES:
  - MUST resolve {cfs_cmd} before any CLI invocation
  - MUST use {cfs_cmd} for all subsequent CLI invocations in the session
```

```text
UNIT ExecutionVisibility

PURPOSE:
  Produce consistent execution-visibility log entries whenever entering
  Constructor Studio prompt sections or completing checklist tasks.

RULES:
  - MUST emit a log line in the format:  - [CONTEXT]: MESSAGE
    when entering any Constructor Studio prompt section
  - MUST emit a log line in the format:  - [CONTEXT]: MESSAGE
    when completing any checklist task
```

```text
UNIT ProtocolGuard

PURPOSE:
  Load all project configuration and specs before workflow work begins.

DO:
  1. Run {cfs_cmd} --json info
  2. Store the returned variables map
  3. WHEN {cf-studio-path}/.gen/AGENTS.md exists
       open and follow {cf-studio-path}/.gen/AGENTS.md
  4. WHEN {cf-studio-path}/config/AGENTS.md exists
       open and follow {cf-studio-path}/config/AGENTS.md
  5. WHEN {cf-studio-path}/.gen/SKILL.md exists
       open and follow {cf-studio-path}/.gen/SKILL.md
  6. WHEN {cf-studio-path}/config/SKILL.md exists
       open and follow {cf-studio-path}/config/SKILL.md
  7. Resolve registry, intent, target, rules, and matched WHEN-clause specs
  8. Open and follow {cf-studio-path}/.core/requirements/language-complexity.md

RULES:
  - MUST execute steps 1-8 in order before any workflow work
  - MUST store the variables map returned by step 1 for later substitution
```

```text
UNIT ConstructorStudioContextBlock

PURPOSE:
  Emit the required context header before any code edit.

DO:
  REQUIRE ProtocolGuard has completed
  EMIT:
    Constructor Studio Context:
    - Constructor Studio: {path}
    - Target: {artifact|codebase}
    - Specs loaded: {list paths or "none required"}

RULES:
  - MUST emit this block before every code edit
```

```text
UNIT AgentSafeInvocation

PURPOSE:
  Constrain all CLI invocations to agent-safe patterns and enforce the
  dual write-confirmation + phase-gate requirement.

STATE:
  CF_PHASE_GATE: armed | released_for_dispatch | released_for_inline_write
    default: armed
    reset: start_of_assistant_turn

  write_confirmation_obtained: unset | true
    default: unset
    scope: per_write_command

RULES:
  - MUST use {cfs_cmd} --json <subcommand> for all CLI invocations
    EXCEPT init, delegate, and update (run those without --json)
  - MUST obtain explicit user confirmation before any write-capable command
  - MUST_NOT add --yes, -y, or --force to any command
    unless the user explicitly requested it
  - MUST_NOT execute a write-capable command unless BOTH conditions hold:
      CF_PHASE_GATE is in a released_for_* state
      AND write_confirmation_obtained == true
  - MUST_NOT treat gate-release as a substitute for write confirmation;
    both are independently required

INVARIANTS:
  - MUST keep CF_PHASE_GATE = armed outside released write windows
  - MUST_NOT write files while CF_PHASE_GATE == armed
  - MUST_NOT write files while write_confirmation_obtained != true

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
  TITLE: Confirm write-capable command
  OPTIONS:
    1 -> SET write_confirmation_obtained = true
         CONTINUE AgentSafeInvocation
    2 -> EMIT "Write cancelled."
         STOP_TURN
  INVALID:
    EMIT "Reply with 1 to confirm or 2 to cancel."
    WAIT user.reply
    STOP_TURN
```
