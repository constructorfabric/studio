---
cf: true
type: workflow
name: cf-kit-ci
description: "Invoke when the user or another skill or workflow needs or asks to run deterministic validation for scoped kit prompt, document, or code assets."
version: 0.1
purpose: Route deterministic kit prompt, document, or code validation into the correct specialist CI workflow instead of inventing kit-local validation logic.
---

# cf-kit-ci

This workflow is the canonical thin deterministic validation entrypoint for kit
prompt, document, and code work.

```pdsl
UNIT KitCiPreset
PURPOSE: Run deterministic kit validation without semantic review or authoring.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET GATE_STATUS: pass | fail | not-run (default not-run, scope workflow_run)
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-thin-domain-routing.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  SET ORIGINAL_INTENT = the user's triggering kit-ci request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  RUN KitThinDomainClassify
  CONTINUE KitThinRouteBlocked WHEN KIT_WORK_DOMAIN == mixed OR KIT_WORK_DOMAIN == unset OR KIT_WORK_DOMAIN == manifest
  LOAD {cf-studio-path}/.core/workflows/prompting-ci.md as the controlling kit prompt CI workflow WHEN KIT_WORK_DOMAIN == prompting
  CONTINUE PromptingCiPreset WHEN KIT_WORK_DOMAIN == prompting
  LOAD {cf-studio-path}/.core/workflows/documenting-ci.md as the controlling kit document CI workflow WHEN KIT_WORK_DOMAIN == documenting
  CONTINUE DocumentingCiPreset WHEN KIT_WORK_DOMAIN == documenting
  LOAD {cf-studio-path}/.core/workflows/coding-ci.md as the controlling kit code CI workflow WHEN KIT_WORK_DOMAIN == coding
  CONTINUE CodingCiEntry WHEN KIT_WORK_DOMAIN == coding
RULES:
  ALWAYS keep this workflow deterministic-validation-only
  ALWAYS inherit the specialist CI workflow report_outputs contract after routing
  ALWAYS route manifest or kit-configuration validation requests to cf-kit rather than this thin prompt/doc/code CI family
  NEVER treat kit-ci as permission to author or semantically review kit assets
```
