---
cf-studio: true
type: workflow
name: cf-sdlc-doc-feature
description: Invoke when the user asks to author, write, revise, generate, or spec a FEATURE — e.g. "generate FEATURE", "spec the feature", "define flows / algorithms / states / definition of done (CDSL)", "write test scenarios for a feature". Thin preset binding the FEATURE artifact KIND, delegating authoring and review to the core cf-write-docs engine.
version: 1.0
purpose: Thin preset that binds the FEATURE artifact KIND and its kit references, then delegates authoring and review to the core cf-write-docs workflow.
---

# cf-sdlc-doc-feature — FEATURE authoring preset

This workflow is a thin preset over the core `cf-write-docs` authoring engine. It binds the FEATURE artifact KIND and its kit resources (template, rules, checklist, example), injects FEATURE-specific authoring rules, and delegates the full author -> deterministic-gate -> semantic-review loop to `cf-write-docs`. It authors no content itself.

```pdsl
UNIT DocFeaturePreset
PURPOSE: Bind the FEATURE artifact KIND and its kit references, then delegate authoring and review to the core cf-write-docs workflow.
STATE:
  SET ARTIFACT_KIND: FEATURE (default FEATURE, scope workflow_run)
DO:
  SET ARTIFACT_KIND = FEATURE
  SET artifact_template = {feature_template}
  SET artifact_rules = {feature_rules}
  SET artifact_checklist = {feature_checklist}
  SET artifact_example = {feature_example}
  LOAD {cf-studio-path}/.core/workflows/write-docs.md as the controlling authoring workflow
  CONTINUE WriteDocsBootstrap
RULES:
  ALWAYS bind ARTIFACT_KIND = FEATURE and the four FEATURE references (template, rules, checklist, example) before delegating to cf-write-docs
  ALWAYS inject {feature_rules} as additional FEATURE-specific authoring rules into every author dispatch
  ALWAYS set the deterministic gate target to `cfs validate --artifact <path>` for the FEATURE file
  ALWAYS pass {feature_checklist} as the artifact checklist to cf-semantic-reviewer-artifact and {feature_example} as the content-depth reference
  ALWAYS carry ARTIFACT_KIND and the bound references as read-only preset data, never overriding cf-write-docs gates or verdicts
  NEVER author FEATURE content in this preset; delegate all authoring and review to cf-write-docs
NOTES:
  cf-write-docs already drives the author -> deterministic gate (cfs validate --artifact) -> semantic review (cf-semantic-reviewer-artifact) loop; this preset only supplies the FEATURE KIND binding and FEATURE-specific rules.
```
