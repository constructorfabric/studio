---
cf: true
type: workflow-phase
name: plan-phase-1-assess
description: "Invoke when /cf-plan enters Phase 1 to assess task scope: identify task type, extract navigation rules, estimate compiled size, scan for interaction points, and identify the target artifact."
loaded_by: workflows/plan.md
version: 1.0
---

# Phase 1: Assess Scope

<!-- toc -->

- [1.1 Identify Task Type](#11-identify-task-type)
- [1.1b Extract Target Workflow Navigation Rules (CRITICAL)](#11b-extract-target-workflow-navigation-rules-critical)
- [1.2 Estimate Compiled Size](#12-estimate-compiled-size)
- [1.3 Identify Target & Resolve Kit Inputs](#13-identify-target--resolve-kit-inputs)
- [1.4 Scan for User Interaction Points (CRITICAL)](#14-scan-for-user-interaction-points-critical)

<!-- /toc -->

## 1.1 Identify Task Type

```text
UNIT Phase1IdentifyTaskType

PURPOSE:
  Map user request signals to a task type and target workflow.

DO:
  MATCH user request signals:
    create | generate | write | update | draft + artifact kind -> SET task_type = generate
                                                                   SET target_workflow = generate.md
    validate | review | check | audit | analyze + artifact kind -> SET task_type = analyze
                                                                    SET target_workflow = analyze.md
    implement | code | build | develop + feature name           -> SET task_type = implement
                                                                   SET target_workflow = generate.md (code mode)

NOTES:
  For implement requests, inspect the direct prompt plus any provided FEATURE, DESIGN,
  code, or task files before deciding the target. Small implement tasks map to direct
  /cf-generate execution when compiled estimate is <= 500 and no reusable authoritative
  raw-input package exists.
```

## 1.1b Extract Target Workflow Navigation Rules (CRITICAL)

```text
UNIT Phase1ExtractNavigationRules

PURPOSE:
  Load all applicable navigation-linked files before plan generation begins.

DO:
  OPEN {cf-studio-path}/.core/workflows/{target_workflow}
  SCAN all navigation directives
  LIST referenced files + WHEN conditions
  EVALUATE each condition
  OPEN every applicable file
  EXTRACT only sections/ranges needed for plan generation
  RECORD loaded-file manifest with: path, reason, sections/ranges, line_count
  EMIT:
    Context loaded for plan generation:
      Workflow: {target_workflow} ({N} navigation rules processed)
      Files inspected: {M} files
      Loaded manifest: {path — sections/ranges — reason}
      Total retained context: ~{L} lines
      All navigation rules processed? [YES/NO]

RULES:
  - MUST NOT proceed until ALL applicable navigation rules are processed
  - MUST NOT proceed until every required file referenced by navigation rules has been opened
  - MUST NOT proceed until every retained slice needed for planning is captured in the manifest
```

## 1.2 Estimate Compiled Size

```text
UNIT Phase1EstimateCompiledSize

PURPOSE:
  Determine whether to continue planning or route to direct execution.

DO:
  COMPUTE estimate = template_lines + rules_lines + checklist_lines + existing_content_lines

  IF oversized raw input already has an approved or reusable plan package:
    REMAIN on plan path regardless of estimate
    CONTINUE Phase1IdentifyTarget
  ELSE IF estimate <= 500:
    CONTINUE Phase1IdentifyTarget  (resolve {task-slug} before checking for reusable package)
  ELSE:
    CONTINUE Phase1IdentifyTarget  (estimate > 500, continue planning)
```

## 1.3 Identify Target & Resolve Kit Inputs

```text
UNIT Phase1IdentifyTarget

PURPOSE:
  Resolve artifact, kit, target_key, and input_signature before the interaction scan.

DO:
  RESOLVE based on task_type:
    generate -> artifact kind, file path, kit
    analyze  -> artifact kind, file path, kit
    implement -> FEATURE spec path, CDSL blocks

  COMPUTE plan.target_key:
    generate artifact target:
      IF single resolved output artifact path known:
        SET plan.target_key = artifact-path:{absolute path}
      ELSE:
        SET plan.target_key = artifact:{artifact kind}:{explicit artifact name}
    analyze path target:
      SET plan.target_key = path:{absolute path} for primary file/directory target
      (analyze artifact target follows generate artifact-target rule)
    implement target:
      IF absolute FEATURE path known:   SET plan.target_key = feature-path:{absolute FEATURE path}
      ELSE IF FEATURE ID known:         SET plan.target_key = feature-id:{FEATURE ID}
      ELSE:                             SET plan.target_key = feature-title:{normalized FEATURE title}

  COMPUTE plan.input_signature:
    DERIVE from each source's kind, path, and content hash (direct prompt + every provided file)
    RUN {cfs_cmd} --json chunk-input ... --output-dir {cf-studio-path}/.plans/{task-slug}/input --dry-run
      (add --include-stdin when direct prompt text must be included)
    SET plan.input_signature = returned signature value

  COMPUTE {task-slug} immediately for deterministic plan-directory naming and reuse

  EMIT:
    Plan scope:
      Type: {generate|analyze|implement}
      Target: {artifact kind or feature name}
      Target key: {canonical target identity}
      Input signature: {sha256 of direct prompt + provided file contents}
      Estimated size: ~{N} lines

NOTES:
  plan.input_signature is authoritative for raw-input package reuse;
  plan.target_key is not sufficient when the raw task input changes.
```

## 1.4 Scan for User Interaction Points (CRITICAL)

```text
UNIT Phase1ScanInteractionPoints

PURPOSE:
  Enumerate all user interaction points before plan generation. Missing points
  is the #2 source of plan failures after missing rules.

INPUT:
  target workflow, rules.md, checklist.md, template.md, all applicable navigation-linked files

DO:
  SCAN all files listed in INPUT recursively for these signals:
    question: ask the user | ask user | what is | which | trailing ?
    input:    user provides | user specifies | user enters | input from user
    confirm:  wait for | confirm | approval | before proceeding
    review:   review | present for | show to user | user inspects
    decision: choose | select | option A or B | decide

  FOR each finding:
    CLASSIFY as Pre-resolvable | Phase-bound | Cross-phase

  ASK all pre-resolvable and cross-phase questions now
  RECORD answers in a decisions block

  EMIT:
    Interaction points scan complete:
      Files scanned: {N}
      Interaction points found: {M}
        - Pre-resolvable: {count}
        - Phase-bound: {count}
        - Cross-phase: {count}
      All source files scanned? [YES/NO]
      All interaction points classified? [YES/NO]

  IF zero found:
    EMIT "No interaction points detected — task is fully autonomous"
    OMIT User Decisions from phase files

RULES:
  - MUST NOT proceed if any source file was not scanned
  - MUST NOT proceed if any interaction point remains unclassified

CONTINUE Phase1RawInputCheck
```

```text
UNIT Phase1RawInputCheck

PURPOSE:
  Decide whether to reuse an existing raw-input package, route to direct execution,
  or prompt for raw-input materialization.

DO:
  IF {cf-studio-path}/.plans/{task-slug}/input/manifest.json exists:
    READ its input_signature
    COMPARE to input_signature from --dry-run invocation above
    IF they match exactly:
      REMAIN on plan path and reuse that authoritative raw-input package
      STOP_TURN (no further routing check needed)

  IF compiled estimate <= 500
    AND oversized raw input does NOT already have an approved or reusable plan package:
    STOP_TURN — direct user to /cf-generate or /cf-analyze

  IF (direct prompt text + all provided files) > 500 total lines
    AND no authoritative raw-input package with same plan.input_signature exists:
    EMIT_MENU RawInputMaterializationMenu
    WAIT user.reply
    STOP_TURN

MENU RawInputMaterializationMenu:
  TITLE: Oversized raw input detected (~{N} lines total). Proceed with raw-input materialization? [y/n]
  PREAMBLE:
    Preparing the plan will write chunk files under {cf-studio-path}/.plans/{task-slug}/input/ by running:
      {cfs_cmd} --json chunk-input ... --output-dir {cf-studio-path}/.plans/{task-slug}/input --max-lines 300 --threshold-lines 500
      Add --include-stdin when direct prompt text must be packaged together with provided files.
      The command also writes {cf-studio-path}/.plans/{task-slug}/input/manifest.json with
      `input_signature` and only replaces the existing package after the full replacement
      package is staged successfully.
  OPTIONS:
    y -> SET CF_PHASE_GATE = released_for_orchestrator_write
            scope = {cf-studio-path}/.plans/{task-slug}/input/
         EXECUTE chunk-input (without --dry-run)
         RECORD emitted chunk paths + manifest.json
         STOP carrying full raw input in active chat context once package exists
         SET CF_PHASE_GATE = armed
         CONTINUE Phase2Decompose
    n -> EMIT "Raw-input materialization declined — stop and re-run with smaller input or approve materialization when ready"
         STOP_TURN  (valid completion state for /cf-plan; no files created)
  INVALID:
    EMIT "Reply with y or n."
    WAIT user.reply
    STOP_TURN

RULES:
  - MUST wait for explicit user confirmation before creating input/ directory or executing chunk-input without --dry-run
  - MUST NOT create any files or directories when user replies n
```
