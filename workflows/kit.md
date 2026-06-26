---
cf: true
type: workflow
name: cf-kit
description: "Invoke when the user or another skill or workflow needs or asks to create or fix a Studio kit, initialize a kit folder, validate or edit .cf-studio-kit.toml, migrate a legacy manifest, normalize kit layout, or discover resources for a new kit."
version: 0.1
purpose: Initialize or revise a kit root into an exact canonical .cf-studio-kit.toml contract through explicit preview, approval, write, and validation gates.
---
# cf-kit
This workflow initializes a target kit folder into a canonical `.cf-studio-kit.toml` through explicit source routing, preview, approval, write, and validation gates.

```pdsl
UNIT KitInitBootstrap
PURPOSE: Load the runtime rules and verify kit CLI support before any kit work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-bootstrap-runtime.md
  RUN SkillInvocationArt
  RUN KitInitBootstrapLoadRuntime
  RUN KitInitBootstrapVerifyNormalize
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-entry-router.md
  CONTINUE KitInitBootstrapNormalizeUnavailable WHEN the normalize capability check fails
  CONTINUE KitInitEntry WHEN the normalize capability check passes
RULES:
  ALWAYS run StudioInstructionsMemoryGate before kit target routing, preflight, discovery, or writes
  ALWAYS remember git-commit-mode so any later commit request in this active workflow session runs GitCommitModeGate before routing, writes, git use, or delegation
  ALWAYS load command-resolution before invoking `{cfs_cmd}` kit commands
  ALWAYS load template-vars before resolving kit resource paths or unknown template variables
  ALWAYS load context-memory before storing or consuming kit discovery resource_context
  ALWAYS verify the kit normalize command surface before previewing, writing, or validating a kit manifest
  NEVER require cf or CFS_INIT before kit; this workflow owns its prerequisite loads
```

```pdsl
UNIT KitInitEntry
PURPOSE: Load the entry router and hand off into the current cf-kit session branch.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-entry-router.md
  CONTINUE KitInitEntryRoute
```

```pdsl
UNIT KitInitPreflight
PURPOSE: Load the preflight branch before validating and routing the target directory.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-target-preflight-route.md
  CONTINUE KitInitPreflightRun
```

```pdsl
UNIT KitInitDiscoveryRun
PURPOSE: Load the discovery branch before invoking read-only candidate discovery.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-run.md
  CONTINUE KitInitDiscoveryRunStart
```

```pdsl
UNIT KitInitDiscoveryProposal
PURPOSE: Load the discovery proposal modules before synthesizing a canonical manifest preview.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-generated-name-preview.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-classify.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-synthesize.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-discovery-proposal.md
  CONTINUE KitInitDiscoveryProposalRun
```

```pdsl
UNIT KitInitValidateWrittenManifest
PURPOSE: Load the post-write validation branch before reporting deterministic status.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-target-validation.md
  CONTINUE KitInitValidateWrittenManifestRun
```

## Canonical Manifest Contract

The workflow MUST treat `.cf-studio-kit.toml` as the only canonical authoring format for new kits.

Required top-level shape:

```toml
manifest_version = "1.0"

[[kits]]
slug = "..."
name = "..."
version = "..."
```

Canonical manifest rules:

- The file MUST start with `manifest_version = "1.0"`.
- The file MUST use `[[kits]]` with nested `[[kits.resources]]`.
- Kit slugs MUST be unique within the file.
- `core.toml` is installed state only; it is never source truth for authored manifest content.
- The workflow MUST NOT invent or emit author-facing `binding_path`.
- The workflow MUST NOT invent or emit `[kits.<slug>.content_identity]` or `[kits.<slug>.resource_hashes]`.
- The workflow MUST NOT invent or emit author-facing `generated_name`.

Each `[[kits.resources]]` entry:

- Required fields: `id`, `kind`, `source`
- Public kinds (`skill`, `agent`, `rule`) also require `name`; supporting kinds may omit it
- Optional fields: `install_path`, `type`, `public`, `description`, `user_modifiable`, `aliases`, `generated_targets`, `origin`
- Optional nested config: `[kits.resources.agent]`, `[kits.resources.permissions]`, `[kits.resources.targets.<target>]`

Kinds:

- Public kinds: `skill`, `agent`, `rule`
- Supporting kinds: `template`, `checklist`, `constraints`, `script`, `directory`, `other`
- Legacy alias `workflow` MAY be normalized to `skill`, but the workflow MUST author new canonical manifests as `kind = "skill"`

Agent-capable resource fields:

- `mode`
- `isolation`
- `model`
- `tools`
- `disallowed_tools`
- `skills`
- `color`
- `memory_dir`
- `role`
- `target`
- `provider`
- `reasoning_effort`
- `context_window`
- `subagents`

Nested subagents:

- Nested subagents live under `[[kits.resources.agent.subagents]]`.
- Their naming semantics MUST mirror `agents.toml`.
- There is no separate `name` field for a subagent.
- The subagent public name source is `subagents[].id`, analogous to the `[agents.<name>]` section key in `agents.toml`.
- `subagents[].source` or `prompt_file` points to the prompt file.

Public naming rules:

- Public `skill`, `agent`, and `rule` resources derive their public generated name only from source frontmatter `name`.
- `resource.id` MUST NOT be used as the public generated name for top-level public resources.
- `prefix_generated_name = false` publishes that top-level public resource name as-is.
- Otherwise the workflow MUST apply `cf-` or `cf-<kit-slug>-` without double-prefixing.
- Nested subagents derive their public generated name from `subagents[].id`.
- `prefix_generated_name = false` publishes that subagent id as-is.
- Otherwise the workflow MUST apply `cf-` or `cf-<kit-slug>-` without double-prefixing.

Resource path rules:

- `source` is always author-facing and relative to kit root.
- `install_path` is the default effective destination for copy-mode installs.
- In `register` mode, the runtime derives effective resource paths from manifest `source` plus the registered manifest root.
- In `register` mode, per-resource bindings MUST NOT be persisted in `core.toml`.
- In `copy` mode, effective bindings are persisted in `core.toml`.

Validation rules:

- `type` MUST be `file` or `directory`.
- `public = true` is valid only for `skill`, `agent`, and `rule`.
- `prefix_generated_name = false` is valid only for public resources or nested subagents.
- `generated_targets` is valid only for public resources or nested subagents.
- `artifacts.<ARTIFACT_KIND>` bindings are valid only for `kind = "constraints"`.

Variable and info rules:

- Resource identifiers are still the source of template variables such as `{resource_id}`.
- In `register` mode, variable resolution MUST come from the canonical manifest plus the registered manifest root.
- `cfs info` and `cfs resolve-vars` MUST reason per kit, not as one merged variable blob.

Authoring discipline:

- The workflow MUST prefer exact existing semantics over inferred convenience.
- If the observed kit layout conflicts with canonical manifest rules, the workflow MUST normalize the layout into the manifest instead of weakening the manifest contract.
