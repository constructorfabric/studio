---
name: cf
aliases: [cf-studio, cf-init, cf-enable]
description: Invoke when user asks to choose a Constructor Studio workflow; resolves cf-* workflows and presents a companion-aware launch menu.
---

# cf / cf-studio — Constructor Studio Router

`cf` (and `cf-studio`) is a thin workflow router. It resolves available cf-*
workflows from core and installed kits, asks for intent when the request is
activation-only, matches workflows and companion groups, and presents a launch
menu. Workflow execution and workflow-specific rule loading happen outside this
root router.

```pdsl
UNIT SessionInit
PURPOSE: Establish cf/cf-studio as a thin router that only resolves workflows, captures intent when needed, and presents a launch menu.
WHEN:
  REQUIRE activation of cf OR activation of cf-studio
DO:
  RESOLVE {cf-studio-path} from the in-context `@cf:root-agents` rule (fallback: its block in the project-root `AGENTS.md`); never via {cfs_cmd}
  REQUIRE {cf-studio-path} is resolved before any LOAD below
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/runtime/workflow-resolution.md
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/routing/root-intent-routing.md
  RUN SkillInvocationArt
  RUN CommandResolution to resolve {cfs_cmd}
  EMIT a load report naming loaded router sources
  CONTINUE IntentRouting
RULES:
  ALWAYS treat cf and cf-studio as the same skill, where cf-studio is a proxy alias to cf
  ALWAYS limit cf/cf-studio to resolving available cf-* workflows, capturing unclear intent, matching workflows/companions, and presenting a launch menu
  ALWAYS run CommandResolution on every cf/cf-studio activation before routing
  NEVER invoke a selected workflow, run workflow-specific gates, ask sub-agent permission, run validators, or perform task work from this root router
  ALWAYS keep workflow-specific prerequisite loading inside the selected workflow rather than in this root router
  ALWAYS report the loaded router sources before routing
NOTES:
  This root intentionally does not load project AGENTS/config prompt packs or global conditional modules for every cf-* workflow. Concrete workflows load the prerequisite rules they need at the step where they need them.
```
