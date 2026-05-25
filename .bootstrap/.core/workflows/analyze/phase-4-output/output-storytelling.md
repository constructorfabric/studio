---
name: analyze-phase-4-output-storytelling
description: "Invoke when EXPLAIN_MODE=true to render Phase 4 Storytelling output by delegating to storytelling.md Phase E5 (Wrap); MUST NOT inline the wrap schema body."
purpose: Phase 4 Storytelling output (EXPLAIN_MODE=true) — delegates to storytelling.md Phase E5 (Wrap); MUST NOT inline the wrap schema body
loaded_by: workflows/analyze.md
version: 1.0
---

### Storytelling Output (EXPLAIN_MODE)
`EXPLAIN_MODE=true` does **not** use the Standard Analysis Output template above and does **not** emit `Fix Prompt` / `Plan Prompt`. It MUST use the Storytelling Output contract from `storytelling.md` Phase E5 (Wrap):

1. `Storytelling Wrap-up` heading
2. `Session` block (role, audience, input, progress, diagrams, open questions, bookmarks, glossary counts)
3. `Key Takeaways` (3-5 bullets, each with source reference; bookmarked items appear verbatim)
4. `Open Questions` list with save prompt and default path
5. `Glossary` (only if non-empty)
6. `Bookmarked Takeaways Export` save prompt (only if bookmarks non-empty)
7. `Suggested Next Steps` (2-3 contextual options; never list all four candidates)

The wrap response is the **complete** Phase 4 output for `EXPLAIN_MODE`. Do NOT append `Fix Prompt`, `Plan Prompt`, or any analysis-style headings.
