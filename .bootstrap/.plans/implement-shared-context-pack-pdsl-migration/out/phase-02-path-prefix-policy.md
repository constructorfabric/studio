# Phase 02 Path Prefix Policy

## Purpose

This document classifies prompt-asset path families, the controller-only load
surfaces that may read them from disk, and the runtime resource paths that
remain legal for ordinary task execution.

## Core Policy

- Prompt-consuming sub-agents must not use path references as self-bootstrap
  instructions for prompt assets.
- Controller surfaces that still perform prompt-asset loads must use runtime
  `{cf-studio-path}`-prefixed references when a runtime mirror exists.
- Canonical source paths may appear in specs or migration notes, but not as
  imperative prompt-load steps for prompt-consuming sub-agents.
- Non-prompt task resources remain ordinary runtime inputs and are outside the
  shared-context-pack prohibition set.

## Path Family Classification

| Path family | Classification | Allowed disk-loader roles | Consumer rule |
| --- | --- | --- | --- |
| `workflows/**/*.md` | Core prompt assets | Top-level orchestrator, dedicated prompt-pack builder | Prompt-consuming sub-agents receive the workflow instructions they need through `prompt_context_view`; they do not reopen workflow files. |
| `skills/studio/{SKILL.md,protocol.md,routing.md,sub-agent-dispatch.md,migrate-from-cypilot.md}` | Core prompt assets | Top-level orchestrator, dedicated prompt-pack builder | Leaf prompt consumers must not open these files directly. |
| `skills/studio/agents/**/*.md` | Agent prompt assets | Top-level orchestrator, dedicated prompt-pack builder | Agents do not self-bootstrap from sibling or parent prompt files. |
| `requirements/**/*.md` | Core prompt assets | Top-level orchestrator, dedicated prompt-pack builder | Read from disk only to populate the pack; later consumers use semantic asset selection. |
| Prompt-bearing `architecture/specs/**/*.md` | Core prompt assets when used as instructions | Top-level orchestrator, dedicated prompt-pack builder | Specs may remain resource material when they are the analysis target, but they are prompt assets when loaded as agent instructions. |
| `AGENTS.md` and runtime AGENTS mirrors | Prompt assets | Top-level orchestrator, dedicated prompt-pack builder, bootstrap/runtime controller | Prompt-consuming sub-agents must not open AGENTS surfaces directly. |
| Runtime skill chain under `{cf-studio-path}/.gen/**` and `{cf-studio-path}/config/**` | Runtime prompt assets | Bootstrap/runtime controller, top-level orchestrator, dedicated prompt-pack builder | Runtime mirrors are controller surfaces, not leaf prompt-consumer inputs. |
| Kit prompt assets under `{cf-studio-path}/config/kits/**` | Kit prompt assets | Bootstrap/runtime controller, top-level orchestrator, dedicated prompt-pack builder | Kits enter the session pack as first-class assets with `origin = "kit"`; leaf agents do not read kit prompt files directly. |
| `skills/studio/agents.toml` | Registry metadata, not a prompt asset | Any workflow that needs registry metadata | Safe to read as metadata, but not a prompt body and not a substitute for `prompt_context_view`. |
| `.bootstrap/.plans/**/out/*.md` | Runtime task resources | Any contract that explicitly names them | These are execution-time artifacts between phases, not prompt assets. |
| Source code, target docs, artifacts under review, manifests, diffs | Runtime task resources | Any contract that explicitly names them | These remain ordinary task inputs outside the shared context pack. |

## Prefix Normalization Rules

### When A Runtime Mirror Exists

- Use `{cf-studio-path}/.core/...` for mirrored core prompt assets loaded by a
  controller at runtime.
- Use `{cf-studio-path}/config/...` or `{cf-studio-path}/.gen/...` for runtime
  prompt surfaces owned by bootstrap/config generation.
- Use `{cf-studio-path}/config/kits/...` for runtime kit prompt assets.

### When No Runtime Mirror Exists

- A canonical source path may be named in documentation, inventories, or
  planning artifacts.
- A prompt-consuming contract still may not use that source path as an
  imperative file-open instruction.
- If a controller truly needs that prompt asset at runtime, later migration
  phases should either introduce the correct runtime mirror or route the load
  through an existing controller-safe path.

## Explicit Exceptions

The following exception class is allowed:

- controller-owned prompt discovery and pack construction

The following exception classes are not allowed:

- leaf agents reading prompt assets because the controller omitted them
- read-only reviewer agents reopening prompt files to compensate for missing
  prompt context
- write-capable agents treating write permission as prompt-loader permission
