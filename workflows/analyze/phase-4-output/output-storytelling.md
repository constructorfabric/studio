---
name: analyze-phase-4-output-storytelling
description: "Invoke when EXPLAIN_MODE=true to render Phase 4 Storytelling output by delegating to storytelling.md Phase E5 (Wrap); MUST NOT inline the wrap schema body."
purpose: Phase 4 Storytelling output (EXPLAIN_MODE=true) — delegates to storytelling.md Phase E5 (Wrap); MUST NOT inline the wrap schema body
loaded_by: workflows/analyze.md
version: 1.0
---

```pdsl
UNIT AnalyzePhase4Storytelling

PURPOSE:
  Render Phase 4 output for EXPLAIN_MODE using the Storytelling Wrap contract.

WHEN:
  - REQUIRE EXPLAIN_MODE == true

DO:
  - RUN Follow storytelling.md Phase E5 (Wrap) contract exactly:
    - RUN "Storytelling Wrap-up" heading
    - Session block (role, audience, input, progress, diagrams, open questions,
       bookmarks, glossary counts)
    - Key Takeaways (3-5 bullets, each with source reference;
       bookmarked items appear verbatim)
    - Open Questions list with save prompt and default path
    - Glossary (only if non-empty)
    - Bookmarked Takeaways Export save prompt (only if bookmarks non-empty)
    - Suggested Next Steps (2-3 contextual options; never list all four candidates)
  - RUN This wrap response is the COMPLETE Phase 4 output for EXPLAIN_MODE.

RULES:
  - NEVER use the Standard Analysis Output template
  - NEVER emit Fix Prompt, Plan Prompt, or any analysis-style headings
  - NEVER inline the wrap schema body; delegate to storytelling.md Phase E5
  - NEVER emit the Remediation Handoff menu (EXPLAIN_MODE disables it)
```
