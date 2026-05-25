---
name: analyze-preamble
description: "Invoke when loading the analyze workflow preamble for route-only methodology selection; heavy methodologies load inside matched sub-agents."
purpose: Analyze workflow preamble — route-only methodology selection; heavy methodologies load inside matched sub-agents
loaded_by: workflows/analyze.md
version: 1.0
---

ALWAYS open and follow `{cf-studio-path}/.core/skills/studio/SKILL.md` WHEN {cfs_mode} is `off`

**Type**: Analysis

ALWAYS open and follow `skills/studio/protocol.md` FIRST

Initialize per-run analyze flags before matching: `SEMANTIC_ONLY=false`, `CHANGE_REVIEW=false`, `CODE_REVIEW=false`, `CODE_BUG_REVIEW=false`, `CONSISTENCY_REVIEW=false`, `PROMPT_REVIEW=false`, `PROMPT_BUG_REVIEW=false`, `EXPLAIN_MODE=false`, `ARTIFACT_REVIEW=false`, `CF_PHASE_GATE=armed`. Phase 0 (`phase-0-dependencies.md`) only MATCHES conditions and SETS flags to true; it MUST NOT re-initialize them to false. CHANGE_REVIEW is set true by phase-0-dependencies.md; ARTIFACT_REVIEW is set true by phase-0-dependencies.md when the resolved target is an artifact and no prompt/code methodology has taken ownership.

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

**CRITICAL routing invariant**: when EXPLAIN_MODE=true the NEXT user-visible assistant message MUST be the E0/E1 explain-session opener; any direct explanation/summary/walkthrough emitted before the four E1 gates resolve is INVALID and MUST be discarded — see storytelling.md AP-#0 for the full invariant.

When the prompt-engineering sub-agent runs, it treats compact-prompts optimization as a **HIGH-priority requirement**.

When the prompt-engineering or prompt-bug-finding sub-agent runs, it treats interaction UX as a **CRITICAL requirement**.
