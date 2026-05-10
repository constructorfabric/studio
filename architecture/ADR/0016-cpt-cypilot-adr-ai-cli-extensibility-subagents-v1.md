---
status: accepted
date: 2026-03-17
decision-makers: project maintainer
---

# ADR-0016: Subagent Registration for AI CLI Extensibility

**ID**: `cpt-cypilot-adr-ai-cli-extensibility-subagents`

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Canonical Format: Claude Code](#canonical-format-claude-code)
  - [Claude Code Subagent Definition (Full Fidelity)](#claude-code-subagent-definition-full-fidelity)
  - [Semantic Model (`agents.toml`)](#semantic-model-agentstoml)
  - [Adaptation to Other Tools](#adaptation-to-other-tools)
  - [Example: `cf-constructor-pr-review` Across All Tools](#example-cf-constructor-pr-review-across-all-tools)
  - [Read-Only Enforcement Strategies](#read-only-enforcement-strategies)
  - [Graceful Degradation](#graceful-degradation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Generate subagent definitions](#generate-subagent-definitions)
  - [Status quo](#status-quo)
- [Hooks — Subagent-Level Only](#hooks--subagent-level-only)
- [Justification](#justification)
  - [Why Subagents](#why-subagents)
  - [Why Not Project-Level Hooks Yet](#why-not-project-level-hooks-yet)
  - [Why Not the Status Quo](#why-not-the-status-quo)
- [Maintaining the Support Matrix](#maintaining-the-support-matrix)
  - [When to update](#when-to-update)
  - [Where to update](#where-to-update)
  - [Verification](#verification)
- [More Information](#more-information)
- [Traceability](#traceability)

<!-- /toc -->

## Context and Problem Statement

Modern AI-powered CLI tools (Claude Code, Cursor, GitHub Copilot, OpenAI Codex) expose **subagent definitions** — isolated, purpose-built agent definitions that the host tool can spawn as child processes with scoped capabilities. A host agent can delegate a well-defined subtask (code generation, PR review) to a subagent that runs in its own context window with its own tool permissions, then returns a result to the parent.

Today, `cypilot agents` generates a single monolithic skill integration per tool. All Cypilot work — generation, validation, review — runs inside a single agent context with full tool access. This creates two problems:

- **Context saturation**: Long-running sessions accumulate context from unrelated subtasks (e.g., code generation context pollutes a subsequent review), degrading output quality and hitting context limits.
- **Overprivileged agents**: A PR review task has write access it does not need, violating least privilege and increasing the blast radius of agent errors.

## Decision Drivers

* **Context management** — subagents isolate subtask context from the parent conversation, preventing context window pollution and enabling the parent to orchestrate multiple independent workstreams without accumulating irrelevant state
* **Orchestration** — the parent agent can dispatch subagents concurrently (e.g., generate code in one subagent while reviewing a different PR in another), improving throughput and enabling multi-step workflows that would otherwise serialize inside a single context
* **Least privilege** — subagents can be scoped to read-only or write-only tool sets, limiting blast radius; a review agent that cannot write files cannot accidentally modify the codebase
* **Multi-tool parity** — Claude Code, Cursor, Copilot, and Codex all support subagent definitions (Windsurf does not)
* **Incremental adoption** — subagents are additive; existing single-agent skill integration continues to work unchanged; subagents layer on top

## Considered Options

1. **Generate subagent definitions** — extend `cypilot agents` to produce isolated subagent definitions alongside existing skills and workflows
2. **Status quo** — continue with the single-agent skill integration; do not generate subagents

## Decision Outcome

Chosen option: **Option 1 — Generate subagent definitions**. Subagents are standard extensibility primitives exposed by the host tools Cypilot already integrates with. Not adopting them means leaving value on the table that the host tools are explicitly designed to provide.

The `cypilot agents` command generates two purpose-built subagent definitions for each supported tool:

| Subagent | Mode | Isolation | Purpose |
|----------|------|-----------|---------|
| `cf-constructor-codegen` | read-write | worktree (Claude Code) | Fully-specified code generation tasks: the parent agent formulates a complete specification and delegates implementation to a subagent that works in an isolated copy of the repo |
| `cf-constructor-pr-review` | read-only | none | Structured checklist-based PR review: the subagent reads the diff and produces a structured review without write access |

Each subagent definition is rendered in the tool's native format (Markdown + YAML frontmatter for Claude Code/Cursor/Copilot, TOML sections for Codex). Tools that do not support subagents (Windsurf) are gracefully skipped with a reason in the JSON output.

Subagent definitions are config-driven: built-in defaults via `_default_subagents()` can be overridden through `cypilot-agents.json` or kit-level `agents.toml` files. This enables teams to define custom subagents for their domain (e.g., a `cypilot-migration` agent for database schema changes).

### Consequences

* Good, because subagents isolate subtask context — a code generation task does not pollute the parent's review context, and vice versa
* Good, because orchestration becomes possible — the parent can dispatch multiple subagents concurrently for independent workstreams
* Good, because least privilege is enforced per-subagent — `cf-constructor-pr-review` cannot write files; `cf-constructor-codegen` works in an isolated worktree
* Good, because config-driven subagent definitions enable teams to extend with domain-specific agents
* Good, because existing single-agent integration is unchanged — subagents are additive
* Neutral, because Windsurf users get no subagent support (tool limitation, not a Cypilot limitation)
* Bad, because more generated files per tool (two subagent files) increases the surface area to maintain

### Confirmation

Confirmed when:

- `cypilot agents --agent claude` generates `cf-constructor-codegen.md` and `cf-constructor-pr-review.md` in `.claude/agents/` with correct YAML frontmatter (isolation, disallowed tools)
- `cypilot agents --agent cursor` generates equivalent subagent files in `.cursor/agents/` with `readonly: true` for pr-review
- `cypilot agents --agent copilot` generates `.agent.md` files in `.github/agents/`
- `cypilot agents --agent openai` generates a single TOML with two agent sections in `.codex/agents/`
- `cypilot agents --agent windsurf` skips subagent generation with a reason in JSON output
- Re-running subagent generation is idempotent (no spurious updates)

## Canonical Format: Claude Code

Subagents are **defined once** in `agents.toml` using semantic properties and **generated for all supported tools** automatically. Claude Code has the richest subagent definition format and supports every semantic property Cypilot needs, so we treat it as the **canonical format** — the full-fidelity representation. Every other tool's output is an adaptation: same semantic content, projected into that tool's native format with graceful degradation for unsupported capabilities.

### Claude Code Subagent Definition (Full Fidelity)

A Claude Code subagent definition is a Markdown file in `.claude/agents/` with YAML frontmatter:

```yaml
---
name: cf-constructor-codegen
description: Cypilot code generator. Use when requirements are fully specified...
tools: Bash, Read, Write, Edit, Glob, Grep
model: inherit
isolation: worktree
---

ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/SKILL.md`
...
```

**Properties available in Claude Code:**

| Property | Purpose | Example |
|----------|---------|---------|
| `name` | Agent identifier | `cf-constructor-codegen` |
| `description` | When the host tool should delegate to this agent | Free text |
| `tools` | Allowed tool list (comma-separated) | `Bash, Read, Write, Edit, Glob, Grep` |
| `disallowedTools` | Denied tool list (for readonly agents) | `Write, Edit` |
| `model` | Model selection | `inherit`, `sonnet`, `haiku`, `opus` |
| `isolation` | Worktree isolation for safe parallel execution | `worktree` |
| `hooks` | Subagent-scoped hooks (frontmatter key) | See [Hooks](#hooks--subagent-level-only) |

This is the full set of capabilities. Every other tool supports a subset.

### Semantic Model (`agents.toml`)

Kit developers define agents once using abstract properties that map cleanly to Claude Code's format:

```toml
[agents.cf-constructor-codegen]
description = "Code generation with full write access"
prompt_file = "agents/cf-constructor-codegen.md"
mode = "readwrite"        # → full tool list (Claude: tools), no disallowedTools
isolation = true          # → isolation: worktree (Claude only)
model = "inherit"         # → model: inherit

[agents.cf-constructor-pr-review]
description = "Read-only PR review"
prompt_file = "agents/cf-constructor-pr-review.md"
mode = "readonly"         # → disallowedTools: Write, Edit (Claude) / readonly: true (Cursor) / filtered tool list (Copilot)
isolation = false
model = "fast"            # → model: sonnet (Claude) / model: fast (Cursor) / ignored (Copilot, Codex)
```

### Adaptation to Other Tools

Each tool's output is a lossy projection of the Claude Code canonical format. The table below shows what is preserved, what is adapted, and what is lost.

**Feature support relative to Claude Code:**

| Claude Code Property | Cursor | GitHub Copilot | OpenAI Codex | Windsurf |
|---|---|---|---|---|
| `tools` (allow list) | Adapted: own tool names (`grep, view, edit, bash`) | Adapted: JSON array (`["*"]`) | Lost: no tool scoping in TOML | N/A |
| `disallowedTools` (deny list) | Adapted: `readonly: true` flag + tool filter | Adapted: filtered allow list `["read", "search"]` | In prompt: no format-level enforcement | N/A |
| `model` | Preserved: `fast` / `inherit` | No equivalent | No equivalent | N/A |
| `isolation: worktree` | No equivalent | No equivalent | No equivalent | N/A |
| `hooks` (frontmatter) | No equivalent | No equivalent | No equivalent | N/A |
| File format | Same: Markdown + YAML | Same: Markdown + YAML (`.agent.md` ext) | Different serialization: TOML (same semantics) | N/A |
| One file per agent | Same | Same | Different: single file for all agents | N/A |

**Notable adaptation details:**

- **Cursor `readonly: true`** — Cursor has a dedicated readonly flag that Claude Code lacks. This is the one case where a target tool is *more expressive* than the canonical format. Claude Code enforces readonly via `disallowedTools`, which is a deny-list pattern. Cursor's `readonly: true` is a first-class declaration. Cypilot generates both: the `readonly` flag and a filtered tool list, providing belt-and-suspenders enforcement.

- **Copilot tool list format** — Copilot uses JSON arrays (`["*"]`, `["read", "search"]`) rather than comma-separated strings. The semantic intent is the same but the syntax differs. Copilot also uses the `.agent.md` file extension to distinguish agent files from regular markdown.

- **Codex TOML format** — OpenAI Codex uses TOML rather than Markdown+YAML, but the semantic content is equivalent: `description` maps directly, and `developer_instructions` carries the same prompt content as the Markdown body. The format difference is an abstraction — the information flows through. What Codex lacks is *format-level enforcement*: there are no TOML keys for tool scoping, model selection, or isolation. These constraints are expressed in `developer_instructions` as prompt instructions rather than as declarative metadata the host tool enforces. All agents are rendered into a single `cypilot-agents.toml` file with `[agents.cypilot_codegen]` sections (hyphens converted to underscores).

- **Windsurf** — does not support subagents at all. Subagent generation is skipped with a reason in the JSON output. Skills and workflows are still generated.

### Example: `cf-constructor-pr-review` Across All Tools

The same semantic definition (`mode: readonly`, `model: fast`, `isolation: false`) produces four different outputs:

**Claude Code** (`.claude/agents/cf-constructor-pr-review.md`):

```yaml
---
name: cf-constructor-pr-review
description: Cypilot PR reviewer...
tools: Bash, Read, Glob, Grep
disallowedTools: Write, Edit
model: sonnet
---

ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/agents/cf-constructor-pr-review.md`
```

**Cursor** (`.cursor/agents/cf-constructor-pr-review.md`):

```yaml
---
name: cf-constructor-pr-review
description: Cypilot PR reviewer...
tools: grep, view, bash
readonly: true
model: fast
---

ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/agents/cf-constructor-pr-review.md`
```

**GitHub Copilot** (`.github/agents/cf-constructor-pr-review.agent.md`):

```yaml
---
name: cf-constructor-pr-review
description: Cypilot PR reviewer...
tools: ["read", "search"]
---

ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/agents/cf-constructor-pr-review.md`
```

**OpenAI Codex** (`.codex/agents/cypilot-agents.toml`, shared with all agents):

```toml
[agents.cypilot_pr_review]
description = "Cypilot PR reviewer..."
developer_instructions = """
ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/agents/cf-constructor-pr-review.md`
"""
```

Note what changes across tools:
- **Tool names** differ (`Bash, Read` vs `grep, view` vs `["read", "search"]`)
- **Readonly mechanism** differs (deny-list vs flag vs allow-list vs prompt-only)
- **Model** is present in Claude/Cursor, absent in Copilot/Codex
- **Format** is Markdown+YAML for three tools, TOML for Codex
- **Prompt body** is identical — all tools point to the same shared agent definition file

### Read-Only Enforcement Strategies

The same semantic intent (`mode: readonly`) is expressed through four different mechanisms:

| Tool | Strategy | Mechanism |
|------|----------|-----------|
| Claude Code | Deny list | `disallowedTools: Write, Edit` — agent can use all tools except those listed |
| Cursor | Flag + allow list | `readonly: true` flag + tool list excludes `edit` |
| GitHub Copilot | Allow list only | Tool list set to `["read", "search"]` — no explicit readonly flag |
| OpenAI Codex | Prompt only | No format-level enforcement; readonly behavior is instructed in `developer_instructions` |

### Graceful Degradation

When a Claude Code property has no equivalent in a target tool:

1. **Silent omission** — the property is not emitted. The subagent works, but without that capability (e.g., no worktree isolation on Cursor — the agent runs in the main working directory).
2. **Best-effort adaptation** — the property is mapped to the closest available mechanism (e.g., Copilot enforces readonly via tool allow-list since it has no `readonly` flag or deny-list).
3. **Prompt fallback** — when the format cannot express a property at all (e.g., Codex TOML), the constraint is documented in the referenced prompt file where the agent reads its instructions.

No tool receives a property it does not understand — malformed frontmatter would cause the host tool to reject the subagent definition.

## Pros and Cons of the Options

### Generate subagent definitions

Extend `cypilot agents` to produce isolated subagent definitions alongside existing skills and workflows.

* Good, because subagents isolate subtask context — code generation does not pollute the parent's review context
* Good, because orchestration becomes possible — parent can dispatch codegen and review concurrently
* Good, because least privilege is enforced per-subagent via tool scoping
* Good, because config-driven definitions enable teams to extend with domain-specific agents
* Good, because existing single-agent integration is unchanged — subagents are additive
* Neutral, because Windsurf users get no subagent support (tool limitation)
* Bad, because more generated files per tool increases maintenance surface

### Status quo

Continue with the single-agent skill integration; do not generate subagents.

* Good, because no additional complexity or generated files
* Bad, because context saturation degrades agent quality in long sessions
* Bad, because all tasks run overprivileged with full tool access
* Bad, because host tools' native extensibility primitives go unused
* Bad, because no concurrent workflow dispatch is possible

## Hooks — Subagent-Level Only

AI CLI tools expose **hooks** — deterministic shell commands that fire on agent lifecycle events. These are powerful for enforcing validation, injecting context, and controlling agent behavior. However, this ADR scopes hook usage to **subagent-level hooks only** — hooks that fire when Cypilot subagents start or stop — and defers project-level hook generation (e.g., `PreToolUse` hooks on every file edit) to a future decision.

**Why subagent-level hooks matter**: Claude Code supports `SubagentStart` and `SubagentStop` hook events that fire when a subagent is spawned or finishes. These can inject Cypilot-specific context into a subagent at launch (e.g., which kit is active, which artifact paths to validate) without polluting the parent agent's context. GitHub Copilot has equivalent `subagentStart`/`subagentStop` events.

**What is in scope for this ADR:**

- Subagent definitions reference the correct SKILL.md and workflow entry points in their prompts — this is the primary mechanism for Cypilot-aware subagent behavior
- Tools that support subagent lifecycle hooks (Claude Code, Copilot) can use `SubagentStart` to inject additional context into Cypilot subagents at spawn time
- Subagent prompt files can declare hooks in their frontmatter (Claude Code supports this) for subagent-scoped behavior

**What is deferred:**

- Project-level `PreToolUse`/`PostToolUse` hooks that run `cpt validate` on every file edit — this requires careful design around config merging, fail-open semantics, and multi-tool format differences
- Project-level `SessionStart` hooks for injecting Cypilot context into all sessions
- A `cypilot hooks install` / `uninstall` CLI command

Project-level hooks are a natural next step after subagent registration stabilizes, and will be addressed in a separate ADR when the implementation is ready.

## Justification

### Why Subagents

Subagents are the host tool's native mechanism for **context management** and **conversation orchestration**. Without them, every Cypilot task — code generation, validation, review — runs inside a single agent context. This creates compounding problems:

* **Context saturation** — a long generation session fills the context window with implementation detail that is irrelevant to a subsequent review. The parent agent's quality degrades as unrelated context accumulates. Subagents run in their own context window and return only the result, keeping the parent's context clean.
* **Serialized workflows** — a single-agent model forces sequential execution. Subagents can run concurrently — the parent can dispatch a codegen task and a review task in parallel without one blocking the other.
* **Overprivilege** — a monolithic agent has full tool access for every task. Subagents scope tool permissions per role: `cf-constructor-pr-review` is read-only (cannot write files); `cf-constructor-codegen` uses worktree isolation (cannot modify the working tree directly). This enforces least privilege at the tool level, reducing the blast radius of agent errors.

These are not hypothetical benefits — they are the reason the host tools built subagent support in the first place. Cypilot should use the primitives its host tools provide.

### Why Not Project-Level Hooks Yet

Project-level hooks (e.g., running `cpt validate` on every `Write`/`Edit` via `PreToolUse`) are valuable but introduce complexity that is best addressed separately:

* **Config merging** — tools like Claude Code store hooks in `.claude/settings.json` alongside user-defined hooks. Non-destructive merge logic must preserve existing hooks, handle format differences across tools, and be idempotent. This is a non-trivial implementation concern that should not block subagent registration.
* **Fail-open design** — hook scripts must exit 0 (allow) when `cpt` is not found, when the file is not a Cypilot artifact, or when validation encounters a runtime error. Getting fail-open semantics right across all tools requires careful testing.
* **Multi-tool format divergence** — Claude Code uses `PreToolUse` with tool name matchers, Copilot uses `preToolUse`, Windsurf uses `pre_write_code`, and Cursor has no hook support at all. Each tool has a different config format, stdin protocol, and blocking mechanism.
* **Incremental value** — subagents deliver the highest-value extensibility primitive (context isolation, orchestration, least privilege). Hooks add deterministic enforcement, which is valuable but secondary. Shipping subagents first lets us validate the extensibility surface before expanding it.

### Why Not the Status Quo

The single-agent skill integration works, but it leaves the host tool's extensibility surface unused. Every tool Cypilot integrates with (Claude Code, Cursor, Copilot, Codex) already exposes subagent definitions. Not adopting them means:

* Accepting context saturation as a permanent limitation
* Accepting overprivilege as a permanent limitation
* Doing more work inside Cypilot's skill layer to approximate what the host tool already provides natively

## Maintaining the Support Matrix

The AI CLI tool landscape is evolving rapidly. Tool vendors add subagent capabilities, change frontmatter schemas, and introduce new features on their own release cadences. To keep Cypilot's subagent generation correct and current:

### When to update

- **Tool adds subagent support** (e.g., Windsurf gains subagents) — add a new entry to `_TOOL_AGENT_CONFIG` and a `_agent_template_<tool>()` function. Update the feature support matrix in this ADR.
- **Tool changes frontmatter schema** (e.g., Cursor renames `readonly` to `readOnly`) — update the corresponding template function. Update the matrix.
- **Tool adds new semantic capability** (e.g., Copilot adds `model` support) — update the template function to emit the new key when the semantic property is present. Move the cell from "silently ignored" to the new mapping. Update the matrix.
- **Tool deprecates a capability** — update the template function to stop emitting the deprecated key. Update the matrix.

### Where to update

1. **`_TOOL_AGENT_CONFIG`** in `agents.py` — output directory, filename format, template function reference
2. **`_agent_template_<tool>()`** in `agents.py` — the per-tool frontmatter rendering logic
3. **`_render_toml_agents()`** in `agents.py` — OpenAI Codex-specific rendering (TOML format)
4. **This ADR** — the feature support matrix and output format tables
5. **`tests/test_subagent_registration.py`** — per-tool template tests and end-to-end generation tests

### Verification

After updating a tool's template, run the existing test suite to verify no regressions. Each tool has dedicated tests that assert the generated frontmatter contains the expected keys and values. The idempotency tests verify that re-running generation produces no spurious changes.

To test against a real tool, generate the subagent files (`cpt generate-agents --agent <tool>`) and verify the host tool recognizes the generated definitions (e.g., Claude Code should list the subagents in its agent picker).

## More Information

- Related: `cpt-cypilot-adr-prefer-cpt-cli-for-agents` (ADR-0015) — subagent prompts reference `cpt` via the same CLI preference mechanism
- Related: `cpt-cypilot-adr-proxy-cli-pattern` (ADR-0007) — subagents use the `cpt` proxy for command forwarding
- Related: `cpt-cypilot-adr-skill-md-entry-point` (ADR-0010) — subagent prompt files reference SKILL.md as their entry point
- Subagent registration is implemented in PR #105 (`feature/subagents` branch)
- Claude Code subagent docs: subagents are defined as Markdown files in `.claude/agents/` with YAML frontmatter for tool scoping and isolation mode
- Claude Code hook events relevant to subagents: `SubagentStart` (inject context at spawn), `SubagentStop` (force continued work or validate completion)
- Project-level hooks (PreToolUse, PostToolUse, SessionStart) are deferred to a future ADR

## Traceability

- **PRD**: [PRD.md](../PRD.md)
- **DESIGN**: [DESIGN.md](../DESIGN.md)

This decision directly addresses the following requirements and design elements:

* `cpt-cypilot-fr-core-agents` — multi-agent integration extended with subagent generation
* `cpt-cypilot-principle-determinism-first` — subagents enforce deterministic privilege scoping (read-only vs read-write)
* `cpt-cypilot-principle-plugin-extensibility` — leveraging host-tool subagent definitions as native extensibility primitives
