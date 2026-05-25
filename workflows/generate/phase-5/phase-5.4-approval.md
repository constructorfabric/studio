---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the iteration is mixed or judgmental-only (judgmental non-empty) and the user-approval gate must be presented before any author fix dispatch.
---

<!-- toc -->

- [Phase 5.4: User-Approval Gate (judgmental findings)](#phase-54-user-approval-gate-judgmental-findings)

<!-- /toc -->

### Phase 5.4: User-Approval Gate (judgmental findings)

Requires: `workflows/shared/inline-fallback-probe.md` before any `cf-*` sub-agent dispatch. Pre-dispatch fail-stop and Mode B degradation rules are defined in `{cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md`.

Enter this gate ONLY when `judgmental` is non-empty (mixed or judgmental-only iterations). The full findings list — both mechanical and judgmental, each with classification + `mechanical_rationale` — has already been rendered in `workflows/generate/phase-5/phase-5.3-findings.md` § Findings display and serves as the user's audit reference for this prompt. Do NOT re-render it here.

```text
Mixed iteration {N}/{MAX_ITER}: {m_count} mechanical (will be auto-fixed when you proceed) + {j_count} judgmental (need your call).
Mechanical IDs (queued for auto-fix on options 1 / 2): {comma-separated mechanical IDs}.
Judgmental IDs (need approval): {comma-separated judgmental IDs}.

How do you want to proceed with the judgmental findings?

1. Approve all → fix all judgmental + auto-fix all mechanical       (suggested)
2. Approve subset → reply IDs of judgmental to fix (e.g. `2: V-003, Rp-007`); mechanical batch is still auto-fixed. Reply `2:` with no IDs to apply the mechanical batch only — un-approved judgmental findings are carried forward in session state and are also left in place for the next iteration's reviewers to re-detect.
3. No fixes — defer ALL findings → applies NO fixes this iteration: the mechanical batch is suppressed (NOT auto-applied) AND all judgmental findings are deferred; ALL remaining findings (mechanical + judgmental) surface to the `workflows/generate/phase-6/remediation-handoff.md` menu. Files remain in their as-of-`workflows/generate/phase-4-write.md` state. Use this when you want to inspect or hand off every finding — including the mechanical ones — before any more fixes. (Contrast with bare `2:` which applies the mechanical batch while deferring judgmental.)
4. Stop loop → no fixes this iteration; exit loop; remaining_findings = all findings (mechanical + judgmental); same `workflows/generate/phase-6/remediation-handoff.md` menu applies. (Like option 3, no mechanical batch is applied; use bare `2:` to apply the mechanical batch before stopping.)

Reply `1`, `2: <comma-separated judgmental IDs>` (or bare `2:` for mechanical-only), `3`, or `4`.
```

Reply parsing rules (canonical; case-insensitive throughout):

| User input (regex, case-insensitive, leading/trailing whitespace stripped) | Interpretation |
|---|---|
| `^1$` | Option 1 — approve all |
| `^2$` (no colon) | **Reject** with `Reply 2 needs a colon: type \`2:\` for mechanical-only, or \`2: <comma-separated judgmental IDs>\` to also approve specific judgmental findings. Reply again.` Do NOT proceed. |
| `^2:\s*$` | Option 2 bare — mechanical batch only |
| `^2:\s*[A-Za-z][A-Za-z0-9_-]*(\s*,\s*[A-Za-z][A-Za-z0-9_-]*)*\s*$` | Option 2 with IDs — split on commas (whitespace around comma tolerated), uppercase IDs, intersect with `judgmental` set, drop unknown IDs with a one-line warning listing them |
| `^3$` | Option 3 — defer (no fixes, exit to `workflows/generate/phase-6/index.md`) |
| `^4$` | Option 4 — stop (no fixes, exit to `workflows/generate/phase-6/index.md`) |
| `^(stop\|enough\|done)$` | Treat as option `4`; open, load, and follow `workflows/shared/stop-token-policy.md` for the canonical stop-token rule. |
| anything else | Reject with `Reply not recognized. Expected \`1\`, \`2:\`, \`2: <IDs>\`, \`3\`, or \`4\`. Reply again.` Do NOT proceed. |

Session-level carry-forward: the orchestrator maintains a `carry_forward` set across iterations, initially empty. After every author dispatch (whether from `workflows/generate/phase-5/phase-5.3-findings.md` § fast-path or from this sub-file's options `1` / `2: <…>` / bare `2:`), union the selected author's returned `findings_not_fixable` array into `carry_forward`, deduplicating by finding `id`. For option `2: <IDs>` and bare `2:`, also union every un-approved judgmental finding into `carry_forward` before the next reviewer pass. A finding rejected across multiple iterations appears at most once in the final set. The set is unioned into `remaining_findings` on every loop exit so author-rejected and user-unapproved judgmental findings are never silently dropped.

Cap-prompt reply rules after an author write: `extend: <M>` → raise `MAX_ITER`
to `<M>` when it is greater than the current cap and return to Phase 5.1;
`accept` → run a post-fix deterministic gate before setting
`loop_exit = "max-iter-stopped"` and `remaining_findings = carry_forward`;
`stop` → set `loop_exit = "manual-handoff"` and
`remaining_findings = carry_forward`. If the post-fix deterministic gate fails,
do not claim the prior PASS; set `loop_exit = "max-iter-stopped-with-failures"`,
carry the failure into `remaining_findings`, then proceed to
`workflows/generate/phase-5/phase-5.5-final.md`.

The cap prompt's `accept` exits only after a post-fix deterministic gate; it
must not reuse a stale pre-fix PASS. After any option that dispatches an author
worker, append the selected author dispatch evidence to `phase5_dispatch_evidence` before updating `manifest` or claiming files were
written.

Parse reply:

- `1` → `to_fix = mechanical + judgmental`. Build a `mode=fix` payload with `target_paths=target_paths` (external analyze→generate entry) or `target_paths=manifest.paths_written` (normal generate entry) and `findings=to_fix`; include `git_commit_mode=GIT_COMMIT_MODE`, `contributing_guide=CONTRIBUTING_GUIDE`, and the matching `git_constraint` block from `workflows/generate/phase-4-write.md` § Git constraint blocks. Execute `workflows/generate/phase-4-write.md` § Author Selection and Dispatch. Append returned `findings_not_fixable` to `carry_forward`. Update `manifest`. Set `N = N + 1`. On `N > MAX_ITER`, emit the cap prompt and apply the cap-prompt reply rules above. Otherwise return to `workflows/generate/phase-5/phase-5.1-det-gate.md`.
- `2: <IDs>` → `approved_judgmental = judgmental ∩ <IDs>`; `unapproved_judgmental = judgmental \ approved_judgmental`; `to_fix = mechanical + approved_judgmental`. Add `unapproved_judgmental` to `carry_forward`, build a `mode=fix` payload with `target_paths=target_paths` (external analyze→generate entry) or `target_paths=manifest.paths_written` (normal generate entry) and `findings=to_fix`; include `git_commit_mode=GIT_COMMIT_MODE`, `contributing_guide=CONTRIBUTING_GUIDE`, and the matching `git_constraint` block from `workflows/generate/phase-4-write.md` § Git constraint blocks. Execute `workflows/generate/phase-4-write.md` § Author Selection and Dispatch. Append returned `findings_not_fixable`, update `manifest`, and set `N = N + 1`. On `N > MAX_ITER`, emit the cap prompt and apply the cap-prompt reply rules above. Otherwise return to `workflows/generate/phase-5/phase-5.1-det-gate.md`; items only in `carry_forward` are still surfaced on eventual exit.
- `3` → set `loop_exit = "user-accepted"`; `remaining_findings = all_findings ∪ carry_forward`; proceed to `workflows/generate/phase-6/index.md` (`workflows/generate/phase-6/remediation-handoff.md` menu MANDATORY because `remaining_findings` is non-empty; `workflows/generate/phase-6/post-write-handoff.md` stays locked until remediation clears).
- `4` → set `loop_exit = "manual-handoff"`; `remaining_findings = all_findings ∪ carry_forward`; proceed to `workflows/generate/phase-6/index.md` (`workflows/generate/phase-6/remediation-handoff.md` menu MANDATORY).

If the user types a stop token (`stop` / `enough` / `done`) at any time, treat as `4`.
