---
cf-studio: true
type: workflow
name: cf-sdlc-reverse-engineer
description: Invoke when the user intent is reconstructing SDLC artifacts (PRD/ADR/DESIGN/DECOMPOSITION/FEATURE) from existing code using code markers (@cpt-*) and the reverse-engineering methodology, without converting from another spec format.
version: 0.1.0
purpose: Phase-1 quick win — reconstruct SDLC artifacts from existing code, marker-first, by delegating authoring to the core cf-write-docs engine under the reverse-engineering methodology.
---

# cf-sdlc-reverse-engineer — code → artifacts

Reconstructs SDLC artifacts from existing code. It is marker-first: it extracts
`@cpt-*` markers from the code scope, then delegates artifact authoring to the
core `cf-write-docs` engine under the cf reverse-engineering methodology,
flagging `@cpt-gap`s where evidence is missing. This differs from
`cf-sdlc-migrate-openspec` (which converts from the OpenSpec format) — this
workflow reconstructs FROM CODE. It authors no content itself; it binds
evidence and delegates.

```pdsl
UNIT ReverseEngineer
PURPOSE: Extract code-marker evidence, then reconstruct the target artifacts via cf-write-docs under the reverse-engineering methodology, in the selected execution mode.
STATE:
  SET CODE_SCOPE: string (default unset, scope workflow_run)
  SET TARGET_ARTIFACT_KINDS: list (default FEATURE, scope workflow_run)
  SET MARKER_STRATEGY: marker-first | pattern-inference (default marker-first, scope workflow_run)
  SET EXEC_MODE: subagents | plan | plan-ralphex (default unset, scope workflow_run)
WHEN:
  REQUIRE the user intent is reconstructing SDLC artifacts from existing code
DO:
  LOAD {cf-studio-path}/.core/workflows/write-docs.md as the controlling authoring engine
  LOAD {cf-studio-path}/.core/requirements/reverse-engineering.md as the reconstruction methodology
  REQUIRE CODE_SCOPE is provided
  SET TARGET_ARTIFACT_KINDS = FEATURE WHEN the user did not specify target kinds
  SET MARKER_STRATEGY = marker-first WHEN the user did not specify a strategy
  RUN ReverseEngineerExtract
  EMIT_MENU ExecModeMenu WHEN EXEC_MODE == unset
  RUN ReverseEngineerSynthesize
RULES:
  ALWAYS resolve CODE_SCOPE, TARGET_ARTIFACT_KINDS, MARKER_STRATEGY, and EXEC_MODE before synthesizing artifacts
  ALWAYS bind the per-KIND artifact references (template, rules, checklist, example) and inject {cf-studio-path}/.core/requirements/reverse-engineering.md as the controlling reconstruction methodology into every cf-write-docs dispatch
  ALWAYS keep reconstruction marker-first; use pattern-inference only when MARKER_STRATEGY == pattern-inference or to fill a flagged gap
  ALWAYS write reconstructed artifacts under `docs/sdlc/{artifact_kind}/` with a Traceability section, never overriding cf-write-docs gates or verdicts
  NEVER convert from another spec format here — that is cf-sdlc-migrate-openspec's scope
MENU ExecModeMenu
TITLE: Choose how to execute the reconstruction (sub-agents is suggested).
OPTIONS:
  1 subagents -> SET EXEC_MODE = subagents; CONTINUE ReverseEngineerSynthesize
  2 plan -> SET EXEC_MODE = plan; CONTINUE ReverseEngineerSynthesize
  3 plan-ralphex -> SET EXEC_MODE = plan-ralphex; CONTINUE ReverseEngineerSynthesize
  INVALID -> EMIT_MENU ExecModeMenu
NOTES:
  subagents reconstructs directly via cf-write-docs author sub-agents; plan builds a cf-plan first then executes; plan-ralphex compiles a cf-plan then delegates execution to ralphex. The per-mode behavior is applied in ReverseEngineerSynthesize.
```

```pdsl
UNIT ReverseEngineerExtract
PURPOSE: Build the marker map from the code scope and flag evidence gaps before authoring.
WHEN:
  REQUIRE CODE_SCOPE and TARGET_ARTIFACT_KINDS are resolved
DO:
  RUN scan of CODE_SCOPE for `@cpt-*` markers and `cfs where-defined` to build a marker map of artifact_kind to its supporting markers with file:line locations
  RUN gap-flagging: emit an `@cpt-gap` flag for each target KIND whose marker count is below its configured minimum, with severity by KIND criticality (PRD/ADR gaps are errors; FEATURE/DESIGN gaps are warnings)
RULES:
  ALWAYS build the marker map before any authoring dispatch
  ALWAYS record file:line traceability evidence for every collected marker
  ALWAYS flag missing-evidence gaps explicitly rather than inventing unsupported content
```

```pdsl
UNIT ReverseEngineerSynthesize
PURPOSE: Reconstruct each target artifact via cf-write-docs and review it, honoring the chosen execution mode.
WHEN:
  REQUIRE the marker map is built AND EXEC_MODE is resolved
DO:
  RUN direct authoring WHEN EXEC_MODE == subagents: for each target artifact kind, dispatch cf-write-docs with the bound KIND references, the marker evidence, the gap flags, and the reverse-engineering methodology as controlling rules
  INVOKE skill `cf-plan` to build the reconstruction plan, then RUN the planned cf-write-docs authoring WHEN EXEC_MODE == plan
  INVOKE skill `cf-plan` to compile the reconstruction plan, then RUN `cfs delegate` to hand execution to ralphex WHEN EXEC_MODE == plan-ralphex
  RUN review delegated to cf-write-docs: its own deterministic gate (`cfs validate --artifact`) and its cf-semantic-reviewer-artifact pass against the KIND checklist
  RUN report-write of each artifact under `docs/sdlc/{artifact_kind}/`, including a Traceability section listing source_markers (file:line:type), gap_flags (missing types + severity), and a methodology_reference to {cf-studio-path}/.core/requirements/reverse-engineering.md
RULES:
  ALWAYS delegate all authoring and review to cf-write-docs; this workflow authors no content directly
  ALWAYS carry the marker evidence and gap flags into every author dispatch as read-only grounding
  ALWAYS embed the Traceability section in every reconstructed artifact so cfs where-defined/where-used can trace it back to code
  NEVER mark an error-severity gap as resolved without supporting evidence or an explicit pattern-inference note
```
