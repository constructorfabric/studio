---
name: analyze-phase-3-to-4-checkpoint
description: "Invoke when transitioning from Analyze Phase 3 to Phase 4 to evaluate the context-budget recovery checkpoint (continue-or-resume gate)."
purpose: Analyze Phase 3 → Phase 4 context-budget recovery checkpoint (continue-or-resume gate)
loaded_by: workflows/analyze.md
version: 1.0
---

### Phase 3 → Phase 4 Checkpoint (Context Budget Recovery)

Before proceeding to Phase 4 Output, estimate remaining context budget. If
budget is below ~30% of original capacity, or if Phase 3 ended with
`PARTIAL=true`, emit a checkpoint that is target-set centric rather than
single-artifact centric.

The checkpoint MUST include:

- `target_paths` / `analyzed_paths` exactly as used by Phase 3, grouped by
  methodology (`artifact`, `code`, `code_bug`, `prompt`, `prompt_bug`,
  `consistency`) and including diff/change-review scope when present.
- Deterministic gate status, validator output summary, and whether the gate
  was `PASS`, `FAIL`, `SKIPPED`, or unavailable.
- Methodology dispatch status for every planned or legacy reviewer:
  `completed`, `failed`, `blocked_by_failed_dep`, `skipped`, or `not_applicable`,
  with task/group ids when a reviewer execution plan was used.
- The complete findings JSON accumulated so far, already namespaced and
  renumbered per `workflows/analyze/phase-3-semantic.md`.
- Semantic report block inventory: one entry per `Validation Report — <Section>`
  block, with source reviewer, target paths, and status.
- Prompt/code/artifact review state: loaded methodology files, kit rules path
  or `null`, checklist/template/example paths when applicable, traceability
  mode, cross-reference paths, and any failed/skipped reviewer reason.
- Deterministic resume gate: file fingerprints or mtimes for every
  `target_path`, `cross_ref_path`, `design_artifact_path`, loaded methodology
  file, and rules/checklist file that affected the review.

After emitting the checkpoint, ask:

```text
Context budget is low after semantic review. Continue to Phase 4 (Output + remediation prompts) in this chat, or start a fresh chat with the checkpoint above?

1. Continue in this chat — proceed to Phase 4 with the checkpoint state already loaded
2. Emit a fresh-chat resume prompt — produce a self-contained prompt that starts with `Invoke skill cf` and embeds the checkpoint

Suggested: 1 when enough context remains for Phase 4; 2 when context pressure is high.

Reply `1` or `2`.
```

Next-turn parser:

- `1` → continue in this chat and enter `workflows/analyze/phase-4-output/index.md`.
- `2` → emit a fresh-chat resume prompt as the final section; the prompt must include `target_paths`, deterministic gate summary, methodology dispatch status, findings JSON, semantic report inventory, and resume fingerprints.
- Anything else re-prompts with the same two choices; do not infer a default.

On resume in a fresh chat, re-read the target set and all referenced rules /
methodology files, verify the deterministic resume gate against the checkpoint
including methodology-file fingerprints, reload the findings JSON and semantic
report inventory, and skip to Phase 4 only when the gate matches. If any
fingerprint changed, do not reuse the checkpoint silently; rerun the affected
deterministic/semantic review groups or ask the user which changed targets to
re-analyze.

If budget is sufficient (≥30% remaining) and Phase 3 is not partial, proceed
directly to Phase 4 without stopping.
