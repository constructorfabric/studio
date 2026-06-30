---
cf: true
type: workflow
name: cf-coding-tests
description: "Invoke when the user or another skill or workflow needs or asks to write tests first, add unit tests, add e2e coverage, codify acceptance criteria as tests, update failing tests for a planned change, or produce a test spec for implementation."
version: 0.1
purpose: Bind test-authoring scope and delegate bounded test implementation to the code-generation workflow.
---

# cf-coding-tests

This workflow is the canonical thin test-authoring skill. It writes or updates
`unit-tests`, `e2e-tests`, or `test-spec` only.

```pdsl
UNIT CodingTestsPreset
PURPOSE: Bind test-authoring scope and delegate to the canonical code-generation workflow.
STATE:
  SET ORIGINAL_INTENT: string | unset (default unset, scope workflow_run)
  SET REVIEW_LOOP_REQUESTED: true | false | unset (default false, scope workflow_run)
  SET TESTS_SCOPE: string | unset (default unset, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's verbatim coding-tests request WHEN ORIGINAL_INTENT == unset
  SET TESTS_SCOPE = "author or update unit-tests, e2e-tests, or test-spec only for the approved phase contract"
  SET REVIEW_LOOP_REQUESTED = false WHEN REVIEW_LOOP_REQUESTED == unset
  LOAD {cf-studio-path}/.core/workflows/coding-gen.md as the controlling test-authoring engine
  CONTINUE CodingGenBootstrap
RULES:
  - ALWAYS treat this workflow as test-authoring only
  - NEVER use this workflow to implement production behavior outside test scaffolding and test expectations
  - ALWAYS use TESTS_SCOPE to constrain the authoring scope in downstream logic; NEVER overwrite ORIGINAL_INTENT with the normalised scope string
```
