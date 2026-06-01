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

- Treat prompts as executable control logic, not just prose. Review branches, preconditions, permissions, state, and recovery behavior.
- Optimize for recall first, then raise precision with evidence. Missing a real prompt bug is usually worse than inspecting one plausible hypothesis.
- Distinguish **behavioral bugs** from general quality smells. A prompt bug causes wrong or unsafe agent behavior, not merely awkward wording.
- Treat user-decision UX failures as behavioral bugs when they can cause the user to choose the wrong path, fail to respond, misunderstand what is required, or lose control of the interaction.
- Work from **invariants, triggers, and failure modes**, not from style alone.
- Treat negative-only prohibitions as bug hypotheses when they can prime the forbidden behavior, omit the required alternative, or make compliance hard to verify.
- Treat excessive simultaneous instructions as a behavioral risk. A prompt with `> 7` active constraints needs explicit density review; `> 10` active constraints needs decomposition, a validator, or an iterative self-check strategy before it can be considered low risk.
- Treat critical instructions buried in the middle of long active context as a defect hypothesis because models may underuse mid-context information.
- Load only the instructions needed for the active execution path, but do not treat an uninspected dependency as irrelevant. When a reference may affect routing, authority, safety, state, recovery, or output behavior, load the smallest decisive slice first and escalate only while the dependency remains materially unresolved.
- Define a `slice` as one contiguous excerpt from one dependency file: one TOC read, one section, or one contiguous line range. A TOC read counts as one slice only when the inspected TOC excerpt itself fits the slice budget; if the TOC is longer than the budget, narrow it to the smallest contiguous TOC subsection or line range that can still resolve the question. Use file metadata, section numbering, heading ranges, and targeted keyword searches to identify that smallest decisive contiguous excerpt. Do not merge disjoint excerpts and count them as one slice; if a section or TOC excerpt is longer than the budget, narrow it to the smallest contiguous subsection or range that can still resolve the question. This slice rule is part of bounded dependency escalation: start narrow, retain only the decisive excerpt, then escalate only if the dependency remains materially unresolved.
- Use bounded dependency escalation: start with `1` slice from `1` dependency file (`<= 120` raw lines per slice), summarize it into the retained working set, and keep at most `3` dependency files and `<= 400` raw dependency lines in active review context at once. If the next escalation would exceed that budget or still requires whole-file loading, stop, checkpoint the unresolved dependency, mark the review `PARTIAL`, and ask the user whether to expand scope or continue in a follow-up review. In non-interactive or CI-style execution, do not block on that question: checkpoint the unresolved dependency set, mark the review `PARTIAL`, and emit the explicit follow-up scope needed for a later run.
- A single review pass is insufficient. High-quality prompt bug discovery requires a **layered review stack** plus targeted validation scenarios.
- Safe context reduction is high priority, but a compaction change becomes a bug if it removes required constraints, triggers, or recovery steps.

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

- Start from always-on system prompts, top-priority guardrails, user-confirmation rules, tool-use policies, write/deploy restrictions, and output contracts.
- Prioritize documents that route execution, load other files, define conditional `WHEN` behavior, manage state/checkpoints, or control recovery after failure.
- Inspect every user-facing question, confirmation gate, options menu, fallback prompt, and suggested next-step block that can change what the user does next.
- Inspect instructions governing tool permissions, dependency loading, validation gates, context compaction, escalation, and multi-turn memory.
- Inspect negative-only guardrails, forbidden-word lists, and repeated descriptions of disallowed behavior. Prioritize cases where the prompt does not state the allowed replacement action.
- Inspect prompt surfaces with dense rule sets. Count active requirements for the current response, not total document bullets; mark `> 7` as high-attention risk and `> 10` as a decomposition hotspot unless validator-backed.
- Inspect long prompts for critical rules placed in the middle rather than near the active beginning, end, current-phase checklist, or final self-check.
- Expand to referenced skills, workflows, requirements, or examples by first checking the smallest decisive slice: entry conditions, authority/safety guards, state rules, recovery rules, and output contracts. If relevance is still uncertain, keep escalating within the dependency budget instead of assuming the dependency is harmless; if the next step would overflow the budget, carry the dependency forward as unresolved review debt and use the `PARTIAL` fallback.
- Use repository signals when available: recently edited prompts, repeated fixes, recurring review comments, long files, duplicated rules, and documents with many cross-references.

## L2: Contract & Invariant Extraction

Extract what the instruction system requires before, during, and after execution.

- Preconditions: required files, loaded context, available tools, user approvals, mode flags, and environmental assumptions.
- Postconditions: allowed outputs, required evidence, mandatory validation, required follow-up actions, response-completion gates, required terminal blocks or handoff prompts, required terminal block ordering, and stop conditions.
- Authority invariants: what the agent may do, must not do, and must ask before doing.
- Constraint-framing invariants: what the agent must do instead of each prohibited behavior; which forbidden tokens or topics are exact compliance targets; which prohibitions are category-level boundaries rather than words to repeat.
- Instruction-density invariants: how many active requirements must be satisfied in the next response; which requirements are primary, optional, duplicate, conditional, or validator-enforced.
- Interaction invariants: when asking the user for input, the prompt must explain why the input is needed, what good input looks like, what each option changes, how to reply, and which option is suggested when the context clearly favors one path.
- Routing invariants: which request types trigger which workflow, dependency, or branch, and which branches are mutually exclusive.
- State invariants: what must survive across turns, checkpoints, compaction, retries, and resumptions.
- Attention-placement invariants: which critical rules must be surfaced early, late, or in the current-phase checklist so they are not lost in long-context middle sections.
- Retained working set: keep a pinned summary of the active hotspot and branch, decisive excerpts, extracted invariants, dependency decisions, open hypotheses, pending validations, and current review status before dropping raw context.
- A dependency is **decisive** when its normative text can change routing, authority, safety boundaries, required state, recovery behavior, output contract, or final status semantics for the hotspot under review. Treat it as checked only after the inspected slice is sufficient to resolve that hotspot-relevant normative effect.
- A dependency is **proved non-material** only when the inspected slice is sufficient to show it does not change any of those behaviors for the hotspot and any remaining mentions are purely descriptive, duplicate, or outside the reviewed hotspot without adding further normative force. If that proof is missing, treat materiality as unresolved rather than harmless.
- If a contract is not explicit, infer it from wording, hierarchy, examples, dependent files, and enforcement language, but mark it as inferred rather than proven.

## L3: Branch, State, and Handoff Exploration

Trace how prompt bugs appear when execution leaves the happy path.

- Walk the main path, then examine ambiguous requests, overlapping triggers, missing prerequisites, missing files, denied permissions, tool failure, validation failure, and partial completion.
- Check completion branches explicitly: look for workflows that can stop after a summary, validator report, next-step menu, or checkpoint-looking block even though required final prompts, handoff blocks, or final response sections are still missing.
- Check precedence: what happens when two rules apply, when a global rule conflicts with a conditional rule, or when recovery text contradicts the normal path.
- Check user-decision branches explicitly: unclear asks, ambiguous options, hidden option consequences, missing suggested path, generic recommendations, option overload, unclear reply formats, and confusing stage transitions.
- For multi-turn workflows, inspect stale assumptions, state loss after compaction, resumed execution without re-validation, and incorrect carryover from prior turns.
- For dependency-driven prompts, inspect circular loading, missing gating, unconditional loading, hidden required dependencies, and dependency-order bugs.
- For tool-driven prompts, inspect unsafe defaults, missing confirmation gates, wrong fallback behavior, silent failure, and retries with no exit condition.

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
| Interaction UX & choice architecture | Unexplained asks, ambiguous options, hidden consequences, no suggested option when one path is clearly best, generic follow-ups, unclear reply format, or option overload that causes user confusion or wrong branching |
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

- Build the smallest trigger: user request, prior state, loaded dependency set, tool result, or context-loss event needed to violate an invariant.
- Express the failure as `input/state -> instruction path -> wrong behavior`.
- Prefer concrete dialogue snippets, branch traces, or tool outcomes over abstract claims.
- Search for contradictory guards, explicit priority rules, or downstream checks that disprove the hypothesis.
- For negative-constraint bugs, test whether the forbidden behavior is made more salient than the allowed replacement behavior. A minimal counterexample should show the prompt naming the forbidden item, the missing alternative, and the likely leakage path.
- For instruction-density bugs, count the active constraints and show which constraint is likely to be dropped, contradicted, or unverifiable under the smallest realistic task.
- For long-context placement bugs, show the active prompt path where the critical rule sits between lower-priority material and is not repeated in the current checklist or completion gate.
- If no plausible failure trace can be constructed, lower confidence or discard the finding.

## L6: Dynamic Validation Strategy

When static review is insufficient, specify the cheapest next proof.

- Use targeted eval prompts for ambiguous routing, conflicting priorities, or output-format defects.
- Use positive-vs-negative A/B prompts when the suspected defect is a negative-only prohibition. Compare the current prompt with a version that states the required alternative behavior.
- Use constraint-count stress tests when the suspected defect is instruction density. Run or specify cases at `3`, `7`, and `10+` active constraints and check per-constraint compliance.
- Use forbidden-token leakage tests when exact banned words or phrases matter. Prefer automated string checks when possible.
- Use long-context placement tests by moving a critical rule between beginning, middle, end, and current-checklist positions when placement sensitivity is part of the risk.
- Use targeted dialogue tests for unclear questions, ambiguous options, suggested-option quality, fallback prompts, and transition clarity at user decision points.
- Use adversarial prompts for jailbreak resistance, authority confusion, prompt injection handling, and unsafe fallback behavior.
- Use multi-turn tests for checkpointing, compaction recovery, resumability, and stale-memory bugs.
- Use tool-path tests for permission denial, validation failure, missing dependencies, and retry handling.
- Use diff-aware regression tests after prompt changes to verify required behavior still holds.
- Use cross-model checks only when model sensitivity is itself part of the risk hypothesis.

**Strong practical stack**:

- Static prompt-engineering review for clarity, structure, and context design
- Defect-oriented prompt review plus targeted evals and compaction regressions for high-risk branches, safety boundaries, and instruction-stack state
- Feedback loop from human review, escaped defects, and production failures

No single prompt review, model run, or evaluator is sufficient for high recall.

## L7: Reporting, Review Status, and Residual Risk

Every review report must start its `Summary` section with:

- Review status: `PASS`, `PARTIAL`, or `FAIL`
- Deterministic gate: `PASS`, `FAIL`, or `SKIPPED`; if `SKIPPED`, state why and explicitly state `no validator-backed evidence for this review path`
- Scope reviewed
- Review basis: `static`, `dynamic`, or `static + dynamic`
- Environment snapshot: model or model family if known, tool environment, conversation/history assumptions, loaded dependencies with the sections or slices inspected, and runtime conditions that may change behavior
- Coverage summary: hotspots checked, dependencies checked, validations run, and validations still pending
- Constraint coverage: active instruction count, negative-only rules checked, forbidden-token or category constraints checked, and any critical rules found in long-context middle positions

Status semantics:

- `PASS`: stated scope was completed, every dependency in scope was inspected enough to resolve its hotspot-relevant normative effect and was then either recorded as decisive or proved non-material by the decision rule above, no confirmed or high-confidence material defect remains open, and residual risk is bounded explicitly.
- `PARTIAL`: coverage is incomplete, blocked, or still waiting on decisive dependency checks, unresolved materiality decisions, unresolved hotspot-relevant normative effects, or dynamic validation.
- `FAIL`: the review path was invalid or at least one confirmed or high-confidence material defect remains open.

If any dependency may still change hotspot behavior because its normative effect was not resolved, the review is `PARTIAL`, not `PASS`.

Never describe semantic review, checklist review, or manual inspection as deterministic, validator-backed, or tool-validated unless actual validator or tool output exists. When the deterministic gate is `SKIPPED`, keep that separation explicit throughout the report.

Companion-format integration:

- When this methodology is paired with `prompt-engineering.md`, keep that document's required report section order.
- Put the six fields above at the top of `Summary`, then place dependency budget, loaded slices, and overflow handling in `Context Budget & Evidence`.
- Reflect hotspot coverage, decisive dependency checks, unresolved review debt, and pending validations in `Layer Summaries` and `Verification Checklist` instead of creating a second competing report preamble.

Report each finding with:

- Bug class
- Severity
- Confidence: `CONFIRMED`, `HIGH`, `MEDIUM`, or `LOW`
- Location
- Violated invariant or contract
- Minimal trigger or counterexample dialogue
- Likely bad behavior
- Evidence
- Proposed fix
- Best validation step

For `Instruction density`, `Negative constraint failure`, `Long-context attention`, or `Constraint realism` findings, also report:

- Active constraint count
- Primary rule likely to fail
- Whether the prompt gives a positive replacement action
- Whether compliance can be checked mechanically, by self-check, or only by human review

Residual uncertainty is mandatory:

- List high-risk branches or dependencies not fully checked.
- List dynamic validations not yet run.
- State which bug classes were checked and which were only partially checked.
- State why the final status is `PARTIAL` or `FAIL` whenever either value is used.
- Never collapse uncertainty into a blanket `PASS`.

## Execution Protocol

Use this sequence for each prompt hotspot:

1. Map the active branch, authority boundary, dependent files, and the first decisive slices to inspect.
2. Extract explicit and inferred invariants, priorities, and stop conditions.
3. Walk the happy path and the most dangerous failure and recovery paths.
4. Sweep all prompt bug classes.
5. Count active constraints and inspect negative-only rules, forbidden-token salience, and critical-rule placement.
6. Build or refute a concrete counterexample dialogue or execution trace.
7. Propose the cheapest confirming dynamic validation.
8. Set overall review status, then report findings and residual risk.

Efficiency rules:

- Prefer narrow prompt slices over loading the full instruction stack.
- When a reference may affect routing, authority, safety, state, recovery, or output behavior, load the smallest decisive slice before judging relevance; default to `1` contiguous slice from `1` dependency file — one TOC read, one section, or one contiguous line range (`<= 120` raw lines) — then summarize it into the retained working set before any further escalation. If the chosen TOC read or section exceeds that budget, narrow it first to a contiguous TOC subsection or line range before counting it as the slice.
- Keep escalation bounded to `<= 3` dependency files and `<= 400` raw dependency lines in active context; prefer TOC, section, or range reads over whole-file loading.
- If the next escalation would exceed that budget or still requires whole-file loading, stop, checkpoint the unresolved dependency set in the report, and mark the review `PARTIAL`. In interactive mode, ask the user whether to expand scope or continue in a follow-up review. In non-interactive or CI mode, emit the checkpoint plus the exact additional scope required for the next pass instead of waiting for input.
- Summarize and drop raw text only after pinning the retained working set.
- Review high-priority always-on text before low-priority examples and commentary.
- When the active prompt surface has `> 7` constraints, summarize the active set into primary / conditional / duplicate / validator-enforced groups before continuing; if `> 10` remain active without validation, mark the hotspot as unresolved or defective.
- Prefer positive replacement rewrites over longer negative guardrail lists when proposing fixes.
- Check cross-file boundaries early because prompt bugs often hide in mismatched assumptions between documents.

## Integration with Studio

- Use this methodology when the user asks to find bugs, hidden failure modes, regressions, unsafe behavior, instruction conflicts, routing defects, or root causes in prompts or agent instruction documents.
- Use `prompt-engineering.md` for clarity, structure, anti-pattern, context-engineering, and improvement synthesis review.
- Align with `prompt-engineering.md` v1.5 rules for positive action framing, instruction-density thresholds, negative-constraint handling, self-check, and long-context placement.
- Use this methodology as the **behavioral defect search procedure** for prompt review, while `prompt-engineering.md` remains the broader quality and design methodology.
- In prompt review, treat interaction UX failures that can mislead, block, or overload the user at decision points as prompt bugs, not merely style issues.
- In prompt review, treat safe compaction opportunities that merely improve efficiency as quality work, but treat compaction that removes required triggers, guardrails, or recovery paths as a prompt bug.

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
- [ ] No claim of `100%` detection or blanket coverage was made
