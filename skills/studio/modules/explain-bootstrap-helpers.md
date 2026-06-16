# Explain Bootstrap Helpers

```pdsl
UNIT ExplainBootstrapIntentRuntime
PURPOSE: Resolve the initial explain intent and runtime helpers before storytelling state is set.
DO:
  SET ORIGINAL_INTENT = the user's triggering explain request (verbatim or shortest faithful summary), or unset when activation-only, WHEN ORIGINAL_INTENT == unset
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md WHEN EXPLAIN_EXPORT == true
```

```pdsl
UNIT ExplainBootstrapModeState
PURPOSE: Set the explain-mode state that reuses the storytelling output contract.
DO:
  SET EXPLAIN_MODE = true
  SET analyze_phase_2_deterministic_gate = SKIPPED
  SET analyze_phase_3_standard_checklist = SKIPPED
  SET analyze_phase_5_next_steps = SKIPPED
  SET analyze_phase_4_output_schema = storytelling_output_schema
  SET enforceRemediationPrompts = false
```

```pdsl
UNIT ExplainBootstrapStorytelling
PURPOSE: Load the storytelling requirements used by cf-explain.
DO:
  RUN ExplainStorytellingReferenceLoad
```
