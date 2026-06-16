# Explain Deliver

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
  LOAD {cf-studio-path}/.core/skills/studio/modules/explain-export-completion.md
  CONTINUE ExplainExport WHEN EXPLAIN_EXPORT == true
  CONTINUE ExplainCompletion WHEN EXPLAIN_EXPORT != true
RULES:
  ALWAYS emit or return an EXPLAIN_RESULT envelope before every terminal exit or next-actions handoff (complete, checkpointed, or cancelled)
  NEVER auto-save checkpoints, bookmarks, or open-questions without explicit user consent
NOTES:
  Envelope shape: { "type": "EXPLAIN_RESULT", "status": "complete|checkpointed|cancelled", "session_id": "<id|null>", "progress": "<X/N|null>", "resume_path": "<path|null>" }
```
