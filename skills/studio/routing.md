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
  - MUST prefer entry 9 (analyze) over entry 8 (generate) on compound
    find+fix intent (see UNIT CompoundFindFix below)
  - MUST surface raw-input-overflow rule when raw input exceeds 500 lines
    before continuing to generate or analyze
  - MUST_NOT collapse the three distinct thresholds (500 / 2000 / 2500)
  - MUST ask for clarification and request exactly one
    RoutingClarificationMenu option, ordered by user-facing likelihood rather
    than WorkflowRoutingTable entry number, when no entry matches
  - MUST surface installed-kit shortcut examples when ProtocolGuard loaded
    kit skill instructions, without collapsing them into the core routing table
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
UNIT RoutingSharedContextPack

PURPOSE:
  Keep workflow routing controller-owned and aligned with shared-context-pack
  loading boundaries.

RULES:
  - Routed workflow and agent prompt assets are controller-owned runtime loads
    and MUST use {cf-studio-path}-prefixed runtime paths when mirrors exist
  - Routing MUST reuse or extend SHARED_CONTEXT_PACK before any downstream
    dispatch that depends on prompt assets
  - Routing MUST NOT instruct prompt-consuming sub-agents to open workflow,
    AGENTS, SKILL, requirement, or spec prompt files directly
```

```text
UNIT WorkflowRoutingTable

PURPOSE:
  Ordered routing table; first matching entry wins.

DO:
  0. WHEN request matches any of:
       cf help | /cf help | cf-studio help | /cf-studio help | cfs help
       -> open and follow {cf-studio-path}/.core/workflows/help.md

  1. WHEN request matches "delegate"
       -> open and follow {cf-studio-path}/.core/skills/studio/agents/cf-ralphex.md

  2. WHEN request matches "compile phase"
       -> open and follow {cf-studio-path}/.core/skills/studio/agents/cf-phase-compiler.md

  3. WHEN request matches "execute phase"
       -> open and follow {cf-studio-path}/.core/skills/studio/agents/cf-phase-runner.md

  4. WHEN request matches any of:
       brainstorm | cf-brainstorm | ideate | explore options |
       design exploration | requirements discovery | option mapping
       -> open and follow {cf-studio-path}/.core/workflows/brainstorm.md

  5. WHEN request matches any of:
       pdsl | cf-pdsl | prompt dsl | prompt contract |
       new prompt file | generate prompt instructions |
       transform prompts to dsl | convert prompt prose to dsl |
       compact prompt instructions | review prompt dsl |
       check prompt state machines | instruction dsl
       -> open and follow {cf-studio-path}/.core/workflows/pdsl.md

  6. WHEN request matches "plan" | "decompose" | "break down"
       -> open and follow {cf-studio-path}/.core/workflows/plan.md

  7. WHEN request matches any of:
       explore | discover context | find relevant context |
       find project context | locate architecture | locate resources |
       context search | resource search
       -> open and follow {cf-studio-path}/.core/workflows/explore.md

  8. WHEN request matches any of:
       create | edit | fix | update | implement | refactor | setup | build
       AND CompoundFindFix does NOT apply
       -> open and follow {cf-studio-path}/.core/workflows/generate.md

  9. WHEN request matches any of:
       analyze | validate | review | check | inspect | audit | compare |
       explain | walk through | teach | onboard |
       bug hunt | find bugs | prompt bugs
       OR CompoundFindFix applies
       -> open and follow {cf-studio-path}/.core/workflows/analyze.md

  10. WHEN request matches any of:
       workspace | multi-repo | add source | cross-reference
       -> open and follow {cf-studio-path}/.core/workflows/workspace.md

  11. WHEN request matches any of:
       map | dependency map | cfs map | visualize dependencies | render graph
       -> open and follow {cf-studio-path}/.core/workflows/map.md

  12. WHEN request matches any of:
        auto-config | configure project | scan brownfield | generate rules
        -> open and follow {cf-studio-path}/.core/workflows/auto-config.md

  13. WHEN request matches "migrate from cypilot" | "migrate-from-cypilot"
        -> open and follow {cf-studio-path}/.core/skills/studio/migrate-from-cypilot.md
```

```text
UNIT CompoundFindFix

PURPOSE:
  Resolve ambiguous requests that match both fix/update/refactor (entry 8)
  and find-bugs/bug-hunt/audit/review (entry 9) keywords simultaneously.

WHEN:
  request matches keywords from entry 8 (fix | update | refactor)
  AND request matches keywords from entry 9 (find bugs | bug hunt | audit | review)

DO:
  SET routing_winner = analyze
  CONTINUE WorkflowRoutingTable entry 9

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
  OR request is activation-only / no-task intent:
     cf | /cf | cf on | /cf on | cfs on | cf-studio | cf-studio on

DO:
  EMIT "I need one routing choice. Pick what you want to do next, or reply with a direct installed-kit shortcut such as `list PRs`, `review PR 123`, `PR status 123`, or `migrate-openspec` when those kit instructions are loaded."
  EMIT_MENU RoutingClarificationMenu
  WAIT user.reply
  STOP_TURN

MENU RoutingClarificationMenu:
  OPTIONS:
    1 -> help -- Show a polished beginner-friendly cf overview without asking setup questions. CONTINUE WorkflowRoutingTable entry 0
    2 -> brainstorm -- Explore options, decisions, requirements, or tradeoffs with an expert panel. CONTINUE WorkflowRoutingTable entry 4
    3 -> explain -- Get a source-grounded walkthrough of code, artifacts, architecture, or decisions. CONTINUE WorkflowRoutingTable entry 9
    4 -> explore -- Find relevant project context, files, resources, and prior decisions before acting. CONTINUE WorkflowRoutingTable entry 7
    5 -> generate -- Create, edit, implement, refactor, fix, or update files/artifacts. CONTINUE WorkflowRoutingTable entry 8
    6 -> analyze -- Review, audit, validate, compare, inspect, or find bugs. CONTINUE WorkflowRoutingTable entry 9
    7 -> plan -- Break a large task into executable phases with briefs. CONTINUE WorkflowRoutingTable entry 6
    8 -> pdsl -- Author, compact, transform, or review prompt/workflow/agent instruction contracts. CONTINUE WorkflowRoutingTable entry 5
    9 -> map -- Build dependency, traceability, or cross-reference maps. CONTINUE WorkflowRoutingTable entry 11
    10 -> workspace -- Configure or inspect multi-repo workspace sources and references. CONTINUE WorkflowRoutingTable entry 10
    11 -> auto-config -- Discover project setup and Constructor Studio/kit configuration. CONTINUE WorkflowRoutingTable entry 12
    12 -> delegate -- Delegate an approved generated plan to the runtime executor. CONTINUE WorkflowRoutingTable entry 1
    13 -> compile phase -- Compile a plan phase brief into an executable phase. CONTINUE WorkflowRoutingTable entry 2
    14 -> execute phase -- Execute the next or specified generated plan phase. CONTINUE WorkflowRoutingTable entry 3
    15 -> migrate-from-cypilot -- Migrate legacy Cypilot setup into Constructor Studio conventions. CONTINUE WorkflowRoutingTable entry 13
  INVALID:
    EMIT "Reply with 1-15, or reply with a concrete direct request such as `review PR 123`."
    WAIT user.reply
    STOP_TURN
```
