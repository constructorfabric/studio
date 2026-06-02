---
description: "Invoke when about to dispatch a cf-* sub-agent — applies dispatch protocol and selects Mode A (native) or Mode B (inline)."
---

# Sub-Agent Dispatch

```pdsl
UNIT SubAgentDispatch
PURPOSE: Apply dispatch protocol and select Mode A (native) or Mode B (inline) before any cf-* sub-agent dispatch.

STATE:
  - SET INLINE_FALLBACK:             bool  default: unset  scope: workflow-run
  - SET INLINE_FALLBACK_PROBED:      bool  default: false  scope: workflow-run
  - SET INLINE_FALLBACK_THIS_ROUND:  bool  default: false  scope: round
  - SET SUB_AGENT_SESSION_APPROVED:  bool  default: unset  scope: session

NOTES:
  Agent prompt sources live at {cf-studio-path}/.core/skills/studio/agents/{name}.md.
  Mode A: native dispatch — controller loads contract, synthesizes final prompt from contract + SHARED_CONTEXT_PACK, dispatches, consumes output.
  Mode B: inline — controller opens agent file, follows it as orchestration guidance, synthesizes final prompt, satisfies Response Completion Gate, returns declared output shape.
  If agent file has no explicit Response Completion Gate, default: return full declared output shape with no required field empty or null.
  CONTINUE in this protocol is a non-returning transfer of control — the called unit does not return to the caller.
  PostPlanDispatchGuard ALWAYS be invoked by DispatchGate when REVIEWER_EXECUTION_PLAN is non-null — see CONTINUE PostPlanDispatchGuard in DispatchGate DO block step 1.
  SEE: skills/studio/SKILL.md § Session Sub-Agent Approval Gate
```

```pdsl
UNIT DispatchGate
PURPOSE: Block dispatch until approval, inline-fallback, and contract-read gates all pass.

WHEN:
  - REQUIRE controller is about to dispatch a cf-* sub-agent

DO:
  - REQUIRE INLINE_FALLBACK != unset
     - REQUIRE INLINE_FALLBACK_PROBED == true
     - REQUIRE (SUB_AGENT_SESSION_APPROVED == true OR INLINE_FALLBACK == true)
  - REQUIRE REVIEWER_EXECUTION_PLAN is non-null:
       - CONTINUE PostPlanDispatchGuard
  - CONTINUE SubAgentContractReadGate
     (SubAgentContractReadGate chains to RegisteredNativeSubAgentSet when INLINE_FALLBACK==false, then to SubAgentModeSelect)

RULES:
  - ALWAYS apply Session Sub-Agent Approval Gate from skills/studio/SKILL.md before any dispatch
  - ALWAYS apply SKILL.md § Change-Review Fail-Closed Sentinel before any resolver/validator/reviewer dispatch when CHANGE_REVIEW == true
  - ALWAYS probe once per workflow run for INLINE_FALLBACK; NEVER inherit INLINE_FALLBACK from a prior workflow run
  - ALWAYS When SUB_AGENT_SESSION_APPROVED == true, re-derived workflow-run default is INLINE_FALLBACK=false; NEVER override to true without explicit user selection for the current documented scope
  - NEVER switch modes silently mid-workflow; if a mid-workflow re-probe yields a different mode result, ALWAYS surface the change to the user before continuing
  - ALWAYS When CHANGE_REVIEW dispatch site is blocked by missing approval, unresolved inline-fallback, or contract-read-and-use failure: NEVER substitute local git status/diff, cfs validate, local semantic review, findings, summaries, or remediation menus; may emit only the required gate menu or matching Dispatch blocked error, then STOP_TURN

ON_ERROR:
  INLINE_FALLBACK == unset ->
    CONTINUE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
    STOP_TURN
  INLINE_FALLBACK_PROBED != true ->
    CONTINUE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
    STOP_TURN
  SUB_AGENT_SESSION_APPROVED != true AND INLINE_FALLBACK != true ->
    CONTINUE {cf-studio-path}/.core/workflows/shared/inline-fallback-probe.md
    STOP_TURN
```

```pdsl
UNIT PostPlanDispatchGuard
PURPOSE: Block any substitution of local semantic analysis for planned reviewer sub-agent tasks when a planner-validated reviewer execution plan is active.

WHEN:
  - REQUIRE REVIEWER_EXECUTION_PLAN is non-null AND planned dispatch has not completed

- REQUIRE PRIORITY: When REVIEWER_EXECUTION_PLAN is non-null, this unit takes precedence — LocalAnalysisSubstitutionViolation supersedes the DispatchGate CHANGE_REVIEW gate-menu response for local-analysis prohibition events.

DO:
  - REQUIRE INLINE_FALLBACK == true:
       TRIGGER PlanRequiresNativeDispatch
  - RUN Check whether the current action constitutes local-analysis substitution as defined in RULES below.
  - REQUIRE local-analysis substitution detected:
       TRIGGER LocalAnalysisSubstitutionViolation
  - REQUIRE check passes clean:
       - CONTINUE SubAgentContractReadGate

RULES:
  - ALWAYS Local semantic analysis means any analysis, triage, summarization, or findings production performed by the controller itself rather than by a dispatched cf-* reviewer sub-agent. The listed examples are illustrative; any action that produces review output without sub-agent dispatch is prohibited.
  - NEVER substitute local semantic analysis for the planned reviewer sub-agent tasks defined in REVIEWER_EXECUTION_PLAN; prohibited local-analysis acts include but are not limited to: git diff triage, rg/grep sweeps, ad-hoc file reads used for review or findings purposes, manual diff inspection, local summarization of changes, and cfs validate
  - NEVER enter Mode B (inline fallback) for any task defined in REVIEWER_EXECUTION_PLAN — INLINE_FALLBACK==true is not an exception to this guard; if INLINE_FALLBACK==true and REVIEWER_EXECUTION_PLAN is non-null, ALWAYS emit the plan-requires-native-dispatch message and STOP_TURN
  - ALWAYS treat any such local-analysis substitution attempt as a dispatch protocol violation named LocalAnalysisSubstitutionViolation
  - ALWAYS surface LocalAnalysisSubstitutionViolation as a named error and STOP_TURN
  - NEVER emit findings, review summaries, or remediation outputs derived from local analysis while REVIEWER_EXECUTION_PLAN is set and dispatch has not completed
  - ALWAYS This unit does not apply after all planned tasks in REVIEWER_EXECUTION_PLAN have been dispatched and their outputs received; post-dispatch finding merges and summaries derived from sub-agent outputs are not local-analysis substitution.

ON_ERROR:
  LocalAnalysisSubstitutionViolation ->
    EMIT "Dispatch blocked: local semantic analysis must not substitute for planned reviewer sub-agent tasks defined in REVIEWER_EXECUTION_PLAN."
    EMIT "Recovery options:"
    EMIT "1. Return to native reviewer dispatch and continue the pending REVIEWER_EXECUTION_PLAN tasks"
    EMIT "2. Abort this review dispatch"
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN
  PlanRequiresNativeDispatch ->
    EMIT "Dispatch blocked: plan-requires-native-dispatch — INLINE_FALLBACK==true does not exempt tasks defined in REVIEWER_EXECUTION_PLAN from the native sub-agent dispatch requirement."
    EMIT "Recovery options:"
    EMIT "1. Turn off inline fallback for this step and continue with native reviewer dispatch"
    EMIT "2. Abort this review dispatch"
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT SubAgentModeSelect
PURPOSE: Select Mode A or Mode B and emit inline-fallback warning when required.

WHEN:
  - REQUIRE DispatchGate passes

DO:
  - SET mode = (INLINE_FALLBACK_THIS_ROUND == true OR INLINE_FALLBACK == true) ? B : A
  - REQUIRE mode == B:
    - CONTINUE InlineFallbackWarning

RULES:
  - ALWAYS Mode A is default when SUB_AGENT_SESSION_APPROVED == true and host supports native sub-agents
  - NEVER choose Mode B for convenience, latency, context pressure, or implementation preference
  - ALWAYS may use Mode B only after explicit user selection
  - ALWAYS When native sub-agents are unavailable, ALWAYS ask whether to use inline fallback or stop; NEVER default to Mode B
  - ALWAYS When SUB_AGENT_SESSION_APPROVED == true, every cf-* dispatch site ALWAYS use Mode A unless a later explicit user menu selection changes the mode for a documented scope
  - NEVER say "continuing locally / in a single read-only context and calling out the deviation" when the only blocker is explicit delegation policy
  - ALWAYS If controller wants to avoid native dispatch while native sub-agents are available, ALWAYS surface NativeSubAgentPolicyConflictMenu and STOP_TURN
```

```pdsl
UNIT InlineFallbackWarning
PURPOSE: Warn user before entering high-risk dispatch contexts under Mode B.

WHEN:
  - REQUIRE mode == B AND dispatch context is one of: brainstorm fan-out, long review loop, generate-author write, deterministic-validator subprocess

DO:
  - EMIT workflow-inline warning text if provided, else:
    - EMIT "Inline-fallback mode active — isolation, parallelism, and subprocess separation guarantees are reduced for this dispatch. Continue? [y/n]"
  - WAIT user.reply
  - STOP_TURN

WHEN:
  - REQUIRE user.reply received

DO:
  - REQUIRE normalize(user.reply) matches /^(y|yes)$/i:
    - CONTINUE SubAgentContractReadGate
  - RUN otherwise
    - EMIT "Dispatch aborted. Choose: (a) retry with inline-fallback acknowledged, (b) switch to parent workflow plan-escalation menu, (c) stop."
    - WAIT user.reply
    - STOP_TURN

RULES:
  - NEVER silently continue on non-affirmative reply
```

```pdsl
UNIT SubAgentContractReadGate
PURPOSE: Ensure agent contract is loaded and used before every dispatch.

WHEN:
  - REQUIRE before any DISPATCH or Mode B inline execution of a cf-* sub-agent

DO:
  - REQUIRE contract loaded from {cf-studio-path}/.core/skills/studio/agents/{name}.md
  - REQUIRE final prompt synthesized from loaded contract
  - REQUIRE final prompt contains all: required input fields, output fields, response format, invariants, enums, row/item schemas, completion gate, invalid-output conditions, final emit instruction

RULES:
  - ALWAYS load agent prompt source fresh for each dispatch synthesis
  - ALWAYS use loaded contract to synthesize the final dispatch prompt; task payload + general instructions is not a valid dispatch prompt
  - ALWAYS verify contract-use before dispatch by checking the synthesized final prompt includes all contract-required fields
  - ALWAYS treat as dispatch-blocking FAIL: (1) contract not loaded fresh; (2) contract path missing, unreadable, ambiguous, or maps to multiple contracts; (3) final prompt not synthesized from loaded contract; (4) final prompt omits or loosely summarizes required contract field, schema, invariant, completion gate, or final emit instruction; (5) controller cannot prove which loaded contract governed the dispatch
  - ALWAYS On FAIL: NEVER dispatch; ALWAYS emit matching Dispatch blocked error; ALWAYS STOP_TURN or route to caller's documented recovery menu
```

```pdsl
UNIT SynthesisInvariants
PURPOSE: Enforce lossless synthesis of the final dispatch prompt.

RULES:
  - ALWAYS Final dispatch prompt synthesis ALWAYS be lossless with respect to required semantics in the source prompt
  - ALWAYS carry forward all mandatory input fields, output fields, invariants, enums, row schemas, completion gates, and invalid-output conditions
  - NEVER replace a normative schema or invariant block with loose prose summary when doing so could omit required fields or behavioral constraints
  - ALWAYS If source prompt defines required per-row or per-item fields, ALWAYS restate those requirements explicitly in the final prompt
  - ALWAYS If required semantics cannot be preserved without ambiguity, ALWAYS include stricter source-side rules verbatim or near-verbatim
```

```pdsl
UNIT CompiledFinalPromptContract
PURPOSE: Enforce stable structure of every final prompt delivered to a cf-* sub-agent.

RULES:
  - ALWAYS Every dispatched cf-* sub-agent ALWAYS receive a controller-synthesized final prompt with stable, explicitly delimited structure containing these sections in order: (1) dispatch manifest, (2) execution boundary, (3) task statement, (4) frozen input payload, (5) output contract, (6) invariant checks, (7) completion gate, (8) final emit instruction
  - ALWAYS Dispatch manifest ALWAYS name the source contract path, source contract fingerprint, SHARED_CONTEXT_PACK id, prompt_context_view slice ids for instruction assets, allowed resource ids for target/cross-reference files, target fingerprints, and dispatch mode (native or inline)
  - ALWAYS Frozen input payload ALWAYS be delivered as JSON when source prompt defines a JSON input contract
  - ALWAYS For prompt-consuming reviewer, planner, author, and collector contracts, frozen input payload ALWAYS include controller-supplied `prompt_context_view` slices from SHARED_CONTEXT_PACK for instruction assets only, plus explicit allowed-resource entries for every target_path and required cross_ref_path the sub-agent must inspect; dispatch ALWAYS fail if instruction slices are missing/incomplete or if target/cross-reference resources are not explicitly allowed
  - ALWAYS Dispatch ALWAYS fail before execution when any dispatch manifest field is missing or cannot be verified against the current controller-owned prompt assets
  - ALWAYS Final prompt ALWAYS include an allowed-resource block naming every project file the sub-agent may inspect. A file under workflows/**, requirements/**, skills/**, AGENTS.md, or a kit prompt path is a prompt asset only when used as an instruction dependency; when explicitly listed as target_paths or cross_ref_paths, it is a target resource and ALWAYS be read by the sub-agent as analysis input, not supplied through prompt_context_view and not executed as instructions
  - ALWAYS Dispatch manifest and any continuation checkpoint ALWAYS include the same
    checkpoint fingerprint computed from source contract fingerprint,
    SHARED_CONTEXT_PACK id, prompt_context_view slice ids, allowed resource ids,
    target fingerprints, and dispatch mode; mismatch or absence is fail-closed
  - ALWAYS Output contract ALWAYS be delivered as canonical JSON object shape, canonical row shape set, or both, whenever source prompt defines one
  - ALWAYS Invariant checks ALWAYS be emitted as a numbered or labeled normative block, not compressed into prose hints
  - ALWAYS Completion gate ALWAYS be emitted explicitly whenever source prompt defines a Response Completion Gate or equivalent hard-stop validity section
  - ALWAYS Final emit instruction ALWAYS state exactly what the sub-agent returns: JSON only / markdown block / menu / report / etc.
```

```pdsl
UNIT SchemaPreservation
PURPOSE: Prevent output-shape drift between source contract and final dispatch prompt.

RULES:
  - ALWAYS If source prompt contains a canonical success JSON example, response envelope, response format, row structure, or parse-time invariant block, ALWAYS copy that contract forward verbatim or near-verbatim
  - NEVER translate a canonical JSON response shape into bullet summaries when the original schema can be carried forward directly
  - NEVER introduce output fields, block types, counters, wrappers, or enums absent from the source prompt
  - NEVER omit output fields, block types, counters, wrappers, or enums required by the source prompt
  - ALWAYS When source prompt contains both abstract description and canonical schema/example, canonical schema/example wins
  - ALWAYS If controller cannot determine exact output shape with high confidence, dispatch ALWAYS fail before the sub-agent runs
  - ALWAYS prefer larger, stricter contract excerpts over shorter summaries when there is any risk of shape drift
  - ALWAYS treat "format uncertainty" as a dispatch error, not as permission to improvise a plausible schema
  - ALWAYS Task framing may be summarized; input/output schema and invariants NEVER be summarized loosely
```

```pdsl
UNIT SubAgentDispatchInstructionFileAuthoringBoundary
PURPOSE: Prevent direct instruction-file writes when cf-generate author dispatch is available.

RULES:
  - ALWAYS Instruction-file targets: paths under workflows/**, requirements/**, any AGENTS.md, any skills/**/SKILL.md, any skills/**/agents/*.md, and equivalent prompt/agent contract files
  - ALWAYS use generate selector + selected-author dispatch path when an instruction-file target has a cf-generate author dispatch path
  - NEVER use apply_patch/Edit/Write/MultiEdit/NotebookEdit/shell-write directly on instruction-file targets while native author dispatch is available
  - ALWAYS INLINE_FALLBACK=true means Mode B execution of the selected author contract; it is NOT permission for controller-local manual patching
  - ALWAYS If controller detects it is about to manually patch an instruction-file target while native author dispatch is available: ALWAYS STOP, keep file untouched, route to workflows/generate/phase-1.5-author-plan.md then workflows/generate/phase-4-write.md
  - ALWAYS Controller-local instruction-file edits allowed only in a documented emergency fallback after explicit user mode selection naming the files and stating why the author-dispatch path is unavailable or blocked

ON_ERROR:
  manual_instruction_patch_attempt ->
    EMIT "Dispatch blocked: instruction-file writes must go through cf-generate author dispatch."
    STOP_TURN
```

```pdsl
UNIT RegisteredNativeSubAgentSet
PURPOSE: Determine whether a named cf-* sub-agent is registered in the host's dispatch tool list.

DO:
  - REQUIRE host announces tool list at session start:
    - SET registered = (cf-{name} present in announced list)
  - RUN otherwise IF agent referenced by name in Skill/Agent-style tool definition surfaced to controller:
    - SET registered = true
  - RUN otherwise
    - SET registered = false
    - EMIT_MENU NativeAgentUnavailableMenu
    - WAIT user.reply
    - STOP_TURN
  - REQUIRE registered == true:
    - CONTINUE SubAgentModeSelect

RULES:
  - ALWAYS default to unregistered when neither method can resolve membership
  - NEVER attempt a probe dispatch to resolve membership; doing so would consume SUB_AGENT_SESSION_APPROVED capacity without authorization

MENU NativeAgentUnavailableMenu:
  TITLE: |
    The requested native cf-* sub-agent is not registered in this host.

    Options:
    1. Use inline fallback for this workflow step
    2. Switch mode or choose a different registered agent
    3. Abort this dispatch

    Suggested: 3 when isolation is required; choose 1 only for a bounded task
    where inline execution is acceptable.
    Reply with 1, 2, or 3.
  OPTIONS:
    1 -> SET INLINE_FALLBACK_THIS_ROUND = true; CONTINUE caller availability recovery path
    2 -> EMIT "Name the mode or registered agent to use instead."; WAIT user.reply; STOP_TURN
    3 -> EMIT "Dispatch aborted because the requested native sub-agent is unavailable."; STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, or 3. Option 1 uses inline fallback for this workflow step, option 2 lets you name a different mode or registered agent, and option 3 aborts this dispatch."
    WAIT user.reply
    STOP_TURN
```

```pdsl
UNIT InlineFallbackThisRound
PURPOSE: Manage the iteration-scoped inline-fallback flag for brainstorm loop rounds.

STATE:
  - SET INLINE_FALLBACK_THIS_ROUND: bool  default: false  scope: round

RULES:
  - ALWAYS Scope: one round of the brainstorm loop (or any caller-defined unit of work that documents the same scope)
  - ALWAYS default to false at the start of every round
  - ALWAYS Set only by the calling workflow's availability-check recovery menu when user selects "inline this round" option
  - NEVER carry the flag across iterations; calling workflow is responsible for clearing it
  - ALWAYS When INLINE_FALLBACK_THIS_ROUND == true: round uses Mode B regardless of session-level INLINE_FALLBACK
  - ALWAYS When INLINE_FALLBACK_THIS_ROUND == false: session-level INLINE_FALLBACK governs the round
```

```pdsl
ON_ERROR:
  source_contract_not_loaded ->
    EMIT "Dispatch blocked: sub-agent contract was not loaded before prompt synthesis."
    STOP_TURN

  source_contract_not_used ->
    EMIT "Dispatch blocked: final dispatch prompt was not synthesized from the loaded sub-agent contract."
    STOP_TURN

  source_contract_missing_or_unreadable ->
    EMIT "Dispatch blocked: sub-agent contract source is missing, unreadable, or ambiguous."
    STOP_TURN

  output_shape_uncertain ->
    EMIT "Dispatch blocked: sub-agent output contract could not be preserved exactly."
    STOP_TURN

  source_contract_summary_would_drop_fields ->
    EMIT "Dispatch blocked: summary would drop required contract fields or invariants."
    STOP_TURN

  unresolved_native_dispatch_state ->
    EMIT "Dispatch blocked: native dispatch state unresolved; re-run the inline fallback probe and checkpoint the dispatch manifest fingerprint before retrying."
    STOP_TURN

  prompt_context_view_missing_or_unverified ->
    EMIT "Dispatch blocked: prompt_context_view slices are missing, incomplete, or unverifiable against SHARED_CONTEXT_PACK."
    STOP_TURN

  checkpoint_fingerprint_mismatch ->
    EMIT "Dispatch blocked: checkpoint fingerprint does not match the current dispatch manifest."
    STOP_TURN
```
