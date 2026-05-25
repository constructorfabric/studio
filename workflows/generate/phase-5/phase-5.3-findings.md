---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the merged findings list (det + semantic) must be displayed, partitioned, and (when all-mechanical) auto-fixed via the fast-path branch.
---

<!-- toc -->

- [Phase 5.3: Findings Display + Auto-Fix-Mechanical Fast Path](#phase-53-findings-display--auto-fix-mechanical-fast-path)

<!-- /toc -->

### Phase 5.3: Findings Display + Auto-Fix-Mechanical Fast Path

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch. Pre-dispatch fail-stop and Mode B degradation rules are defined in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

**External entry from `analyze.md` Remediation Handoff option 1**: this phase accepts entry from the analyze workflow (when the user picks "Continue here in fix mode" on the analyze-side handoff menu). On external entry, the orchestrator must initialize the following Phase-5 state before executing the body of this phase:

- **MUST re-probe** `workflows/shared/inline-fallback-probe.md` FIRST — analyze-side `INLINE_FALLBACK` does NOT carry across this handoff. `SUB_AGENT_SESSION_APPROVED` carries across; `INLINE_FALLBACK` does not.
- `all_findings` = the merged findings list handed off from analyze (already namespaced per `workflows/analyze/phase-3-semantic.md` § Namespace rule)
- `carried_validation_results` and `carried_semantic_reports` = analyze-side
  deterministic results and semantic report blocks for Phase 6 external-entry
  output, especially when `MAX_ITER=0`
- `external_target_paths = analyzed_paths` and MUST be preserved until an
  author dispatch returns a non-empty `manifest.paths_written`; downstream
  remediation re-entry uses it as the fallback target set
- `target_paths = analyzed_paths` (in-scope target set for every downstream validation, review, and author dispatch)
- `manifest.paths_written = []` until an author dispatch returns an actual write manifest
- `MAX_ITER` = resolved via the `workflows/generate/phase-5/index.md` § Pre-Phase-Setup (MAX_ITER resolution) prompt at handoff time (default `5` on enter; `0` to skip the loop and surface findings into `workflows/generate/phase-6/index.md` directly)
- `N`, `carry_forward` = inherit the canonical Phase 5 state initialization defined in `workflows/generate/phase-5/index.md` § Dispatcher (`N = 1`, `carry_forward = []`); the dispatcher definition is the single source of truth and external entry uses identical values
- `kit_rules_path`, `rules_mode`, `template_path`, `example_path`, `checklist_path`, `kind`, `name`, `system`, `design_artifact_path` (code mode) = resolved from the analyze-side context the same way `workflows/generate/phase-0-dependencies.md` + `workflows/generate/phase-0.5-clarify.md` would resolve them on a fresh generate run; when any of these values cannot be inferred, emit the following structured clarification prompt for each missing value before proceeding:

  ```text
  One or more generate-context values could not be inferred from the analyze-side handoff. Please supply the following:

  Why this input is needed: The generate-side author dispatch requires [{variable_name}] to select the correct template/rules/author tier.
  Suggested: {inferred_value_from_artifacts_toml_or_N/A_if_not_available}
  Reply with `{variable_name}: <value>`
  ```

  Emit one prompt per unresolved variable in order: `kind`, `rules_mode`, `system`, `kit_rules_path`, `template_path`, `example_path`, `checklist_path`, `name`, `design_artifact_path`. Wait for user reply before proceeding to the body of this phase.

External-fix handoff guard: before any file edit or inline patch attempt, Phase
5 state MUST show `handoff_guard.inline_fallback_reprobed = true`,
`handoff_guard.max_iter_resolved = true`, and
`handoff_guard.dispatch_evidence_required = true`. Inline patching is permitted only when `INLINE_FALLBACK=true` or `MAX_ITER=0`. When `MAX_ITER > 0` and
`INLINE_FALLBACK=false`, missing `phase5_dispatch_evidence` for the required
validator/reviewer/author sequence means the orchestrator MUST stop before editing files and repair the dispatch state instead of applying patches inline.

After initialization, execute the body of this sub-file normally (it treats external-entry state identically to internal-entry state).

If `MAX_ITER == 0`: skip the partition + auto-fix logic, but STILL render the full findings list (see the Findings display block below) so the user has the audit trail in chat. For external analyze→generate entry, use the carried findings from analyze without a fresh Phase 5 validation/review and emit `Iteration 1/1 (MAX_ITER=0): zero-iteration external entry; surfacing all carried findings to workflows/generate/phase-6/index.md.` For internal generate entry, use the findings from the one fresh validator + semantic-reviewer pass and emit `Iteration 1/1 (MAX_ITER=0): zero-iteration internal entry; surfacing the single-pass findings to workflows/generate/phase-6/index.md.` Then set `remaining_findings = all_findings` and route to `workflows/generate/phase-6/index.md` (Remediation Handoff menu MANDATORY when `remaining_findings` is non-empty).

Set `remaining_findings = []` on entry to this phase (before any branch executes). Branches below override this value before exiting.

Partition `all_findings` by the `mechanical` flag:

- `mechanical = [f for f in all_findings if f.mechanical]`
- `judgmental = [f for f in all_findings if not f.mechanical]`

If `all_findings` is empty and `carry_forward` is also empty, emit:

```text
Iteration {N}/{MAX_ITER}: clean — exiting review loop.
```

Then set `loop_exit = "clean"`, `remaining_findings = []`, and
proceed to `workflows/generate/phase-5/phase-5.5-final.md`.

If `all_findings` is empty but `carry_forward` is non-empty, the loop is not
clean. Do not announce `clean`. Exit only as one of:

- `loop_exit = "manual-handoff"` when the user stopped or chose handoff;
  set `remaining_findings = carry_forward`.
- `loop_exit = "user-accepted"` when the user explicitly accepted those
  carried findings as-is after seeing their IDs; set
  `remaining_findings = carry_forward`.
- Protocol error when neither condition is true; stop and surface that
  unresolved carry-forward findings cannot be hidden by a clean validator pass.

#### Findings display (ALWAYS rendered — preserves audit history in the chat)

When `all_findings` is non-empty, render every finding in a single ordered list so the user can audit the classification and rationale BEFORE any fix proceeds. The list includes BOTH mechanical and judgmental findings; mechanical-vs-judgmental classification is shown inline together with each agent's `mechanical_rationale` so the user can spot misclassifications.

Before rendering, the orchestrator MUST verify every finding object has a non-empty `mechanical_rationale` string. On missing field, substitute the literal text `<no rationale provided by {agent_name}>` for that finding and continue rendering (do not abort the iteration).

```text
Iteration {N}/{MAX_ITER}. Det gate: {PASS|FAIL}. Findings: High {h} / Medium {m} / Low {l}; mechanical {m_count}, judgmental {j_count}.

[{id}] [{mech|judg}] [{severity}] `{path}`:{line} — {category}
       Evidence: "{evidence_quote}"
       Why {mechanical|judgmental}: {mechanical_rationale}
       Suggested fix: {suggested_fix}
[{next id}] ... (one block per finding, mechanical and judgmental interleaved by source order)
```

The orchestrator MUST emit every finding before deciding the next step: do not collapse, summarize, or truncate the finding list before user approval; the displayed list and the full findings JSON must identify the same IDs so later fix, prompt, and plan handoffs cannot reference unseen findings.

#### Branch — all-mechanical fast path

If `judgmental` is EMPTY (i.e., every finding has `mechanical: true`), emit the announcement immediately after the findings display:

```text
All {m_count} findings are mechanical — deterministic fixes derivable from each finding's `mechanical_rationale` alone. No user approval required. Auto-fixing now.
```

Then build the full mode=fix Inputs contract (matching the
`workflows/generate/phase-4-write.md` author worker Inputs schema, with
`mode=fix` replacing `mode=create` and `findings` replacing the original
`inputs`):

- `mode`: `"fix"`
- `kind`, `name`, `system`, `rules_mode` — carried over from `workflows/generate/phase-4-write.md`
- `target_paths`: `target_paths`
- `findings`: `mechanical`
- `template_path`, `example_path`, `kit_rules_path` resolved from `rules.md` (or `null` in RELAXED non-kit)
- `checklist_path` included only when STRICT explicitly requires checklist guidance during fix (mirrors `workflows/generate/phase-4-write.md` § STRICT-checklist conditional)
- `design_artifact_path` code mode only
- `git_commit_mode` = `GIT_COMMIT_MODE` (MUST be included)
- `contributing_guide` = `CONTRIBUTING_GUIDE` (MUST be included; `null` when not found)
- `git_constraint` = the mode-matched constraint block from `workflows/generate/phase-4-write.md` § Git constraint blocks (include the block matching the current `GIT_COMMIT_MODE`)

When `INLINE_FALLBACK=true`, MUST set `CF_PHASE_GATE=released_for_inline_write`
IMMEDIATELY before executing the inline write block below (see SKILL.md §
Phase-Skip Gate). MUST reset `CF_PHASE_GATE=armed` IMMEDIATELY after the
inline write block completes — both on success AND on failure.

Execute `workflows/generate/phase-4-write.md` § Author Selection and Dispatch
with that payload. Append the selected author's returned `findings_not_fixable`
to the session-level `carry_forward` set; open, load, and follow
`workflows/generate/phase-5/phase-5.4-approval.md` § Session-level
carry-forward for the canonical rule. Update `manifest` from the returned
manifest, set `N = N + 1`. On `N > MAX_ITER`:
<!-- Gate invariant: CF_PHASE_GATE is already 'armed' at this point (reset above after the inline write block). The cap prompt does not modify gate state. -->
emit the `Review-Loop Iteration Cap Prompt` (defined in `workflows/generate/phase-5/index.md` §
Pre-Phase-Setup as the canonical wording) and apply the same cap-reply rules
from `workflows/generate/phase-5/phase-5.4-approval.md`: `extend: <M>` raises
the cap, `accept` exits only after a post-fix deterministic gate, and `stop`
exits with `loop_exit = "manual-handoff", remaining_findings =
carry_forward`. If `N ≤ MAX_ITER`, return to
`workflows/generate/phase-5/phase-5.1-det-gate.md`.

If the user types a stop token (`stop` / `enough` / `done`) BEFORE the orchestrator dispatches the auto-fix (i.e., while the announcement is being read), treat it as `workflows/generate/phase-5/phase-5.4-approval.md` § option `4` (manual-handoff): skip the auto-fix dispatch, set `remaining_findings = all_findings`, set `loop_exit = "manual-handoff"`, proceed to `workflows/generate/phase-6/index.md`.

#### Branch — mixed or judgmental-only

If `judgmental` is non-empty, proceed to `workflows/generate/phase-5/phase-5.4-approval.md` with both `mechanical` and `judgmental` lists in scope. The `workflows/generate/phase-5/phase-5.4-approval.md` menu acknowledges that the full findings list above has already been rendered for audit; the menu governs which judgmental findings get fixed alongside the mechanical batch.
