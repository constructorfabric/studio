---
cf: true
type: requirement
name: Prompt Engineering Review Methodology
version: 1.7
purpose: Systematic methodology for reviewing and improving agent instructions with evidence-backed constraint framing, compact-prompts optimization, interaction UX quality, and router-based decomposition
---

# Prompt Engineering Review Methodology


<!-- toc -->

- [Overview](#overview)
- [Layer Map](#layer-map)
- [L1: Document Classification](#l1-document-classification)
- [L2: Clarity & Specificity](#l2-clarity--specificity)
- [L3: Structure & Organization](#l3-structure--organization)
- [L4: Completeness Analysis](#l4-completeness-analysis)
- [L5: Anti-Pattern Detection](#l5-anti-pattern-detection)
  - [Specification](#specification)
  - [Context & Memory](#context--memory)
  - [Execution & Output](#execution--output)
  - [Interaction UX](#interaction-ux)
  - [Maintainability](#maintainability)
- [L6: Context Engineering](#l6-context-engineering)
- [L7: Testability Assessment](#l7-testability-assessment)
- [L8: User Interaction UX](#l8-user-interaction-ux)
- [L9: Agent Ergonomics](#l9-agent-ergonomics)
- [L10: Improvement Synthesis](#l10-improvement-synthesis)
- [Integration with Constructor Studio](#integration-with-constructor-studio)
- [References](#references)
- [Validation](#validation)

<!-- /toc -->

**Scope**: Any file containing agent instructions — system prompts, skills, workflows, requirements, `AGENTS.md`, and methodologies.

**Out of scope**: This does not provide a "best prompt" template or generate production prompts; it defines a review method and report format.

**Companion methodology**: for bug hunting, hidden failure modes, unsafe behavior, regressions, instruction conflicts, or root-cause analysis in prompts and agent instructions, also use `prompt-bug-finding.md` as the behavioral defect search procedure.

## Overview

Agent instructions are executable policy for agent behavior and user interaction. Review them like software: classify the artifact, test for ambiguity, verify structure, identify missing contracts, detect anti-patterns, manage context budget, confirm testability, check interaction UX, check model ergonomics, then synthesize prioritized fixes.

```pdsl
UNIT PromptEngineeringStance

PURPOSE:
  Define the review stance applied at every layer of the prompt engineering review.

RULES:
  - ALWAYS reduce loaded context whenever behavior, determinism, constraints, safety, output contracts, and recovery rules stay intact
  - ALWAYS prefer positive, action-oriented requirements; when a blocked behavior matters, pair the prohibition with the required alternative and a verification check
  - ALWAYS keep one response surface to 3-7 primary rules when possible; allow up to 10 only when rules are short, independent, and checked; decompose or validate beyond 10
  - ALWAYS confirm for every user ask that the prompt explains why the input is needed, what the user should provide, what each option does next, which path is suggested, and how to reply
```

## Layer Map

| Layer | Question |
|---|---|
| L1 | What kind of instruction document is this? |
| L2 | Are the instructions explicit and unambiguous? |
| L3 | Is the document scannable and cognitively manageable? |
| L4 | What required information is missing? |
| L5 | Which prompt anti-patterns are present? |
| L6 | Is context loaded, compressed, and preserved correctly? |
| L7 | Can compliance be verified? |
| L8 | Are user-facing questions, options, and transitions easy to understand and act on? |
| L9 | Does the document align with LLM strengths and limits? |
| L10 | What should be fixed first? |

## L1: Document Classification

```pdsl
UNIT PromptEngineeringL1

PURPOSE:
  Classify the document and establish its type, scope, audience, dependencies, and preconditions.

DO:
  - RUN primary type classification: identify whether the document is a System Prompt, Skill/Tool, Workflow, Requirement, AGENTS.md, Template, or Checklist
  - RUN instruction scope classification: mark whether the rules are Global, Conditional (WHEN-gated), or Task-Specific
  - RUN audience classification: determine whether it targets a Single Agent Type, is Agent-Agnostic, or is Hybrid
  - RUN dependency analysis: list referenced docs, detect circular dependencies, confirm dependencies exist and are accessible, and verify version compatibility
  - RUN precondition analysis: record what must already be true, what context must be loaded first, and what tools or capabilities are assumed
```

## L2: Clarity & Specificity

**Ambiguity scan**: flag vague qualifiers (`appropriate`, `relevant`, `suitable`, `proper`, `good`), subjective terms (`better`, `improved`, `professional`, `clean`), undefined references (`the above`, `this`, `that`, `it`), implicit assumptions, and weasel words (`might`, `could`, `possibly`, `generally`, `usually`).

**Specificity**: every instruction should state **WHO** acts, **WHAT** happens, **WHEN** it triggers, **HOW** it is executed, and **WHY** it matters.

**Compact clarity rules**: use short imperative sentences; front-load trigger + action + object (`WHEN X, do Y to Z`); use explicit nouns and verbs; replace vague wording with measurable limits or decision rules; keep stable terminology; remove filler and repeated restatements; prefer bullets, tables, and checklists over narrative; keep only examples that change behavior or clarify edge cases.

```pdsl
UNIT PromptEngineeringL2

PURPOSE:
  Detect ambiguity, enforce specificity and framing rules, and audit instruction density.

RULES:
  - ALWAYS flag vague qualifiers, subjective terms, undefined references, implicit assumptions, and weasel words in the ambiguity scan
  - ALWAYS require each instruction to state WHO acts, WHAT happens, WHEN it triggers, HOW it is executed, and WHY it matters
  - ALWAYS prefer explicit counts, limits, and thresholds over words like few, brief, or many
  - ALWAYS use imperative mood, prefer active voice, and keep to one action per sentence when possible
  - ALWAYS prefer positive requirements; when a negative is necessary, pair it with the required alternative; distinguish MUST NOT / NEVER from SHOULD NOT / AVOID
  - ALWAYS flag negative-only instructions unless they also state the desired replacement behavior; name exact blocked tokens only when verification depends on exact matching; otherwise prefer category-level constraints plus the required replacement behavior
  - ALWAYS count active requirements and treat more than 7 concurrent requirements as a risk and more than 10 as a decomposition trigger unless the prompt includes a validator, checklist, or iterative self-refinement loop
  - ALWAYS verify critical rules are marked MUST / REQUIRED / CRITICAL and optional rules are marked MAY / OPTIONAL / CONSIDER with an obvious importance hierarchy
```

## L3: Structure & Organization

**Hierarchy quality**: headings follow logical `H1 -> H2 -> H3` order, section titles are descriptive, related content is grouped together, and the document uses inverted-pyramid ordering where important content appears early.

**Visual hierarchy**: emphasize important terms with bolding, keep code and IDs in backticks, make warnings visually distinct, and clearly demarcate examples.

```pdsl
UNIT PromptEngineeringL3

PURPOSE:
  Verify document structure, navigation quality, cognitive load, and redundancy.

RULES:
  - ALWAYS verify headings follow logical H1 -> H2 -> H3 order, section titles are descriptive, related content is grouped, and important content appears early
  - ALWAYS verify long sections are split into digestible units, lists replace enumeration paragraphs, tables handle structured comparison, and code blocks are reserved for commands and examples
  - ALWAYS verify long docs include a TOC, related sections are cross-linked, boundaries are visually clear, and a summary or overview appears near the start
  - ALWAYS verify one concept per paragraph, nested conditionals do not exceed two levels, complex logic is expressed as decision trees or ordered steps, and abbreviations are defined on first use
  - ALWAYS verify contradictions are removed, intentional repetition is marked as intentional, and duplication is replaced with cross-references
```

## L4: Completeness Analysis

**Identity & purpose**: verify a purpose statement, scope boundary, and success criteria.

**Operational elements**: verify entry conditions, exit conditions, response-completion gates, required terminal sections or handoff blocks, error handling, clarification strategy, option semantics, and edge-case guidance.

```pdsl
UNIT PromptEngineeringL4

PURPOSE:
  Identify missing contracts, operational elements, integration elements, and scenario coverage gaps.

RULES:
  - ALWAYS verify a purpose statement, scope boundary, and success criteria exist
  - ALWAYS verify entry conditions, exit conditions, response-completion gates, required terminal sections or handoff blocks, error handling, clarification strategy, option semantics, and edge-case guidance are present
  - ALWAYS verify dependencies are listed, outputs are defined, handoffs to other workflows are specified, required final prompt pairs or terminal block ordering is explicit, and every required user decision point explains what happens after each option
  - ALWAYS ask what happens if the agent does not understand, preconditions are not met, multiple interpretations exist, external resources are unavailable, or the user does not understand what a requested choice means
  - ALWAYS verify happy path, error paths, recovery procedures, escalation triggers, user-decision branches, and completion branches are documented
  - ALWAYS check whether the response can terminate after a summary, validation block, or next-step menu even though required final sections are still missing
```

## L5: Anti-Pattern Detection

Anti-pattern codes are reference labels. All detected codes MUST be reported with location and recommended fix.

### Specification

| Code | Detect when |
|---|---|
| `AP-VAGUE` | Instructions rely on common sense, ambiguity, or implicit knowledge. |
| `AP-MISSING-FORMAT` | Output format is not specified. |
| `AP-MISSING-ROLE` | Needed persona or expertise is undefined. |
| `AP-MISSING-CONSTRAINTS` | Length, scope, style, or boundary constraints are missing. |
| `AP-OVERLOAD` | Too many tasks are packed into one instruction. |
| `AP-MICROMANAGE` | Low-level detail constrains execution without improving outcomes. |
| `AP-LONG-WINDED` | The same rule is padded with prose, repetition, or bloated examples. |
| `AP-CONFLICTING` | Requirements contradict one another. |
| `AP-IMPOSSIBLE` | Not all requirements can be satisfied simultaneously. |
| `AP-NEGATIVE-ONLY` | A prohibition says what not to do without stating the required alternative behavior. |
| `AP-FORBIDDEN-PRIMING` | A prompt repeatedly names exact blocked tokens or labels when category-level wording would preserve the rule. |
| `AP-INSTRUCTION-DENSITY` | More than `7` active requirements compete in one response surface, or more than `10` are present without decomposition or validation. Mitigation: per-constraint self-check loop (decompose → critique → refine each constraint separately) significantly improves compliance under high density. |
| `AP-NO-ROUTER` | Multi-step or branching instructions lack a compact router/index that says what may load next and when. |
| `AP-OVERSIZED-RESOURCE` | A loadable instruction resource, module, or deliberate slice exceeds the `500`-line acceptable size (warning: decompose the skill, compact it, and lazy-load instructions) or the `1000`-line critical ceiling (FAIL). |
| `AP-MONOLITHIC-STEP` | Multiple steps, branches, or modes are bundled into one loadable unit instead of decomposed into routeable modules. |

### Context & Memory

| Code | Detect when |
|---|---|
| `AP-CONTEXT-BLOAT` | Excessive context dilutes priorities. |
| `AP-SYSTEM-PROMPT-BLOAT` | A system prompt violates the compact-prompt always-on budget rule: always-on text exceeds the `500`-line acceptable size (warning: decompose, compact, and lazy-load) or the `1000`-line critical ceiling, or embeds conditional blocks that should be modular. |
| `AP-CONTEXT-STARVATION` | Critical context is missing. |
| `AP-CONTEXT-DRIFT` | Required context may be lost through compaction or long sessions. |
| `AP-BURIED-PRIORITY` | Critical rules are hidden instead of surfaced early and scannably. |
| `AP-LOST-MIDDLE` | Critical instructions or references sit in the middle of a long prompt where attention may degrade. Note: the U-shaped attention effect (primacy + recency bias) is significantly reduced in large frontier models but remains substantial in smaller models; apply this check conservatively for GPT-4-class targets and strictly for smaller models. |
| `AP-VAGUE-REFERENCE` | References such as `the above` or `this` have no clear antecedent. |
| `AP-ASSUMES-MEMORY` | The document assumes the agent will remember earlier turns. |
| `AP-NO-CHECKPOINT` | Long workflows lack state checkpoints. |
| `AP-IMPLICIT-STATE` | State changes are not explicitly tracked. |

### Execution & Output

| Code | Detect when |
|---|---|
| `AP-NO-VERIFICATION` | No self-check or validation step exists. |
| `AP-FALSE-COMPLETION` | The prompt allows the response to end after a summary, validation result, next-step menu, or checkpoint-looking block even though required final sections or handoff prompts are still missing. |
| `AP-MISSING-TERMINAL-BLOCK` | Required final prompt blocks, handoff sections, or terminal block ordering are unspecified or only implied. |
| `AP-SKIP-ALLOWED` | Critical steps are easy to skip. |
| `AP-SILENT-FAIL` | Failures are not surfaced to the user. |
| `AP-INFINITE-LOOP` | Retry loops can stall indefinitely. |
| `AP-HALLUCINATION-PRONE` | The prompt encourages guessing. |
| `AP-NO-UNCERTAINTY` | The agent is not allowed to say `I don't know`. |
| `AP-NO-SOURCES` | Claims need not be cited or verified. |

### Interaction UX

| Code | Detect when |
|---|---|
| `AP-UNEXPLAINED-ASK` | The prompt asks the user for information or confirmation without stating why it is needed or what good input looks like. |
| `AP-AMBIGUOUS-OPTIONS` | Options or reply labels are hard to distinguish, use unclear wording, or hide important differences. |
| `AP-HIDDEN-CONSEQUENCE` | The user is asked to choose before the prompt explains what each option will do next. |
| `AP-NO-SUGGESTED-OPTION` | A decision point lacks a suggested or recommended path even though the current context clearly favors one option. |
| `AP-GENERIC-SUGGESTION` | Suggested follow-ups or recommended options are generic instead of being anchored to the current request, state, or prior result. |
| `AP-OPTION-OVERLOAD` | Too many choices, too much prose, or mixed decision scopes increase cognitive load unnecessarily. |

### Maintainability

| Code | Detect when |
|---|---|
| `AP-HARDCODED` | Magic strings or numbers appear instead of parameters. |
| `AP-DRY-VIOLATION` | The same rule appears in multiple places. |
| `AP-NO-VERSION` | Breaking changes are not versioned. |
| `AP-TANGLED` | Editing one area breaks unrelated behavior. |

```pdsl
UNIT PromptEngineeringL5

PURPOSE:
  Scan the document for all listed anti-pattern codes and report every detection.

RULES:
  - ALWAYS check the document against all anti-pattern codes in all five catalogs: Specification, Context & Memory, Execution & Output, Interaction UX, and Maintainability
  - ALWAYS report each detected anti-pattern with its code, exact location, and recommended fix
  - NEVER report an anti-pattern without a specific location and fix recommendation
```

## L6: Context Engineering

**Content audit**: identify compressible sections, redundant sections, content that should load conditionally, and approximate size. Optional sizing helpers: `wc -l path/to/document.md` for line count and a simple word-count proxy for rough token estimation.

**Information priority**: confirm the most critical instructions appear in the first `20%` of the document, examples and details can be truncated without losing core behavior, and conditional content is clearly marked for selective loading.

A **loadable instruction resource** is any file, module, or deliberate contiguous slice that the agent is expected to load as one active execution unit at runtime. Concrete test: a unit qualifies as a loadable instruction resource only when the agent must ingest it whole at runtime — invoked as a single programmatic load or import (for example a `Read` of the whole file, an `ALWAYS open and follow {path}` directive, a workflow `WHEN`-clause spec load, or a router pointing at the file as the next-load target). Examples that ARE loadable instruction resources: a workflow phase file, a skill `SKILL.md` actively loaded by the protocol guard, a router-referenced module, a checklist file ingested whole during a phase, an agent prompt opened in full.

**Exemptions**: methodology documents, reference guides, multi-chapter specifications, ADRs, design documents, and other non-runtime documentation are exempt from the `<= 500` line acceptable-size guidance UNLESS they contain runtime execution sequences or agent-loadable instruction blocks (e.g., `WHEN`-clause specs, `ALWAYS open and follow` directives, or router targets). When such a document carries runtime instructions inline, the runtime block itself is the loadable resource and SHOULD be either (a) within the `<= 500`-line acceptable size, or (b) extracted into its own routeable module; it MUST never exceed the `1000`-line critical ceiling.

**Measurement rule**: count headings, blank lines, lists, and examples within the runtime-loadable unit (do not count surrounding non-runtime prose in an exempted document). PASS when every runtime-loadable unit is `<= 500` lines (acceptable). WARN when a unit is `501`–`1000` lines: recommend decomposing the skill, compacting it, and lazy-loading instructions. FAIL (critical) when any runtime unit exceeds `1000` lines.

**Migration rule**: during brownfield review or refactor, an oversized legacy prompt may be inspected through bounded slices to plan decomposition. That temporary inspection does not make the legacy prompt compliant; a prompt over the `1000`-line critical ceiling remains non-compliant until decomposed, and the compliant target state is routeable resources `<= 500` lines each.

**Router / module type reference**:

| Module type | Purpose | MUST contain | MUST NOT contain |
|---|---|---|---|
| Router / index | Entry point and branch selection | purpose, branch names, explicit triggers, next-file mapping, stop/escalate rule | full downstream step-by-step content for multiple branches |
| Step module | One execution step | goal, prerequisites, actions, outputs, next route or stop condition | instructions for unrelated steps, future phases, or sibling branches |
| Decision module | One user/system choice point | options, consequences, suggested path, reply contract, next-file mapping | hidden consequences, mixed decision scopes, or unrelated execution detail |
| Shared invariant module | Reusable always-on constraints | invariants reused by multiple branches, stable definitions, non-branching guardrails | branch-local sequencing or large optional guidance |
| Recovery module | Error, retry, or resume path | failure trigger, recovery actions, return route | normal-path bulk instructions |

**Compactness examples**:

| Anti-pattern | Before | After |
|---|---|---|
| `AP-LONG-WINDED` | `When you are in a situation where context may be running low...` | `WHEN context runs low, summarize loaded instructions into a short operational checklist and drop the raw text.` |
| `AP-BURIED-PRIORITY` | `Use good judgment... before writing anything make sure they have approved it.` | `MUST NOT write files before explicit user confirmation.` |

```pdsl
UNIT PromptEngineeringL6

PURPOSE:
  Enforce context engineering rules: system prompt budget, loadable resource budget, overflow controls, and router decomposition.

RULES:
  - ALWAYS identify compressible, redundant, and conditional sections with approximate size
  - ALWAYS confirm most critical instructions appear in the first 20% of the document
  - ALWAYS keep the always-on portion of a System Prompt within the 500-line acceptable size; count headings, blank lines, and lists; PASS if <= 500; WARN at 501-1000 and recommend decomposing the skill, compacting it, and lazy-loading instructions; NEVER allow it to exceed 1000 lines (CRIT, FAIL)
  - ALWAYS require that any document telling the agent to load more files defines budget, gating, chunking, summarization, and a fail-safe (CRIT)
  - ALWAYS require minimum overflow controls: max files / max total lines or mandatory summarize-and-drop policy; rules for when a dependency should load; partial loading by TOC/section/range; conversion of loaded text into operational summary; stop / checkpoint / ask-user fallback when budget would be exceeded
  - ALWAYS keep any loadable instruction resource within the 500-line acceptable size; PASS if every runtime-loadable unit is <= 500; WARN at 501-1000 and recommend decomposing the skill, compacting it, and lazy-loading instructions; NEVER allow any unit to exceed 1000 lines (CRIT, FAIL)
  - ALWAYS require that behavior spanning multiple steps, branches, modes, or recovery paths is decomposed into a compact router plus on-demand modules (CRIT); NEVER inline full instructions for sibling branches or later steps that are not yet active
  - ALWAYS apply the preferred representation: use compact tables for router/index data and short ordered lists for execution steps
  - ALWAYS check: safe reductions found, content kept intentionally, deferred or blocked opportunities, and behavior-preservation confirming MUST, MUST NOT, triggers, thresholds, output rules, and fail-safes remain intact
  - ALWAYS verify lossless-first compression order: remove filler/courtesy, repeated framing, hedging, decorative transitions, duplicated examples, archival detail, optional explanatory prose in that order; NEVER remove constraints, thresholds, triggers, fail-safes, or required terminal blocks before higher-noise categories are exhausted
  - ALWAYS verify controlled shorthand: compressed phrasing is acceptable only when a fresh agent can interpret the rule without guessing; one stable compressed label per concept; non-obvious shorthand defined once near first use
  - ALWAYS run decompression test: verify a reviewer can restate each compressed rule in full plain language; mark FAIL if compression depends on hidden context, unstated shorthand, or memory of earlier turns
  - ALWAYS check instruction-density: list every active instruction; merge duplicates; remove non-operative prose; convert large rule sets into a router plus current-phase checklist; mark AP-INSTRUCTION-DENSITY and recommend decomposition if active set remains > 10
```

```pdsl
UNIT PromptEngineeringMandatoryLoadingProtocol

PURPOSE:
  Enforce the seven-step mandatory loading protocol for router-decomposed documents.

RULES:
  - ALWAYS load the router or entry module first
  - ALWAYS resolve the active branch, mode, or step from explicit triggers before loading any downstream module
  - ALWAYS load exactly one downstream module at a time unless two modules are both mandatory for the same immediate action and still respect the <= 500-line acceptable-size rule
  - ALWAYS retain only a short operational summary plus required state after each module; drop unrelated raw text
  - ALWAYS load the next module only from an explicit next, when, if, or decision mapping
  - NEVER keep recovery, review, and completion modules always-on by default; load them only when their trigger fires
  - ALWAYS restart from the router or checkpoint plus the next required module on resumption; NEVER restart from chat memory alone
  - ALWAYS report loaded files with sizes and sections/ranges, chosen budget, and whether it was respected or which fail-safe path was taken
```

## L7: Testability Assessment

```pdsl
UNIT PromptEngineeringL7

PURPOSE:
  Verify that every instruction is testable, compliance is observable, and verification mechanisms are built in.

RULES:
  - ALWAYS verify each instruction can answer: did the agent do it, do it correctly, and do it completely
  - ALWAYS require visible artifacts, visible intermediate steps, and explicit compliance evidence
  - ALWAYS verify validation criteria, a pre-completion self-check, checklist formatting for critical steps, and proof-of-work requirements when failure risk is high
  - ALWAYS require the agent to verify the final answer against the constraints before completion when a prompt has 5 or more active constraints; the self-check may be internal or visible but the output contract must make compliance observable
  - ALWAYS verify for every user-facing choose/confirm that tests can confirm from the emitted prompt alone: why the input is needed, what reply format is accepted, what each option does, and whether any suggested option is anchored to the current context
  - ALWAYS verify that when a workflow requires terminal prompts or final handoff blocks, the pre-completion self-check verifies those exact blocks were emitted before the response may end
  - ALWAYS prefer rules that can be checked by automated tools, another agent, or a human reviewer
  - ALWAYS provide at least one correct happy-path example with full input-to-output trace and key edge cases
  - ALWAYS show negative tests: what not to do, what incorrect outputs look like, and how to recover
```

## L8: User Interaction UX

```pdsl
UNIT PromptEngineeringL8

PURPOSE:
  Verify that all user-facing questions, options, and transitions meet interaction UX standards.

RULES:
  - ALWAYS verify every user-facing prompt explains why the input is needed, what the user is expected to provide, what each option leads to, which option is suggested in the current context, and exactly how the user should reply
  - ALWAYS verify each question, confirmation gate, or next-step menu moves the user toward a concrete outcome and states why this question is being asked now
  - ALWAYS verify that when the user's choice depends on system capabilities, constraints, or uncertainty, the prompt explains what the system can do, what it cannot do, and why the recommendation is appropriate
  - ALWAYS verify the prompt does not ask the user to restate already-available context, and that complex requests are broken into manageable steps
  - ALWAYS verify options or reply labels are easy to distinguish, use clear wording, and do not hide important differences
  - ALWAYS verify the user is not asked to choose before the prompt explains what each option will do next
  - ALWAYS verify a decision point has a suggested or recommended path when the current context clearly favors one option
  - ALWAYS verify suggested follow-ups or recommended options are anchored to the current request, state, or prior result and not generic
  - ALWAYS verify too many choices, too much prose, or mixed decision scopes do not increase cognitive load unnecessarily
  - ALWAYS verify the prompt tells the user exactly how to answer so the reply format never has to be guessed
  - ALWAYS verify confusion or unsupported input leads to a targeted clarifying question, a small set of clear alternatives, or a nearest-supported path instead of a dead-end response
  - ALWAYS verify shifts between stages are explicitly communicated so the user understands what changed and why
```

## L9: Agent Ergonomics

```pdsl
UNIT PromptEngineeringL9

PURPOSE:
  Verify that instructions align with LLM capabilities, training alignment, and graceful degradation patterns.

RULES:
  - ALWAYS verify instructions do not ask impossible things, break complex reasoning into steps when beneficial (see CoT caveat below), and request output formats the model handles well (JSON, Markdown, etc.)
  - ALWAYS verify familiar prompt patterns, an appropriate role/persona, and a style consistent with effective prompting are used
  - ALWAYS rewrite vague or negative rules into direct actions; prefer Do X when Y over Do not forget X; prefer If data is missing, say UNKNOWN over Do not hallucinate
  - ALWAYS treat exact word counts, exact token counts, exact character limits, and long simultaneous rule sets as high-risk unless automated validation or post-processing is available
  - ALWAYS verify partial failure behavior is defined, whether the agent can recover without intervention, and when it must ask for help
  - ALWAYS require verification or citation, permit uncertainty, mark speculation, and use external tools for factual queries
  - ALWAYS verify iterative improvement is supported, feedback incorporation is defined, and partial success is actionable
  - ALWAYS verify multi-turn use, clarification requests, and mid-task scope changes are supported
  - ALWAYS prefer one compact positive example over several overlapping prose rules when format, tone, or structure matters; remove any example that no longer changes behavior
  - ALWAYS order multiple constraints from most specific / hardest to satisfy first to least specific / easiest last — LLMs show higher compliance with hard-to-easy ordering than easy-to-hard or random ordering regardless of model architecture and size
  - ALWAYS flag chain-of-thought decomposition as potentially harmful for tasks involving implicit pattern recognition, intuitive judgment, or face/signal recognition — CoT can reduce performance on tasks where deliberate verbalization hurts human performance too; do not apply CoT unconditionally
  - ALWAYS note that prompt format sensitivity (Markdown vs JSON vs plain text) is strongly model-size dependent: smaller models vary up to ±40% by format for the same task; larger frontier models are substantially more robust — flag format choice as a calibration concern when the target model is not known or may vary
  - ALWAYS recommend per-constraint self-check (decompose, critique, refine each constraint independently) when AP-INSTRUCTION-DENSITY is detected; per-constraint loops significantly outperform single-pass self-refinement under high constraint counts
```

## L10: Improvement Synthesis

**Severity**:

| Severity | Criteria | Action |
|---|---|---|
| `CRITICAL` | Blocks task completion | Fix immediately |
| `HIGH` | Causes incorrect or inconsistent output | Fix before deployment |
| `MEDIUM` | Reduces quality or efficiency | Fix next iteration |
| `LOW` | Minor improvement opportunity | Backlog |

**Effort**:

| Effort | Criteria |
|---|---|
| `TRIVIAL` | Single word or phrase change |
| `SMALL` | Single section rewrite |
| `MEDIUM` | Multiple section changes |
| `LARGE` | Document restructure |

```pdsl
UNIT PromptEngineeringL10

PURPOSE:
  Synthesize all findings into prioritized fixes with actionable guidance.

RULES:
  - ALWAYS list CRITICAL plus TRIVIAL/SMALL fixes as quick wins, rank by impact-to-effort ratio, and note dependencies between fixes; for user-facing prompts, prioritize fixes that reduce user confusion at decision points before cosmetic wording changes
  - ALWAYS list structural changes, refactoring opportunities, and missing sections or companion docs as strategic improvements
  - ALWAYS provide What, Where, Why, How, and Verify for each fix; for interaction UX fixes, include the intended user mental model, the suggested default path, and the exact outcome text that should become clearer
  - ALWAYS define tests for critical fixes, regression checks for preserved behavior, and validation that fixes do not conflict
```

## Execution Protocol

**Prerequisites**: full document text is accessible; related documents are available for cross-reference; document purpose and context are understood; example outputs are available when applicable.

**Work budgeting pass schedule**:

| Document Size | L1-L3 | L4-L6 | L7-L9 | L10 |
|---|---|---|---|---|
| Small (`< 500`) | 1 pass | 1 pass | 1 pass | 1 synthesis pass |
| Medium (`500-2000`) | 1-2 passes | 1-2 passes | 1-2 passes | 1 synthesis pass |
| Large (`> 2000`) | 2 passes | 2 passes | 2 passes | 1-2 synthesis passes |

```pdsl
UNIT PromptEngineeringExecutionProtocol

PURPOSE:
  Define execution order, budgeting, error handling, and output format for the review.

DO:
  - RUN layers 1 through 10 in sequence
  - RUN size check with wc -l path/to/document.md before beginning; use pass budget from the work budgeting table
  - EMIT report in this section order: Summary, Context Budget & Evidence, Compact-Prompts Findings, Layer Summaries, Issues Found (Critical / High / Medium / Low tables), Recommended Fixes (Immediate / Next Iteration / Backlog), and Verification Checklist

RULES:
  - ALWAYS execute all 10 layers in sequence; checkpoint findings after each layer before continuing
  - ALWAYS include all required report fields: Summary (document type, overall quality GOOD/NEEDS_IMPROVEMENT/POOR, critical issue count, total issue count), Context Budget & Evidence (budget, inputs loaded with path and size and sections/ranges, overflow handling), Compact-Prompts Findings (safe reductions found, content kept intentionally, deferred/blocked opportunities, behavior-preservation check), Layer Summaries (every layer explicitly; dedicated interaction-UX findings when user-facing content exists), Verification Checklist
  - ALWAYS start Summary with the required status block from prompt-bug-finding.md when paired with that methodology, including Review status and Deterministic gate PASS/FAIL/SKIPPED; when gate is SKIPPED, state why and explicitly state no validator-backed evidence for this review path before the quality counts
  - NEVER mark a check N/A unless the document explicitly makes it inapplicable; otherwise mark FAIL or PARTIAL and explain what is missing
  - NEVER describe semantic review, checklist review, or manual inspection as deterministic, validator-backed, or tool-validated when the deterministic gate is SKIPPED unless actual validator or tool output exists
  - ALWAYS note blockers and continue if a layer exceeds its pass budget; incomplete analysis is better than no analysis

ON_ERROR:
  partial layer completion -> document completed checks, note blockers, mark the layer PARTIAL, then proceed to the next layer
  dependencies inaccessible -> analyze what is available; flag missing dependencies in findings
  examples missing -> flag Layer 7 and recommend examples; continue
  context unclear -> ask the user or make assumptions explicit
  resume after interruption -> default to a chat-only checkpoint; save review-checkpoint-{document}-{layer}.md only with explicit user request or approval; on resume, read the available checkpoint source, verify the document is unchanged, and continue
```

## Integration with Constructor Studio

- Use this methodology for semantic validation and generation of instruction documents.
- Keep `AGENTS.md` and related adapters aligned with these rules.
- Pair this methodology with `prompt-bug-finding.md` when the task is defect-oriented.

## References

This document is the authoritative working method. External sources inform its design, but the prompt surface here stays intentionally compact.

**Companion methodology**: `prompt-bug-finding.md` for bug hunting, hidden failure modes, unsafe behavior, regressions, instruction conflicts, or root-cause analysis in prompts and agent instructions.

**Research and practice references**:

- OpenAI prompt engineering best practices: put instructions first, separate instruction from context, use specific desired formats, show examples, reduce imprecise wording, and state what to do instead of only what not to do. https://help.openai.com/en/articles/6654000-using-advanced-prompt-engineering-techniques
- `Semantic Gravity Wells: Why Negative Constraints Backfire`: negative constraints can fail because naming forbidden terms primes the model toward them. https://arxiv.org/abs/2601.08070
- `Curse of Instructions`: instruction following degrades as the number of simultaneous instructions increases; prompts with up to ten verifiable instructions show sharp all-instruction success loss, partially improved by self-refinement. https://openreview.net/forum?id=R6q67CDBCH
- `InFoBench`: complex instructions are better evaluated by decomposing them into simpler criteria and checking requirement-level compliance. https://arxiv.org/abs/2401.03601
- `FollowBench`: incrementally adding constraints exposes weaknesses in fine-grained constraint following. https://arxiv.org/abs/2310.20410
- `Lost in the Middle`: long-context models may underuse information placed in the middle of long inputs; critical rules should not be buried there. https://arxiv.org/abs/2307.03172
- `What Prompts Don't Say`: simply adding more requirements does not reliably improve performance because instruction-following capacity is limited and requirements may conflict. https://arxiv.org/abs/2505.13360
- `When Instructions Multiply` (2025): quantifies the degradation law — prompt-level accuracy(n) = instruction-level accuracy^n; experiments across GPT-4o, Claude-3.5, Gemini-1.5, Gemma2, Llama3.1 confirm constant per-instruction degradation. https://arxiv.org/abs/2509.21051
- `How Many Instructions Can LLMs Follow at Once?` (2025): ManyIFEval benchmark with up to ten verifiable instructions; performance degrades consistently and gradually as instruction count rises across all tested frontier models. https://arxiv.org/abs/2507.11538
- `Order Matters: Position Bias in Multi-constraint Instruction Following` (ACL Findings 2025): LLMs perform significantly better when constraints are ordered hard-to-easy; the effect is consistent across architectures and parameter sizes. https://arxiv.org/abs/2502.17204
- `Mind Your Step (by Step): Chain-of-Thought can Reduce Performance` (2024): CoT degrades performance on tasks where deliberate reasoning harms human performance (implicit patterns, intuitive recognition); do not apply CoT unconditionally. https://arxiv.org/abs/2410.21333
- `The Curse of CoT: Limitations in In-Context Learning` (2025): long-CoT reasoning models fail to overcome fundamental limitations in planning tasks despite higher computational cost. https://arxiv.org/abs/2504.05081
- `Does Prompt Formatting Have Any Impact on LLM Performance?` (2024): prompt format (CSV, JSON, Markdown, YAML) causes up to ±40% accuracy swings in smaller models; larger models are substantially more robust — format sensitivity is a model-size property. https://arxiv.org/abs/2411.10541
- `LLM Self-Correction with DeCRIM` (2024): decompose-critique-refine per-constraint self-check significantly outperforms single-pass self-refinement when multiple constraints are active; recommended mitigation for AP-INSTRUCTION-DENSITY. https://arxiv.org/abs/2410.06458
- `Lost in the Middle: An Emergent Property` (2025): reframes the lost-in-the-middle effect as emergent from information-retrieval demands during pretraining; larger models show substantially reduced or eliminated U-shaped attention curves. https://arxiv.org/abs/2510.10276

## Validation

```pdsl
UNIT PromptEngineeringValidation

PURPOSE:
  Define the completion gate for a prompt engineering review.

RULES:
  - ALWAYS verify all 10 layers were analyzed
  - ALWAYS verify all checklist items were attempted with PASS, FAIL, PARTIAL, or explicit N/A
  - ALWAYS verify issues were categorized by severity and effort
  - ALWAYS verify fixes were prioritized by impact/effort with implementation guidance
  - ALWAYS verify safe compact-prompts opportunities were identified and prioritized for prompt/instruction documents
  - ALWAYS verify compact-prompts findings were reported explicitly in the review output
  - ALWAYS verify negative-only instructions were checked and paired with required alternative behavior where needed
  - ALWAYS verify active instruction count was checked: > 7 constraints treated as risk and > 10 constraints decomposed or validator-backed
  - ALWAYS verify critical instructions were checked for beginning/end placement rather than being buried in long-context middle sections
  - ALWAYS verify for every user-facing interaction point: question purpose, option clarity, option outcomes, suggested-path quality, reply format, and fallback clarity were checked explicitly
  - ALWAYS verify required completion gates, terminal blocks, and false-completion paths were checked explicitly when the document defines a final response contract
```
