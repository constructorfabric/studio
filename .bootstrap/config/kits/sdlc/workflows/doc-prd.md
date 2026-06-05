---
cf-studio: true
type: workflow
name: cf-sdlc-doc-prd
description: Invoke when the user asks to author, write, revise, or generate a PRD — e.g. "generate PRD", "write the PRD", "create product requirements", "capture actors, FR/NFR, use cases, or success criteria". Thin preset binding the PRD artifact KIND, delegating authoring and review to the core cf-write-docs engine.
version: 1.0
purpose: Thin preset that binds the PRD artifact KIND and its kit references, then delegates authoring and review to the core cf-write-docs workflow.
---

# cf-sdlc-doc-prd — PRD authoring preset

This workflow is a thin preset over the core `cf-write-docs` authoring engine. It binds the PRD artifact KIND and its kit resources (template, rules, checklist, example), injects PRD-specific authoring rules, and delegates the full author -> deterministic-gate -> semantic-review loop to `cf-write-docs`. It authors no content itself.

```pdsl
UNIT DocPrdPreset
PURPOSE: Bind the PRD artifact KIND and its kit references, then delegate authoring and review to the core cf-write-docs workflow.
STATE:
  SET ARTIFACT_KIND: PRD (default PRD, scope workflow_run)
DO:
  SET ARTIFACT_KIND = PRD
  SET artifact_template = {prd_template}
  SET artifact_rules = {prd_rules}
  SET artifact_checklist = {prd_checklist}
  SET artifact_example = {prd_example}
  LOAD {cf-studio-path}/.core/workflows/write-docs.md as the controlling authoring workflow
  CONTINUE WriteDocsBootstrap
RULES:
  ALWAYS bind ARTIFACT_KIND = PRD and the four PRD references (template, rules, checklist, example) before delegating to cf-write-docs
  ALWAYS inject {prd_rules} as additional PRD-specific authoring rules into every author dispatch
  ALWAYS set the deterministic gate target to `cfs validate --artifact <path>` for the PRD file
  ALWAYS pass {prd_checklist} as the artifact checklist to cf-semantic-reviewer-artifact and {prd_example} as the content-depth reference
  ALWAYS carry ARTIFACT_KIND and the bound references as read-only preset data, never overriding cf-write-docs gates or verdicts
  NEVER author PRD content in this preset; delegate all authoring and review to cf-write-docs
NOTES:
  cf-write-docs already drives the author -> deterministic gate (cfs validate --artifact) -> semantic review (cf-semantic-reviewer-artifact) loop; this preset only supplies the PRD KIND binding and PRD-specific rules.
```
