---
name: mode-resolution
description: "Invoke when loading the canonical STRICT vs RELAXED rules-mode behavior definitions for a generate workflow phase."
purpose: Canonical STRICT vs RELAXED rules-mode behavior for generate and analyze workflow phases
loaded_by: workflows/generate.md, workflows/analyze.md
version: 1.0
---

<!-- toc -->

- [Rules Mode Behavior](#rules-mode-behavior)
- [Warnings](#warnings)

<!-- /toc -->

```pdsl
UNIT ModeResolution

PURPOSE:
  Define the canonical STRICT vs RELAXED rules-mode behavior for generate
  and analyze workflow phases.

RULES:
  - MUST NOT hardcode a rules mode in plan-compiled phase files;
    mode resolution happens in the downstream generate/analyze workflow
    at phase execution time

NOTES:
  Plan workflow note: workflows/plan.md does not resolve a rules mode itself.
```

## Rules Mode Behavior

```pdsl
UNIT StrictMode

PURPOSE:
  Define required behavior when rules_mode = STRICT.

RULES:
  - MUST load required generation-phase dependencies
    (typically template + example for artifacts, design/spec context for code)
  - MUST run checklist-driven review in Phase 5
  - MUST require validation PASS before Phase 6 proceeds
```

```pdsl
UNIT RelaxedMode

PURPOSE:
  Define required behavior when rules_mode = RELAXED.

RULES:
  - MUST use user-provided or best-effort phase-appropriate dependencies
  - MUST attempt post-write validation automatically when:
      validator command is available
      AND at least one target file was written
  - MUST stop with an explicitly unvalidated result when validation cannot
    reach PASS after recovery — MUST NOT treat this as success
```

## Warnings

```pdsl
UNIT RulesUnavailableWarning

PURPOSE:
  Emit the rules-unavailable warning when no kit rules are loaded in STRICT mode.

WHEN:
  rules.md is not loaded AND rules_mode == STRICT

DO:
  EMIT "⚠️ Generated without Constructor Studio rules (reduced quality assurance)"

RULES:
  - MUST fire this warning before proceeding when condition is met
```

```pdsl
UNIT ValidationFailWarning

PURPOSE:
  Emit the validation-FAIL warning when validation reaches FAIL in STRICT mode.

WHEN:
  validation gate fails AND rules_mode == STRICT

DO:
  EMIT "⚠️ Validated — FAIL (RELAXED mode): rules applied but validation could not reach PASS"

RULES:
  - MUST fire this warning before proceeding when condition is met
```
