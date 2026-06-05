---
cf-studio: true
type: workflow
name: cf-sdlc-implement
description: Invoke when the user asks to implement, build, or write the code for a FEATURE — e.g. "implement", "write the code", "build this feature", "implement FEATURE with @cpt-* traceability". Thin preset binding the CODE artifact KIND, delegating implementation and review to the core cf-coding engine.
version: 1.0
purpose: Thin preset that binds the CODE artifact KIND and its kit references, then delegates implementation and review to the core cf-coding workflow.
---

# cf-sdlc-implement — CODE implementation preset

This workflow is a thin preset over the core `cf-coding` authoring engine. It binds the CODE artifact KIND and its kit resources (codebase rules and checklist), points the implementation at a source FEATURE with `@cpt-*` traceability markers, and delegates the full coder -> deterministic-gate -> semantic-review loop to `cf-coding`. It authors no code itself.

```pdsl
UNIT ImplementPreset
PURPOSE: Bind the CODE artifact KIND and its kit references, then delegate implementation and review to the core cf-coding workflow.
STATE:
  SET ARTIFACT_KIND: CODE (default CODE, scope workflow_run)
DO:
  SET ARTIFACT_KIND = CODE
  SET codebase_rules_ref = {codebase_rules}
  SET codebase_checklist_ref = {codebase_checklist}
  SET source_feature = the FEATURE artifact the implementation realizes
  LOAD {cf-studio-path}/.core/workflows/coding.md as the controlling implementation workflow
  CONTINUE CodingBootstrap
RULES:
  ALWAYS bind ARTIFACT_KIND = CODE and the {codebase_rules} and {codebase_checklist} references before delegating to cf-coding
  ALWAYS inject {codebase_rules} as additional CODE traceability and implementation rules into every coder dispatch
  ALWAYS set the deterministic gate target to `cfs validate --artifact <code-path>` for code traceability in addition to the project's test, lint, typecheck, and build commands
  ALWAYS pass {codebase_checklist} as the artifact checklist to the cf-coding review loop and the resolved source FEATURE as the implementation contract
  ALWAYS require `@cpt-*` markers that trace implemented code back to the source FEATURE IDs, per {codebase_rules}
  ALWAYS carry ARTIFACT_KIND and the bound references as read-only preset data, never overriding cf-coding gates or verdicts
  NEVER author code in this preset; delegate all implementation and review to cf-coding
NOTES:
  cf-coding already drives the coder -> deterministic gate (tests/lint/typecheck/build plus cfs validate) -> semantic review loop; this preset only supplies the CODE KIND binding, the codebase traceability rules, and the source FEATURE contract.
```
