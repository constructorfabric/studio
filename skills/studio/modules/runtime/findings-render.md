# Findings Render

```pdsl
UNIT FindingsRenderContract
PURPOSE: Shape review or analysis findings into a canonical report artifact and result-envelope payload.
STATE:
  SET FINDINGS_REPORT_TYPE: review-findings | ci-findings | other | unset (default unset, scope unit_run)
  SET FINDINGS_RESULT_STATUS: completed | failed | blocked | unset (default unset, scope unit_run)
  SET FINDINGS: list | unset (default unset, scope unit_run)
  SET FINDINGS_REPORT_REF: ref | unset (default unset, scope unit_run)
  SET FINDINGS_REPORT: object | unset (default unset, scope unit_run)
  SET report_outputs: list | unset (default unset, scope unit_run)
WHEN:
  REQUIRE FINDINGS_REPORT_TYPE != unset
  REQUIRE FINDINGS_RESULT_STATUS != unset
  REQUIRE FINDINGS is provided
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md WHEN ThinSkillRuntimeContracts is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/review/finding-contract.md WHEN ReviewFindingContract is not yet loaded
  RUN ThinSkillRuntimeContracts
  RUN ArtifactContractLoad
  RUN FindingsRenderInputContract
  RUN FindingsRenderReportContract
  RUN FindingsRenderOutputContract
RULES:
  ALWAYS use this module only after findings were already collected or aggregated
  ALWAYS keep browser, pagination, and fix-approval UX outside this module
  NEVER let rendering choose reviewers, rerun analysis, or rewrite findings content
```

```pdsl
UNIT FindingsRenderInputContract
PURPOSE: Validate the accepted rendering inputs.
RULES:
  ALWAYS allow FINDINGS_REPORT_TYPE values review-findings, ci-findings, or other only
  ALWAYS require FINDINGS_RESULT_STATUS to use canonical top-level statuses and reject completed-with-assumptions for findings rendering
  ALWAYS require every review-findings entry to satisfy ReviewFindingContract
  ALWAYS allow ci-findings or other findings to reuse ReviewFindingContract when the caller normalized them to that shape
  ALWAYS allow FINDINGS to be an empty list when the caller is rendering a zero-findings report
  NEVER treat a non-empty findings list as an automatic failed status; the caller chooses the top-level result status
```

```pdsl
UNIT FindingsRenderReportContract
PURPOSE: Produce the canonical findings report object.
DO:
  SET FINDINGS_REPORT = object containing report_type, ref, summary, findings, total_count, and severity_counts
RULES:
  ALWAYS set report_type = FINDINGS_REPORT_TYPE
  ALWAYS set ref = FINDINGS_REPORT_REF when one was supplied, otherwise keep ref empty or caller-derived
  ALWAYS compute severity_counts for CRITICAL, MAJOR, and MINOR when findings use ReviewFindingContract severities
  ALWAYS keep summary short and deterministic with respect to report_type and counts, including the zero-findings case
  NEVER drop the underlying findings list from FINDINGS_REPORT merely because a top-level result envelope also references the report
```

```pdsl
UNIT FindingsRenderOutputContract
PURPOSE: Produce the canonical report_outputs entry for the top-level result envelope.
DO:
  SET report_outputs = report_outputs plus one entry with report_type = FINDINGS_REPORT.report_type, ref = FINDINGS_REPORT.ref, and summary = FINDINGS_REPORT.summary WHEN report_outputs != unset
  SET report_outputs = one entry with report_type = FINDINGS_REPORT.report_type, ref = FINDINGS_REPORT.ref, and summary = FINDINGS_REPORT.summary WHEN report_outputs == unset
RULES:
  ALWAYS keep findings in report_outputs rather than produced_artifacts
  ALWAYS emit report_outputs as a list, even when there is exactly one findings report
  ALWAYS preserve any caller-supplied non-findings report_outputs entries when appending the findings report output
  NEVER overwrite an existing deterministic-report output while adding findings output
  NEVER require this module to own produced_artifacts or missing_artifacts population
```
