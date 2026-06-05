---
cf-studio: true
type: workflow
name: cf-sdlc-decompose
description: Invoke when the user asks to decompose, break down, or author/revise a DECOMPOSITION — e.g. "decompose", "break into features", "create the feature list / plan", "order features and dependencies with coverage back to PRD/DESIGN". Thin preset binding the DECOMPOSITION artifact KIND, delegating authoring and review to the core cf-write-docs engine.
version: 1.0
purpose: Thin preset that binds the DECOMPOSITION artifact KIND and its kit references, then delegates authoring and review to the core cf-write-docs workflow.
---

# cf-sdlc-decompose — DECOMPOSITION authoring preset

This workflow is a thin preset over the core `cf-write-docs` authoring engine. It binds the DECOMPOSITION artifact KIND and its kit resources (template, rules, checklist, example), injects DECOMPOSITION-specific authoring rules, and delegates the full author -> deterministic-gate -> semantic-review loop to `cf-write-docs`. It authors no content itself.

```pdsl
UNIT DecomposePreset
PURPOSE: Bind the DECOMPOSITION artifact KIND and its kit references, then delegate authoring and review to the core cf-write-docs workflow.
STATE:
  SET ARTIFACT_KIND: DECOMPOSITION (default DECOMPOSITION, scope workflow_run)
DO:
  SET ARTIFACT_KIND = DECOMPOSITION
  SET artifact_template = {decomposition_template}
  SET artifact_rules = {decomposition_rules}
  SET artifact_checklist = {decomposition_checklist}
  SET artifact_example = {decomposition_example}
  LOAD {cf-studio-path}/.core/workflows/write-docs.md as the controlling authoring workflow
  CONTINUE WriteDocsBootstrap
RULES:
  ALWAYS bind ARTIFACT_KIND = DECOMPOSITION and the four DECOMPOSITION references (template, rules, checklist, example) before delegating to cf-write-docs
  ALWAYS inject {decomposition_rules} as additional DECOMPOSITION-specific authoring rules into every author dispatch
  ALWAYS set the deterministic gate target to `cfs validate --artifact <path>` for the DECOMPOSITION file
  ALWAYS pass {decomposition_checklist} as the artifact checklist to cf-semantic-reviewer-artifact and {decomposition_example} as the content-depth reference
  ALWAYS carry ARTIFACT_KIND and the bound references as read-only preset data, never overriding cf-write-docs gates or verdicts
  NEVER author DECOMPOSITION content in this preset; delegate all authoring and review to cf-write-docs
NOTES:
  cf-write-docs already drives the author -> deterministic gate (cfs validate --artifact) -> semantic review (cf-semantic-reviewer-artifact) loop; this preset only supplies the DECOMPOSITION KIND binding and DECOMPOSITION-specific rules.
```
