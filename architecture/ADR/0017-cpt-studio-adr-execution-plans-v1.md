---
status: accepted
date: 2026-03-18
decision-makers: project maintainer
---

# ADR-0017: Execution Plans for Context-Bounded Agent Tasks

<!-- toc -->

- [Context and Problem Statement](#context-and-problem-statement)
- [Decision Drivers](#decision-drivers)
- [Considered Options](#considered-options)
- [Decision Outcome](#decision-outcome)
  - [Consequences](#consequences)
  - [Confirmation](#confirmation)
- [Pros and Cons of the Options](#pros-and-cons-of-the-options)
  - [Option 1: No Decomposition — Single-Shot Execution](#option-1-no-decomposition--single-shot-execution)
  - [Option 2: Manual Decomposition by User](#option-2-manual-decomposition-by-user)
  - [Option 3: Automated Execution Plans with Compiled Phase Files](#option-3-automated-execution-plans-with-compiled-phase-files)
- [More Information](#more-information)
- [Traceability](#traceability)

<!-- /toc -->

**ID**: `cpt-studio-adr-execution-plans`

## Context and Problem Statement

Studio workflows can load 3000+ lines of instructions before an AI agent writes any output (SKILL.md + execution-protocol.md + workflow + rules + template + checklist + example + constraints + project context). This causes context window overflow, leading to attention drift (different parts of instructions "win" on each run), partial completion (agent runs out of context mid-task), and inconsistent results. How should Studio handle large agent tasks that exceed a single context window?

## Decision Drivers

* **Determinism** — consistent results across runs require bounded, focused context per execution unit
* **Agent-agnostic execution** — phase files must be executable by any AI agent without Studio knowledge
* **Kit rules integrity** — kit rules are law and must never be trimmed or summarized to fit a budget
* **User autonomy** — users should not need to manually figure out how to break tasks into manageable pieces
* **Recoverability** — if a phase fails or context is lost, execution must be resumable from the last checkpoint

## Considered Options

1. **No Decomposition — Single-Shot Execution** — load all context and execute in one pass
2. **Manual Decomposition by User** — user breaks task into smaller requests manually
3. **Automated Execution Plans with Compiled Phase Files** — tool decomposes task and generates self-contained phase files

## Decision Outcome

Chosen option: **Option 3 — Automated Execution Plans with Compiled Phase Files**, because it moves decomposition complexity from the user to the tool, ensures each phase file contains exactly the context needed (no more, no less), and produces deterministic, agent-agnostic instruction files that can be executed in any AI coding assistant.

### Consequences

* Good, because each phase file is bounded (≤500 lines target, ≤1000 max) ensuring consistent attention
* Good, because phase files are self-contained — all rules, paths, and context pre-resolved and inlined
* Good, because any AI agent can execute a phase file without Studio context or tools
* Good, because plan manifest (`plan.toml`) provides checkpoint/recovery for multi-session work
* Good, because decomposition strategies are codified (by template sections, checklist categories, or CDSL blocks)
* Bad, because plan generation itself consumes context and requires careful budget management
* Bad, because phase files duplicate kit content (rules inlined into each phase) increasing storage
* Bad, because inter-phase dependencies require careful ordering and intermediate result passing
* Neutral, because the plan workflow is itself a complex workflow that must follow its own rules

### Confirmation

Confirmed when:

- Plan workflow file (`workflows/plan.md`) exists and follows workflow structure conventions
- Phase template file (`requirements/plan-template.md`) exists with all required sections
- Decomposition strategies file (`requirements/plan-decomposition.md`) exists with strategies for generate/analyze/implement
- Generated phase files are self-contained: zero unresolved `{variable}` references, zero "open file X" instructions requiring Studio knowledge
- Generated phase files respect line budget: ≤500 lines target, ≤1000 lines maximum
- Phase files can be executed by any AI agent without Studio context or tools
- Plan manifest (`plan.toml`) correctly tracks phase status across executions
- Kit rules are never trimmed — phases are split instead when budget is exceeded

## Pros and Cons of the Options

### Option 1: No Decomposition — Single-Shot Execution

Load all kit dependencies, project context, and workflow instructions into a single context and execute the entire task in one pass.

* Good, because simplest implementation — no decomposition logic needed
* Good, because no intermediate state management or phase handoffs
* Bad, because context overflow causes attention drift and inconsistent results
* Bad, because partial completion requires manual re-scoping and re-execution
* Bad, because large artifacts (PRD, DESIGN) cannot be generated reliably in one pass
* Bad, because users must manually retry with smaller scope when execution fails

### Option 2: Manual Decomposition by User

User manually breaks large tasks into smaller requests (e.g., "generate PRD sections 1-3", then "generate PRD sections 4-6").

* Good, because no tool complexity — user controls decomposition
* Good, because user can apply domain knowledge to choose split points
* Bad, because requires user to understand kit structure (which sections, which rules apply where)
* Bad, because user must manually track progress and ensure coverage
* Bad, because inconsistent decomposition across users and projects
* Bad, because user must manually ensure rules are included in each sub-request

### Option 3: Automated Execution Plans with Compiled Phase Files

Tool analyzes task scope, decomposes into phases using codified strategies, and generates self-contained phase files with all context pre-resolved.

* Good, because decomposition is consistent and follows kit-defined strategies
* Good, because phase files are agent-agnostic — any AI can execute them
* Good, because kit rules are preserved completely (phases split, rules never trimmed)
* Good, because plan manifest enables progress tracking and recovery
* Good, because intermediate results are explicitly defined and passed between phases
* Bad, because plan generation is itself a complex workflow requiring careful implementation
* Bad, because phase files duplicate content (same rules may appear in multiple phases)
* Bad, because requires storage for plan directory and phase files

## More Information

**Decomposition Strategies**:

| Task Type | Strategy | Phase Boundaries |
|-----------|----------|------------------|
| Generate (artifact creation) | By template sections | 2-4 H2 sections per phase |
| Analyze (validation/review) | By checklist categories | Structural → Semantic → Cross-ref → Traceability → Synthesis |
| Implement (code from FEATURE) | By CDSL blocks | One flow/algorithm/state + tests per phase |

**Phase File Structure** (from `plan-template.md`):

1. TOML frontmatter (plan ID, phase number, dependencies, input/output paths)
2. Preamble ("Any AI agent can execute this file")
3. What (2-3 sentences describing phase scope)
4. Prior Context (summary of previous phases' outputs)
5. User Decisions (pre-resolved answers to interactive questions)
6. Rules (inlined kit rules applicable to this phase — never trimmed)
7. Input (pre-resolved file paths, inlined project context)
8. Task (numbered step-by-step instructions)
9. Acceptance Criteria (binary pass/fail checklist)
10. Output Format (expected output structure and completion report)

**Line Budget Enforcement**:

- Target: ≤500 lines per phase file
- Maximum: ≤1000 lines per phase file
- If rules push phase over budget: split phase, never trim rules
- Execution context budget: ≤2000 lines (phase file + runtime reads + outputs)

**Plan Storage**:

```
{cf-studio-path}/.plans/{task-slug}/
├── plan.toml           # manifest with phase metadata and status
├── brief-01-{slug}.md  # compilation brief for phase 1
├── phase-01-{slug}.md  # compiled phase file 1
├── brief-02-{slug}.md  # compilation brief for phase 2
├── phase-02-{slug}.md  # compiled phase file 2
└── out/                # intermediate results between phases
```

## Traceability

- **PRD**: [PRD.md](../PRD.md)
- **DESIGN**: [DESIGN.md](../DESIGN.md)
- **Feature Spec**: [features/execution-plans.md](../features/execution-plans.md)

This decision directly addresses the following requirements and design elements:

* `cpt-studio-fr-core-execution-plans` — Implements the execution plan requirement: decomposition into self-contained phase files with line budgets and three decomposition strategies
* `cpt-studio-fr-core-workflows` — Extends the workflow system with a plan workflow that produces phase files rather than direct results
* `cpt-studio-principle-determinism-first` — Enforces determinism by bounding context per phase and using deterministic tools where possible
* `cpt-studio-flow-execution-plans-generate-plan` — Defines the user flow for generating execution plans
* `cpt-studio-flow-execution-plans-execute-phase` — Defines the user flow for executing individual phases
* `cpt-studio-algo-execution-plans-decompose` — Specifies the decomposition algorithm with three strategies
* `cpt-studio-algo-execution-plans-compile-phase` — Specifies the phase file compilation algorithm
* `cpt-studio-algo-execution-plans-enforce-budget` — Specifies budget enforcement with phase splitting (never rule trimming)
