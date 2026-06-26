---
cf: true
type: workflow
name: cf-testing
description: "Invoke when the user explicitly asks for `testing` or `cf-testing` by name."
version: 0.1
purpose: Delegate test-authoring requests to the code-test workflow.
---

# cf-testing

This workflow is a compatibility alias. The canonical thin test-authoring
entrypoint is `cf-coding-tests`.

```pdsl
UNIT TestingAlias
PURPOSE: Redirect legacy cf-testing invocations into the canonical thin test-authoring workflow.
DO:
  EMIT "Note: testing is now an alias for coding-tests. Continuing with the canonical workflow."
  LOAD {cf-studio-path}/.core/workflows/coding-tests.md as the controlling test-authoring workflow
  CONTINUE CodingTestsPreset
RULES:
  - ALWAYS preserve caller intent and compatibility expectations
```
