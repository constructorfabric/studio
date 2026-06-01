---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the orchestrator needs the canonical generate-workflow validation checklist and Agent Self-Test (post-flight gate before ending the response).
---

<!-- toc -->

- [Minimal Validation Manifest](#minimal-validation-manifest)
- [Detailed Post-Flight Checklist](#detailed-post-flight-checklist)
- [Agent Self-Test (STRICT mode — post-flight lazy)](#agent-self-test-strict-mode--post-flight-lazy)

<!-- /toc -->

## Minimal Validation Manifest

```text
UNIT GenerateValidationManifest

PURPOSE:
  Eager minimal validation manifest for the generate workflow.
  This section is safe to load before Phase 1 because it declares only the
  non-deferrable validation gates and leaves the detailed checklist post-flight lazy.

INVARIANTS:
  - MUST have executed {cf-studio-path}/.core/skills/studio/protocol.md
  - MUST have loaded phase-appropriate dependencies (generation: template/example
    unless checklist explicitly required; validation/review: checklist when applicable)
  - MUST preserve explicit write confirmation before any file write or write-capable dispatch
  - MUST have set AUTHOR_PLAN_OFFER_RESOLVED before any Phase 3 / Phase 4
    decision point, using ONLY canonical values from
    workflows/generate/phase-1.5/state-contract.md
  - MUST lazy-load Phase 1.5 at the first post-approval branch when the eager
    applicability predicates require author-plan resolution before disk/write-path selection
  - Prompt-consuming late phases and downstream authors MUST consume only
    controller-supplied prompt_context_view slices from SHARED_CONTEXT_PACK;
    they MUST_NOT reopen workflow, requirement, or AGENTS prompt assets from disk
  - MUST preserve dispatch gates, write confirmation, and shared-context authority
  - MUST defer the detailed checklist and STRICT self-test until post-flight validation
```

## Detailed Post-Flight Checklist

```text
UNIT GenerateValidationCriteria

PURPOSE:
  Canonical detailed post-flight checklist for the generate workflow.
  Lazy-load this section only when preparing the final validation gate,
  terminal handoff, or final response.

INVARIANTS:
  - MUST have clarified system context (if using rules)
  - MUST have clarified output destination
  - MUST have identified parent references
  - MUST have verified ID naming is unique
  - MUST have collected and confirmed information
  - WHEN AUTHOR_PLAN_OFFER_RESOLVED=memory|disk:
    MUST have parsed, validated, and used AUTHOR_EXECUTION_PLAN to drive
    Phase 4 task dispatch
  - WHEN AUTHOR_PLAN_OFFER_RESOLVED=disk:
    MUST have recorded AUTHOR_PLAN_CACHE_DIR; plan cache MUST contain:
    index.md, plan.json, one agents/{author}.md per involved author,
    one task Markdown file per planned task
  - WHEN AUTHOR_PLAN_OFFER_RESOLVED is a terminal cancellation state:
    MUST have skipped Phase 3 and Phase 4; MUST NOT have dispatched
    write-capable author
  - MUST have generated content with no placeholders
  - MUST have all IDs following naming convention
  - MUST have all cross-references valid
  - MUST have written file after confirmation (if file output)
  - MUST have updated artifacts registry (if file output + rules)
  - MUST have executed validation
  - MUST have executed language content check ({cfs_cmd} check-language)
    when allowed_content_languages is configured
  - MUST have recorded exact deterministic validator command(s), per-command
    validator results, and overall deterministic gate
  - MUST have recorded Validator availability proof when deterministic gate is SKIPPED
  - MUST have recorded Semantic review basis
  - MUST have recorded Skip reason and Validator-backed evidence note when
    deterministic gate is SKIPPED
  - MUST have completed final-response gate self-check before ending response
    (for file-writing output)
  - IF output was chat-only AND no files changed AND remaining_findings is empty AND no outstanding validation or waiver decision remains:
    terminal handoff requirements are exempt for that Phase 6 skip path
  - WHEN files written AND remaining_findings is empty:
    MUST have emitted Post-Write Review Handoff menu as FINAL section
    (including RELAXED explicitly unvalidated exits)
  - WHEN files written AND remaining_findings non-empty
    (manual-handoff | user-accepted with remaining | MAX_ITER=0 surfacing all
     findings | RELAXED Deterministic gate: FAIL):
    MUST have emitted Remediation Handoff menu as FINAL section
    MUST have withheld W1/W2/W3 choices until remediation clears
  - MUST have emitted terminal handoff menu with exactly the three canonical
    options for current state (Remediation: R1/R2/R3; Post-Write Review: W1/W2/W3)
    with actual counts filled in
  - IF output was chat-only AND no files changed AND remaining_findings is empty AND no outstanding validation or waiver decision remains:
    MUST skip terminal handoff menu emission instead of synthesizing a
    terminal handoff heading
  - WHEN user picks R2/R3/W2/W3 in their next turn:
    MUST emit corresponding template (Fix Prompt, Plan Prompt, Direct Review Prompt,
    or Plan Review Prompt) as FINAL section of that next response;
    R1/W1 are dispatched in-session without emitting prompt block
```

## Agent Self-Test (STRICT mode — post-flight lazy)

```text
UNIT AgentSelfTestStrict

PURPOSE:
  Answer these AFTER doing the work and include evidence in the output
  (STRICT mode only). This self-test is post-flight lazy and MUST load only at
  the final response gate.

DO:
  ANSWER each question with evidence AFTER completing work:

  | Question | Evidence required |
  |----------|-------------------|
  | Template loaded? | State template path read this turn; confirm non-empty (Read {template_path}: {N} lines) |
  | Example referenced? | State example path read this turn, or explicitly record N/A when RELAXED non-kit with no example |
  | Placeholders absent? | Confirm no {placeholder} or <!-- TODO --> tokens remain in any written file; quote written file content line-count as evidence |
  | Explicit yes received before write? | Show turn where user's Phase 3 confirmation was received before any author dispatch or inline write |
  | CF_PHASE_GATE not left in released_* state? | Confirm gate is armed at end of session; list every gate transition that occurred and confirm each was reset |
  | Post-Write Review Handoff (or Remediation Handoff when remaining findings exist) emitted as terminal section? | Quote the heading emitted, unless the clean Phase 6 skip path applies |

RULES:
  - IF ANY answer is NO or lacks evidence:
    Generate output is INVALID
    MUST fix before ending the response

NOTES:
  Sample output format:
    ### Agent Self-Test Results
    | Question | Answer | Evidence |
    |----------|--------|----------|
    | Template loaded? | YES | Read workflows/templates/my-template.md: 85 lines |
    | Example referenced? | YES | Read examples/example.md: 42 lines |
    | Placeholders absent? | YES | Written file confirmed 120 lines, no {placeholder} tokens |
    | Explicit yes received? | YES | User replied "yes" at Phase 3 approval turn |
    | CF_PHASE_GATE not in released_*? | YES | Gate transitions: armed→released_for_dispatch→armed; no gate left open |
    | Terminal handoff emitted? | YES | Final section is "Post-Write Review Handoff" (remaining_findings = []) |

  Clean Phase 6 skip exception:
    IF Phase 6 skip applies because output is chat-only, no files changed,
       remaining_findings is empty, and no outstanding validation or waiver decision remains:
      self-test handoff-heading evidence is exempt
      EMIT heading exactly `### Clean Phase 6 Skip Evidence`
      EMIT one structured line containing:
        skip_reason=phase_6_clean_chat_only;
        output=chat-only;
        files_changed=false;
        remaining_findings=empty;
        outstanding_validation_or_waiver_decision=false
      DO NOT emit `### Agent Self-Test Results` or any terminal handoff heading

UNIT AgentSelfTestRelaxed

PURPOSE:
  Define RELAXED mode self-test skip behavior.

WHEN:
  rules_mode == RELAXED

DO:
  EMIT exactly:
---
⚠️ Self-test skipped (RELAXED mode — no Constructor Studio rules)
---
```
