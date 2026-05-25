---
description: "Invoke when routing a Constructor Studio command or user request to the matching workflow or agent."
---

# Constructor Studio Routing

```text
UNIT CfsRouting

PURPOSE:
  Map every Constructor Studio command or user request to exactly one
  workflow or agent entry point, in priority order.

RULES:
  - MUST evaluate entries top-to-bottom and stop at the first match
  - MUST prefer entry 7 (analyze) over entry 6 (generate) on compound
    find+fix intent (see UNIT CompoundFindFix below)
  - MUST surface raw-input-overflow rule when raw input exceeds 500 lines
    before continuing to generate or analyze
  - MUST_NOT collapse the three distinct thresholds (500 / 2000 / 2500)
  - MUST ask for clarification and request exactly one of
    plan | generate | analyze | workspace | migrate
    when no entry matches
```

```text
UNIT CliAliasAndInvocation

PURPOSE:
  Define CLI alias and agent-safe invocation rules for routing.

RULES:
  - MUST treat /cf-studio as identical to /cf (same skill, same behavior)
  - MUST use {cfs_cmd} --json agents --agent <name> for agent lookup
  - MUST run init, delegate, and update without --json
  - MUST obtain write confirmation before any write-capable direct CLI command
```

```text
UNIT WorkflowRoutingTable

PURPOSE:
  Ordered routing table; first matching entry wins.

DO:
  1. WHEN request matches "delegate"
       -> open and follow {cf-studio-path}/.core/skills/studio/agents/cf-ralphex.md

  2. WHEN request matches "compile phase"
       -> open and follow {cf-studio-path}/.core/skills/studio/agents/cf-phase-compiler.md

  3. WHEN request matches "execute phase"
       -> open and follow {cf-studio-path}/.core/skills/studio/agents/cf-phase-runner.md

  4. WHEN request matches any of:
       pdsl | cf-pdsl | prompt dsl | prompt contract |
       new prompt file | generate prompt instructions |
       transform prompts to dsl | convert prompt prose to dsl |
       compact prompt instructions | review prompt dsl |
       check prompt state machines | instruction dsl
       -> open and follow workflows/pdsl.md

  5. WHEN request matches "plan" | "decompose" | "break down"
       -> open and follow workflows/plan.md

  6. WHEN request matches any of:
       create | edit | fix | update | implement | refactor | setup | build
       AND CompoundFindFix does NOT apply
       -> open and follow workflows/generate.md

  7. WHEN request matches any of:
       analyze | validate | review | check | inspect | audit | compare |
       explain | walk through | teach | onboard |
       bug hunt | find bugs | prompt bugs
       OR CompoundFindFix applies
       -> open and follow workflows/analyze.md

  8. WHEN request matches any of:
       workspace | multi-repo | add source | cross-reference
       -> open and follow workflows/workspace.md

  9. WHEN request matches any of:
       map | dependency map | cfs map | visualize dependencies | render graph
       -> open and follow workflows/cf-map.md

  10. WHEN request matches any of:
        auto-config | configure project | scan brownfield | generate rules
        -> open and follow workflows/auto-config.md

  11. WHEN request matches "migrate from cypilot" | "migrate-from-cypilot"
        -> open and follow migrate-from-cypilot.md
```

```text
UNIT CompoundFindFix

PURPOSE:
  Resolve ambiguous requests that match both fix/update/refactor (entry 6)
  and find-bugs/bug-hunt/audit/review (entry 7) keywords simultaneously.

WHEN:
  request matches keywords from entry 6 (fix | update | refactor)
  AND request matches keywords from entry 7 (find bugs | bug hunt | audit | review)

DO:
  SET routing_winner = analyze
  CONTINUE WorkflowRoutingTable entry 7

NOTES:
  Routing both to generate skips the find phase entirely. The analyze run
  produces findings, then offers a Remediation Handoff that routes into
  generate if the user accepts.
```

```text
UNIT OversizedRawInputGate

PURPOSE:
  Enforce the three distinct input-size thresholds before routing continues.

STATE:
  raw_input_lines: integer
    default: 0

  workflow_context_lines: integer
    default: 0

WHEN:
  raw_input_lines > 500

DO:
  REQUIRE surface {cf-studio-path}/.core/requirements/raw-input-overflow.md
  EMIT_MENU RawInputOverflowMenu
  WAIT user.reply
  STOP_TURN

RULES:
  - MUST_NOT collapse raw-input threshold (500) with analyze gate (> 2000)
    or generate gate (> 2500)
  - MUST treat all three thresholds as independent checks

NOTES:
  The raw-input threshold (500 lines of pasted text or directly provided files)
  is a pre-routing gate. The analyze (> 2000 lines) and generate (> 2500 lines)
  thresholds are workflow-level estimated-context gates checked inside those
  workflows.
```

```text
UNIT AmbiguousRoutingFallback

PURPOSE:
  Handle requests that match no routing entry.

WHEN:
  no WorkflowRoutingTable entry matches

DO:
  EMIT "I need more context to route this request. Which best describes what you need?"
  EMIT_MENU RoutingClarificationMenu
  WAIT user.reply
  STOP_TURN

MENU RoutingClarificationMenu:
  OPTIONS:
    1 -> plan        -- CONTINUE WorkflowRoutingTable entry 5
    2 -> generate    -- CONTINUE WorkflowRoutingTable entry 6
    3 -> analyze     -- CONTINUE WorkflowRoutingTable entry 7
    4 -> workspace   -- CONTINUE WorkflowRoutingTable entry 8
    5 -> migrate     -- CONTINUE WorkflowRoutingTable entry 11
  INVALID:
    EMIT "Reply with 1, 2, 3, 4, or 5."
    WAIT user.reply
    STOP_TURN
```
