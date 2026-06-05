---
cf-studio: true
type: workflow
name: cf-sdlc-doc-adr
description: Invoke when the user asks to author, write, revise, generate, or record an ADR or architecture decision — e.g. "generate ADR", "record a decision", "document why we chose X", "capture context / options / decision / consequences". Thin preset binding the ADR artifact KIND, delegating authoring and review to the core cf-write-docs engine.
version: 1.0
purpose: Thin preset that binds the ADR artifact KIND and its kit references, then delegates authoring and review to the core cf-write-docs workflow.
---

# cf-sdlc-doc-adr — ADR authoring preset

This workflow is a thin preset over the core `cf-write-docs` authoring engine. It binds the ADR artifact KIND and its kit resources (template, rules, checklist, example), injects ADR-specific authoring rules, and delegates the full author -> deterministic-gate -> semantic-review loop to `cf-write-docs`. It authors no content itself.

```pdsl
UNIT DocAdrPreset
PURPOSE: Bind the ADR artifact KIND and its kit references, then delegate authoring and review to the core cf-write-docs workflow.
STATE:
  SET ARTIFACT_KIND: ADR (default ADR, scope workflow_run)
DO:
  SET ARTIFACT_KIND = ADR
  SET artifact_template = {adr_template}
  SET artifact_rules = {adr_rules}
  SET artifact_checklist = {adr_checklist}
  SET artifact_example = {adr_example}
  LOAD {cf-studio-path}/.core/workflows/write-docs.md as the controlling authoring workflow
  CONTINUE WriteDocsBootstrap
RULES:
  ALWAYS bind ARTIFACT_KIND = ADR and the four ADR references (template, rules, checklist, example) before delegating to cf-write-docs
  ALWAYS inject {adr_rules} as additional ADR-specific authoring rules into every author dispatch
  ALWAYS set the deterministic gate target to `cfs validate --artifact <path>` for the ADR file
  ALWAYS pass {adr_checklist} as the artifact checklist to cf-semantic-reviewer-artifact and {adr_example} as the content-depth reference
  ALWAYS carry ARTIFACT_KIND and the bound references as read-only preset data, never overriding cf-write-docs gates or verdicts
  NEVER author ADR content in this preset; delegate all authoring and review to cf-write-docs
NOTES:
  cf-write-docs already drives the author -> deterministic gate (cfs validate --artifact) -> semantic review (cf-semantic-reviewer-artifact) loop; this preset only supplies the ADR KIND binding and ADR-specific rules.
```
