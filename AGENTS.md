<!-- @cf:root-agents -->
```toml
cf-studio-path = ".bootstrap"
```
<!-- /@cf:root-agents -->

## Shared Context Pack

Top-level Constructor Studio controllers own prompt-asset discovery and runtime
loading for this repository. Prompt-consuming sub-agents MUST receive the
instruction slices they need through `prompt_context_view` from the
session-scoped `SHARED_CONTEXT_PACK`; they MUST NOT reopen `SKILL.md`,
`workflows/**/*.md`, `requirements/**/*.md`, `AGENTS.md`, or kit prompt files
from disk.
