---
cf-studio: true
type: workflow
name: cf-sdlc-change-impact-analysis
description: Invoke when the user intent is analyzing the impact of an upstream artifact change (PRD/ADR/DESIGN/DECOMPOSITION/FEATURE) on downstream artifacts and code.
version: 0.1.0
purpose: Phase-1 dependency foundation — trace an upstream artifact change to downstream affected artifacts and code, in cascade-tracking or release-readiness-estimation mode.
---

# cf-sdlc-change-impact-analysis — change impact analysis

Read-only analysis workflow. Given an upstream artifact change, it traces the
downstream blast radius across the pipeline (PRD → ADR + DESIGN → DECOMPOSITION
→ FEATURE → CODE) and reports affected artifacts, coverage gaps, and stale
markers. It composes the core `cf-analyze` engine with deterministic `cfs`
traceability commands as cached internal sub-steps, and writes no artifact
content — only a report. It produces the impact data the Phase-2
`cf-sdlc-release-readiness-gate` consumes.

```pdsl
UNIT ChangeImpactAnalysis
PURPOSE: Resolve inputs and run the impact analysis in the selected mode, then emit a read-only report.
STATE:
  SET MODE: cascade-tracking | release-readiness-estimation (default unset, scope workflow_run)
  SET UPSTREAM_ARTIFACT_TYPE: PRD | ADR | DESIGN | DECOMPOSITION | FEATURE (default unset, scope workflow_run)
  SET UPSTREAM_ARTIFACT_ID: string (default unset, scope workflow_run)
  SET BASELINE_REF: string (default origin/main-or-prior-tag, scope workflow_run)
  SET CURRENT_REF: string (default HEAD, scope workflow_run)
WHEN:
  REQUIRE the user intent is analyzing the downstream impact of an upstream artifact change
DO:
  LOAD {cf-studio-path}/.core/workflows/analyze.md as the controlling analysis engine
  LOAD {change_impact_config} as the kit-owned thresholds (stale_flag_threshold, impact severity levels, cascade depth per artifact type, marker coverage threshold)
  REQUIRE UPSTREAM_ARTIFACT_TYPE and UPSTREAM_ARTIFACT_ID are provided
  SET BASELINE_REF = origin/main or the prior release tag WHEN the user did not provide a baseline
  SET CURRENT_REF = HEAD WHEN the user did not provide a current ref
  EMIT_MENU ModeMenu WHEN MODE == unset
  RUN ChangeImpactSubsteps
  RUN report-render: aggregate the sub-step results and format them into `.change-impact/{UPSTREAM_ARTIFACT_ID}/report.md` with sections Summary, Cascade tree, Coverage gaps, Stale flags, Traceability evidence
  EMIT the report path and a short findings summary
RULES:
  ALWAYS resolve MODE, UPSTREAM_ARTIFACT_TYPE, UPSTREAM_ARTIFACT_ID, BASELINE_REF, and CURRENT_REF before running the sub-steps
  ALWAYS read every threshold from {change_impact_config}, never hard-code thresholds in this workflow
  ALWAYS keep this workflow read-only — write only the report under `.change-impact/`, never edit artifacts or code
  ALWAYS write the report under a dedicated `.change-impact/` namespace, never under `.prs/`
  NEVER block a merge from this workflow; it reports impact, it does not gate
MENU ModeMenu
TITLE: Choose the analysis mode — cascade-tracking flags affected/stale artifacts; release-readiness-estimation scores impact and recommends a version bump.
OPTIONS:
  1 cascade-tracking -> SET MODE = cascade-tracking; CONTINUE ChangeImpactSubsteps
  2 release-readiness-estimation -> SET MODE = release-readiness-estimation; CONTINUE ChangeImpactSubsteps
  INVALID -> EMIT_MENU ModeMenu
```

```pdsl
UNIT ChangeImpactSubsteps
PURPOSE: Run the cached internal sub-steps in order — analyze the change, trace dependents, measure coverage — feeding the report.
WHEN:
  REQUIRE MODE, UPSTREAM_ARTIFACT_TYPE, UPSTREAM_ARTIFACT_ID, BASELINE_REF, and CURRENT_REF are resolved
DO:
  RUN diff-analyze: dispatch the cf-analyze engine over the upstream artifact between BASELINE_REF and CURRENT_REF to characterize the change
  RUN dependents-trace: `cfs where-used --id <changed ids>` plus `{constraints}` cross-reference rules to collect downstream artifacts and `@cpt-*` code markers, bounded by the per-artifact-type cascade depth from {change_impact_config}
  RUN coverage-measure: `cfs spec-coverage` over the affected downstream set to quantify marker coverage against the configured threshold
  RUN stale-detect: flag downstream markers whose source was not updated within stale_flag_threshold relative to the change, as stale flags with severity
  RUN aggregation of diff-analyze, dependents-trace, coverage-measure, and stale-detect into one impact result for the report
RULES:
  ALWAYS run the sub-steps in order: diff-analyze, then dependents-trace, then coverage-measure, then stale-detect
  ALWAYS cache each sub-step by the key UPSTREAM_ARTIFACT_ID + BASELINE_REF + CURRENT_REF + MODE, and invalidate a cache entry when the upstream artifact's modification time changes
  ALWAYS include, for every affected artifact and marker, its file:line traceability evidence in the result
  ALWAYS, in release-readiness-estimation mode, derive a recommended version bump from impact severity using the version-semantics policy owned by cf-sdlc-release-readiness-gate
  NEVER expose these sub-steps as new cfs commands; keep them internal to this workflow
NOTES:
  This workflow is the Phase-1 dependency foundation; its aggregated impact result (cascade tree, coverage gaps, stale flags) is consumed by cf-sdlc-release-readiness-gate in Phase-2.
```
