# Brave New World Fallback

```pdsl
UNIT BraveNewWorldFallback
PURPOSE: Preserve the original workflow behavior when autonomous selection is not allowed.
WHEN:
  - REQUIRE BRAVE_NEW_WORLD_ENABLED == true
  - REQUIRE classification_status != eligible OR every available option is blocked, destructive, irreversible, external, permission-escalating, secret-bearing, financial, git-mutating, unknown-blast-radius, not derivable from visible context, or otherwise fails BraveNewWorldEligibilityChecklist
DO:
  - SET BRAVE_NEW_WORLD_LAST_STATUS = fallback
  - EMIT "Brave New World needs your choice here because <blocked_or_ambiguous_reason>."
  - EMIT the original menu or question unchanged
  - WAIT user.reply when the underlying workflow requires WAIT
  - STOP_TURN when the underlying workflow requires STOP_TURN
RULES:
  - ALWAYS emit the original menu or question unchanged on fallback
  - ALWAYS preserve all underlying workflow handoff, logging, WAIT, STOP_TURN, terminal-shape, and output-contract behavior
  - NEVER continue past the original hard stop without user input
```

```pdsl
UNIT BraveNewWorldVerificationCases
PURPOSE: Define regression cases for reviewing this overlay.
RULES:
  - ALWAYS verify destructive, irreversible, external-service, permission-escalation, secret, payment, deployment, publication, install/update, and git-mutating prompts emit BraveNewWorldFallback, preserve the original menu, and preserve required WAIT and STOP_TURN behavior
  - ALWAYS verify planning, routing, synthesized next-action, brainstorm-start, skill-loading, review-scope, and validation-retry menus can be auto-selected for non-destructive and reversible visible action paths
  - ALWAYS verify brainstorm steering questions can be answered from visible current workflow state without confidential, legal, financial, personal, or irreversible human judgment
  - ALWAYS verify an ambiguous menu with multiple safe progress options selects the least project-damaging option that best advances the user's current request and records the tie-break reason
  - ALWAYS verify one blocked case and one positive progress case both record all decision-log fields and announce the choice before continuation or fallback
```
