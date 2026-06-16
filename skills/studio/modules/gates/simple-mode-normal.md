# Normal Mode Branch

```pdsl
UNIT SimpleModeNormal
PURPOSE: Preserve existing workflow behavior after the user declines simple mode.
WHEN:
  - REQUIRE SIMPLE_MODE == normal
DO:
  - REQUIRE SIMPLE_MODE == normal
RULES:
  - ALWAYS continue with the workflow's existing menus, gates, stops, and output contracts
  - NEVER add simple-mode explanations or automatic selections while SIMPLE_MODE == normal
```
