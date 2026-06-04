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

```pdsl
UNIT GenerateValidationManifest

PURPOSE:
  Eager minimal validation manifest for the generate workflow.
  This section is safe to load before Phase 1 because it declares only the
  non-deferrable validation gates and leaves the detailed checklist post-flight lazy.

INVARIANTS:
  - ALWAYS have executed {cf-studio-path}/.core/skills/studio/protocol.md
  - ALWAYS have loaded phase-appropriate dependencies (generation: template/example
    unless checklist explicitly required; validation/review: checklist when applicable)
  - ALWAYS preserve explicit write confirmation before any file write or write-capable dispatch
  - ALWAYS have set AUTHOR_PLAN_OFFER_RESOLVED before any Phase 3 / Phase 4
    decision point, using ONLY canonical values from
    workflows/generate/phase-1.5/state-contract.md
  - ALWAYS lazy-load Phase 1.5 at the first post-approval branch when the eager
    applicability predicates require author-plan resolution before disk/write-path selection
  - ALWAYS Prompt-consuming late phases and downstream authors ALWAYS consume only
    controller-supplied prompt_context_view slices from SHARED_CONTEXT_PACK;
    they NEVER reopen workflow, requirement, or AGENTS prompt assets from disk
  - ALWAYS preserve dispatch gates, write confirmation, and shared-context authority
  - ALWAYS defer the detailed checklist and STRICT self-test until post-flight validation
```

## Detailed Post-Flight Checklist

```pdsl
UNIT GenerateValidationCriteria

PURPOSE:
  Canonical detailed post-flight checklist for the generate workflow.
  Lazy-load this section only when preparing the final validation gate,
  terminal handoff, or final response.

INVARIANTS:
  - ALWAYS have clarified system context (if using rules)
  - ALWAYS have clarified output destination
  - ALWAYS have identified parent references
  - ALWAYS have verified ID naming is unique
  - ALWAYS have collected and confirmed information
  - ALWAYS WHEN AUTHOR_PLAN_OFFER_RESOLVED=memory|disk|inline:
    ALWAYS have parsed, validated, and used AUTHOR_EXECUTION_PLAN to drive
    Phase 4 task dispatch
  - ALWAYS WHEN AUTHOR_PLAN_OFFER_RESOLVED=skipped_by_user:
    ALWAYS have used the single-author flow and NEVER claimed planned parallel dispatch
  - ALWAYS WHEN AUTHOR_PLAN_OFFER_RESOLVED=disk:
    ALWAYS have recorded AUTHOR_PLAN_CACHE_DIR; plan cache ALWAYS contain:
    index.md, plan.json, one agents/{author}.md per involved author,
    one task Markdown file per planned task
  - ALWAYS WHEN AUTHOR_PLAN_OFFER_RESOLVED is a terminal cancellation state:
    ALWAYS have skipped Phase 3 and Phase 4; NEVER have dispatched
    write-capable author
  - ALWAYS have generated content with no placeholders
  - ALWAYS have all IDs following naming convention
  - ALWAYS have all cross-references valid
  - ALWAYS have written file after confirmation (if file output)
  - ALWAYS have updated artifacts registry (if file output + rules)
  - ALWAYS have executed validation
  - ALWAYS have executed language content check ({cfs_cmd} check-language)
    when allowed_content_languages is configured
  - ALWAYS have recorded exact deterministic validator command(s), per-command
    validator results, and overall deterministic gate
  - ALWAYS have recorded Validator availability proof when deterministic gate is SKIPPED
  - ALWAYS have recorded Semantic review basis
  - ALWAYS have recorded Skip reason and Validator-backed evidence note when
    deterministic gate is SKIPPED
  - ALWAYS have completed final-response gate self-check before ending response
    (for file-writing output)
  - ALWAYS IF output was chat-only AND no files changed AND remaining_findings is empty AND no outstanding validation or waiver decision remains:
    terminal handoff requirements are exempt for that Phase 6 skip path
  - ALWAYS WHEN files written AND remaining_findings is empty:
    ALWAYS have emitted Post-Write Review Handoff menu as FINAL section
    (including RELAXED explicitly unvalidated exits)
  - ALWAYS WHEN files written AND remaining_findings non-empty
    (manual-handoff | user-accepted with remaining | MAX_ITER=0 surfacing all
     findings | RELAXED Deterministic gate: FAIL):
    ALWAYS have emitted Remediation Handoff menu as FINAL section
    ALWAYS have withheld W1/W2/W3 choices until remediation clears
  - ALWAYS have emitted terminal handoff menu with exactly the three canonical
    options for current state (Remediation: R1/R2/R3; Post-Write Review: W1/W2/W3)
    with actual counts filled in
  - ALWAYS IF output was chat-only AND no files changed AND remaining_findings is empty AND no outstanding validation or waiver decision remains:
    ALWAYS skip terminal handoff menu emission instead of synthesizing a
    terminal handoff heading
  - ALWAYS WHEN user picks R2/R3/W2/W3 in their next turn:
    ALWAYS emit corresponding template (Fix Prompt, Plan Prompt, Direct Review Prompt,
    or Plan Review Prompt) as FINAL section of that next response;
    R1/W1 are dispatched in-session without emitting prompt block
```

## Agent Self-Test (STRICT mode — post-flight lazy)

```pdsl
UNIT AgentSelfTestStrict

PURPOSE:
  Answer these AFTER doing the work and include evidence in the output
  (STRICT mode only). This self-test is post-flight lazy and ALWAYS load only at
  the final response gate.

DO:
  - RUN ANSWER each question with evidence AFTER completing work:

  - RUN | Question | Evidence required |
  - RUN |----------|-------------------|
  - RUN | Template loaded? | State template path read this turn; confirm non-empty (Read {template_path}: {N} lines) |
  - RUN | Example referenced? | State example path read this turn, or explicitly record N/A when RELAXED non-kit with no example |
  - RUN | Placeholders absent? | Confirm no {placeholder} or <!-- TODO --> tokens remain in any written file; quote written file content line-count as evidence |
  - RUN | Explicit yes received before write? | Show turn where user's Phase 3 confirmation was received before any author dispatch or inline write |
  - RUN | CF_PHASE_GATE not left in released_* state? | Confirm gate is armed at end of session; list every gate transition that occurred and confirm each was reset |
  - RUN | Post-Write Review Handoff (or Remediation Handoff when remaining findings exist) emitted as terminal section? | Quote the heading emitted, unless the clean Phase 6 skip path applies |

RULES:
  - ALWAYS IF ANY answer is NO or lacks evidence:
    Generate output is INVALID
    ALWAYS fix before ending the response

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
  - REQUIRE rules_mode == RELAXED

DO:
  - EMIT exactly:
- RUN ---
- RUN ⚠️ Self-test skipped (RELAXED mode — no Constructor Studio rules)
- RUN ---
```
