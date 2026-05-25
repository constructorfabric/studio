
<!-- toc -->

- [Rules Mode Behavior](#rules-mode-behavior)
- [Warnings](#warnings)

<!-- /toc -->

---
name: mode-resolution
description: "Invoke when loading the canonical STRICT vs RELAXED rules-mode behavior definitions for a generate workflow phase."
purpose: Canonical STRICT vs RELAXED rules-mode behavior for generate and analyze workflow phases
loaded_by: workflows/generate.md, workflows/analyze.md
version: 1.0
---

Plan workflow note: `workflows/plan.md` does not resolve a rules mode itself; mode resolution happens in the downstream `generate`/`analyze` workflow at phase execution time. Plan-compiled phase files MUST NOT hardcode a rules mode.

## Rules Mode Behavior

STRICT: generation must load the required generation-phase dependencies (typically template + example for artifacts, design/spec context for code), checklist-driven review must run in Phase 5, and Phase 6 requires validation `PASS`. RELAXED: use user-provided or best-effort phase-appropriate dependencies, still attempt post-write validation automatically when the validator command is available and at least one target file was written, and if validation cannot reach `PASS` after recovery, stop with an explicitly unvalidated result instead of treating it as success.

## Warnings

Rules-unavailable case (no template/example/kit loaded):
```text
⚠️ Generated without Constructor Studio rules (reduced quality assurance)
```

Validation FAIL despite rules applied:
```text
⚠️ Validated — FAIL (RELAXED mode): rules applied but validation could not reach PASS
```

Fire rules-unavailable warning when no checklist, template, or kit rules are available for the target. Fire validation-FAIL warning when rules were loaded and validation ran but reached FAIL status in RELAXED mode.
