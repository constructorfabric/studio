---
name: analyze-validation-criteria
description: "Invoke when verifying the Analyze workflow Validation Criteria post-flight checklist before ending the response."
purpose: Analyze workflow Validation Criteria — post-flight checklist verified before ending the response
loaded_by: workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Validation Criteria](#validation-criteria)

<!-- /toc -->

```text
UNIT AnalyzeValidationCriteria

PURPOSE:
  Post-flight checklist gate verified before ending the response.

DO:
  Verify ALL items below; MUST_NOT end the response until all applicable items pass.

RULES:
  - MUST verify every applicable item in this checklist before ending the response
  - MUST_NOT claim PASS for any item that is not verified
  - MUST_NOT end the response while any applicable item is unchecked
```

## Validation Criteria

- [ ] `skills/studio/protocol.md` executed
- [ ] Dependencies loaded when required for the active methodology (checklist, template, example for artifact review; methodology-specific files for code/prompt review)
- [ ] Analysis scope clarified
- [ ] Traceability mode determined when applicable
- [ ] Registry consistency verified when applicable
- [ ] Cross-reference scope identified
- [ ] Target exists and readable
- [ ] Deterministic gate executed when available and required, otherwise explicitly marked `SKIPPED` with reason
- [ ] Language content check executed when `allowed_content_languages` is configured, otherwise explicitly marked `SKIPPED (not configured)`
- [ ] ID uniqueness verified (within artifact and across system)
- [ ] Cross-references verified (outgoing and incoming)
- [ ] Traceability markers verified (if `FULL` traceability)
- [ ] Result correctly reported (PASS/FAIL/PARTIAL)
- [ ] Prompt review output follows the prompt-engineering reviewer section order when `PROMPT_REVIEW=true`; prompt-bug-only output uses the prompt-bug-finder block without requiring prompt-engineering sections
- [ ] Prompt Review Partial Checkpoint output is allowed when `PROMPT_REVIEW=true` and `checkpoint.type = "PARTIAL_CHECKPOINT"`; in that case the checkpoint block, resume anchors, covered layers, uncovered layers, and supported findings replace the full 10-layer report until review resumes
- [ ] When `PROMPT_REVIEW=true`, all 10 prompt-engineering layers have explicit PASS / FAIL / PARTIAL / N/A statuses; any N/A status includes evidence that the layer is genuinely inapplicable
- [ ] When `PROMPT_REVIEW=true`, the prompt review includes evidence quotes with line numbers for every FAIL / PARTIAL layer and enough PASS evidence to support the claimed coverage
- [ ] When `PROMPT_REVIEW=true`, compact-prompts and decision-point UX checks were executed and reported, not inferred from section order alone
- [ ] When `PROMPT_REVIEW=true`, the `findings` JSON block is present, parseable, and ID-aligned with the visible issues list; empty array is allowed only when every layer passed or was evidence-backed N/A
- [ ] When `PROMPT_REVIEW=true`, every finding has severity, path, line or null, category, evidence_quote, root_cause, suggested_fix, `mechanical`, and non-empty `mechanical_rationale`
- [ ] Recommendations provided (if PASS)
- [ ] For outputs with actionable issues, the final-response gate self-check was completed before ending the response
- [ ] `Remediation Handoff` menu emitted as the FINAL section when actionable issues exist
- [ ] Handoff menu lists exactly the three canonical options (in-session continuation, Fix Prompt on demand, Plan Prompt on demand) with actual finding counts (High/Medium/Low)
- [ ] Workflow response did not end before the handoff menu was emitted
- [ ] For code review / `review my changes` requests, any reported fixable finding produced the handoff menu in the same response
- [ ] When the user picks option 2 or 3 in their next turn, the corresponding `Fix Prompt` / `Plan Prompt` is emitted as the FINAL section of that next response; option 1 is dispatched in-session without emitting any prompt block
- [ ] Output to chat only
- [ ] Next steps suggested
- [ ] No completed `/cf-analyze` path bypassed Phase 3 except the deterministic-FAIL blocking branch defined in `{cf-studio-path}/.core/workflows/analyze/phase-2-det-gate.md` and except `EXPLAIN_MODE=true` runs which legitimately bypass Phase 3 per `{cf-studio-path}/.core/workflows/analyze/preamble.md`; incomplete semantic review is reported as `PARTIAL` with resume guidance
- [ ] When `EXPLAIN_MODE=true`: Storytelling Protocol phases E0-E5 from `{cf-studio-path}/.core/requirements/storytelling.md` were followed in order
- [ ] When `EXPLAIN_MODE=true`: storytelling `{mode}` (presentation / review / onboarding / decision / socratic / change-impact) was resolved at session start via the **always-ask** prompt (methodology emitted the 6-mode prompt with a suggested default, waited for explicit user confirmation; mode was NEVER auto-selected from intent verbs / KIND defaults / project preference) and applied consistently throughout (audience composition, slot semantics, body style, wrap-output schema match the resolved mode). Exception: when `CF_HELP_PRESET=true`, `cf help` pre-fills mode/disposition/audience/context variables and those values count as explicit gate answers.
- [ ] When `CF_HELP_PRESET=true`: the normal Storytelling Protocol E0-E5 ran against `{cf-studio-path}`; output was not replaced by a custom one-shot `Cf Overview` status summary.
- [ ] When `EXPLAIN_MODE=true`: Phase 4 used the Storytelling Output schema (Wrap section) and did NOT emit the `Remediation Handoff` menu, `Fix Prompt`, or `Plan Prompt`
- [ ] When `EXPLAIN_MODE=true`: Phase 5 (Offer Next Steps) was skipped — only the Storytelling Output schema's `Suggested Next Steps` section was emitted; no second/duplicate next-step menu
- [ ] When `EXPLAIN_MODE=true`: every portion ≤ resolved page-size soft target (default 200 words; configurable per Page Size Preference, fits on half a screen — no scrolling) with 7-slot navigation block in Next-first order (Next / Deeper / Lateral / Recap / Ask / Wrap / Back) and one `→ suggested`
- [ ] When `EXPLAIN_MODE=true`: Next nav slots offered topic-pick menus with continue / skip-ahead / revisit options plus `Custom` and `Back`; bare `next` or slot `1` did not jump directly to one preselected topic
- [ ] When `EXPLAIN_MODE=true`: Deeper/Lateral nav slots offered topic-pick menus with `Custom` and `Back`; bare `deeper` / `lateral` or slots `2` / `3` did not jump directly to one preselected topic
- [ ] When `EXPLAIN_MODE=true`: every non-trivial claim has a source reference emitted as a **clickable Markdown link** (e.g. `(see [DESIGN.md §4.2](DESIGN.md#42-data-model))`, never plain-text); ungrounded claims silently skipped (no agent-initiated `[?]` markers in the methodology's narrative); open-questions buffer entries originate ONLY from user-asked questions the input cannot answer
