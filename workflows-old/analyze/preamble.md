---
name: analyze-preamble
description: "Invoke when loading the analyze workflow preamble for route-only methodology selection; heavy methodologies load inside matched sub-agents."
purpose: Analyze workflow preamble — route-only methodology selection; heavy methodologies load inside matched sub-agents
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzePreamble

PURPOSE:
  Initialize per-run analyze flags, perform route-only methodology selection,
  and handle storytelling trigger detection before any phase executes.

STATE:
  - SET SEMANTIC_ONLY: false | true
    default: false
    reset: start of workflow run
  - SET CHANGE_REVIEW: false | true
    default: false
  - SET CODE_REVIEW: false | true
    default: false
  - SET CODE_BUG_REVIEW: false | true
    default: false
  - SET CONSISTENCY_REVIEW: false | true
    default: false
  - SET PROMPT_REVIEW: false | true
    default: false
  - SET PROMPT_BUG_REVIEW: false | true
    default: false
  - SET EXPLAIN_MODE: false | true
    default: false
  - SET ARTIFACT_REVIEW: false | true
    default: false
  - SET FREEFORM_REVIEW: false | true
    default: false
  - SET CF_PHASE_GATE: armed
    default: armed
    reset: start of workflow run
  - SET enforceRemediationPrompts: true | false
    default: true
    reset: start of workflow run
  - SET CF_HELP_PRESET: false | true
    default: false
  - SET EXPLAIN_TARGET: string | null
    default: null
  - SET STORYTELLING_MODE: string | null
    default: null
  - SET STORYTELLING_ARTIFACT_DISPOSITION: string | null
    default: null
  - SET STORYTELLING_AUDIENCE: string | null
    default: null
  - SET STORYTELLING_ARTIFACT_LANGUAGE: string | null
    default: null
  - SET STORYTELLING_CONTEXT_PACK_STRATEGY: string | null
    default: null
  - SET STORYTELLING_PLAN_APPROVED: false | true
    default: false
  - SET STORYTELLING_DIAGRAM_FORMAT: ascii | mermaid | both | null
    default: null
  - SET STORYTELLING_DIAGRAM_FORMAT_PRESET: false | true
    default: false
  - SET STORYTELLING_HELP_GOAL: string | null
    default: null
  - SET STORYTELLING_PHASE: e0 | e1_mode | e1_disposition | e1_audience | e1_plan | e2 | e5 | done
    default: e0

DO:
  - RUN ALWAYS load {cf-studio-path}/.core/skills/studio/SKILL.md WHEN {cfs_mode} == off
  - RUN ALWAYS load {cf-studio-path}/.core/skills/studio/protocol.md FIRST
  - RUN Initialize workflow-owned analysis flags to their defaults:
    SEMANTIC_ONLY=false, CHANGE_REVIEW=false, CODE_REVIEW=false,
    CODE_BUG_REVIEW=false, CONSISTENCY_REVIEW=false, PROMPT_REVIEW=false,
    PROMPT_BUG_REVIEW=false, EXPLAIN_MODE=false, ARTIFACT_REVIEW=false,
    FREEFORM_REVIEW=false, CF_PHASE_GATE=armed, enforceRemediationPrompts=true
  - RUN PRESERVE route-supplied preset variables if already set by routing:
    CF_HELP_PRESET, EXPLAIN_TARGET, STORYTELLING_MODE,
    STORYTELLING_ARTIFACT_DISPOSITION, STORYTELLING_AUDIENCE,
    STORYTELLING_ARTIFACT_LANGUAGE, STORYTELLING_CONTEXT_PACK_STRATEGY,
    STORYTELLING_PLAN_APPROVED,
    STORYTELLING_DIAGRAM_FORMAT, STORYTELLING_DIAGRAM_FORMAT_PRESET,
    STORYTELLING_HELP_GOAL
  - REQUIRE CF_HELP_PRESET == true:
    - LOAD {cf-studio-path}/.core/requirements/storytelling.md
    - SET EXPLAIN_MODE = true
    - SET EXPLAIN_TARGET = "{cf-studio-path}" unless already set
    - SET STORYTELLING_MODE = "presentation" unless already set
    - SET STORYTELLING_ARTIFACT_DISPOSITION = "chat-only" unless already set
    - SET STORYTELLING_AUDIENCE = "Constructor Studio newcomers" unless already set
    - SET STORYTELLING_CONTEXT_PACK_STRATEGY = "hybrid" unless already set
    - SET STORYTELLING_PLAN_APPROVED = true
    - SET STORYTELLING_DIAGRAM_FORMAT = "ascii" unless already set
    - SET STORYTELLING_DIAGRAM_FORMAT_PRESET = true
    - SET STORYTELLING_PHASE = e0
    - SET enforceRemediationPrompts = false
    - NEVER Phase 2 deterministic gate
    - NEVER Phase 3 standard semantic checklist
    - NEVER Phase 5 (Storytelling Output emits Suggested Next Steps)
    - REQUIRE Storytelling Output schema in Phase 4
    - NEVER emitting analyze remediation prompt blocks
    - REQUIRE HelpPresetStorytellingFirstOutputContract before any
      user-visible assistant output
    - CONTINUE through the normal Storytelling Protocol E0-E5 using the
    prefilled variables as already-resolved gate answers
    do not ask mode, disposition, audience, context-pack-strategy, export,
    plan-approval, or diagram-format questions for this run
    - NEVER custom one-shot help rendering or a generic status overview
  - RUN Match methodology flags from user request:
    IF code/codebase/implementation analysis:
      - SET CODE_REVIEW = true
      - NEVER opening code-checklist.md or bug-finding.md in the orchestrator
    IF bug hunting / logic bug / edge-case / regression / root-cause / "all bugs":
      - SET CODE_BUG_REVIEW = true
      - NEVER opening bug-finding.md in the orchestrator
    IF documentation/artifact consistency / contradiction / cross-document alignment:
      - SET CONSISTENCY_REVIEW = true
      - NEVER opening consistency-checklist.md in the orchestrator
    IF instruction targets (system prompts, agent prompts, LLM prompts, agent
       instructions/guidelines, skills, workflows, methodologies, AGENTS.md,
       navigation rules, AI-agent instruction docs) OR user mentions
       "prompt engineering review", "prompt bug review", "prompt bugs",
       "instruction quality":
      - SET PROMPT_REVIEW = true
      - NEVER opening prompt-engineering.md in the orchestrator
    IF defect-oriented prompt/instruction request (prompt bug review, prompt bugs,
       hidden failure modes, unsafe behavior, regressions, instruction conflicts,
       routing defects, root-cause search):
      - SET PROMPT_BUG_REVIEW = true
      - NEVER opening prompt-bug-finding.md in the orchestrator
  - REQUIRE all standard methodology flags are false (CODE_REVIEW=false,
    CODE_BUG_REVIEW=false, CONSISTENCY_REVIEW=false, PROMPT_REVIEW=false,
    PROMPT_BUG_REVIEW=false, CHANGE_REVIEW=false, ARTIFACT_REVIEW=false)
    AND CF_HELP_PRESET=false AND EXPLAIN_MODE=false
    AND ORIGINAL_INTENT has meaningful task content (user provided a request,
    question, custom instruction, or custom prompt that did not match any
    standard methodology — i.e. ORIGINAL_INTENT is NOT a bare /cf-analyze or
    "cf analyze" invocation with no additional text):
    - SET FREEFORM_REVIEW = true
    - NEVER opening any methodology checklist, reviewer file, or bug-finding file
      in the orchestrator for this path
  - REQUIRE all methodology flags including FREEFORM_REVIEW are false
    (CODE_REVIEW=false, CODE_BUG_REVIEW=false, CONSISTENCY_REVIEW=false,
    PROMPT_REVIEW=false, PROMPT_BUG_REVIEW=false, CHANGE_REVIEW=false,
    ARTIFACT_REVIEW=false, FREEFORM_REVIEW=false)
    AND CF_HELP_PRESET=false AND EXPLAIN_MODE=false
    AND ORIGINAL_INTENT contains no identifiable analysis target
    (bare skill invocation such as /cf-analyze or cf analyze with no task text):
    - EMIT "What would you like me to analyze? Describe the target — e.g. a file path, directory, artifact name, PR number, diff, or paste content — and the review type (code review, prompt review, artifact validation, change review, or other)."
    - WAIT user.reply
    - STOP_TURN
    - NEVER route to or invoke AmbiguousRoutingFallback for this case; this is an in-workflow scope prompt, not a routing fallback
  - REQUIRE multiple methodology flags are true:
    Phase 3 dispatches multiple sub-agents
  - REQUIRE explicit pedagogical/storytelling intent:
    - LOAD {cf-studio-path}/.core/requirements/storytelling.md
    - SET EXPLAIN_MODE = true
    - NEVER Phase 2 deterministic gate
    - NEVER Phase 3 standard semantic checklist
    - REQUIRE Storytelling Output schema in Phase 4
    - NEVER Phase 5 (Storytelling Output emits Suggested Next Steps)
    - SET enforceRemediationPrompts = false
    - NEVER emitting analyze remediation prompt blocks
  - REQUIRE EXPLAIN_MODE == true AND (PROMPT_REVIEW == true OR PROMPT_BUG_REVIEW == true):
    - EMIT_MENU StorytellingVsPromptReviewMenu
    - WAIT user.reply
    - STOP_TURN

MENU StorytellingVsPromptReviewMenu:
  TITLE: "Your request combines storytelling and prompt-review intent. Which should I run?"
  OPTIONS:
    1 -> SET EXPLAIN_MODE = true; proceed with storytelling walkthrough
    2 -> SET PROMPT_REVIEW = true; SET PROMPT_BUG_REVIEW = true; SET EXPLAIN_MODE = false; proceed with prompt engineering review
  INVALID:
    EMIT "Reply `1` or `2`."
    WAIT user.reply
    STOP_TURN

INVARIANTS:
  - ALWAYS initialize workflow-owned analysis flags before Phase 0 runs
  - ALWAYS preserve route-supplied preset variables across initialization
  - ALWAYS Phase 0 (phase-0-dependencies.md) NEVER re-initialize flags to false
  - NEVER auto-enter EXPLAIN_MODE for ordinary review/audit/inspect requests
    (review my changes, review this PR, review this diff, audit this design,
     inspect this code, check what changed, find bugs in X) — those continue
     through the standard analyze contract
  - ALWAYS WHEN EXPLAIN_MODE=true: the NEXT user-visible assistant message ALWAYS be the
    E0/E1 explain-session opener; any direct explanation/summary/walkthrough
    emitted before the four E1 gates resolve is INVALID (see {cf-studio-path}/.core/requirements/storytelling.md AP-#0)
  - ALWAYS WHEN CF_HELP_PRESET=true: the preset variables are the E1 gate answers;
    NEVER ask those gates again; ALWAYS run the normal Storytelling Protocol
    E0-E5 against EXPLAIN_TARGET={cf-studio-path}; NEVER replace it with a
    custom one-shot overview/status summary; ALWAYS render diagrams as ASCII
    inline in chat unless the user overrides mid-session
  - ALWAYS WHEN CF_HELP_PRESET=true: preset resolution skips prompts, not phases;
    Phase E0/E1 state is still represented, E2 portion delivery still uses the
    Storytelling portion shape, and terminal output still uses the E5 wrap
    schema
  - ALWAYS set enforceRemediationPrompts=false ONLY when EXPLAIN_MODE=true
  - ALWAYS Each methodology is loaded by exactly one matched sub-agent; the orchestrator
    only routes and merges outputs
  - NEVER apply or invoke AmbiguousRoutingFallback from within the analyze workflow;
    when the triggering request is a bare skill invocation with no target or methodology
    (e.g. /cf-analyze, cf analyze alone), ALWAYS ask for the missing target or scope
    inline using the no-target gate above — never fall back to the routing menu
  - ALWAYS FREEFORM_REVIEW is mutually exclusive with the no-target state: if
    FREEFORM_REVIEW=true, ORIGINAL_INTENT always contains a meaningful task/request
    to use as freeform analysis criteria; NEVER set FREEFORM_REVIEW=true for a bare
    /cf-analyze invocation with no task text
  - ALWAYS FREEFORM_REVIEW is set only when no standard methodology flag matched;
    NEVER set FREEFORM_REVIEW=true when any of CODE_REVIEW, CODE_BUG_REVIEW,
    CONSISTENCY_REVIEW, PROMPT_REVIEW, PROMPT_BUG_REVIEW, CHANGE_REVIEW,
    ARTIFACT_REVIEW, CF_HELP_PRESET, or EXPLAIN_MODE is true

```pdsl
UNIT HelpPresetStorytellingFirstOutputContract

PURPOSE:
  Make the first legal cf-help explain output explicit and fail-closed.

WHEN:
  - REQUIRE CF_HELP_PRESET == true

RULES:
  - ALWAYS IF EXPLAIN_MODE == true:
      EXPLAIN_MODE first-output contract wins over CF_HELP_PRESET; the next
      user-visible assistant message MUST be the E0/E1 explain-session opener
      with preset answers represented, not an E2 portion
  - ALWAYS the next user-visible assistant message MUST be one of:
      1. a Storytelling E0/E1 opener for EXPLAIN_TARGET={cf-studio-path}
      2. a Storytelling E5 wrap after legal portion delivery or user-requested wrap
      3. a deterministic load/error menu from the active workflow
  - ALWAYS legal E0/E1 help-preset openers include the input-access log,
    resolved preset mode/disposition/audience/context, and plan-approval state
  - NEVER emit a standalone `Constructor Studio Help`, `Common requests`,
    command-surface summary, generic status overview, or `EXPLAIN_RESULT`
    completion envelope before the legal Storytelling output above
  - ALWAYS if the planned response is a summary/help overview instead of a
    legal Storytelling output, discard it and restart from this contract
```

NOTES:
  Storytelling mode-coupled review requires explicit storytelling intent:
    "explain this PR review-style", "walk me through this PR with panel feedback",
    "storytelling review of X", or any explain-family verb followed by a
    review-mode pick at the always-ask prompt.
  When the prompt-engineering sub-agent runs: compact-prompts optimization is
    a HIGH-priority requirement; interaction UX is a CRITICAL requirement.
  Plain analyze intent stays in standard analyze: ordinary review/audit/inspection
    NEVER auto-enter EXPLAIN_MODE.
```
