---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: Invoke when the project is BROWNFIELD (existing code present) and the reverse-engineering / auto-config gate must be evaluated before Phase 0.
---

## Reverse Engineering Prerequisite (BROWNFIELD only)

`GREENFIELD`: skip this section and proceed to Phase 0. `BROWNFIELD`: reverse-engineering may inform generated artifacts, code implementation, and code edits. ALWAYS SKIP this section WHEN GREENFIELD — nothing to reverse-engineer.

For BROWNFIELD work:
- Use Protocol Guard's matched WHEN-clause spec resolution for the current request; treat only task-matched, applicable project specs/rules as satisfying the brownfield rules gate.
- If one or more project-specific specs/rules are matched for the current request, load and follow them before generating.
- If no project-specific specs/rules are matched for the current brownfield request, offer auto-config even when unrelated files exist under `{cf-studio-path}/config/rules/` or unrelated specs are registered.
- MUST NOT treat mere on-disk rules-file presence or any unrelated registered spec as sufficient to skip auto-config.
- ALWAYS open and follow `{cf-studio-path}/.core/requirements/auto-config.md` WHEN user accepts auto-config.

```text
Brownfield project detected — existing code found but no task-matched, applicable project-specific specs/rules were found for this request.
Auto-config can scan your project and generate rules that teach Constructor Studio your conventions.
This produces config/rules/, heading-level WHEN rules in config/AGENTS.md, navigation rules for existing project guides, and system entries in config/artifacts.toml.

→ Run auto-config now? [yes/no/skip]
Reply with `yes`, `no`, or `skip`.
"yes"  → Suggested for first-time setup; run auto-config now, then return to generation with task-matched project rules.
"no"   → Cancel generation now.
"skip" → Continue without task-matched project specs/rules (reduced quality for this run).
```

If user confirms `yes`: execute auto-config methodology (Phases 1→6), then return to generate and proceed to `workflows/generate/phase-0-dependencies.md`. If user says `skip`: proceed without task-matched project-specific specs/rules and continue to `workflows/generate/phase-0-dependencies.md`. If user says `no`: cancel the generate workflow.

ALWAYS open and follow `{cf-studio-path}/.core/requirements/storytelling.md` WHEN user requests an explanatory / educational / presentation / guide / README / training-material **package** to be written to disk (intent like `generate guide for X`, `make a README from X`, `export explain package`, `create training material from X`, `build onboarding doc set for X`, `write a how-to package about X`, or equivalents in any user language). WHEN this rule triggers, set BOTH `EXPLAIN_MODE=true` AND `EXPLAIN_EXPORT=true`; the storytelling methodology handles plan + portion construction; the package is written under `{cf-studio-path}/.cache/explain/packages/{slug}-{ISO-timestamp}/`. Standard `generate.md` write-permission gates apply (user confirmation before writing files; do NOT add `--yes`/`-y` to write-capable commands unless the user explicitly requested non-interactive behavior). The hybrid execution from `storytelling.md` Export Mode applies: Phases E0/E1 (pre-flight, role/audience confirmation, plan approval) remain interactive; portion construction runs in batch after plan approval and writes files directly (no per-portion chat navigation prompts).
