---
description: "Invoke when about to dispatch a cf-* sub-agent — applies dispatch protocol and selects Mode A (native) or Mode B (inline)."
---

# Sub-Agent Dispatch

```text
UNIT SubAgentDispatch
PURPOSE: Apply dispatch protocol and select Mode A (native) or Mode B (inline) before any cf-* sub-agent dispatch.

STATE:
  INLINE_FALLBACK:             bool  default: unset  scope: workflow-run
  INLINE_FALLBACK_PROBED:      bool  default: false  scope: workflow-run
  INLINE_FALLBACK_THIS_ROUND:  bool  default: false  scope: round
  SUB_AGENT_SESSION_APPROVED:  bool  default: unset  scope: session

NOTES:
  Agent prompt sources live at {cf-studio-path}/.core/skills/studio/agents/{name}.md.
  Mode A: native dispatch — controller loads contract, synthesizes final prompt from contract + SHARED_CONTEXT_PACK, dispatches, consumes output.
  Mode B: inline — controller opens agent file, follows it as orchestration guidance, synthesizes final prompt, satisfies Response Completion Gate, returns declared output shape.
  If agent file has no explicit Response Completion Gate, default: return full declared output shape with no required field empty or null.
  CONTINUE in this protocol is a non-returning transfer of control — the called unit does not return to the caller.
  PostPlanDispatchGuard MUST be invoked by DispatchGate when REVIEWER_EXECUTION_PLAN is non-null — see CONTINUE PostPlanDispatchGuard in DispatchGate DO block step 1.
  SEE: skills/studio/SKILL.md § Session Sub-Agent Approval Gate
```

```text
UNIT DispatchGate
PURPOSE: Block dispatch until approval, inline-fallback, and contract-read gates all pass.

WHEN: controller is about to dispatch a cf-* sub-agent

DO:
  1. IF REVIEWER_EXECUTION_PLAN is non-null:
       CONTINUE PostPlanDispatchGuard
  2. REQUIRE INLINE_FALLBACK != unset
     REQUIRE INLINE_FALLBACK_PROBED == true
     REQUIRE (SUB_AGENT_SESSION_APPROVED == true OR INLINE_FALLBACK == true)
  3. CONTINUE SubAgentContractReadGate
     (SubAgentContractReadGate chains to RegisteredNativeSubAgentSet when INLINE_FALLBACK==false, then to SubAgentModeSelect)

RULES:
  - MUST apply Session Sub-Agent Approval Gate from skills/studio/SKILL.md before any dispatch
  - MUST apply SKILL.md § Change-Review Fail-Closed Sentinel before any resolver/validator/reviewer dispatch when CHANGE_REVIEW == true
  - MUST probe once per workflow run for INLINE_FALLBACK; MUST_NOT inherit INLINE_FALLBACK from a prior workflow run
  - When SUB_AGENT_SESSION_APPROVED == true, re-derived workflow-run default is INLINE_FALLBACK=false; MUST_NOT override to true without explicit user selection for the current documented scope
  - MUST_NOT switch modes silently mid-workflow; if a mid-workflow re-probe yields a different mode result, MUST surface the change to the user before continuing
  - When CHANGE_REVIEW dispatch site is blocked by missing approval, unresolved inline-fallback, or contract-read-and-use failure: MUST_NOT substitute local git status/diff, cfs validate, local semantic review, findings, summaries, or remediation menus; MAY emit only the required gate menu or matching Dispatch blocked error, then STOP_TURN

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

```text
UNIT PostPlanDispatchGuard
PURPOSE: Block any substitution of local semantic analysis for planned reviewer sub-agent tasks when a planner-validated reviewer execution plan is active.

WHEN: REVIEWER_EXECUTION_PLAN is non-null AND planned dispatch has not completed

PRIORITY: When REVIEWER_EXECUTION_PLAN is non-null, this unit takes precedence — LocalAnalysisSubstitutionViolation supersedes the DispatchGate CHANGE_REVIEW gate-menu response for local-analysis prohibition events.

DO:
  1. Check whether the current action constitutes local-analysis substitution as defined in RULES below.
  2. IF local-analysis substitution detected:
       TRIGGER LocalAnalysisSubstitutionViolation
  3. IF check passes clean:
       CONTINUE SubAgentContractReadGate

RULES:
  - Local semantic analysis means any analysis, triage, summarization, or findings production performed by the controller itself rather than by a dispatched cf-* reviewer sub-agent. The listed examples are illustrative; any action that produces review output without sub-agent dispatch is prohibited.
  - MUST_NOT substitute local semantic analysis for the planned reviewer sub-agent tasks defined in REVIEWER_EXECUTION_PLAN; prohibited local-analysis acts include but are not limited to: git diff triage, rg/grep sweeps, ad-hoc file reads used for review or findings purposes, manual diff inspection, local summarization of changes, and cfs validate
  - MUST_NOT enter Mode B (inline fallback) for any task defined in REVIEWER_EXECUTION_PLAN — INLINE_FALLBACK==true is not an exception to this guard; if INLINE_FALLBACK==true and REVIEWER_EXECUTION_PLAN is non-null, MUST emit the plan-requires-native-dispatch message and STOP_TURN
  - MUST treat any such local-analysis substitution attempt as a dispatch protocol violation named LocalAnalysisSubstitutionViolation
  - MUST surface LocalAnalysisSubstitutionViolation as a named error and STOP_TURN
  - MUST_NOT emit findings, review summaries, or remediation outputs derived from local analysis while REVIEWER_EXECUTION_PLAN is set and dispatch has not completed
  - This unit does not apply after all planned tasks in REVIEWER_EXECUTION_PLAN have been dispatched and their outputs received; post-dispatch finding merges and summaries derived from sub-agent outputs are not local-analysis substitution.

ON_ERROR:
  LocalAnalysisSubstitutionViolation ->
    EMIT "Dispatch blocked: local semantic analysis must not substitute for planned reviewer sub-agent tasks defined in REVIEWER_EXECUTION_PLAN."
    STOP_TURN
  INLINE_FALLBACK == true AND REVIEWER_EXECUTION_PLAN is non-null ->
    EMIT "Dispatch blocked: plan-requires-native-dispatch — INLINE_FALLBACK==true does not exempt tasks defined in REVIEWER_EXECUTION_PLAN from the native sub-agent dispatch requirement."
    STOP_TURN
```

```text
UNIT SubAgentModeSelect
PURPOSE: Select Mode A or Mode B and emit inline-fallback warning when required.

WHEN: DispatchGate passes

DO:
  SET mode = (INLINE_FALLBACK_THIS_ROUND == true OR INLINE_FALLBACK == true) ? B : A
  IF mode == B:
    CONTINUE InlineFallbackWarning

RULES:
  - Mode A is default when SUB_AGENT_SESSION_APPROVED == true and host supports native sub-agents
  - MUST_NOT choose Mode B for convenience, latency, context pressure, or implementation preference
  - MAY use Mode B only after explicit user selection
  - When native sub-agents are unavailable, MUST ask whether to use inline fallback or stop; MUST_NOT default to Mode B
  - When SUB_AGENT_SESSION_APPROVED == true, every cf-* dispatch site MUST use Mode A unless a later explicit user menu selection changes the mode for a documented scope
  - MUST_NOT say "continuing locally / in a single read-only context and calling out the deviation" when the only blocker is explicit delegation policy
  - If controller wants to avoid native dispatch while native sub-agents are available, MUST surface NativeSubAgentPolicyConflictMenu and STOP_TURN
```

```text
UNIT InlineFallbackWarning
PURPOSE: Warn user before entering high-risk dispatch contexts under Mode B.

WHEN: mode == B AND dispatch context is one of: brainstorm fan-out, long review loop, generate-author write, deterministic-validator subprocess

DO:
  EMIT workflow-inline warning text if provided, else:
    EMIT "Inline-fallback mode active — isolation, parallelism, and subprocess separation guarantees are reduced for this dispatch. Continue? [y/n]"
  WAIT user.reply
  STOP_TURN

WHEN: user.reply received

DO:
  IF normalize(user.reply) matches /^(y|yes)$/i:
    CONTINUE
  ELSE:
    EMIT "Dispatch aborted. Choose: (a) retry with inline-fallback acknowledged, (b) switch to parent workflow plan-escalation menu, (c) stop."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST_NOT silently continue on non-affirmative reply
```

```text
UNIT SubAgentContractReadGate
PURPOSE: Ensure agent contract is loaded and used before every dispatch.

WHEN: before any DISPATCH, PARALLEL_DISPATCH, RE-DISPATCH, or Mode B inline execution of a cf-* sub-agent

DO:
  REQUIRE contract loaded from {cf-studio-path}/.core/skills/studio/agents/{name}.md
  REQUIRE final prompt synthesized from loaded contract
  REQUIRE final prompt contains all: required input fields, output fields, response format, invariants, enums, row/item schemas, completion gate, invalid-output conditions, final emit instruction

RULES:
  - MUST load agent prompt source fresh for each dispatch synthesis
  - MUST use loaded contract to synthesize the final dispatch prompt; task payload + general instructions is not a valid dispatch prompt
  - MUST verify contract-use before dispatch by checking the synthesized final prompt includes all contract-required fields
  - MUST treat as dispatch-blocking FAIL: (1) contract not loaded fresh; (2) contract path missing, unreadable, ambiguous, or maps to multiple contracts; (3) final prompt not synthesized from loaded contract; (4) final prompt omits or loosely summarizes required contract field, schema, invariant, completion gate, or final emit instruction; (5) controller cannot prove which loaded contract governed the dispatch
  - On FAIL: MUST_NOT dispatch; MUST emit matching Dispatch blocked error; MUST STOP_TURN or route to caller's documented recovery menu
```

```text
UNIT SynthesisInvariants
PURPOSE: Enforce lossless synthesis of the final dispatch prompt.

RULES:
  - Final dispatch prompt synthesis MUST be lossless with respect to required semantics in the source prompt
  - MUST carry forward all mandatory input fields, output fields, invariants, enums, row schemas, completion gates, and invalid-output conditions
  - MUST_NOT replace a normative schema or invariant block with loose prose summary when doing so could omit required fields or behavioral constraints
  - If source prompt defines required per-row or per-item fields, MUST restate those requirements explicitly in the final prompt
  - If required semantics cannot be preserved without ambiguity, MUST include stricter source-side rules verbatim or near-verbatim
```

```text
UNIT CompiledFinalPromptContract
PURPOSE: Enforce stable structure of every final prompt delivered to a cf-* sub-agent.

RULES:
  - Every dispatched cf-* sub-agent MUST receive a controller-synthesized final prompt with stable, explicitly delimited structure containing these sections in order: (1) dispatch manifest, (2) execution boundary, (3) task statement, (4) frozen input payload, (5) output contract, (6) invariant checks, (7) completion gate, (8) final emit instruction
  - Dispatch manifest MUST name the source contract path, source contract fingerprint, SHARED_CONTEXT_PACK id, prompt_context_view slice ids, allowed resource ids, target fingerprints, and dispatch mode (native or inline)
  - Frozen input payload MUST be delivered as JSON when source prompt defines a JSON input contract
  - For prompt-consuming reviewer, planner, author, and collector contracts, frozen input payload MUST include the controller-supplied `prompt_context_view` slices from SHARED_CONTEXT_PACK that cover every target path and required cross-reference; dispatch MUST fail if the slices are missing, incomplete, or replaced by instructions to reopen workflow/requirement/skill/AGENTS files from disk
  - Dispatch MUST fail before execution when any dispatch manifest field is missing or cannot be verified against the current controller-owned prompt assets
  - Final prompt MUST include an allowed-resource block naming any non-prompt project files the sub-agent may inspect; prompt assets under workflows/**, requirements/**, skills/**, AGENTS.md, kit prompt files, and agent prompt files MUST be supplied through `prompt_context_view`, not reopened by the sub-agent
  - Dispatch manifest and any continuation checkpoint MUST include the same
    checkpoint fingerprint computed from source contract fingerprint,
    SHARED_CONTEXT_PACK id, prompt_context_view slice ids, allowed resource ids,
    target fingerprints, and dispatch mode; mismatch or absence is fail-closed
  - Output contract MUST be delivered as canonical JSON object shape, canonical row shape set, or both, whenever source prompt defines one
  - Invariant checks MUST be emitted as a numbered or labeled normative block, not compressed into prose hints
  - Completion gate MUST be emitted explicitly whenever source prompt defines a Response Completion Gate or equivalent hard-stop validity section
  - Final emit instruction MUST state exactly what the sub-agent returns: JSON only / markdown block / menu / report / etc.
```

```text
UNIT SchemaPreservation
PURPOSE: Prevent output-shape drift between source contract and final dispatch prompt.

RULES:
  - If source prompt contains a canonical success JSON example, response envelope, response format, row structure, or parse-time invariant block, MUST copy that contract forward verbatim or near-verbatim
  - MUST_NOT translate a canonical JSON response shape into bullet summaries when the original schema can be carried forward directly
  - MUST_NOT introduce output fields, block types, counters, wrappers, or enums absent from the source prompt
  - MUST_NOT omit output fields, block types, counters, wrappers, or enums required by the source prompt
  - When source prompt contains both abstract description and canonical schema/example, canonical schema/example wins
  - If controller cannot determine exact output shape with high confidence, dispatch MUST fail before the sub-agent runs
  - MUST prefer larger, stricter contract excerpts over shorter summaries when there is any risk of shape drift
  - MUST treat "format uncertainty" as a dispatch error, not as permission to improvise a plausible schema
  - Task framing MAY be summarized; input/output schema and invariants MUST NOT be summarized loosely
```

```text
UNIT InstructionFileAuthoringBoundary
PURPOSE: Prevent direct instruction-file writes when cf-generate author dispatch is available.

RULES:
  - Instruction-file targets: paths under workflows/**, requirements/**, any AGENTS.md, any skills/**/SKILL.md, any skills/**/agents/*.md, and equivalent prompt/agent contract files
  - MUST use generate selector + selected-author dispatch path when an instruction-file target has a cf-generate author dispatch path
  - MUST_NOT use apply_patch/Edit/Write/MultiEdit/NotebookEdit/shell-write directly on instruction-file targets while native author dispatch is available
  - INLINE_FALLBACK=true means Mode B execution of the selected author contract; it is NOT permission for controller-local manual patching
  - If controller detects it is about to manually patch an instruction-file target while native author dispatch is available: MUST STOP, keep file untouched, route to workflows/generate/phase-1.5-author-plan.md then workflows/generate/phase-4-write.md
  - Controller-local instruction-file edits allowed only in a documented emergency fallback after explicit user mode selection naming the files and stating why the author-dispatch path is unavailable or blocked

ON_ERROR:
  manual_instruction_patch_attempt ->
    EMIT "Dispatch blocked: instruction-file writes must go through cf-generate author dispatch."
    STOP_TURN
```

```text
UNIT RegisteredNativeSubAgentSet
PURPOSE: Determine whether a named cf-* sub-agent is registered in the host's dispatch tool list.

DO:
  IF host announces tool list at session start:
    SET registered = (cf-{name} present in announced list)
  ELSE IF agent referenced by name in Skill/Agent-style tool definition surfaced to controller:
    SET registered = true
  ELSE:
    SET registered = false
    EMIT_MENU NativeAgentUnavailableMenu
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST default to unregistered when neither method can resolve membership
  - MUST_NOT attempt a probe dispatch to resolve membership; doing so would consume SUB_AGENT_SESSION_APPROVED capacity without authorization

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
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN
```

```text
UNIT InlineFallbackThisRound
PURPOSE: Manage the iteration-scoped inline-fallback flag for brainstorm loop rounds.

STATE:
  INLINE_FALLBACK_THIS_ROUND: bool  default: false  scope: round

RULES:
  - Scope: one round of the brainstorm loop (or any caller-defined unit of work that documents the same scope)
  - MUST default to false at the start of every round
  - Set only by the calling workflow's availability-check recovery menu when user selects "inline this round" option
  - MUST_NOT carry the flag across iterations; calling workflow is responsible for clearing it
  - When INLINE_FALLBACK_THIS_ROUND == true: round uses Mode B regardless of session-level INLINE_FALLBACK
  - When INLINE_FALLBACK_THIS_ROUND == false: session-level INLINE_FALLBACK governs the round
```

```text
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
