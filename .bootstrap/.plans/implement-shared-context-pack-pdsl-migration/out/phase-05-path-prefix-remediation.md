# Phase 05 Path Prefix And Direct-Load Remediation

## Applied Remediations

| File | Previous pattern | Remediation |
| --- | --- | --- |
| `requirements/storytelling.md` | Root-relative shared block reference to `requirements/storytelling-shared.md`. | Replaced with the runtime prompt path `{cf-studio-path}/.core/requirements/storytelling-shared.md` and documented that the dispatching controller publishes the needed prompt text through `prompt_context_view`. |
| `requirements/storytelling.md` | Module-loading behavior was described without explicit runtime prompt-path normalization. | Added router-contract units that name `{cf-studio-path}/.core/requirements/storytelling-{phases,modes,preferences,export}.md` as the controller-owned prompt assets for the storytelling router. |
| `architecture/specs/sysprompts.md` | Loading algorithm ended with direct per-agent injection semantics. | Updated the algorithm so matching project sysprompts are published into `SHARED_CONTEXT_PACK`, then delivered to prompt-consuming sub-agents via `prompt_context_view`. |
| `architecture/specs/shared-context-pack.md` | Controller/consumer boundaries were still mostly prose-first. | Added explicit PDSL controller/consumer contracts that formalize fail-closed behavior when prompt context is missing or stale, eliminating any ambiguity about direct-read fallback. |

## Valid Exceptions Left In Place

- `architecture/specs/sysprompts.md` keeps relative `sysprompts/*.md` examples inside the `config/AGENTS.md` example block. This remains valid because the project-level navigation file is itself a controller-owned prompt surface rooted at `{cf-studio-path}/config/`.
- `requirements/auto-config.md` and `requirements/reverse-engineering.md` continue to reference `{cf-studio-path}/.core/requirements/...` controller prompt assets directly. These are controller methodologies, not prompt-consuming sub-agent contracts.
- `architecture/specs/artifacts-registry.md` retains the `Add to config AGENTS.md` example because it documents the controller-facing navigation rule for `artifacts.toml` work rather than telling a prompt-consuming sub-agent to self-bootstrap from disk.

## No-Change Findings

- No migrated file required a remaining direct read of `SKILL.md`, `workflows/*.md`, `requirements/*.md`, `AGENTS.md`, or kit prompt assets by a prompt-consuming sub-agent.
- No additional `{cf-studio-path}` normalization was required for the other migrated files because their controller-owned prompt references were already runtime-prefixed or were intentionally relative within a controller-owned `config/AGENTS.md` example.
