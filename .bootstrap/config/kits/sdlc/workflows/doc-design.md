---
cf-studio: true
type: workflow
name: cf-sdlc-doc-design
description: Invoke when the user asks to author, write, revise, generate, or produce a DESIGN or system/technical design — e.g. "generate DESIGN", "design the system", "define components / interfaces / architecture / boundaries". Thin preset binding the DESIGN artifact KIND, delegating authoring and review to the core cf-write-docs engine.
version: 1.0
purpose: Thin preset that binds the DESIGN artifact KIND and its kit references, then delegates authoring and review to the core cf-write-docs workflow.
---

# cf-sdlc-doc-design — DESIGN authoring preset

This workflow is a thin preset over the core `cf-write-docs` authoring engine. It binds the DESIGN artifact KIND and its kit resources (template, rules, checklist, example), injects DESIGN-specific authoring rules, and delegates the full author -> deterministic-gate -> semantic-review loop to `cf-write-docs`. It authors no content itself.

```pdsl
UNIT DocDesignPreset
PURPOSE: Bind the DESIGN artifact KIND and its kit references, then delegate authoring and review to the core cf-write-docs workflow.
STATE:
  SET ARTIFACT_KIND: DESIGN (default DESIGN, scope workflow_run)
DO:
  SET ARTIFACT_KIND = DESIGN
  SET artifact_template = {design_template}
  SET artifact_rules = {design_rules}
  SET artifact_checklist = {design_checklist}
  SET artifact_example = {design_example}
  LOAD {cf-studio-path}/.core/workflows/write-docs.md as the controlling authoring workflow
  CONTINUE WriteDocsBootstrap
RULES:
  ALWAYS bind ARTIFACT_KIND = DESIGN and the four DESIGN references (template, rules, checklist, example) before delegating to cf-write-docs
  ALWAYS inject {design_rules} as additional DESIGN-specific authoring rules into every author dispatch
  ALWAYS set the deterministic gate target to `cfs validate --artifact <path>` for the DESIGN file
  ALWAYS pass {design_checklist} as the artifact checklist to cf-semantic-reviewer-artifact and {design_example} as the content-depth reference
  ALWAYS carry ARTIFACT_KIND and the bound references as read-only preset data, never overriding cf-write-docs gates or verdicts
  NEVER author DESIGN content in this preset; delegate all authoring and review to cf-write-docs
NOTES:
  cf-write-docs already drives the author -> deterministic gate (cfs validate --artifact) -> semantic review (cf-semantic-reviewer-artifact) loop; this preset only supplies the DESIGN KIND binding and DESIGN-specific rules.
```
