---
cf: true
type: requirement
name: Agent Compliance Protocol
version: 1.0
purpose: Enforcement protocol for AI agents executing Studio workflows (STRICT mode only)
---

# Agent Compliance Protocol

<!-- toc -->

- [Overview](#overview)
- [Agent Anti-Patterns](#agent-anti-patterns)
- [Mandatory Behaviors (STRICT mode)](#mandatory-behaviors-strict-mode)
- [Validation Output Schema (STRICT mode)](#validation-output-schema-strict-mode)
- [Error Handling](#error-handling)
- [Checkpoint Guidance](#checkpoint-guidance)
- [Recovery from Anti-Pattern Detection](#recovery-from-anti-pattern-detection)
- [Relaxed Mode Behavior](#relaxed-mode-behavior)
- [Consolidated Validation Checklist](#consolidated-validation-checklist)

<!-- /toc -->

**Type**: Requirement
**Applies**: Only when Rules Mode = STRICT (see `{cf-studio-path}/.core/skills/studio/protocol.md` § `ProtocolGuard`)

## Overview
This protocol defines mandatory behaviors for AI agents executing Studio workflows when Studio rules are enabled. It prevents common agent failure modes through structural enforcement.

**Key principle**: Trust but verify — agents must provide observable evidence (quotes, line numbers, tool call confirmations) for every claim. "I checked it" without evidence = violation.

## Agent Anti-Patterns
Known failure modes to actively avoid:

| ID | Anti-pattern | Description | Detection signal |
|---|---|---|---|
| AP-001 | SKIP_SEMANTIC | Pass deterministic gate → skip semantic validation | No checklist items in output |
| AP-002 | MEMORY_VALIDATION | Validate from context/summary, not fresh file read | No Read tool call for target artifact |
| AP-003 | ASSUMED_NA | Mark checklist categories `N/A` without checking document | No quotes proving explicit N/A statements exist |
| AP-004 | BULK_PASS | Claim "all checks pass" without per-item verification | No individual evidence per checklist item |
| AP-005 | SELF_TEST_LIE | Answer self-test YES without actually completing work | Self-test output before actual validation work |
| AP-006 | SHORTCUT_OUTPUT | Report PASS immediately after deterministic gate | No semantic review section in output |
| AP-007 | TEDIUM_AVOIDANCE | Skip thorough checklist review because it's "tedious" | Missing categories in validation output |
| AP-008 | CONTEXT_ASSUMPTION | Assume file contents from previous context | System message says "file truncated" or "content summarized" + no fresh Read tool call in current turn |

```pdsl
UNIT AntiPatternEnforcement

PURPOSE:
  Invalidate workflow output whenever any known anti-pattern is exhibited.

RULES:
  - ALWAYS invalidate workflow output when any AP-001 through AP-008 anti-pattern is detected
```

## Mandatory Behaviors (STRICT mode)

Evidence examples:

```text
Read architecture/DESIGN.md: 742 lines
Read kits/sdlc/artifacts/DESIGN/checklist.md: 839 lines
```

Checklist progress evidence format:

| Category | Status | Evidence |
|---|---|---|
| ARCH-DESIGN-001 | PASS | Lines 45-67: "System purpose is to provide..." |
| ARCH-DESIGN-002 | PASS | Lines 102-145: Principles section with 9 principles |
| PERF-DESIGN-001 | N/A | Line 698: "Performance architecture not applicable — local CLI tool" |
| SEC-DESIGN-001 | N/A | No explicit N/A statement found → VIOLATION |

Agent self-test questions:

1. Did I load and follow `agent-compliance.md` (this protocol)?
2. Did I read the ENTIRE artifact via Read tool THIS turn?
3. Did I check EVERY checklist category?
4. Did I provide evidence for each PASS/FAIL/N/A?
5. Did I verify N/A claims have explicit document statements?
6. Am I reporting based on actual file content, not memory/summary?

```pdsl
UNIT StrictModeCompliance

PURPOSE:
  Enforce mandatory reading, tracking, evidence, and self-test behaviors when Rules Mode is STRICT.

WHEN:
  - REQUIRE Rules Mode == STRICT

DO:
  - LOAD artifact under validation via Read tool
  - EMIT "Read {path}: {line_count} lines"
  - LOAD checklist for the artifact type via Read tool
  - EMIT "Read {path}: {line_count} lines"
  - RUN ChecklistExecution
    NOTES: Use todo tracking tool; process each category individually; output PASS/FAIL/N/A per category with evidence.
  - RUN ValidationOutput
  - RUN SelfTest
    NOTES: Self-test questions MUST be answered AFTER validation work is complete, not before.

RULES:
  - ALWAYS use the Read tool for every artifact being validated or referenced
  - ALWAYS re-read files if context was compacted (check for "too large to include" or "content summarized" warnings)
  - ALWAYS track checklist progress category by category using a todo tracking tool
  - ALWAYS output PASS, FAIL, or N/A for each checklist category with evidence
  - ALWAYS answer self-test questions after validation work is complete
  - NEVER rely on context summaries for validation decisions
  - NEVER assume file contents from previous turns
  - NEVER skip a checklist category without an explicit N/A justification
  - NEVER batch all checklist categories into a single PASS claim
  - NEVER mark a category N/A unless the document contains an explicit statement confirming it
  - NEVER report completion without a per-category breakdown

NOTES:
  Evidence standards:
  - PASS: quote specific text (2-5 sentences) and include line numbers or section headers
  - N/A: quote explicit "Not applicable because..." statement from the document; agent CANNOT decide N/A on behalf of document author — if no explicit statement exists, report VIOLATION
  - FAIL: state what is missing/incorrect and where it should be
```

## Validation Output Schema (STRICT mode)

```pdsl
UNIT ValidationOutputSchema

PURPOSE:
  Require the six-section structured output format for all STRICT mode validation reports.

WHEN:
  - REQUIRE Rules Mode == STRICT

RULES:
  - ALWAYS structure validation output with all six sections in order:
      1. Protocol Compliance — Rules Mode: STRICT; Artifact Read: {path} ({N} lines); Checklist Loaded: {path} ({N} lines)
      2. Deterministic Gate — Status: PASS/FAIL; Errors: {list if any}
      3. Semantic Review (MANDATORY) — Checklist Progress table with {ID} | PASS/FAIL/N/A | {quote or violation description} per category; Categories Summary with Total, PASS, FAIL, N/A (explicit), N/A (missing statement) → VIOLATIONS
      4. Agent Self-Test — answers to all 6 self-test questions with evidence
      5. Final Status — Deterministic: PASS/FAIL; Semantic: PASS/FAIL ({N} issues); Overall: PASS/FAIL
      6. Issues (if any) — detailed issue descriptions
  - NEVER accept free-form "PASS" or "looks good" as valid output in STRICT mode
  - NEVER omit the Semantic Review section when Deterministic Gate passes
```

## Error Handling

```pdsl
UNIT ErrorHandling

PURPOSE:
  Define required responses and recovery actions for validation errors.

WHEN:
  - REQUIRE Rules Mode == STRICT

ON_ERROR:
  read_tool_fails ->
    EMIT "⚠️ Cannot read artifact: {error}"
    STOP_TURN
    NOTES: Validation cannot proceed without artifact content; fix path/file and retry.

  context_compacted_during_validation ->
    EMIT "⚠️ Context compacted during validation"
    NOTES: Previous Read outputs may be summarized or truncated.
    RUN re-read all artifacts via Read tool
    CONTINUE from current checkpoint

  checklist_not_found ->
    EMIT "⚠️ Checklist not found: {path}"
    STOP_TURN
    NOTES: Semantic validation requires checklist; fix rules path or artifacts.toml configuration.
```

## Checkpoint Guidance

When validating artifacts `>500` lines OR checklist has `>15` categories:

```pdsl
UNIT CheckpointGuidance

PURPOSE:
  Persist durable progress checkpoints during large artifact or long checklist validation.

WHEN:
  - REQUIRE artifact line count > 500
  - OR checklist category count > 15

DO:
  - REQUIRE checkpoint is persisted after each group of 3-5 categories
    NOTES: Checkpoint fields: completedCategoryIDs, statuses, remainingCategoryIDs, artifactPath, artifactLineCount, timestamp.
           Target: todo tracking tool or JSON file/DB — not solely conversation output.
  - REQUIRE checkpoint is written to durable storage before any context compaction
    NOTES: Pre-compaction checkpoint adds: resume instructions, retry/backoff options, manual-override flag.

ON_ERROR:
  resume_after_compaction ->
    LOAD artifact via Read tool
    REQUIRE current line count == saved artifactLineCount
    NOTES: On mismatch: EMIT discrepancy details (saved vs current line count, artifact path,
           timestamps); SET checkpoint status = inconsistent; STOP_TURN.
           Surface investigation/retry instruction to user; do not auto-resume on divergence.
           Checkpoint metadata MUST include retry/backoff options and a manual-override flag.
    CONTINUE from recorded checkpoint position
```

## Recovery from Anti-Pattern Detection

```pdsl
UNIT AntiPatternRecovery

PURPOSE:
  Execute the five-step recovery sequence whenever an anti-pattern violation is detected.

WHEN:
  - REQUIRE anti-pattern violation is detected by agent or user

DO:
  - EMIT "I exhibited anti-pattern {ID}: {description}"
  - EMIT "This happened because {honest reason}"
  - EMIT "Previous validation output is INVALID"
  - RUN full compliance protocol from beginning
  - EMIT compliance evidence in new output

RULES:
  - ALWAYS complete all five recovery steps in order
  - NEVER resume from or append to prior invalid validation output after detection
```

## Relaxed Mode Behavior

```pdsl
UNIT RelaxedModeBehavior

PURPOSE:
  Apply no compliance enforcement and emit a reduced-rigor disclaimer when Rules Mode is RELAXED.

WHEN:
  - REQUIRE Rules Mode == RELAXED

DO:
  - EMIT "⚠️ Validated without Studio rules (reduced rigor)"

RULES:
  - NEVER apply the STRICT compliance protocol when Rules Mode == RELAXED
```

## Consolidated Validation Checklist

Use this checklist to validate agent compliance protocol understanding.

| Group | Check | Required | How to verify |
|---|---|---|---|
| **Understanding (U)** | U.1 Agent understands all 8 anti-patterns | YES | Can identify AP-001 through AP-008 by name |
| **Understanding (U)** | U.2 Agent knows mandatory behaviors for STRICT mode | YES | Can list Read, Checklist, Evidence, Self-Test requirements |
| **Understanding (U)** | U.3 Agent knows evidence standards for PASS/FAIL/N/A | YES | Can describe what each status requires |
| **Understanding (U)** | U.4 Agent knows self-test must be AFTER work | YES | Self-test appears at end of validation output |
| **Understanding (U)** | U.5 Agent knows output schema for STRICT mode | YES | Validation output follows 6-section schema |
| **Understanding (U)** | U.6 Agent knows recovery procedure for violations | YES | Can list 5 recovery steps |
| **Understanding (U)** | U.7 Agent knows RELAXED mode has no enforcement | YES | Includes disclaimer when RELAXED |
| **Execution (E)** | E.1 Read tool used for every artifact | YES | `Read {path}:` confirmation in output |
| **Execution (E)** | E.2 Checklist progress tracked with TodoWrite | YES | Todo list shows category progress |
| **Execution (E)** | E.3 Evidence provided for every status claim | YES | Evidence table has no empty cells |
| **Execution (E)** | E.4 Self-test answered with evidence | YES | All 6 questions answered with proof |
| **Execution (E)** | E.5 Output follows STRICT mode schema | YES | All 6 sections present |
| **Execution (E)** | E.6 No anti-patterns exhibited | YES | No detection signals present |
| **Final (F)** | F.1 All Understanding checks pass | YES | U.1-U.7 verified |
| **Final (F)** | F.2 All Execution checks pass | YES | E.1-E.6 verified |
| **Final (F)** | F.3 Validation output is complete | YES | No `continuing later` or partial reports |
