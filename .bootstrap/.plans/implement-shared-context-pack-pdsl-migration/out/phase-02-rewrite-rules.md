# Phase 02 Rewrite Rules

## Purpose

This document is the canonical rewrite policy for migrating Constructor Studio
prompt assets into the shared-context-pack model without changing behavior.
Later phases must follow these rules when they rewrite workflows, skills,
requirements, specs, and agent prompt files.

## Rule Set

### 1. Separate Prompt Assets From Task Resources

- Treat a file as a prompt asset when its primary role is to instruct agent
  behavior, routing, review criteria, validation, or methodology.
- Treat a file as a task resource when its primary role is target content to be
  analyzed, transformed, validated, or reported on.
- If a file mixes both, extract only the prompt-bearing sections into the
  shared context pack and keep the full file in ordinary runtime inputs.
- Never place source code, plan artifacts, user deliverables, PR diffs, or
  other task content into `SHARED_CONTEXT_PACK`.

### 2. Loader Authority Is Limited To Controllers

- Only a top-level orchestrator, a dedicated shared-context-pack builder, or
  another explicitly designated top-level controller may load prompt assets
  from disk.
- Prompt-consuming sub-agents must receive prompt material only through
  `prompt_context_view`.
- Missing prompt context is an orchestration defect, not a license for a
  sub-agent to read prompt files directly.

### 3. Forbidden Direct-Load Patterns

The following are migration defects when they appear in prompt-consuming
sub-agents:

- Direct opens of `SKILL.md` surfaces
- Direct opens of `workflows/**/*.md`
- Direct opens of `requirements/**/*.md`
- Direct opens of prompt-bearing `architecture/specs/**/*.md`
- Direct opens of `AGENTS.md` surfaces
- Direct opens of sysprompt files
- Direct opens of kit prompt assets

These paths may still be named when:

- documenting forbidden examples
- documenting orchestrator-only exceptions
- classifying a path family in policy/spec text

### 4. Preserve Behavior During PDSL Normalization

- Preserve the current behavior before compacting wording.
- Rewrite executable behavior into explicit PDSL blocks.
- Keep rationale, migration notes, and background in `NOTES` or prose sections.
- Preserve every approval gate, stop point, write boundary, dispatch rule,
  invalid-input path, and state reset.
- Never drop `MUST`, `ALWAYS`, `NEVER`, `FORBID`, `REQUIRE`, `STOP_TURN`, or
  explicit failure semantics during compaction.
- Use `ON_ERROR` whenever failure handling changes control flow.

### 5. Family-Specific Rewrite Requirements

| Family | Target form | Required migration result |
| --- | --- | --- |
| Top-level orchestrator workflows | PDSL controller contracts | Keep controller-owned disk loads, but route them through session pack construction and `prompt_context_view` generation. |
| Workflow fragments used only by orchestrators | PDSL controller contracts | Convert root-relative prompt loads to controller-safe references and remove ad hoc prompt reload wording. |
| Prompt-consuming agent contracts | PDSL consumer contracts | Replace direct prompt-load instructions with semantic `prompt_context_requirements` plus a hard rule that `prompt_context_view` is the sole prompt source. |
| Shared runtime skill/bootstrap surfaces | Controller/runtime exceptions | Preserve only the minimal controller bootstrap needed to discover, load, and hand off prompt assets; do not turn runtime mirrors into canonical authoring targets unless a phase explicitly requires it. |
| Requirements corpus | PDSL-compatible prompt assets | Keep checklist or methodology prose when it is reference content, but move executable gating behavior, menus, state, and failure handling into PDSL blocks during migration. |
| Prompt-bearing specs | PDSL-compatible prompt assets | Keep reference/spec prose when it defines concepts or schemas, but express executable operating rules, menus, states, and authority boundaries in explicit PDSL blocks when those rules are consumed as instructions. |

### 6. Path Normalization Rules

- Imperative prompt-load references that remain in controller surfaces must use
  runtime `{cf-studio-path}`-prefixed references.
- Canonical source paths may be discussed in specs, inventories, and migration
  notes, but prompt-consuming contracts must not use them as self-bootstrap
  instructions.
- When a canonical prompt asset has a runtime mirror under `.bootstrap`,
  controller surfaces should load the runtime path and publish the result into
  the shared context pack.
- `agents.toml` remains registry metadata, not a prompt asset; migration work
  may extend it with prompt-context declarations, but it is not itself a
  prompt body.

### 7. Shared Context Pack Invariants

- `SHARED_CONTEXT_PACK` stays session-scoped.
- Assets are reused and incrementally enriched across workflow runs in the same
  chat session.
- Asset freshness remains `etag`-based.
- Asset origin semantics remain `core`, `kit`, or `project`.
- Kit prompt assets remain first-class shared-context-pack assets rather than
  ad hoc disk reads inside sub-agents.

## Current Self-Migration Gaps

The current PDSL toolchain is itself a migration target. Later phases must
remove these defects without changing user-visible behavior:

- `workflows/pdsl.md` still mixes `{cf-studio-path}`-prefixed loads with
  root-relative prompt loads for protocol, stop-token policy, and mode files.
- `skills/studio/agents/cf-pdsl-author.md`,
  `skills/studio/agents/cf-pdsl-transformer.md`, and
  `skills/studio/agents/cf-pdsl-reviewer.md` still instruct direct prompt reads
  of `SKILL.md` and `architecture/specs/PDSL.md`.
- `skills/studio/agents.toml` currently has no
  `prompt_context_requirements` declarations.

## Enforcement Summary

Later phases must treat a rewrite as incomplete if any migrated
prompt-consuming contract still:

- tells itself to open prompt assets from disk
- lacks semantic prompt-context requirements
- blurs prompt assets with task resources
- removes approval or failure semantics while compacting to PDSL
