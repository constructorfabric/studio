---
cf: true
type: workflow
name: cf-docs-ci
description: "Invoke when the user explicitly asks for `docs-ci` or `cf-docs-ci` by name."
version: 0.1
purpose: Delegate document CI requests to the document-validation workflow.
---

# cf-docs-ci

This workflow is a compatibility alias. The canonical thin document CI
entrypoint is `cf-documenting-ci`.

```pdsl
UNIT DocsCiAlias
PURPOSE: Redirect legacy docs-ci invocations into the canonical thin document CI workflow.
DO:
  LOAD {cf-studio-path}/.core/workflows/documenting-ci.md as the controlling CI workflow
  CONTINUE DocumentingCiPreset
```
