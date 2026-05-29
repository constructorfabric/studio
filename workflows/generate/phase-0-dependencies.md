---
name: generate-phase-0-dependencies
description: "Invoke when the generate workflow enters dependency resolution after `{cf-studio-path}/.core/skills/studio/protocol.md` — ensures kit deps, capability probe, CONTRIBUTING discovery, and raw-input overflow rule."
purpose: Generate Phase 0 — ensure dependencies, capability probe, CONTRIBUTING discovery, raw-input overflow rule
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 0: Ensure Dependencies](#phase-0-ensure-dependencies)

<!-- /toc -->

## Phase 0: Ensure Dependencies

```text
UNIT GeneratePhase0Dependencies

PURPOSE:
  After `{cf-studio-path}/.core/skills/studio/protocol.md`, resolve kit deps, sub-agent approval, CONTRIBUTING discovery,
  raw-input overflow rule, and panel mode flags before Phase 1.

DO:
  REQUIRE KITS_PATH, phase-appropriate dependency set, and REQUIREMENTS are known
    from `{cf-studio-path}/.core/skills/studio/protocol.md`
  NOTE: {cfs_cmd}, {cf-studio-path}, {project_root} resolved by `{cf-studio-path}/.core/skills/studio/protocol.md`;
        on context loss re-run `{cfs_cmd} --json info` before any path-dependent step
  LOAD {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
    (evaluates SKILL.md § Session Sub-Agent Approval Gate; assigns INLINE_FALLBACK)
  REQUIRE inline-fallback-probe completes before Phase 1 and before any sub-agent dispatch

RULES:
  - MUST NOT proceed to Phase 1 until all generation-phase dependencies
    required for the current target are available

MENU DependencyResolution:
  TITLE: Dependency resolution routing (machine reference)
  OPTIONS:
    rules.md loaded ->
      NOTE: Phase-appropriate dependencies already resolved; proceed silently.
      CONTINUE Phase1
    rules.md not loaded ->
      EMIT prompt asking user to provide/specify the generation-phase dependencies needed now
      NOTE: request checklist only when current phase or rules explicitly require it
      WAIT user.reply
      CONTINUE Phase1
    code_mode_additional ->
      EMIT prompt asking user to specify the design artifact if missing
      IF current rules explicitly require implementation-time checklist guidance:
        LOAD {cf-studio-path}/.core/requirements/code-checklist.md
      ELSE:
        NOTE: defer checklist to Phase 5 review
      CONTINUE Phase1
```

### CONTRIBUTING Guide Discovery (runs unconditionally — every generate run)

```text
UNIT ContributingGuideDiscovery

PURPOSE:
  Search for and store CONTRIBUTING_GUIDE before any write-capable sub-agent dispatch.

DO:
  Search in order; stop at first match:
    1. {project_root}/CONTRIBUTING.md or {project_root}/CONTRIBUTING
    2. {project_root}/.github/CONTRIBUTING.md
    3. {project_root}/docs/CONTRIBUTING.md
    4. {project_root}/CONTRIBUTING.rst or {project_root}/CONTRIBUTING.txt
  IF found:
    SET CONTRIBUTING_GUIDE = { "path": "<absolute path>", "directives": "<key directives summary>" }
    Load file subject to ~200-line cap; if longer, read first 200 lines and summarize
    commit-message format, branch-naming conventions, PR-template requirements into directives;
    drop full body from context
  IF not found:
    SET CONTRIBUTING_GUIDE = null

RULES:
  - MUST run unconditionally — independent of GIT_COMMIT_MODE
  - MUST NOT skip even when GIT_COMMIT_MODE=none

NOTES:
  Discovery informs non-commit concerns (style, branch naming, PR templates)
  as well as commit constraints when GIT_COMMIT_MODE=commit.
```

### Raw-Input Overflow Rule

```text
UNIT RawInputOverflowRule

PURPOSE:
  Enforce plan-escalation offer when direct user prompt plus all provided files
  exceeds 500 total lines.

DO:
  LOAD {cf-studio-path}/.core/requirements/raw-input-overflow.md
  IF (user_prompt_lines + all_provided_file_lines) > 500:
    STOP direct generation
    EMIT offer: /cf-plan vs continue here with reduced guarantees
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST stop and offer /cf-plan when input exceeds 500 lines
  - MUST follow raw-input-overflow.md exactly as specified in that file
```

### Panel Mode Flags (session-scoped, defaults single-agent)

```text
UNIT PanelModeFlags

PURPOSE:
  Initialize session-scoped panel mode flags for brainstorm orchestration.

STATE:
  PANEL_MODE_TOPIC: single-agent | fan-out
    default: single-agent
    scope: session
  PANEL_MODE_CHALLENGE: single-agent | fan-out
    default: single-agent
    scope: session

DO:
  READ env CFS_PANEL_MODE_TOPIC -> SET state.run_config.PANEL_MODE_TOPIC
  READ env CFS_PANEL_MODE_CHALLENGE -> SET state.run_config.PANEL_MODE_CHALLENGE

RULES:
  - MUST apply PANEL_MODE_TOPIC and PANEL_MODE_CHALLENGE independently
  - MUST read env vars at Phase 0.7 brainstorm start
  - MUST apply for the lifetime of the session

NOTES:
  PANEL_MODE_TOPIC: orchestration for topic rounds; single-agent = one
  cf-brainstorm-panel dispatch per round; fan-out = parallel per-expert dispatch
  via cf-brainstorm-expert.
  PANEL_MODE_CHALLENGE: same semantics, independently switchable.
  Single-agent mode is inherently sequential; INLINE_FALLBACK degradation is a
  no-op for it.
  Override env vars: CFS_PANEL_MODE_TOPIC and CFS_PANEL_MODE_CHALLENGE
  (each accepts single-agent or fan-out).
```
