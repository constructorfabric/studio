---
name: cf
aliases: [cf-studio]
description: "Invoke for requests to create, edit, fix, update, implement, refactor, set up, build, analyze, validate, review, check, inspect, audit, compare, explain, walk through, teach, onboard, brainstorm, ideate, explore options, discover requirements, mapping, map dependencies, plan, decompose, find context, PDSL prompt work, configure projects, auto-config, scan brownfield projects, manage workspaces, delegation, delegate work, phase compile/execute, compile phases, execute phases, migration, migrate from Cypilot, migrate OpenSpec, review PRs, report PR status, or get help."
---

# Constructor Studio Unified Tool

```pdsl
UNIT CfSkillInit
PURPOSE: Activate cf skill and delegate runtime rules to canonical protocol files.
DO:
  - SET {cfs_mode} = on
  - LOAD {cf-studio-path}/.core/skills/studio/protocol.md
  - LOAD {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md
  - LOAD {cf-studio-path}/.core/skills/studio/routing.md
  - LOAD {cf-studio-path}/.core/requirements/pdsl-execution-card.md
  - CONTINUE Bootstrap
RULES:
  - ALWAYS SET {cfs_mode} = on before any other action
  - ALWAYS {cf-studio-path}/.core/skills/studio/protocol.md owns Bootstrap, HardRules, WorkflowProtocolNonSubstitution,
    NormativeKeywords, PhaseSkipGate, SharedContextPackAuthority, and
    CompletionInvariants
  - ALWAYS {cf-studio-path}/.core/skills/studio/sub-agent-dispatch.md owns SubAgentDefaultPolicy,
    SubAgentApprovalGate, ChangeReviewFailClosedSentinel, and
    InstructionFileAuthoringBoundary
  - ALWAYS {cf-studio-path}/.core/skills/studio/routing.md owns Constructor Studio request routing
```
