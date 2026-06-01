---
name: analyze-preamble
description: "Invoke when loading the analyze workflow preamble for route-only methodology selection; heavy methodologies load inside matched sub-agents."
purpose: Analyze workflow preamble — route-only methodology selection; heavy methodologies load inside matched sub-agents
loaded_by: workflows/analyze.md
version: 1.0
---

```text
UNIT AnalyzePreamble

PURPOSE:
  Initialize per-run analyze flags, perform route-only methodology selection,
  and handle storytelling trigger detection before any phase executes.

STATE:
  SEMANTIC_ONLY: false | true
    default: false
    reset: start of workflow run
  CHANGE_REVIEW: false | true
    default: false
  CODE_REVIEW: false | true
    default: false
  CODE_BUG_REVIEW: false | true
    default: false
  CONSISTENCY_REVIEW: false | true
    default: false
  PROMPT_REVIEW: false | true
    default: false
  PROMPT_BUG_REVIEW: false | true
    default: false
  EXPLAIN_MODE: false | true
    default: false
  ARTIFACT_REVIEW: false | true
    default: false
  CF_PHASE_GATE: armed
    default: armed
    reset: start of workflow run
  enforceRemediationPrompts: true | false
    default: true
    reset: start of workflow run
  CF_HELP_PRESET: false | true
    default: false
  EXPLAIN_TARGET: string | null
    default: null
  STORYTELLING_MODE: string | null
    default: null
  STORYTELLING_ARTIFACT_DISPOSITION: string | null
    default: null
  STORYTELLING_AUDIENCE: string | null
    default: null
  STORYTELLING_CONTEXT_PACK_STRATEGY: string | null
    default: null
  STORYTELLING_PLAN_APPROVED: false | true
    default: false
  STORYTELLING_DIAGRAM_FORMAT: ascii | mermaid | both | null
    default: null
  STORYTELLING_DIAGRAM_FORMAT_PRESET: false | true
    default: false
  STORYTELLING_HELP_GOAL: string | null
    default: null

DO:
  ALWAYS load {cf-studio-path}/.core/skills/studio/SKILL.md WHEN {cfs_mode} == off
  ALWAYS load {cf-studio-path}/.core/skills/studio/protocol.md FIRST
  Initialize workflow-owned analysis flags to their defaults:
    SEMANTIC_ONLY=false, CHANGE_REVIEW=false, CODE_REVIEW=false,
    CODE_BUG_REVIEW=false, CONSISTENCY_REVIEW=false, PROMPT_REVIEW=false,
    PROMPT_BUG_REVIEW=false, EXPLAIN_MODE=false, ARTIFACT_REVIEW=false,
    CF_PHASE_GATE=armed, enforceRemediationPrompts=true
  PRESERVE route-supplied preset variables if already set by routing:
    CF_HELP_PRESET, EXPLAIN_TARGET, STORYTELLING_MODE,
    STORYTELLING_ARTIFACT_DISPOSITION, STORYTELLING_AUDIENCE,
    STORYTELLING_CONTEXT_PACK_STRATEGY, STORYTELLING_PLAN_APPROVED,
    STORYTELLING_DIAGRAM_FORMAT, STORYTELLING_DIAGRAM_FORMAT_PRESET,
    STORYTELLING_HELP_GOAL
  IF CF_HELP_PRESET == true:
    LOAD {cf-studio-path}/.core/requirements/storytelling.md
    SET EXPLAIN_MODE = true
    SET EXPLAIN_TARGET = "{cf-studio-path}" unless already set
    SET STORYTELLING_MODE = "presentation" unless already set
    SET STORYTELLING_ARTIFACT_DISPOSITION = "chat-only" unless already set
    SET STORYTELLING_AUDIENCE = "Constructor Studio newcomers" unless already set
    SET STORYTELLING_CONTEXT_PACK_STRATEGY = "hybrid" unless already set
    SET STORYTELLING_PLAN_APPROVED = true
    SET STORYTELLING_DIAGRAM_FORMAT = "ascii" unless already set
    SET STORYTELLING_DIAGRAM_FORMAT_PRESET = true
    SET enforceRemediationPrompts = false
    FORBID Phase 2 deterministic gate
    FORBID Phase 3 standard semantic checklist
    FORBID Phase 5 (Storytelling Output emits Suggested Next Steps)
    REQUIRE Storytelling Output schema in Phase 4
    FORBID emitting analyze remediation prompt blocks
    CONTINUE through the normal Storytelling Protocol E0-E5 using the
    prefilled variables as already-resolved gate answers
    do not ask mode, disposition, audience, context-pack-strategy, export,
    plan-approval, or diagram-format questions for this run
    FORBID custom one-shot help rendering or a generic status overview
  Match methodology flags from user request:
    IF code/codebase/implementation analysis:
      SET CODE_REVIEW = true
      FORBID opening code-checklist.md or bug-finding.md in the orchestrator
    IF bug hunting / logic bug / edge-case / regression / root-cause / "all bugs":
      SET CODE_BUG_REVIEW = true
      FORBID opening bug-finding.md in the orchestrator
    IF documentation/artifact consistency / contradiction / cross-document alignment:
      SET CONSISTENCY_REVIEW = true
      FORBID opening consistency-checklist.md in the orchestrator
    IF instruction targets (system prompts, agent prompts, LLM prompts, agent
       instructions/guidelines, skills, workflows, methodologies, AGENTS.md,
       navigation rules, AI-agent instruction docs) OR user mentions
       "prompt engineering review", "prompt bug review", "prompt bugs",
       "instruction quality":
      SET PROMPT_REVIEW = true
      FORBID opening prompt-engineering.md in the orchestrator
    IF defect-oriented prompt/instruction request (prompt bug review, prompt bugs,
       hidden failure modes, unsafe behavior, regressions, instruction conflicts,
       routing defects, root-cause search):
      SET PROMPT_BUG_REVIEW = true
      FORBID opening prompt-bug-finding.md in the orchestrator
  IF multiple methodology flags are true:
    Phase 3 dispatches multiple sub-agents
  IF explicit pedagogical/storytelling intent:
    LOAD {cf-studio-path}/.core/requirements/storytelling.md
    SET EXPLAIN_MODE = true
    FORBID Phase 2 deterministic gate
    FORBID Phase 3 standard semantic checklist
    REQUIRE Storytelling Output schema in Phase 4
    FORBID Phase 5 (Storytelling Output emits Suggested Next Steps)
    SET enforceRemediationPrompts = false
    FORBID emitting analyze remediation prompt blocks
  IF EXPLAIN_MODE == true AND PROMPT_REVIEW intent also detected:
    EMIT_MENU StorytellingVsPromptReviewMenu
    WAIT user.reply
    STOP_TURN

MENU StorytellingVsPromptReviewMenu:
  TITLE: "Your request combines storytelling and prompt-review intent. Which should I run?"
  OPTIONS:
    1 -> SET EXPLAIN_MODE = true; proceed with storytelling walkthrough
    2 -> SET PROMPT_REVIEW = true; SET EXPLAIN_MODE = false; proceed with prompt engineering review
  INVALID:
    EMIT "Reply `1` or `2`."
    WAIT user.reply
    STOP_TURN

INVARIANTS:
  - MUST initialize workflow-owned analysis flags before Phase 0 runs
  - MUST preserve route-supplied preset variables across initialization
  - Phase 0 (phase-0-dependencies.md) MUST_NOT re-initialize flags to false
  - MUST_NOT auto-enter EXPLAIN_MODE for ordinary review/audit/inspect requests
    (review my changes, review this PR, review this diff, audit this design,
     inspect this code, check what changed, find bugs in X) — those continue
     through the standard analyze contract
  - WHEN EXPLAIN_MODE=true: the NEXT user-visible assistant message MUST be the
    E0/E1 explain-session opener; any direct explanation/summary/walkthrough
    emitted before the four E1 gates resolve is INVALID (see {cf-studio-path}/.core/requirements/storytelling.md AP-#0)
  - WHEN CF_HELP_PRESET=true: the preset variables are the E1 gate answers;
    MUST_NOT ask those gates again; MUST run the normal Storytelling Protocol
    E0-E5 against EXPLAIN_TARGET={cf-studio-path}; MUST_NOT replace it with a
    custom one-shot overview/status summary; MUST render diagrams as ASCII
    inline in chat unless the user overrides mid-session
  - MUST set enforceRemediationPrompts=false ONLY when EXPLAIN_MODE=true
  - Each methodology is loaded by exactly one matched sub-agent; the orchestrator
    only routes and merges outputs

NOTES:
  Storytelling mode-coupled review requires explicit storytelling intent:
    "explain this PR review-style", "walk me through this PR with panel feedback",
    "storytelling review of X", or any explain-family verb followed by a
    review-mode pick at the always-ask prompt.
  When the prompt-engineering sub-agent runs: compact-prompts optimization is
    a HIGH-priority requirement; interaction UX is a CRITICAL requirement.
  Plain analyze intent stays in standard analyze: ordinary review/audit/inspection
    MUST NOT auto-enter EXPLAIN_MODE.
```

Implementation note: the `AnalyzePreamble` unit above is authoritative. Keep routing here, defer full methodologies to the matched sub-agents, and enforce the same first-turn storytelling contract: when `EXPLAIN_MODE=true`, the next user-visible message is the E0/E1 opener. For prompt-review routes, compact-prompts optimization stays **HIGH** priority and interaction UX stays **CRITICAL**.
