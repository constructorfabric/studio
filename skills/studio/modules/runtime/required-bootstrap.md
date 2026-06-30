# Required Bootstrap

Use this module when a generated skill or workflow shim must load the minimum
shared Constructor Studio runtime before handing control to its target
protocol.

```pdsl
UNIT RequiredBootstrap
PURPOSE: Load the mandatory core runtime modules before any generated target skill or workflow executes.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN PdslExecutionSemantics
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/thin-skill-contracts.md
  RUN ThinSkillRuntimeContracts
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  RUN CommandResolution to resolve {cfs_cmd}
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  RUN ContentMemory
  RUN ResourceContextMemory
RULES:
  ALWAYS run this bootstrap before loading or executing a generated target skill/workflow
  ALWAYS load and execute PDSL semantics before interpreting downstream PDSL blocks
  ALWAYS load the thin-skill runtime contracts before downstream skill-local
  prerequisite or result-envelope logic executes
  ALWAYS treat this bootstrap as the minimum contract load for kit-owned thin
  skills and generated shims, not only Studio-owned entrypoints
  ALWAYS load Studio instruction memory so rules from `{cf-studio-path}/.gen` and `{cf-studio-path}/config` are remembered before target work begins
  ALWAYS resolve `{cfs_cmd}` before any downstream unit may invoke a Constructor Studio CLI command
  ALWAYS keep template-vars and context-memory loaded so downstream protocols can resolve variables and classify remembered context deterministically
  ALWAYS activate ContentMemory so downstream content payloads inherit the runtime lifecycle rules from bootstrap
  ALWAYS activate ResourceContextMemory so downstream workflows can safely store and forward resource_context without reintroducing bootstrap gaps
  ALWAYS treat this bootstrap as exclusively for generated shims and thin skills that bypass workflow-bootstrap; NEVER load required-bootstrap in a flow that has already run WorkflowBootstrapRouterPrelude unless ContentMemory and ResourceContextMemory are idempotent on re-activation
  NEVER allow a generated shim to interpret skill-local blocked, override, or
  result-envelope behavior before ThinSkillRuntimeContracts has executed
```
