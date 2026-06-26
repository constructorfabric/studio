---
cf: true
type: workflow
name: cf-kit-review
description: "Invoke when the user or another skill or workflow needs or asks to semantically review scoped kit prompt, document, or code assets and report findings."
version: 0.1
purpose: Route semantic kit prompt, document, or code review into the correct specialist workflow instead of inventing kit-local review logic.
---

# cf-kit-review

This workflow is the canonical thin semantic review entrypoint for kit prompt,
document, and code work.

```pdsl
UNIT KitReviewPreset
PURPOSE: Run semantic kit review by delegating to the correct specialist review workflow.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/prerequisite-check.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-thin-domain-routing.md
  SET ORIGINAL_INTENT = the user's triggering kit-review request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  RUN KitThinDomainClassify
  CONTINUE KitThinRouteBlocked WHEN KIT_WORK_DOMAIN == mixed OR KIT_WORK_DOMAIN == unset OR KIT_WORK_DOMAIN == manifest
  LOAD {cf-studio-path}/.core/workflows/prompting-review.md as the controlling kit prompt-review workflow WHEN KIT_WORK_DOMAIN == prompting
  CONTINUE PromptingReviewPreset WHEN KIT_WORK_DOMAIN == prompting
  LOAD {cf-studio-path}/.core/workflows/documenting-review.md as the controlling kit document-review workflow WHEN KIT_WORK_DOMAIN == documenting
  CONTINUE DocumentingReviewPreset WHEN KIT_WORK_DOMAIN == documenting
  LOAD {cf-studio-path}/.core/workflows/coding-review.md as the controlling kit code-review workflow WHEN KIT_WORK_DOMAIN == coding
  CONTINUE CodingReviewEntry WHEN KIT_WORK_DOMAIN == coding
RULES:
  - ALWAYS route semantic review to the prompt, document, or code specialist workflow that matches the kit asset type
  - ALWAYS route manifest or kit-configuration review requests to cf-kit rather than this thin prompt/doc/code review family
  - ALWAYS block mixed-domain review requests until the user scopes them or plans them
  - NEVER apply fixes from kit-review
```
