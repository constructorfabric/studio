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
    FORBID emitting Fix Prompt / Plan Prompt
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
    FORBID emitting Fix Prompt / Plan Prompt
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

ALWAYS open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` WHEN {cfs_mode} is `off`

**Type**: Analysis

ALWAYS open and follow `{cf-studio-path}/.core/skills/studio/protocol.md` FIRST

Initialize per-run analyze flags before matching: `SEMANTIC_ONLY=false`, `CHANGE_REVIEW=false`, `CODE_REVIEW=false`, `CODE_BUG_REVIEW=false`, `CONSISTENCY_REVIEW=false`, `PROMPT_REVIEW=false`, `PROMPT_BUG_REVIEW=false`, `EXPLAIN_MODE=false`, `ARTIFACT_REVIEW=false`, `CF_PHASE_GATE=armed`. Preserve any route-supplied preset variables such as `CF_HELP_PRESET`, `EXPLAIN_TARGET`, `STORYTELLING_DIAGRAM_FORMAT`, and `STORYTELLING_*` values; do not reset them to defaults after routing. Phase 0 (`phase-0-dependencies.md`) only MATCHES conditions and SETS flags to true; it MUST NOT re-initialize them to false. CHANGE_REVIEW is set true by phase-0-dependencies.md; ARTIFACT_REVIEW is set true by phase-0-dependencies.md when the resolved target is an artifact and no prompt/code methodology has taken ownership.

WHEN `CF_HELP_PRESET=true`, treat `cf help` as a normal explain/storytelling request whose required variables are already resolved: `EXPLAIN_TARGET={cf-studio-path}`, `STORYTELLING_MODE=presentation`, `STORYTELLING_ARTIFACT_DISPOSITION=chat-only`, `STORYTELLING_AUDIENCE=Constructor Studio newcomers`, `STORYTELLING_CONTEXT_PACK_STRATEGY=hybrid`, `STORYTELLING_PLAN_APPROVED=true`, `STORYTELLING_DIAGRAM_FORMAT=ascii`, and `STORYTELLING_DIAGRAM_FORMAT_PRESET=true`. Do not ask mode, disposition, audience, context-pack-strategy, export, plan-approval, or diagram-format questions; run the normal Storytelling Protocol E0-E5 against `{cf-studio-path}` with standard portions, source grounding, navigation, and ASCII inline diagrams. Do NOT replace it with a custom one-shot `Cf Overview` status summary.

WHEN user requests analysis of code, codebase changes, or implementation behavior (Code mode), set `CODE_REVIEW=true`. Do NOT open `code-checklist.md` or `bug-finding.md` in the orchestrator; Phase 3 dispatches separate code methodology sub-agents.

WHEN user requests bug hunting, logic bug review, edge-case search, regression risk analysis, root-cause search in code, or asks to find "all bugs/problems" in code, set `CODE_BUG_REVIEW=true`. Do NOT open `bug-finding.md` in the orchestrator.

WHEN user requests analysis of documentation/artifact consistency, contradiction detection, or cross-document alignment, set `CONSISTENCY_REVIEW=true`. Do NOT open `consistency-checklist.md` in the orchestrator; dispatch the consistency reviewer.

WHEN user requests analysis of the following instruction targets, set `PROMPT_REVIEW=true`. Do NOT open `prompt-engineering.md` in the orchestrator:
- System prompts, agent prompts, or LLM prompts
- Agent instructions or agent guidelines
- Skills, workflows, or methodologies
- AGENTS.md or navigation rules
- Any document containing instructions for AI agents
- User explicitly mentions `prompt engineering review`, `prompt bug review`, `prompt bugs`, or `instruction quality`

WHEN the prompt/instruction request is defect-oriented (`prompt bug review`, `prompt bugs`, hidden failure modes, unsafe behavior, regressions, instruction conflicts, routing defects, root-cause search), also set `PROMPT_BUG_REVIEW=true`. Do NOT open `prompt-bug-finding.md` in the orchestrator.

If multiple methodology flags are true, Phase 3 dispatches multiple sub-agents. Each methodology is loaded by exactly one matched sub-agent; the orchestrator only routes and merges outputs.

ALWAYS open and follow `{cf-studio-path}/.core/requirements/storytelling.md` WHEN user signals explicit pedagogical/storytelling intent (intent-based; canonical trigger list and mode disambiguation live in storytelling.md).

**Plain analyze intent stays in standard analyze**: ordinary review / audit / inspection requests (`review my changes`, `review this PR`, `review this diff`, `audit this design`, `inspect this code`, `check what changed`, `find bugs in X`) MUST NOT auto-enter `EXPLAIN_MODE` — they continue through the standard analyze contract (deterministic gate + semantic checklist + Remediation Handoff menu on actionable issues). Storytelling mode-coupled review requires explicit storytelling intent: `explain this PR review-style`, `walk me through this PR with panel feedback`, `storytelling review of X`, or any `explain`-family verb followed by a review-mode pick at the always-ask prompt.

WHEN this rule triggers, set `EXPLAIN_MODE=true`, skip Phase 2 deterministic gate, skip Phase 3 standard semantic checklist, use the Storytelling Output schema in Phase 4, skip Phase 5 (Storytelling Output already emits Suggested Next Steps), and override `enforceRemediationPrompts` (do NOT emit `Fix Prompt` / `Plan Prompt` — open questions are author-routed by user, not Constructor Studio-routed). If both `EXPLAIN_MODE` and `PROMPT_REVIEW` intents are detected on the same request, ask the user to disambiguate before loading either methodology.

```text
Your request combines storytelling and prompt-review intent. Which should I run?
1. Storytelling walkthrough (EXPLAIN_MODE)
2. Prompt engineering review (PROMPT_REVIEW)
Reply `1` or `2`.
```

**CRITICAL routing invariant**: when EXPLAIN_MODE=true the NEXT user-visible assistant message MUST be the E0/E1 explain-session opener; any direct explanation/summary/walkthrough emitted before the four E1 gates resolve is INVALID and MUST be discarded. The full invariant is in {cf-studio-path}/.core/requirements/storytelling.md AP-#0.

When the prompt-engineering sub-agent runs, it treats compact-prompts optimization as a **HIGH-priority requirement**.

When the prompt-engineering or prompt-bug-finding sub-agent runs, it treats interaction UX as a **CRITICAL requirement**.
