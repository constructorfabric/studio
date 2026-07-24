---
cf: true
type: workflow
name: cf-kit-fix
description: "Invoke when the user or another skill or workflow needs or asks to apply approved review findings or fix scoped kit prompt, document, or code issues from an existing findings report."
version: 0.1
purpose: Route approved kit prompt, document, or code fixes into the correct specialist fix workflow instead of inventing kit-local remediation logic.
---

# cf-kit-fix

This workflow is the canonical thin fix entrypoint for kit prompt, document,
and code work.

```pdsl
UNIT KitFixBootstrap
PURPOSE: Initialize thin kit fixing and route into approved-finding application through the correct specialist workflow.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default true, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/prerequisite-check.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/handoff-suggestions.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-thin-domain-routing.md
  SET ORIGINAL_INTENT = the user's triggering kit-fix request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  SET REVIEW_LOOP_REQUESTED = true WHEN REVIEW_LOOP_REQUESTED == unset
  RUN KitThinDomainClassify
  CONTINUE KitThinRouteBlocked WHEN KIT_WORK_DOMAIN == mixed OR KIT_WORK_DOMAIN == unset OR KIT_WORK_DOMAIN == manifest
  LOAD {cf-studio-path}/.core/workflows/prompting-fix.md as the controlling kit prompt-fix workflow WHEN KIT_WORK_DOMAIN == prompting
  CONTINUE PromptingFixBootstrap WHEN KIT_WORK_DOMAIN == prompting
  LOAD {cf-studio-path}/.core/workflows/documenting-fix.md as the controlling kit document-fix workflow WHEN KIT_WORK_DOMAIN == documenting
  CONTINUE DocumentingFixBootstrap WHEN KIT_WORK_DOMAIN == documenting
  LOAD {cf-studio-path}/.core/workflows/coding-fix.md as the controlling kit code-fix workflow WHEN KIT_WORK_DOMAIN == coding
  CONTINUE CodingFixBootstrap WHEN KIT_WORK_DOMAIN == coding
RULES:
  ALWAYS inherit the specialist fix workflow prerequisite and override behavior after routing
  ALWAYS route fixes to the prompt, document, or code specialist workflow that matches the kit asset type
  ALWAYS route manifest or kit-configuration fix requests to cf-kit rather than this thin prompt/doc/code fix family
  ALWAYS block mixed-domain fix requests until the user scopes them or route them through cf-kit-planning
  NEVER run semantic review from kit-fix
```
