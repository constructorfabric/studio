---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the project is BROWNFIELD (existing code present) and the reverse-engineering / auto-config gate must be evaluated before Phase 0.
---

## Reverse Engineering Prerequisite (BROWNFIELD only)

```pdsl
UNIT ReverseEngineeringPrerequisite

PURPOSE:
  Evaluate auto-config / storytelling-package gates for BROWNFIELD projects
  before Phase 0.

DO:
  - REQUIRE AUTO_CONFIG == true:
    - CONTINUE AutoConfigFastPath

  - REQUIRE project is GREENFIELD:
    SKIP this section
    PROCEED to Phase 0
    - RETURN

  - RUN # BROWNFIELD path:
  - REQUIRE project is BROWNFIELD:
    USE Protocol Guard's matched WHEN-clause spec resolution for current request
    TREAT ONLY task-matched, applicable project specs/rules as satisfying
      the brownfield rules gate

    IF one or more project-specific specs/rules matched for current request:
      - LOAD and follow them before generating

    IF no project-specific specs/rules matched for current brownfield request:
      OFFER auto-config even when unrelated files exist under
        {cf-studio-path}/config/rules/ or unrelated specs are registered

RULES:
  - ALWAYS SKIP this section WHEN GREENFIELD — nothing to reverse-engineer
  - NEVER treat mere on-disk rules-file presence or any unrelated registered spec
    as sufficient to skip auto-config
  - ALWAYS open and follow {cf-studio-path}/.core/requirements/auto-config.md
    WHEN user accepts auto-config

MENU BrownfieldAutoConfigOffer:
  TITLE: Brownfield project detected — existing code found but no task-matched,
    applicable project-specific specs/rules were found for this request.
    Auto-config can scan your project and generate rules that teach Constructor Studio
    your conventions. This produces config/rules/, heading-level WHEN rules in
    config/AGENTS.md, navigation rules for existing project guides, and system entries
    in config/artifacts.toml.
  OPTIONS:
    1 yes ->
      NOTE: Suggested for first-time setup; run auto-config now, then return to
            generation with task-matched project rules.
      EXECUTE auto-config methodology (Phases 1→6)
      RETURN to generate
      CONTINUE {cf-studio-path}/.core/workflows/generate/phase-0-dependencies.md
    no ->
      CANCEL the generate workflow
    skip ->
      PROCEED without task-matched project-specific specs/rules
        (reduced quality for this run)
      CONTINUE {cf-studio-path}/.core/workflows/generate/phase-0-dependencies.md
  INVALID:
    EMIT "Reply with yes, no, or skip."
    WAIT user.reply
    STOP_TURN

UNIT AutoConfigFastPath

PURPOSE:
  Define AUTO_CONFIG fast path behavior when invoked via Invoke skill `cf-auto-config`.

WHEN:
  - REQUIRE AUTO_CONFIG == true (set by Invoke skill `cf-auto-config` thin entry point at {cf-studio-path}/.core/workflows/auto-config.md)

DO:
  - RUN TREAT this branch as higher precedence than normal generate update/refactor
    routing and higher precedence than any `{cfs_cmd} --json info` notice that
    suggests `cfs update`.
  - NEVER satisfying AUTO_CONFIG by running `cfs update`, `make update`,
    bootstrap refresh, kit refresh, cache refresh, or generated-agent refresh
    unless the user explicitly switches from auto-config to those commands.
  - RUN SKIP the yes/no/skip offer prompt above
  - RUN auto-config methodology ({cf-studio-path}/.core/requirements/auto-config.md)
    Phases 1→6 directly
  - RUN AFTER Phase 6 completes:
    - RETURN to generate ONLY if user explicitly asks to continue
    OTHERWISE stop after auto-config
  - RUN NOTE: thin entry point's terminal state is auto-config completion, not generation

UNIT StorytellingPackageGate

PURPOSE:
  Trigger storytelling methodology for explanatory/educational/presentation
  package write-to-disk requests.

WHEN:
  - REQUIRE user requests explanatory/educational/presentation/guide/README/training-material
  - REQUIRE PACKAGE to be written to disk
  - REQUIRE (intent like: "generate guide for X", "make a README from X",
   "export explain package", "create training material from X",
   "build onboarding doc set for X", "write a how-to package about X",
   or equivalents in any user language)

DO:
  - RUN ALWAYS open and follow {cf-studio-path}/.core/requirements/storytelling.md
  - SET EXPLAIN_MODE = true
  - SET EXPLAIN_EXPORT = true
  - RUN NOTE: storytelling methodology handles plan + portion construction
  - RUN NOTE: package is written under
    {cf-studio-path}/.cache/explain/packages/{slug}-{ISO-timestamp}/
  - RUN NOTE: standard generate.md write-permission gates apply
    (user confirmation before writing files; NEVER add --yes/-y to
     write-capable commands unless user explicitly requested non-interactive)
  - RUN NOTE: hybrid execution from storytelling.md Export Mode:
    Phases E0/E1 (pre-flight, role/audience confirmation, plan approval) remain interactive
    Portion construction runs in batch after plan approval and writes files directly
    (no per-portion chat navigation prompts)
```
