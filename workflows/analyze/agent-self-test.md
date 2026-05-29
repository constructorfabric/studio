---
name: analyze-agent-self-test
description: "Invoke when running the Analyze Agent Self-Test (STRICT mode) to answer canonical questions with evidence before ending the response."
purpose: Analyze Agent Self-Test (STRICT mode) — canonical questions, evidence requirements, sample answer table, RELAXED-mode disclaimer
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Agent Self-Test (STRICT mode — AFTER completing work)](#agent-self-test-strict-mode--after-completing-work)

<!-- /toc -->

```text
UNIT AnalyzeAgentSelfTest

PURPOSE:
  Run the canonical STRICT-mode self-test after completing analysis work; all
  questions must be answered with evidence before the response ends.

WHEN:
  STRICT mode AND finalization phase reached

DO:
  Answer all questions in the table below with evidence.
  EMIT self-test results table.
  IF any answer is NO or lacks evidence:
    EMIT "Analysis is INVALID, must restart"
    STOP_TURN

RULES:
  - MUST answer AFTER doing the work, not before
  - MUST include evidence for every answer
  - MUST_NOT claim YES without supporting evidence
```

## Agent Self-Test (STRICT mode — AFTER completing work)

Answer these AFTER doing the work and include evidence in the output.

| Question | Evidence required |
|----------|-------------------|
| Did I read `{cf-studio-path}/.core/skills/studio/protocol.md` before starting? | Show loaded rules and dependencies. |
| Did I use Read tool to read the ENTIRE artifact THIS turn? | `Read {path}: {N} lines` |
| Did I check EVERY checklist category individually? | Category breakdown table with per-category status. |
| Did I provide evidence (quotes, line numbers) for each PASS/FAIL/N/A? | Evidence column in category table. |
| For N/A claims, did I quote explicit "Not applicable" statements from the document? | Quote lines showing the author marked N/A. |
| Am I reporting from actual file content, not memory/summary? | Fresh Read tool call visible this turn. |
| If I reported actionable issues, did I end the response with the `Remediation Handoff` menu? | Final section is the 3-option handoff menu (in-session continuation / Fix Prompt on demand / Plan Prompt on demand) with actual finding counts. (N/A when `EXPLAIN_MODE=true` — see next row.) |
| If `EXPLAIN_MODE=true`, was the `Remediation Handoff` menu suppressed and the Storytelling Output schema (Phase E5 Wrap) used in Phase 4? | Wrap output emitted with Session / Key Takeaways / Open Questions / (optional Glossary, Bookmark Export) / Suggested Next Steps; no handoff menu, no `Fix Prompt` / `Plan Prompt` headings. |

Sample:
```markdown
### Agent Self-Test Results
| Question | Answer | Evidence |
|----------|--------|----------|
| Read execution-protocol? | YES | Loaded cf-sdlc rules, checklist.md |
| Read artifact via Read tool? | YES | Read DESIGN.md: 742 lines |
| Checked every category? | YES | 12 categories in table above |
| Evidence for each status? | YES | Quotes included per category |
| N/A has document quotes? | YES | Lines 698, 712, 725 |
| Based on fresh read? | YES | Read tool called this turn |
| Remediation Handoff menu emitted? | YES | Final section is the 3-option menu with actual finding counts (N/A when EXPLAIN_MODE=true) |
| EXPLAIN_MODE Storytelling schema used? | N/A | EXPLAIN_MODE=false (this run is standard analyze) |
```
**If ANY answer is NO or lacks evidence → Analysis is INVALID, must restart**

RELAXED mode disclaimer:
```text
⚠️ Self-test skipped (RELAXED mode — no Constructor Studio rules)
```
