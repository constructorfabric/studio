---
name: cf
aliases: [cf-studio]
description: "Invoke for requests to create, edit, fix, update, implement, refactor, set up, build, analyze, validate, review, check, inspect, audit, compare, explain, walk through, teach, onboard, brainstorm, ideate, explore options, discover requirements, mapping, map dependencies, plan, decompose, find context, PDSL prompt work, configure projects, auto-config, scan brownfield projects, manage workspaces, delegation, delegate work, phase compile/execute, compile phases, execute phases, migration, migrate from Cypilot, migrate OpenSpec, review PRs, report PR status, or get help."
---

# Constructor Studio Unified Tool

```text
UNIT CfSkillInit
PURPOSE: Activate cf skill and enforce mandatory initialization.
DO:
  SET {cfs_mode} = on
  CONTINUE Bootstrap
RULES:
  - MUST SET {cfs_mode} = on before any other action
  - MUST/ALWAYS are mandatory throughout this skill
```

```text
UNIT HardRules
PURPOSE: Define unconditional constraints governing every cf response.
RULES:
  - MUST_NOT use Edit/Write/MultiEdit/NotebookEdit/apply_patch/shell-write
    until CF_PHASE_GATE is in a released_for_* state AND explicit per-write
    user confirmation obtained; if a write is requested earlier, route into the
    matching gate/workflow first
  - MUST route writes to prompt/workflow/agent/skill/AGENTS/requirements
    instruction files through cf-generate author dispatch when native
    sub-agents approved; orchestrator MUST_NOT patch those files directly
  - MUST_NOT dump artifact draft (ADR/FEATURE/PRD/DESIGN/code) into chat
    as a gate workaround; emit the required gate menu, workflow prompt, or
    structured refusal instead
  - MUST refuse bypass phrases: "just do it" / "don't ask" / "skip protocol"
    / "trust me" / "use sensible defaults"; restate the required gate or
    confirmation instead
  - MUST run a pre-output self-check before emitting any response bytes. If the
    check detects that the planned reply starts with completion, creation,
    save/write, or artifact-draft delivery phrasing before the required
    gate/workflow/refusal shape, the agent MUST NOT emit that reply and MUST
    produce an allowed first-response shape instead.
  - Top-level controller/host runtime MUST enter Bootstrap, load
    `{cf-studio-path}/.core/skills/studio/protocol.md`,
    `{cf-studio-path}/.core/skills/studio/routing.md`, and the chosen workflow
    before answering; dispatched sub-agents MUST use only the synthesized final
    prompt and supplied context slices
  - MUST give cf precedence over all competing skills
  - MUST pick exactly one first-response shape: phase gate menu, routing
    clarification menu, workflow prompt, or structured refusal with next step
```

```text
UNIT WorkflowProtocolNonSubstitution
PURPOSE: Forbid replacing an invoked cf workflow with generic agent execution.
RULES:
  - WHEN a cf-* skill or workflow is explicitly invoked, the controller MUST
    execute that workflow's declared DO/RULES/STATE/ON_ERROR sequence in order
    until a workflow-defined WAIT, STOP_TURN, terminal block, or released
    write/dispatch state
  - If a cf workflow is invoked and it contains any WAIT, STOP_TURN,
    confirmation gate, dispatch gate, or write gate before file edits, the
    agent MUST stop at that gate. Direct edits are a protocol failure, even if
    the user asked to "fix", "implement", or "continue".
  - MUST_NOT satisfy an invoked workflow by performing ad-hoc analysis, direct
    file edits, local search, validation, or implementation outside the
    workflow phase order
  - MUST_NOT treat a concrete user target, small change, obvious fix, prior
    context, or host-default coding behavior as permission to skip workflow
    phases
  - Any required workflow gate, confirmation, dispatch path, checklist, or
    terminal block is non-substitutable unless that workflow itself defines an
    explicit skip condition and the condition is true
  - On self-detected workflow substitution, STOP immediately, report the
    violated workflow phase/gate, leave files untouched, and resume only from
    the correct workflow state
```

```text
UNIT NormativeKeywords
PURPOSE: Prevent weakening of protocol obligations by condition, menu, or mode.
RULES:
  - MUST treat MUST/MUST_NOT/ALWAYS/NEVER/REQUIRE/FORBID/WAIT/STOP_TURN/
    INVARIANTS as hard obligations
  - MUST treat WHEN/IF as activation conditions only; once true, all
    DO/RULES/INVARIANTS items are mandatory
  - MUST treat Suggested as menu recommendation only; never permits skipping
    gate, prompt, reply parsing, validation, or terminal block
  - MUST treat "can use"/"can run" as capability description only; never
    weakens gate WAIT/STOP_TURN behavior
  - MUST treat RELAXED mode as reduced dependency rigor, not optional protocol;
    RELAXED MUST rules still apply; unvalidated results are not PASS
  - MUST treat default values as fallback only after owning parser/gate
    authorizes the fallback; defaults never bypass required user prompts
```

```text
UNIT Bootstrap
PURPOSE: Have the top-level controller/host runtime load required context files
         before any phase work begins.
DO:
  Top-level controller/host runtime loads each of
    [`{cf-studio-path}/.core/skills/studio/protocol.md`,
     `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`,
     `{cf-studio-path}/.core/skills/studio/routing.md`]:
    Estimate file size before loading.
    IF size > ~200 lines: load incrementally; IF context exhausted: STOP with a checkpoint message; STOP_TURN
    ELSE: load fully
  CONTINUE active workflow or routing
RULES:
  - These load duties apply to the top-level controller/host runtime only
  - Dispatched sub-agents MUST consume supplied prompt_context_view / final
    prompt context instead of reopening prompt assets from disk
  - MUST load protocol.md before any workflow work
  - MUST load sub-agent-dispatch.md before any cf-* sub-agent dispatch
  - MUST load routing.md before routing decisions
  - MUST treat routing.md § CanonicalRoutingPrecedenceState as the single
    precedence authority for workflow entry, explain mode, workspace quick
    commands, AGENTS prompt-asset order, and fallback dispatch state
  - MUST NOT skip any of the three files
  - MUST treat sub-agent-dispatch.md § SubAgentContractReadGate as
    dispatch-blocking for every cf-* DISPATCH, PARALLEL_DISPATCH,
    RE-DISPATCH, or inline fallback execution
```

```text
UNIT SharedContextPackAuthority
PURPOSE: Make controller-owned shared-context-pack loading the only legal
         prompt-asset loading path for workflow execution.
STATE:
  SHARED_CONTEXT_PACK: session_scoped logical pack  default: empty  scope: session
RULES:
  - A chat session MUST have exactly one logical SHARED_CONTEXT_PACK
  - Top-level controllers MUST reuse the existing session pack before loading
    any new prompt asset
  - Reused prompt assets MUST be revalidated by etag and refreshed/replaced
    before contributing to a synthesized final dispatch prompt when stale
  - Only a dispatching controller, dedicated shared-context-pack builder, or
    explicitly designated top-level runtime controller may load prompt assets
  - Prompt-consuming sub-agents MUST receive a fully materialized final
    dispatch prompt synthesized from agent prompt source + SHARED_CONTEXT_PACK
    and an explicit prompt_context_view slice list in the dispatch manifest
  - Agent prompt source MUST be loaded and used as the sub-agent contract before
    every cf-* dispatch; if not loaded/readable/reflected in the synthesized
    prompt, dispatch MUST fail before the sub-agent runs
  - Sub-agents MUST_NOT discover prompt dependencies or reload prompt assets
  - Sub-agents MUST use the synthesized final prompt plus supplied slices as
    their prompt-asset authority; if required prompt context is missing, they
    MUST report the gap to the controller instead of reopening prompt files
  - Missing required prompt context MUST fail dispatch before sub-agent runs
  - Checkpoint or resume after context compaction MUST rehydrate the same
    SHARED_CONTEXT_PACK id and verify prompt_context_view slice ids plus source
    contract fingerprint before any sub-agent continues
  - Controller-owned prompt loads MUST use {cf-studio-path}-prefixed runtime
    paths when a runtime mirror exists
```

```text
UNIT InstructionFileAuthoringBoundary
PURPOSE: Prevent controller-local edits to instruction files when a
         cf-generate author path exists.
STATE:
  INSTRUCTION_FILE_TARGET:
    any path under workflows/** | requirements/** | any AGENTS.md
    | any skills/**/SKILL.md | any skills/**/agents/*.md
    | any equivalent prompt/agent contract path named by the active workflow
RULES:
  - When target matches INSTRUCTION_FILE_TARGET and cf-generate author dispatch
    exists: MUST route through workflows/generate/phase-1.5-author-plan.md
    and workflows/generate/phase-4-write.md instead of patching locally
  - When host.supports_native_subagents == true AND
    SUB_AGENT_SESSION_APPROVED == true: instruction-file writes MUST use native
    cf-generate author dispatch whenever the selected author is registered
  - INLINE_FALLBACK=true authorizes only Mode B inline execution of the
    selected author contract; MUST_NOT be reinterpreted as permission for
    controller-local Edit/Write/MultiEdit/NotebookEdit/apply_patch/shell-write
  - released_for_orchestrator_write MUST_NOT be used for INSTRUCTION_FILE_TARGET
    except during documented emergency fallback after explicit user mode
    selection naming the files and stating why author-dispatch is unavailable
  - Generic write confirmation, user_bypass, and small-change reasoning do NOT
    authorize controller-local instruction-file edits when author path available
  - If about to manually patch an INSTRUCTION_FILE_TARGET while native author
    dispatch is available: SET CF_PHASE_GATE = armed; stop the write; route
    into phase-1.5-author-plan.md then phase-4-write.md
```

```text
UNIT PhaseSkipGate
PURPOSE: Prevent write-tool use except in explicitly released states.
STATE:
  CF_PHASE_GATE: armed | released_for_dispatch | released_for_orchestrator_write
                 | released_for_inline_write | user_bypass
    default: armed  scope: session
WHEN:
  CF_PHASE_GATE == armed
DO:
  FORBID Edit
  FORBID Write
  FORBID MultiEdit
  FORBID NotebookEdit
  FORBID apply_patch
  FORBID shell-write
  FORBID Bash with write redirection (>, >>, tee, here-docs)
  FORBID Bash that mutates files (rm, mv, cp, mkdir, touch, chmod, ln, rename)
  FORBID Bash destructive git (commit/push/reset --hard/checkout --/restore)
  FORBID Bash invoking write-capable CLI (in-place formatters, package installers)
  NOTE: Read/Grep/Glob always exempt; Bash exempt only when all above clear; doubt = write
RULES:
  - MUST default CF_PHASE_GATE = armed on skill load
  - MUST ignore path, size, or user phrasing when gate is armed
  - MUST_NOT inherit gate state in sub-agents — each sub-agent starts armed
  - MUST_NOT allow orchestrator to write while CF_PHASE_GATE == released_for_dispatch
  - MUST reset CF_PHASE_GATE = armed after dispatch returns or errors (released_for_dispatch)
  - MUST reset CF_PHASE_GATE = armed after named writes complete or fail
    (released_for_orchestrator_write or released_for_inline_write)
  - MUST reset CF_PHASE_GATE = armed at start of next orchestrator turn (user_bypass)
ON_ERROR:
  write_while_armed ->
    SET CF_PHASE_GATE = armed
    EMIT "phase-skip prevented — switching to Invoke skill `cf-<workflow>`"
    Route into matching workflow without writing
    STOP_TURN
  NotebookEdit_or_MultiEdit_partial_failure ->
    Abort remaining cells/edits
    SET CF_PHASE_GATE = armed
    STOP_TURN
```

```text
UNIT SubAgentDefaultPolicy
PURPOSE: Make native sub-agent dispatch the default execution path whenever
         the host can provide it.
RULES:
  - Native cf-* dispatch is the default for every workflow phase referencing
    a cf-* sub-agent when the host supports native sub-agents
  - A host/tool policy requiring explicit delegation/approval before sub-agent
    tool use is a distinct blocked state when native cf-* sub-agents are
    discoverable or desired; MUST resolve with NativeSubAgentPolicyConflictMenu;
    MUST_NOT collapse into host.supports_native_subagents == false
  - MUST_NOT decide on its own to avoid native sub-agents for convenience,
    context size, simplicity, latency, or implementation preference
  - MAY avoid native sub-agents only when: (1) user explicitly selected inline
    fallback in SubAgentApprovalMenu; OR (2) host cannot provide native support
    AND user explicitly selected inline fallback in recovery menu; OR (3) the
    workflow phase has no cf-* dispatch path
  - If orchestrator believes native sub-agents should not be used while host
    supports them: MUST ask via SubAgentApprovalMenu and STOP_TURN; MUST_NOT
    continue locally in the same turn
  - After SUB_AGENT_SESSION_APPROVED == true: workflow phases with cf-* dispatch
    paths MUST use native sub-agents unless a later explicit user menu selection
    changes the mode for a documented scope
INVARIANTS:
  - Inline fallback / no-dispatch is never orchestrator-default when native
    sub-agents are available
  - Missing approval is a blocked state, not permission to continue locally
  - Context-management concerns route to planner/decomposition or checkpoint;
    they do not authorize bypassing native sub-agent dispatch
  - Emitting a "continuing locally / calling out the deviation" message while
    native cf-* sub-agents are discoverable but policy-blocked is a violation
```

## Session Sub-Agent Approval Gate

```text
UNIT SubAgentApprovalGate
PURPOSE: Obtain explicit user approval for native sub-agent dispatch,
         once per chat session.
STATE:
  SUB_AGENT_SESSION_APPROVED: unset | true
    default: unset  scope: session  reset: external-entry handoffs re-probe

  INLINE_FALLBACK: unset | true | false
    default: unset  scope: workflow_run (NOT carried across workflow runs)

  INLINE_FALLBACK_PROBED: false | true
    default: false  scope: workflow_run

  NATIVE_SUBAGENT_POLICY_CONFLICT: false | true
    default: false  scope: workflow_run (derived)

WHEN:
  SUB_AGENT_SESSION_APPROVED == unset
  AND native cf-* sub-agents are discoverable or desired for the current workflow
DO:
  IF host/tool policy requires explicit user delegation or approval
     AND INLINE_FALLBACK == unset:
    SET NATIVE_SUBAGENT_POLICY_CONFLICT = true
    EMIT_MENU NativeSubAgentPolicyConflictMenu
    WAIT user.reply
    STOP_TURN
  IF host.supports_native_subagents == true:
    EMIT_MENU SubAgentApprovalMenu
    WAIT user.reply
    STOP_TURN
  IF host.supports_native_subagents == false:
    EMIT_MENU HostNoNativeSubAgentMenu
    WAIT user.reply
    STOP_TURN

MENU SubAgentApprovalMenu:
  TITLE: |
    Approve sub-agent use for this session.

    This workflow uses Constructor Studio sub-agents by default for
    isolated/parallel work when the host supports them.

    | Option | Action |
    |---|---|
    | 1 | Use native sub-agents — isolated/parallel dispatch, remembered for this session |
    | 2 | Use inline fallback for this workflow — no isolation, slower, but no host primitive needed |

    Suggested: 1 because native dispatch preserves context-isolation and
    parallelism when the host supports it.

    Reply with 1 or 2.
  OPTIONS:
    1 ->
      SET SUB_AGENT_SESSION_APPROVED = true
      SET INLINE_FALLBACK = false
      SET INLINE_FALLBACK_PROBED = true
      CONTINUE CurrentWorkflow
    2 ->
      SET INLINE_FALLBACK = true
      SET INLINE_FALLBACK_PROBED = true
      CONTINUE CurrentWorkflow
  INVALID:
    EMIT "Reply with 1 or 2."
    WAIT user.reply
    STOP_TURN
NOTES:
  SubAgentApprovalMenu, NativeSubAgentPolicyConflictMenu, and
  HostNoNativeSubAgentMenu are the canonical menu definitions.
  inline-fallback-probe.md MUST reference these menu definitions and MUST_NOT
  redefine their wording or option semantics locally.

MENU NativeSubAgentPolicyConflictMenu:
  TITLE: |
    Native cf-* sub-agents are discoverable for this workflow, but this host
    requires your explicit delegation approval before I can dispatch them.

    Options:
    1. Authorize native sub-agent/delegation for this session
    2. Use explicit inline fallback for this workflow
    3. Stop

    Suggested: 1 because native dispatch preserves isolation and parallelism.
    Reply with 1, 2, or 3.
  OPTIONS:
    1 ->
      SET SUB_AGENT_SESSION_APPROVED = true
      SET INLINE_FALLBACK = false
      SET INLINE_FALLBACK_PROBED = true
      CONTINUE CurrentWorkflow
    2 ->
      SET INLINE_FALLBACK = true
      SET INLINE_FALLBACK_PROBED = true
      CONTINUE CurrentWorkflow
    3 ->
      EMIT "Stopped before choosing native dispatch or inline fallback."
      STOP_TURN
  INVALID:
    EMIT "Reply with 1, 2, or 3."
    WAIT user.reply
    STOP_TURN

MENU HostNoNativeSubAgentMenu:
  TITLE: |
    Native sub-agents are not available in this host.

    I need one fallback choice before continuing because this workflow normally
    uses sub-agent isolation for cf-* dispatches.

    Options:
    1. Use inline fallback for this workflow — no isolation or parallelism
    2. Stop before local execution

    Suggested: 2 when isolation is required; choose 1 only for a bounded task
    where inline execution is acceptable.
    Reply with 1 or 2.
  OPTIONS:
    1 ->
      SET INLINE_FALLBACK = true
      SET INLINE_FALLBACK_PROBED = true
      CONTINUE CurrentWorkflow
    2 ->
      EMIT "Sub-agent dispatch unavailable; stopping before local execution."
      STOP_TURN
  INVALID:
    EMIT "Reply with 1 to use inline fallback or 2 to stop."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST apply SubAgentDefaultPolicy before resolving this gate
  - MUST check policy-conflict condition first (highest priority) before checking
    host.supports_native_subagents
  - MUST emit NativeSubAgentPolicyConflictMenu and STOP_TURN when native cf-*
    sub-agents are discoverable but host/tool policy requires explicit user
    delegation before sub-agent tool use
  - MUST emit SubAgentApprovalMenu and STOP_TURN when host.supports_native_subagents
    == true and no policy conflict is active
  - MUST end the turn (STOP_TURN) immediately after emitting any menu
  - MUST trim reply and accept the active menu's option numbers when embedded
    in longer phrases (e.g. "option 1 please")
  - MUST_NOT continue without native sub-agents while host supports them unless
    user explicitly selected option 2
  - MUST_NOT continue in inline fallback when host does not support native
    sub-agents unless user explicitly selected HostNoNativeSubAgentMenu option 1
  - MUST_NOT reinterpret policy-conflict blocking as host lacking native support
  - MUST_NOT default INLINE_FALLBACK from host capability or missing approval
  - MUST_NOT set INLINE_FALLBACK = true from missing approval alone
  - MUST_NOT carry INLINE_FALLBACK across workflow runs
  - MUST carry SUB_AGENT_SESSION_APPROVED across runs in the same chat session
  - MUST re-probe on external-entry handoffs
  - Sub-agents MUST skip this gate unless they will dispatch another cf-* sub-agent
  - MUST_NOT narrate the policy conflict and continue locally

INVARIANTS:
  - Native sub-agents are the default path when host.supports_native_subagents == true
  - MUST_NOT set INLINE_FALLBACK = true from missing approval or missing host
    support alone; explicit user fallback selection required
  - MUST_NOT set INLINE_FALLBACK = false unless SUB_AGENT_SESSION_APPROVED == true
```

```text
UNIT ChangeReviewFailClosedSentinel
PURPOSE: Forbid local change-review work until required gate and dispatch
         states are resolved.
WHEN:
  CHANGE_REVIEW == true
RULES:
  - MUST treat unresolved native-sub-agent approval, unresolved inline-fallback
    probe/menu state, or unresolved resolver/validator/reviewer
    contract-read-and-use state as fail-closed
  - While fail-closed: MUST_NOT run or narrate local git status, git diff,
    changed-file triage, cfs validate, local semantic review, findings,
    review summaries, or remediation menus
  - While fail-closed: MAY emit only the missing gate menu required to resolve
    the blocked state, OR the matching "Dispatch blocked: ..." error from
    sub-agent-dispatch.md
  - After either allowed output: MUST STOP_TURN
  - Resolving one gate does not weaken the sentinel for later dispatch sites;
    each required dispatch gate remains fail-closed until resolved
```

```text
UNIT CompletionInvariants
PURPOSE: Enforce that every response ends with the correct workflow terminal block.
INVARIANTS:
  - MUST_NOT consider a response complete until the correct terminal block present
  - cf-generate (no remaining findings): terminal = Post-Write Review Handoff menu
  - cf-generate (remaining findings): terminal = Remediation Handoff menu;
    W1/W2/W3 options MUST be locked until remediation clears
  - cf-generate (pre-review warning stop with files written):
    terminal = Pre-Review Warning Handoff block (phase-5.2-semantic.md)
  - cf-analyze (actionable findings): terminal = Remediation Handoff menu
  - cf-plan (compiled phase files): terminal = Phase 4.2 next-steps menu
    OR Phase 3.2A brief-checkpoint menu (when briefs_only)
  - cf-plan (prompts_emitted stop): terminal = emitted prompt set; no Phase 4.2 menu
  - cf-plan (raw-input n / decomposition n stop): terminal = canonical stop
    message from {cf-studio-path}/.core/workflows/plan.md; no terminal menu
RULES:
  - Analyze remediation and review handoff prompt blocks MUST be emitted only
    on the NEXT turn after the user picks the matching handoff option — never
    in the same turn as the handoff menu
  - MUST be emitted only on the NEXT turn
```
