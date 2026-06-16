---
cf: true
type: requirement
name: Prompt Bug-Finding Methodology
version: 1.4
purpose: Compact methodology for high-recall discovery of behavioral defects in prompts and agent instructions, including constraint-framing, instruction-density, long-context, and interaction UX failures that cause wrong or stalled behavior
---

# Prompt Bug-Finding Methodology

**Scope**: behavioral defect discovery in system prompts, agent prompts, workflows, skills, `AGENTS.md`, requirements, tool-use policies, and multi-file instruction sets.

**Non-goal**: guarantee `100%` prompt bug detection. Prompt behavior depends on the model, tool environment, conversation history, loaded dependencies, and runtime conditions. The practical target is **maximum recall with explicit hypotheses, counterexamples, evidence, and validation paths**.

## Core Principles

```pdsl
UNIT PromptBugFindingPrinciples

PURPOSE:
  Establish the behavioral principles governing all prompt bug-finding review work.

RULES:
  - ALWAYS treat prompts as executable control logic; review branches, preconditions, permissions, state, and recovery behavior
  - ALWAYS optimize for recall first, then raise precision with evidence
  - ALWAYS distinguish behavioral bugs from general quality smells; a prompt bug causes wrong or unsafe agent behavior
  - ALWAYS treat user-decision UX failures as behavioral bugs when they can cause the user to choose the wrong path, fail to respond, misunderstand what is required, or lose control of the interaction
  - ALWAYS work from invariants, triggers, and failure modes, not style alone
  - ALWAYS treat negative-only prohibitions as bug hypotheses when they can prime the forbidden behavior, omit the required alternative, or make compliance hard to verify
  - ALWAYS treat prompts with more than 7 active constraints as high-density risk; prompts with more than 10 active constraints require decomposition, a validator, or an iterative self-check strategy
  - ALWAYS treat critical instructions buried in the middle of long active context as a defect hypothesis
  - ALWAYS load only the instructions needed for the active execution path; load the smallest decisive slice first for any reference that may affect routing, authority, safety, state, recovery, or output behavior
  - NEVER treat an uninspected dependency as irrelevant when it may affect routing, authority, safety, state, recovery, or output behavior
  - NEVER rely on a single review pass; require a layered review stack plus targeted validation scenarios
  - NEVER treat a compaction change as safe when it removes required constraints, triggers, or recovery steps
```

## Bounded Dependency Escalation

A `slice` is one contiguous excerpt from one dependency file: one TOC read, one section, or one contiguous line range. If a TOC read or section exceeds the slice budget, narrow it to the smallest contiguous subsection or range that can still resolve the question. Do not merge disjoint excerpts into one slice.

```pdsl
UNIT PromptBugFindingContextBudget

PURPOSE:
  Define bounded dependency escalation rules for prompt review passes.

STATE:
  - SET dependency_files_active: integer
    default: 1
  - SET dependency_lines_active: integer
    default: 120

RULES:
  - ALWAYS start with 1 slice from 1 dependency file (<= 120 raw lines per slice)
  - ALWAYS summarize each slice into the retained working set before any further escalation
  - ALWAYS keep at most 3 dependency files and <= 400 raw dependency lines in active review context at once
  - ALWAYS stop, checkpoint the unresolved dependency set, mark review PARTIAL, and ask user whether to expand scope when the next escalation would exceed budget or still requires whole-file loading
  - ALWAYS checkpoint the unresolved dependency set, mark review PARTIAL, and emit the explicit follow-up scope needed for a later run in non-interactive or CI execution; do not block waiting for input
  - ALWAYS define decisive dependency: a dependency whose normative text can change routing, authority, safety boundaries, required state, recovery behavior, output contract, or final status semantics for the hotspot under review
  - ALWAYS treat a dependency as checked only after the inspected slice is sufficient to resolve the hotspot-relevant normative effect
  - ALWAYS treat materiality as unresolved when proof of non-materiality is missing; never assume harmless
  - NEVER treat unresolved materiality as PASS
```

## Layer Map

| Layer | Question |
|---|---|
| L1 | Where are the highest-risk behavioral hotspots in the prompt stack? |
| L2 | What contracts, permissions, and invariants must always hold? |
| L3 | Which branches, states, handoffs, or refusals can break them? |
| L4 | Which universal prompt bug classes apply here? |
| L5 | Can a concrete counterexample dialogue or execution trace be constructed? |
| L6 | What dynamic validation would confirm or refute the suspected bug? |
| L7 | What is the review status, confidence, impact, and next action? |

## L1: Prompt Hotspot Mapping

Focus first on instructions most likely to create high-impact failures.

```pdsl
UNIT PromptBugFindingL1

PURPOSE:
  Identify and prioritize the highest-risk behavioral hotspots in the prompt stack.

DO:
  - SET hotspot_list: always-on system prompts, top-priority guardrails, user-confirmation rules, tool-use policies, write/deploy restrictions, and output contracts
  - RUN prioritization: route-controlling documents, conditional WHEN behavior, state/checkpoint managers, and recovery-after-failure controllers first
  - RUN inspection of every user-facing question, confirmation gate, options menu, fallback prompt, and suggested next-step block that can change what the user does next
  - RUN inspection of tool permissions, dependency loading, validation gates, context compaction, escalation, and multi-turn memory instructions
  - RUN inspection of negative-only guardrails, forbidden-word lists, and repeated descriptions of disallowed behavior; prioritize cases where the prompt does not state the allowed replacement action
  - RUN density check: count active requirements for the current response; mark > 7 as high-attention risk and > 10 as a decomposition hotspot unless validator-backed
  - RUN placement check: inspect long prompts for critical rules placed in the middle rather than near the active beginning, end, current-phase checklist, or final self-check
  - LOAD referenced skills, workflows, requirements, or examples by smallest decisive slice first; if relevance is still uncertain, keep escalating within the dependency budget; carry unresolved dependency forward as PARTIAL if budget would overflow
  - LOAD repository signals when available: recently edited prompts, repeated fixes, recurring review comments, long files, duplicated rules, and documents with many cross-references
```

## L2: Contract & Invariant Extraction

Extract what the instruction system requires before, during, and after execution.

```pdsl
UNIT PromptBugFindingL2

PURPOSE:
  Extract explicit and inferred contracts and invariants from the prompt instruction system.

DO:
  - SET preconditions: required files, loaded context, available tools, user approvals, mode flags, and environmental assumptions
  - SET postconditions: allowed outputs, required evidence, mandatory validation, required follow-up actions, response-completion gates, required terminal blocks or handoff prompts, required terminal block ordering, and stop conditions
  - SET authority_invariants: what the agent may do, must not do, and must ask before doing
  - SET constraint_framing_invariants: required alternative for each prohibited behavior; whether forbidden tokens are exact compliance targets or category-level boundaries
  - SET instruction_density_invariants: how many active requirements must be satisfied in the next response; which are primary, optional, duplicate, conditional, or validator-enforced
  - SET interaction_invariants: when asking the user for input, the prompt must explain why the input is needed, what good input looks like, what each option changes, how to reply, and which option is suggested when context clearly favors one path
  - SET routing_invariants: which request types trigger which workflow/dependency/branch, and which branches are mutually exclusive
  - SET state_invariants: what must survive across turns, checkpoints, compaction, retries, and resumptions
  - SET attention_placement_invariants: which critical rules must be surfaced early, late, or in the current-phase checklist

RULES:
  - ALWAYS mark inferred contracts as inferred rather than proven
  - ALWAYS retain a pinned working set: active hotspot and branch, decisive excerpts, extracted invariants, dependency decisions, open hypotheses, pending validations, and current review status before dropping raw context
```

## L3: Branch, State, and Handoff Exploration

Trace how prompt bugs appear when execution leaves the happy path.

```pdsl
UNIT PromptBugFindingL3

PURPOSE:
  Explore branches, state transitions, and handoffs that can expose prompt bugs.

DO:
  - RUN main path, ambiguous requests, overlapping triggers, missing prerequisites, missing files, denied permissions, tool failure, validation failure, and partial completion
  - RUN completion branch check: look for workflows that can stop after a summary, validator report, next-step menu, or checkpoint-looking block even though required final prompts, handoff blocks, or final response sections are still missing
  - RUN precedence check: when two rules apply, when a global rule conflicts with a conditional rule, or when recovery text contradicts the normal path
  - RUN user-decision branch check: unclear asks, ambiguous options, hidden option consequences, missing suggested path, generic recommendations, option overload, unclear reply formats, and confusing stage transitions
  - RUN multi-turn workflow check: stale assumptions, state loss after compaction, resumed execution without re-validation, and incorrect carryover from prior turns
  - RUN dependency-driven prompt check: circular loading, missing gating, unconditional loading, hidden required dependencies, and dependency-order bugs
  - RUN tool-driven prompt check: unsafe defaults, missing confirmation gates, wrong fallback behavior, silent failure, and retries with no exit condition
```

## L4: Universal Prompt Bug-Class Sweep

Apply the same defect lenses regardless of prompt style.

| Class | Typical failures |
|---|---|
| Instruction conflict & precedence | Contradictory rules, buried override, global rule silently defeated by local text |
| Trigger & gating | Missing `WHEN`, overlapping triggers, wrong branch, unconditional load, branch with no exit |
| Missing precondition | Prompt assumes files, tools, memory, approvals, or context that may not exist |
| Output contract | Missing schema, incomplete format, no evidence requirement, success criteria unclear |
| Completion & finalization gate | False completion criteria, response can end after summary/validation/next steps, required terminal blocks or handoff prompts missing, final block ordering unspecified |
| Tool-use & safety boundary | Writes before confirmation, unsafe action path, missing approval, invalid tool sequence |
| Interaction UX & choice architecture | Unexplained asks, ambiguous options, hidden consequences, no suggested option when one path is clearly best, generic follow-ups, unclear reply format, or option overload |
| Context & compaction | Critical rule dropped, oversized always-on text, missing summarize-and-drop, compaction loses invariants |
| Long-context attention | Critical rule buried in the middle of long context, active checklist absent, low-priority prose separates trigger from action |
| Memory & state | Implicit state, missing checkpoint, stale carryover, resume path skips re-checks |
| Recovery & escalation | No fallback, silent failure, infinite retry loop, no ask-user path, missing partial output behavior |
| Ambiguity & underspecification | Vague language, undefined actor, unclear authority, multiple valid interpretations |
| Overconstraint & impossibility | Requirements cannot all be satisfied, excessive coupling, impossible ordering |
| Instruction density | Too many simultaneous active requirements, duplicate constraints, unprioritized rule stacks, no validator for dense constraints |
| Negative constraint failure | Negative-only rule, forbidden behavior repeated unnecessarily, no allowed replacement behavior, no compliance check |
| Constraint realism | Exact word/token/character limits or many formatting rules without automated validation or post-processing |
| Security & compliance | Hallucination encouragement, source-free claims, authority leak, unsafe instruction injection path |
| Integration & handoff | Broken workflow routing, mismatched assumptions between docs, missing next-step contract |
| Observability & verification | No self-check, no evidence, failures hidden, compliance cannot be externally verified |

## L5: Counterexample Construction

A suspected prompt bug becomes much stronger when you can describe exactly how the agent fails.

```pdsl
UNIT PromptBugFindingL5

PURPOSE:
  Build or refute concrete counterexample dialogues or execution traces for suspected prompt bugs.

DO:
  - SET trigger: the smallest user request, prior state, loaded dependency set, tool result, or context-loss event needed to violate an invariant
  - SET failure_expression: input/state -> instruction path -> wrong behavior
  - RUN search for contradictory guards, explicit priority rules, or downstream checks that disprove the hypothesis
  - RUN negative-constraint test: show the forbidden item named in the prompt, the missing alternative, and the likely leakage path
  - RUN instruction-density test: count active constraints and show which constraint is likely to be dropped, contradicted, or unverifiable
  - RUN long-context placement test: show where the critical rule sits between lower-priority material and is not repeated in the current checklist or completion gate

RULES:
  - ALWAYS prefer concrete dialogue snippets, branch traces, or tool outcomes over abstract claims
  - ALWAYS lower confidence or discard the finding when no plausible failure trace can be constructed
```

## L6: Dynamic Validation Strategy

When static review is insufficient, specify the cheapest next proof.

```pdsl
UNIT PromptBugFindingL6

PURPOSE:
  Select the cheapest confirming dynamic validation for each unresolved prompt bug hypothesis.

DO:
  - RUN targeted eval prompts for ambiguous routing, conflicting priorities, or output-format defects
  - RUN positive-vs-negative A/B prompts when suspected defect is a negative-only prohibition; compare current prompt with version that states the required alternative behavior
  - RUN constraint-count stress tests when suspected defect is instruction density; run or specify cases at 3, 7, and 10+ active constraints
  - RUN forbidden-token leakage tests when exact banned words or phrases matter; prefer automated string checks
  - RUN long-context placement tests by moving a critical rule between beginning, middle, end, and current-checklist positions
  - RUN targeted dialogue tests for unclear questions, ambiguous options, suggested-option quality, fallback prompts, and transition clarity at user decision points
  - RUN adversarial prompts for jailbreak resistance, authority confusion, prompt injection handling, and unsafe fallback behavior
  - RUN multi-turn tests for checkpointing, compaction recovery, resumability, and stale-memory bugs
  - RUN tool-path tests for permission denial, validation failure, missing dependencies, and retry handling
  - RUN diff-aware regression tests after prompt changes to verify required behavior still holds

NOTES:
  Strong practical stack:
  1. Static prompt-engineering review for clarity, structure, and context design
  2. Defect-oriented prompt review plus targeted evals and compaction regressions for high-risk branches, safety boundaries, and instruction-stack state
  3. Feedback loop from human review, escaped defects, and production failures
  No single prompt review, model run, or evaluator is sufficient for high recall.
```

## L7: Reporting, Review Status, and Residual Risk

```pdsl
UNIT PromptBugFindingL7

PURPOSE:
  Produce the mandatory review status, findings, and residual risk report for prompt bug review.

DO:
  - EMIT Summary section with: review status (PASS/PARTIAL/FAIL), deterministic gate (PASS/FAIL/SKIPPED with reason if SKIPPED), scope reviewed, review basis (static/dynamic/static+dynamic), environment snapshot (model family, tool environment, conversation assumptions, loaded dependencies with sections/slices, runtime conditions), coverage summary (hotspots checked, dependencies checked, validations run/pending), constraint coverage (active instruction count, negative-only rules checked, forbidden-token constraints checked, critical rules in long-context middle positions)
  - EMIT per-finding: bug class, severity (CRITICAL/MAJOR/MINOR only), confidence (CONFIRMED/HIGH/MEDIUM/LOW), location, violated invariant or contract, minimal trigger or counterexample dialogue, likely bad behavior, evidence, proposed fix, best validation step
  - EMIT additional fields for Instruction density/Negative constraint failure/Long-context attention/Constraint realism findings: active constraint count, primary rule likely to fail, whether prompt gives positive replacement action, whether compliance can be checked mechanically/by self-check/only by human review
  - EMIT residual uncertainty: high-risk branches or dependencies not fully checked, dynamic validations not yet run, bug classes checked vs. only partially checked, reason for PARTIAL or FAIL status

RULES:
  - ALWAYS assign PASS only when: stated scope completed, every dependency in scope inspected enough to resolve hotspot-relevant normative effect (decisive or proved non-material), no confirmed or high-confidence material defect remains open, and residual risk is bounded explicitly
  - ALWAYS assign PARTIAL when: coverage incomplete, blocked, or waiting on decisive dependency checks, unresolved materiality decisions, unresolved hotspot-relevant normative effects, or dynamic validation
  - ALWAYS assign FAIL when: review path was invalid or at least one confirmed or high-confidence material defect remains open
  - ALWAYS assign PARTIAL when any dependency may still change hotspot behavior because its normative effect was not resolved
  - NEVER describe semantic review, checklist review, or manual inspection as deterministic, validator-backed, or tool-validated unless actual validator or tool output exists
  - ALWAYS reject any finding severity value outside CRITICAL, MAJOR, or MINOR
  - NEVER collapse uncertainty into a blanket PASS

NOTES:
  When paired with prompt-engineering.md: keep that document's required report section order. Put the six Summary fields at the top of Summary, then place dependency budget, loaded slices, and overflow handling in Context Budget & Evidence. Reflect hotspot coverage in Layer Summaries and Verification Checklist instead of creating a second competing report preamble.
```

## Execution Protocol

Use this sequence for each prompt hotspot:

```pdsl
UNIT PromptBugFindingExecution

PURPOSE:
  Execute the eight-step review sequence for each prompt hotspot.

DO:
  - RUN Step 1: map the active branch, authority boundary, dependent files, and the first decisive slices to inspect
  - RUN Step 2: extract explicit and inferred invariants, priorities, and stop conditions
  - RUN Step 3: walk the happy path and the most dangerous failure and recovery paths
  - RUN Step 4: sweep all prompt bug classes
  - RUN Step 5: count active constraints and inspect negative-only rules, forbidden-token salience, and critical-rule placement
  - RUN Step 6: build or refute a concrete counterexample dialogue or execution trace
  - RUN Step 7: propose the cheapest confirming dynamic validation
  - RUN Step 8: set overall review status, then report findings and residual risk

RULES:
  - ALWAYS prefer narrow prompt slices over loading the full instruction stack
  - ALWAYS load the smallest decisive slice before judging relevance of any reference that may affect routing, authority, safety, state, recovery, or output behavior; default to 1 contiguous slice <= 120 raw lines from 1 dependency file; narrow TOC reads or sections that exceed budget before counting as the slice
  - ALWAYS keep escalation bounded to <= 3 dependency files and <= 400 raw dependency lines; prefer TOC/section/range reads over whole-file loading
  - ALWAYS stop, checkpoint the unresolved dependency set, and mark review PARTIAL when the next escalation would exceed budget or still requires whole-file loading
  - ALWAYS summarize and drop raw text only after pinning the retained working set
  - ALWAYS review high-priority always-on text before low-priority examples and commentary
  - ALWAYS summarize active constraint set into primary/conditional/duplicate/validator-enforced groups when active prompt surface has > 7 constraints; mark hotspot unresolved or defective if > 10 remain without validation
  - ALWAYS prefer positive replacement rewrites over longer negative guardrail lists when proposing fixes
  - ALWAYS check cross-file boundaries early because prompt bugs often hide in mismatched assumptions between documents
```

## Integration with Studio

```pdsl
UNIT PromptBugFindingIntegration

PURPOSE:
  Define when and how to integrate this methodology with other Studio components.

WHEN:
  - REQUIRE user asks to find bugs, hidden failure modes, regressions, unsafe behavior, instruction conflicts, routing defects, or root causes in prompts or agent instruction documents

DO:
  - RUN this methodology as the behavioral defect search procedure for prompt review
  - RUN prompt-engineering.md for clarity, structure, anti-pattern, context-engineering, and improvement synthesis review alongside this methodology
  - RUN this methodology to treat interaction UX failures at decision points as prompt bugs, not merely style issues
  - RUN this methodology to treat compaction that removes required triggers, guardrails, or recovery paths as a prompt bug; treat safe compaction that merely improves efficiency as quality work only

RULES:
  - ALWAYS align with prompt-engineering.md v1.6 rules for positive action framing, instruction-density thresholds, negative-constraint handling, self-check, and long-context placement
```

## References

This methodology is operational and compact; these sources justify the added bug lenses:

- OpenAI prompt engineering best practices: instructions first, clear format examples, less imprecise wording, and positive replacement behavior instead of only prohibitions. https://help.openai.com/en/articles/6654000-using-advanced-prompt-engineering-techniques
- `Semantic Gravity Wells: Why Negative Constraints Backfire`: naming forbidden terms can prime the model toward violating the constraint. https://arxiv.org/abs/2601.08070
- `Curse of Instructions`: following all instructions degrades as simultaneous instruction count rises; self-refinement can partially improve dense-instruction prompts. https://openreview.net/forum?id=R6q67CDBCH
- `InFoBench`: complex instruction compliance should be evaluated by decomposed requirement-level checks. https://arxiv.org/abs/2401.03601
- `FollowBench`: progressively added constraints reveal fine-grained instruction-following failures. https://arxiv.org/abs/2310.20410
- `Lost in the Middle`: long-context models may underuse information in the middle of the input context. https://arxiv.org/abs/2307.03172
- `What Prompts Don't Say`: adding more requirements does not reliably improve performance when requirements conflict or exceed instruction-following capacity. https://arxiv.org/abs/2505.13360

## Validation

Review is complete when:

- [ ] Behavioral hotspots were identified and prioritized
- [ ] Explicit and inferred invariants were extracted
- [ ] Happy path, failure paths, and recovery paths were examined
- [ ] All prompt bug classes were swept for the target scope
- [ ] Negative-only prohibitions were checked for missing positive replacement behavior and forbidden-term priming
- [ ] Active instruction count was checked; `> 7` constraints were treated as risk and `> 10` constraints were decomposed, validator-backed, or reported as unresolved/defective
- [ ] Critical rules were checked for beginning/end/current-checklist placement rather than being buried in long-context middle sections
- [ ] Constraint realism was checked for exact word/token/character limits and dense formatting requirements without automated validation
- [ ] Each reported issue includes a plausible trigger or counterexample
- [ ] Missing proof was converted into a concrete dynamic validation step
- [ ] Review status, deterministic gate state, environment snapshot, coverage summary, and decisive dependency outcomes were reported explicitly
- [ ] Loaded dependency slices were bounded as contiguous TOC/section/range reads, any dependency concluded non-material was backed by inspected-slice proof, and any unresolved hotspot-relevant normative effect forced `PARTIAL` instead of `PASS`
- [ ] User-decision points were checked for explain-why, option clarity, option consequences, suggested-path quality, reply format, and fallback behavior whenever the reviewed scope contains interactive prompts
- [ ] For workflows or instructions with required terminal outputs, completion gates, required handoff blocks, and terminal block ordering were checked explicitly
- [ ] Confidence and residual uncertainty were reported explicitly
