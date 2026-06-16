---
cf: true
type: workflow
name: cf-explain
version: 0.1
description: "Invoke for requests to explain, walk through, teach, onboard, give a code tour, produce a source-grounded narrative, or summarize a decision."
purpose: Run an interactive, pedagogically-paced storytelling walkthrough of an artifact, codebase, or document via sub-agents — resolving mode/disposition/audience/plan through four gates before any answer-style content, and optionally exporting a Markdown package.
---

# cf-explain

This skill runs an interactive, pedagogically-paced storytelling walkthrough of an artifact, codebase, or document — delivering small source-grounded portions with a fixed navigator, only after resolving mode, artifact disposition, audience, and plan approval through four gates. It never emits answer-style content before those gates resolve, follows the storytelling phases E0 through E5 in order, and can optionally export a Markdown package — all via sub-agents.

```pdsl
UNIT ExplainBootstrap
PURPOSE: Arm explain mode and load the storytelling methodology before any explain work.
STATE:
  SET EXPLAIN_EXPORT: true | false (default false, scope workflow_run)
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-bootstrap.md
  RUN WorkflowBootstrapCoreSession
  RUN ExplainBootstrapIntentRuntime
  RUN ExplainBootstrapModeState
  RUN ExplainBootstrapStorytelling
  CONTINUE ExplainIntentCapture WHEN ORIGINAL_INTENT == unset
  CONTINUE ExplainExploreGate WHEN ORIGINAL_INTENT != unset
RULES:
  ALWAYS run StudioInstructionsMemoryGate before explain preflight, routing, storytelling gates, or delivery
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, export, or delegation
  ALWAYS load storytelling and sub-agent dispatch before any explain work
  ALWAYS load context-memory before carrying resource_context into storytelling dispatches
  ALWAYS load template-vars before resolving explanation export package paths or unknown template variables
  ALWAYS capture ORIGINAL_INTENT before explanation context discovery, target preflight, or storytelling dispatch
  NEVER offer companion cf-* workflows from cf-explain; explain owns its target and storytelling gates directly
  NEVER offer cf-brainstorm from cf-explain; explanation narrative choices are resolved by the storytelling gates
  NEVER emit any answer-style, portion, or summary content before the four E1 gates (mode -> disposition -> audience -> plan approval) resolve — this is the critical AP#0 violation
  ALWAYS follow storytelling phases E0 through E5 in order and NEVER skip Discovery (E1) or the strict-context boundary
  NEVER treat storytelling output as a validation report
  NEVER require cf or CFS_INIT before explain; this workflow owns its prerequisite loads
```

```pdsl
UNIT ExplainBootstrapIntentRuntime
PURPOSE: Resolve the initial explain intent and runtime helpers before storytelling state is set.
DO:
  SET ORIGINAL_INTENT = the user's triggering explain request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN WorkflowBootstrapDispatchContext
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md WHEN EXPLAIN_EXPORT == true
```

```pdsl
UNIT ExplainBootstrapModeState
PURPOSE: Set the explain-mode state that reuses the storytelling output contract.
DO:
  SET EXPLAIN_MODE = true
  SET analyze_phase_2_deterministic_gate = SKIPPED
  SET analyze_phase_3_standard_checklist = SKIPPED
  SET analyze_phase_5_next_steps = SKIPPED
  SET analyze_phase_4_output_schema = storytelling_output_schema
  SET enforceRemediationPrompts = false
```

```pdsl
UNIT ExplainBootstrapStorytelling
PURPOSE: Load the storytelling requirements used by cf-explain.
DO:
  LOAD {cf-studio-path}/.core/requirements/storytelling.md (its router loads storytelling-shared, storytelling-phases, storytelling-modes, and storytelling-preferences)
  LOAD {cf-studio-path}/.core/requirements/storytelling-export.md WHEN EXPLAIN_EXPORT == true
```
```pdsl
UNIT ExplainIntentCapture
PURPOSE: Capture the explanation target before context discovery or storytelling preflight runs.
STATE:
  SET EXPLAIN_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
DO:
  EMIT "What should I explain? Provide the file, artifact, code area, decision, or topic to walk through."
  SET EXPLAIN_INTENT_CAPTURE_STATE = resume
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS stop the turn after prompting so explain routing resumes in an explicit unit
  NEVER run ExplainE0Preflight while ORIGINAL_INTENT is unset
```

```pdsl
UNIT ExplainIntentCaptureResume
PURPOSE: Route the resumed explanation target into the shared explore gate.
STATE:
  SET EXPLAIN_INTENT_CAPTURE_STATE: prompt | resume | unset (default unset, scope workflow_run)
WHEN:
  REQUIRE EXPLAIN_INTENT_CAPTURE_STATE == resume
DO:
  SET ORIGINAL_INTENT = user.reply
  SET EXPLAIN_INTENT_CAPTURE_STATE = unset
  CONTINUE ExplainExploreGate
```
```pdsl
UNIT ExplainExploreGate
PURPOSE: Offer task-relevant context discovery before explain preflight, after Bootstrap and before the storytelling target is resolved.
WHEN:
  REQUIRE ORIGINAL_INTENT != unset
DO:
  SET WORKFLOW_PREP_EXPLORE_MENU = ExplainExploreMenu
  SET WORKFLOW_PREP_BRAINSTORM_GATE = ExplainE0Preflight
  LOAD {cf-studio-path}/.core/skills/studio/modules/gates/workflow-prep.md
  CONTINUE WorkflowPrepExploreGate
RULES:
  ALWAYS use WorkflowPrepExploreGate for the shared explore prompt mechanics
MENU ExplainExploreMenu
TITLE: Before starting a source-grounded explanation, discover task-relevant context (explicit target, nearby docs/code/artifacts, referenced IDs, and audience-relevant background) with cf-explore — or skip? Explore is suggested when the target is implicit, broad, unfamiliar, or cross-cutting; skip when the target and context are already explicit. Reply with a number.
OPTIONS:
  1 explore -> INVOKE skill `cf-explore` with intent=workflow-prep, task=ORIGINAL_INTENT, return_context=true; require it to return resource_context only and not perform explanation, review, authoring, or validation, SET RESOURCE_CONTEXT = provided, then CONTINUE ExplainE0Preflight
  2 skip -> CONTINUE ExplainE0Preflight
  INVALID -> EMIT_MENU ExplainExploreMenu
```
```pdsl
UNIT ExplainE0Preflight
PURPOSE: Resolve the explanation target and input access via preflight before any portion content (Phase E0).
DO:
  RUN SubAgentDispatch for the storytelling-preflight dispatch group before launching preflight
  DISPATCH storytelling-preflight with the raw target/path, user prompt, cf_studio_path, project_root, and RESOURCE_CONTEXT when provided to resolve the input-access tier, run the session-discovery scan, and enforce size guards (returns a lightweight handle, no bulk extraction)
  INVOKE skill `cf-explore` with intent=analyze and return_context=true to discover targets WHEN the explanation target is not explicit
  CONTINUE ExplainE1Gates
RULES:
  ALWAYS run the E0 input-access chain (preflight) for non-local targets before reporting any "not found"
  ALWAYS pass ExplainExploreGate-resolved RESOURCE_CONTEXT to storytelling-preflight as read-only context references, never as a gate verdict or inline bulk prompt text
  NEVER emit portion content in E0
```
```pdsl
UNIT ExplainE1Gates
PURPOSE: Resolve the four Discovery gates as separate user-interaction boundaries via storytelling-gate, advancing one gate per turn (Phase E1).
STATE:
  SET E1_GATE: mode | disposition | audience | plan | done (default mode, scope workflow_run)
DO:
  RUN resolve mode/disposition/audience/plan from the STORYTELLING_* presets, represent those preset answers in the E0/E1 opener, SET E1_GATE = done, and CONTINUE ExplainE2Deliver WHEN CF_HELP_PRESET == true AND STORYTELLING_PLAN_APPROVED == true
  RUN SubAgentDispatch for the storytelling-gate dispatch group before launching each E1 gate WHEN CF_HELP_PRESET != true OR STORYTELLING_PLAN_APPROVED != true
  DISPATCH storytelling-gate gate_id=mode to render the numbered always-ask mode menu, WAIT user.reply, SET E1_GATE = disposition, STOP_TURN WHEN E1_GATE == mode
  DISPATCH storytelling-gate gate_id=artifact-disposition, WAIT user.reply, SET E1_GATE = audience, STOP_TURN WHEN E1_GATE == disposition
  DISPATCH storytelling-gate gate_id=audience, WAIT user.reply, SET E1_GATE = plan, STOP_TURN WHEN E1_GATE == audience
  DISPATCH storytelling-gate gate_id=plan to render the 4-option plan-approval menu (handle Edit/Pivot/Cancel per storytelling-gate), WAIT user.reply, STOP_TURN WHEN E1_GATE == plan AND the plan is NOT yet approved
  CONTINUE ExplainE2Deliver WHEN E1_GATE == plan AND the plan is approved
RULES:
  ALWAYS under CF_HELP_PRESET == true, resolve the four gates from the STORYTELLING_* presets instead of prompting (preset resolution skips the prompts, not the phases) and NEVER emit a one-shot overview/command list — the next output is the E0/E1 opener, then E2 delivery
  ALWAYS run the gates in order mode -> disposition -> audience -> plan and keep each a separate user-interaction boundary
  ALWAYS resolve mode always-ask (intent/default only suggest, never auto-select)
  ALWAYS advance E1_GATE only after the current gate's user reply is received; NEVER re-ask an already-resolved gate
  ALWAYS handle Edit/Pivot/Cancel from the plan gate per storytelling-gate
  ALWAYS on a plan-gate Cancel, RETURN an EXPLAIN_RESULT envelope with status="cancelled" and STOP_TURN
  NEVER enter E2 before the plan-approval gate resolves
```
```pdsl
UNIT ExplainE2Deliver
PURPOSE: Build the content pack once, then run the source-grounded portion-delivery loop (Phase E1.5 + E2).
DO:
  RUN SubAgentDispatch for the storytelling-context-pack dispatch group before launching context-pack
  DISPATCH storytelling-context-pack with RESOURCE_CONTEXT when provided to read the input once and emit the content_pack (strategy-parametrized) before the first portion
  RUN the portion-delivery loop per storytelling-phases — each portion is a small source-grounded unit (soft target <= 200 words, no scroll) with the fixed 7-slot navigator (Next / Deeper / Lateral / Recap / Ask / Wrap / Back)
  EMIT each portion plus its nav block
  WAIT user.reply
  STOP_TURN
  CONTINUE ExplainE5Wrap WHEN the user wraps or the plan is complete
RULES:
  ALWAYS ground every non-trivial claim in the input and omit ungrounded claims rather than fabricate
  ALWAYS pass ExplainExploreGate-resolved RESOURCE_CONTEXT to storytelling-context-pack as read-only context references, never as a gate verdict or inline bulk prompt text
  ALWAYS visualize-by-default with an audience-adapted constructed diagram unless there is an articulable reason not to
  ALWAYS use clickable Markdown link refs
  NEVER combine multiple plan items into one mega-portion or require the user to scroll — decompose into sub-portions, summary first
```
```pdsl
UNIT ExplainE5Wrap
PURPOSE: Synthesize takeaways, carry open questions forward, and return the completion envelope (Phase E5).
DO:
  RUN SubAgentDispatch for the storytelling-wrap dispatch group before launching wrap
  DISPATCH storytelling-wrap to synthesize key takeaways, carry open questions forward verbatim, emit the glossary/bookmarks export prompt when present, and propose 2-3 contextual next steps
  RUN a mid-session checkpoint only on explicit user consent (persistence is wrap-time and consent-only)
  CONTINUE ExplainExport WHEN EXPLAIN_EXPORT == true
  CONTINUE ExplainCompletion WHEN EXPLAIN_EXPORT != true
RULES:
  ALWAYS emit or return an EXPLAIN_RESULT envelope before every terminal exit or next-actions handoff (complete, checkpointed, or cancelled)
  NEVER auto-save checkpoints, bookmarks, or open-questions without explicit user consent
NOTES:
  Envelope shape: { "type": "EXPLAIN_RESULT", "status": "complete|checkpointed|cancelled", "session_id": "<id|null>", "progress": "<X/N|null>", "resume_path": "<path|null>" }
```
```pdsl
UNIT ExplainCompletion
PURPOSE: Return the explain completion envelope, then offer context-grounded next actions.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  EMIT the EXPLAIN_RESULT envelope
  RUN NextActionsOffer
RULES:
  ALWAYS use this unit only after storytelling wrap completes and control is about to return to the user
  ALWAYS emit the EXPLAIN_RESULT envelope before offering next actions
  NEVER bypass NextActionsOffer on a clean terminal path that returns control to the user
```
```pdsl
UNIT ExplainExport
PURPOSE: Write the finalized Markdown package when export mode is active.
WHEN:
  REQUIRE EXPLAIN_EXPORT == true
DO:
  RUN TemplateVarResolution before resolving the export package path
  RUN SubAgentDispatch for the storytelling-export dispatch group before launching export
  DISPATCH storytelling-export to write the finalized package under {cf-studio-path}/.cache/explain/packages/{slug}-{ISO}/ (index.md, per-portion files, navigation, mode extras)
  RETURN the EXPLAIN_RESULT envelope
  STOP_TURN
RULES:
  NEVER export a socratic session — refuse with the required message and write nothing
  ALWAYS in export mode keep navigation in file footers and chat to E0/E1 plus the final summary (no per-portion chat nav)
```
```pdsl
UNIT ExplainDispatch
PURPOSE: Name the storytelling sub-agents used per phase and guard the dispatch rails.
RULES:
  ALWAYS dispatch storytelling-preflight from {cf-studio-path}/.core/skills/studio/agents/storytelling-preflight.md (E0 input-access tier + session-discovery + size guards)
  ALWAYS dispatch storytelling-context-pack from {cf-studio-path}/.core/skills/studio/agents/storytelling-context-pack.md (E1.5 read-once content pack)
  ALWAYS dispatch the storytelling sub-agents from {cf-studio-path}/.core/skills/studio/agents/ per phase — storytelling-preflight (E0), storytelling-gate (each E1 gate plus context-pack-strategy/export-format gates), storytelling-context-pack (E1.5), storytelling-wrap (E5), storytelling-export (export)
  ALWAYS run SubAgentDispatch before every native storytelling dispatch group; preset gate resolution skips prompt dispatches only when the workflow explicitly resolves the gate without launching an agent
  ALWAYS dispatch cf-explorer via INVOKE skill `cf-explore` for non-explicit targets, never by dispatching cf-explorer directly
  ALWAYS pass ExplainExploreGate-resolved RESOURCE_CONTEXT to storytelling-preflight and storytelling-context-pack as read-only context references when provided
  ALWAYS deliver storytelling prompt content to sub-agents through prompt_context_view / pack handles
  NEVER let a sub-agent reopen prompt or instruction files from disk
```
