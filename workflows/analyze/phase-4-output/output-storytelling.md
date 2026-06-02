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
  EXPLAIN_MODE == true

DO:
  Follow storytelling.md Phase E5 (Wrap) contract exactly:
    1. "Storytelling Wrap-up" heading
    2. Session block (role, audience, input, progress, diagrams, open questions,
       bookmarks, glossary counts)
    3. Key Takeaways (3-5 bullets, each with source reference;
       bookmarked items appear verbatim)
    4. Open Questions list with save prompt and default path
    5. Glossary (only if non-empty)
    6. Bookmarked Takeaways Export save prompt (only if bookmarks non-empty)
    7. Suggested Next Steps (2-3 contextual options; never list all four candidates)
  This wrap response is the COMPLETE Phase 4 output for EXPLAIN_MODE.

RULES:
  - MUST_NOT use the Standard Analysis Output template
  - MUST_NOT emit Fix Prompt, Plan Prompt, or any analysis-style headings
  - MUST_NOT inline the wrap schema body; delegate to storytelling.md Phase E5
  - MUST_NOT emit the Remediation Handoff menu (EXPLAIN_MODE disables it)
```
