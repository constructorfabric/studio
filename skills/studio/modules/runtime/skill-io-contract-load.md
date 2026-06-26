# Skill IO Contract Load

```pdsl
UNIT SkillIoContractLoad
PURPOSE: Bridge shared bootstrap/runtime contracts into the thin-skill IO contract modules.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md WHEN ThinSkillRuntimeContracts is not yet loaded
  RUN ThinSkillRuntimeContracts
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/artifact-contract-load.md WHEN ArtifactContractLoad is not yet loaded
  RUN ArtifactContractLoad
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/prerequisite-check.md WHEN PrerequisiteCheckContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md WHEN BlockedReportContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-next-actions.md WHEN BlockedNextActionsContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/assumption-override.md WHEN AssumptionOverrideContract is not yet loaded
RULES:
  ALWAYS use this bridge after shared bootstrap/runtime contract load and before skill-local prerequisite, blocked, override, report, or result logic
  ALWAYS reuse ThinSkillRuntimeContracts as the canonical status and envelope source
  ALWAYS load artifact, prerequisite, blocked-report, and assumption-override modules through this bridge instead of duplicating bootstrap semantics inside a thin skill
  NEVER treat this bridge as permission to run producer skills, artifact-specific authoring, or workflow-specific orchestration
```

```pdsl
UNIT SkillIoPrerequisiteContractLoad
PURPOSE: Load the shared prerequisite-side IO modules without invoking workflow behavior.
DO:
  RUN SkillIoContractLoad
  RUN ArtifactRegistryContract
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/prerequisite-check.md WHEN PrerequisiteCheckContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-report.md WHEN BlockedReportContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/blocked-next-actions.md WHEN BlockedNextActionsContract is not yet loaded
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/assumption-override.md WHEN AssumptionOverrideContract is not yet loaded
RULES:
  ALWAYS use this unit before a thin skill evaluates required artifacts or renders a blocked envelope
  NEVER duplicate artifact registry or blocked-envelope rules inside a skill-local prerequisite declaration
```
