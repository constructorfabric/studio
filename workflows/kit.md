---
cf: true
type: workflow
name: cf-kit
description: "Invoke when user intent is initializing a kit folder, creating or validating .cf-studio-kit.toml, converting legacy manifest.toml, normalizing conf.toml + layout, or discovering resources for a new kit manifest."
version: 0.1
purpose: Initialize a kit root into a canonical .cf-studio-kit.toml through explicit preview, approval, write, and validation gates.
---

# cf-kit

This workflow initializes a target kit folder into a canonical `.cf-studio-kit.toml`. It resolves the target folder first, then applies init-time source precedence for that folder: keep an existing canonical manifest read-only, convert a legacy `manifest.toml` through `cfs kit normalize`, or discover candidate resources through `cf-explore`, propose a conservative manifest, gate all writes on user approval, then validate the written manifest through dry-run normalization.

Executor contract: the controller owns filesystem writes, exact-byte preview checks, CLI invocations, and state checkpoints across turns. `cf-explore` owns read-only discovery and returns resource_context; this workflow consumes only resource paths, short summaries, suggested resource kinds, evidence, and missing-context questions from that context.

```pdsl
UNIT KitInitBootstrap
PURPOSE: Load the runtime rules and verify kit CLI support before any kit work.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/skill-invocation-art.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/pdsl-execution-card.md
  RUN SkillInvocationArt
  RUN KitInitBootstrapLoadRuntime
  RUN KitInitBootstrapVerifyNormalize
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
UNIT KitInitBootstrapLoadRuntime
PURPOSE: Load the kit runtime support modules before any target routing or CLI work.
DO:
  LOAD and REMEMBER rules from {cf-studio-path}/.core/skills/studio/modules/subagents/git-commit-mode.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/studio-instructions-memory.md
  RUN StudioInstructionsMemoryGate
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/template-vars.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/context-memory.md
  RUN CommandResolution to resolve {cfs_cmd}
```

```pdsl
UNIT KitInitBootstrapVerifyNormalize
PURPOSE: Verify that the kit normalize command surface is available.
DO:
  RUN verify `{cfs_cmd} kit normalize --help` supports `--from`, `--output`, `--dry-run`, and `--stdout`
```

```pdsl
UNIT KitInitBootstrapNormalizeUnavailable
PURPOSE: Stop early when the required kit normalize capability is unavailable.
DO:
  EMIT "Required kit normalization command is unavailable; update Constructor Studio, then retry cf-kit."
  STOP_TURN
```

```pdsl
UNIT KitInitEntry
PURPOSE: Capture the target folder from the user request or ask for it before any discovery or write logic.
STATE:
  SET ORIGINAL_INTENT: string (default unset, scope workflow_run)
  SET TARGET_DIR: string (default unset, scope workflow_run)
  SET CANONICAL_MANIFEST: string (default unset, scope workflow_run)
  SET LEGACY_MANIFEST: string (default unset, scope workflow_run)
  SET LEGACY_CONF: string (default unset, scope workflow_run)
  SET TARGET_SOURCE: unset | canonical | legacy_manifest | legacy_layout | discovery (default unset, scope workflow_run)
  SET NORMALIZE_SOURCE_HINT: unset | manifest | layout (default unset, scope workflow_run)
  SET RESOURCE_CONTEXT: unset | provided (default unset, scope workflow_run)
  SET DISCOVERY_STATUS: unset | provided | empty | error (default unset, scope workflow_run)
  SET PREVIEW_STATUS: unset | pass | fail | error (default unset, scope workflow_run)
  SET PENDING_EDIT_BRANCH: unset | legacy_manifest | discovery (default unset, scope workflow_run)
  SET PENDING_MANUAL_GUIDANCE: unset | true (default unset, scope workflow_run)
  SET CURRENT_PREVIEW_TOML: string (default unset, scope workflow_run)
  SET CURRENT_PREVIEW_REPORT: string (default unset, scope workflow_run)
  SET APPROVED_PREVIEW: string (default unset, scope workflow_run)
DO:
  SET ORIGINAL_INTENT = the user's triggering request (verbatim or shortest faithful summary)
  CONTINUE KitInitApplyUserEdits WHEN PENDING_EDIT_BRANCH != unset AND the user reply contains requested manifest edits
  CONTINUE KitInitManualGuidanceProposal WHEN PENDING_MANUAL_GUIDANCE == true AND the user reply contains manual resource guidance
  SET TARGET_DIR = the target folder path from the user request WHEN the request already names a concrete folder
  CONTINUE KitInitAskTarget WHEN TARGET_DIR == unset
  SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer WHEN TARGET_DIR != unset
RULES:
  ALWAYS capture the original intent before routing any cf-kit branch
  ALWAYS resolve the target folder before discovery, preview, validation, or write work
  NEVER guess a target folder from vague intent alone
```

```pdsl
UNIT KitInitAskTarget
PURPOSE: Ask for the target folder when the request did not provide one.
WHEN:
  REQUIRE TARGET_DIR == unset
DO:
  EMIT "[Kit Init]: I need the target folder before I can build or validate a kit manifest."
  EMIT_MENU KitInitTargetMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS let the user provide the folder path directly in free text
  NEVER continue to preflight while TARGET_DIR is still unset
MENU KitInitTargetMenu
TITLE: Which folder should become or be checked as a kit root? Reply with a number, or send the folder path directly.
OPTIONS:
  1 path:<folder> | path -> Reply `path: <folder>` or send the folder path alone, then SET TARGET_DIR, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer
  2 cancel -> STOP_TURN
  INVALID -> treat non-empty path-like free text as TARGET_DIR, SET PLAN_FIRST_CONTINUE = KitInitPreflight, SET CURRENT_WORKFLOW = cf-kit, SET COMPANION_CONTINUE = PlanFirstGate, LOAD {cf-studio-path}/.core/skills/studio/modules/routing/companion-skills.md, LOAD {cf-studio-path}/.core/skills/studio/modules/gates/plan-first.md, and CONTINUE CompanionSkillOffer; handle `cancel`, `help`, or non-path text by EMIT "Reply with `path: <folder>`, a path-like folder value, or 2 to cancel." and EMIT_MENU KitInitTargetMenu
```

```pdsl
UNIT KitInitPreflight
PURPOSE: Resolve the target folder, block invalid paths, and compute the relevant manifest paths.
WHEN:
  REQUIRE TARGET_DIR != unset
DO:
  RUN resolve TARGET_DIR to an absolute normalized path
  CONTINUE KitInitPreflightInvalidTarget WHEN the resolved path does not exist or is not a directory
  RUN KitInitPreflightSetManifestPaths
  CONTINUE KitInitRoute WHEN the resolved path exists and is a directory
RULES:
  ALWAYS block missing paths and non-directories before any preview or discovery work
  ALWAYS compute the canonical and legacy manifest paths from the resolved target folder
  NEVER attempt to discover or write resources outside a valid target directory
```

```pdsl
UNIT KitInitPreflightInvalidTarget
PURPOSE: Report an invalid target folder and wait for a replacement or cancel.
DO:
  EMIT "Target folder not found or not a directory: {TARGET_DIR}"
  EMIT_MENU KitInitTargetRetryMenu
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT KitInitPreflightSetManifestPaths
PURPOSE: Compute the canonical and legacy manifest paths from the resolved target folder.
DO:
  SET CANONICAL_MANIFEST = `<target>/.cf-studio-kit.toml`
  SET LEGACY_MANIFEST = `<target>/manifest.toml`
  SET LEGACY_CONF = `<target>/conf.toml`
MENU KitInitTargetRetryMenu
TITLE: The target path is missing or is not a directory. Reply with a number, or send another folder path directly.
OPTIONS:
  1 retry -> Reply with another folder path, then CONTINUE KitInitPreflight
  2 cancel -> STOP_TURN
  INVALID -> treat non-empty path-like free text as TARGET_DIR and CONTINUE KitInitPreflight; handle `cancel`, `help`, or non-path text by EMIT "Reply with `path: <folder>`, a path-like folder value, or 2 to cancel." and EMIT_MENU KitInitTargetRetryMenu
```

```pdsl
UNIT KitInitRoute
PURPOSE: Apply folder-init source precedence and route to the correct read-only or write-gated branch.
WHEN:
  REQUIRE TARGET_DIR != unset
DO:
  RUN KitInitRouteDetectSource
  RUN KitInitRouteSetNormalizeHint
  CONTINUE KitInitExistingManifestOffer WHEN TARGET_SOURCE == canonical
  CONTINUE KitInitLegacySourcePreview WHEN TARGET_SOURCE == legacy_manifest OR TARGET_SOURCE == legacy_layout
  CONTINUE KitInitDiscoveryRun WHEN TARGET_SOURCE == discovery
RULES:
  ALWAYS apply folder-init source precedence as `.cf-studio-kit.toml` > legacy `manifest.toml` > `conf.toml + layout` > discovery proposal
  ALWAYS keep an existing canonical manifest read-only
  NEVER route a folder with `manifest.toml` and no canonical manifest straight to discovery
  NEVER write `.cf-studio-kit.toml` before a clear approval menu resolves
```

```pdsl
UNIT KitInitRouteDetectSource
PURPOSE: Detect which init source branch applies to the target folder.
DO:
  SET TARGET_SOURCE = canonical WHEN CANONICAL_MANIFEST exists
  SET TARGET_SOURCE = legacy_manifest WHEN CANONICAL_MANIFEST does not exist AND LEGACY_MANIFEST exists
  SET TARGET_SOURCE = legacy_layout WHEN CANONICAL_MANIFEST does not exist AND LEGACY_MANIFEST does not exist AND (LEGACY_CONF exists OR recognized kit layout directories exist)
  SET TARGET_SOURCE = discovery WHEN CANONICAL_MANIFEST does not exist AND LEGACY_MANIFEST does not exist AND TARGET_SOURCE == unset
```

```pdsl
UNIT KitInitRouteSetNormalizeHint
PURPOSE: Set the legacy-source normalize hint after source detection.
DO:
  SET NORMALIZE_SOURCE_HINT = manifest WHEN TARGET_SOURCE == legacy_manifest
  SET NORMALIZE_SOURCE_HINT = layout WHEN TARGET_SOURCE == legacy_layout
```

```pdsl
UNIT KitInitExistingManifestOffer
PURPOSE: Avoid silent overwrite when a canonical manifest already exists in the target folder.
WHEN:
  REQUIRE TARGET_SOURCE == canonical
DO:
  EMIT "A canonical manifest already exists at <target>/.cf-studio-kit.toml."
  EMIT_MENU KitInitExistingManifestMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS offer read-only validation or cancel when the canonical manifest already exists
  NEVER overwrite an existing canonical manifest silently
MENU KitInitExistingManifestMenu
TITLE: `.cf-studio-kit.toml` already exists. What should happen?
OPTIONS:
  1 validate -> RUN `{cfs_cmd} kit normalize <target> --dry-run` to load and validate the current canonical manifest without writing; EMIT the validation report and manifest summary; STOP_TURN
  2 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-2." and EMIT_MENU KitInitExistingManifestMenu
```

```pdsl
UNIT KitInitLegacySourcePreview
PURPOSE: Convert a legacy manifest.toml or conf.toml + layout source into a canonical preview, then gate the write on approval.
WHEN:
  REQUIRE TARGET_SOURCE == legacy_manifest OR TARGET_SOURCE == legacy_layout
DO:
  RUN KitInitLegacySourcePreviewGenerate
  CONTINUE KitInitLegacySourcePreviewSuccess WHEN PREVIEW_STATUS == pass
  CONTINUE KitInitLegacySourcePreviewFailure WHEN PREVIEW_STATUS != pass
RULES:
  ALWAYS treat `<target>/manifest.toml` as the selected legacy input when it exists and `<target>/.cf-studio-kit.toml` does not
  ALWAYS treat `conf.toml + layout` as the selected legacy input when no canonical or legacy manifest exists and layout evidence exists
  ALWAYS preview the normalized canonical manifest before any write
  ALWAYS verify the normalized preview contains top-level `manifest_version = "1.0"`; never approve or write an unversioned manifest
  ALWAYS follow KitGeneratedNamePreviewContract before the approval menu renders any public generated-name preview
  NEVER write the canonical manifest before the approval menu resolves
```

```pdsl
UNIT KitInitLegacySourcePreviewGenerate
PURPOSE: Generate the legacy-source preview and classify its status.
DO:
  RUN `{cfs_cmd} kit normalize <target> --from <NORMALIZE_SOURCE_HINT> --dry-run` for validation findings, report, and public generated-name preview
  RUN `{cfs_cmd} kit normalize <target> --from <NORMALIZE_SOURCE_HINT> --stdout` for the exact proposed canonical `.cf-studio-kit.toml` bytes
  SET PREVIEW_STATUS = pass WHEN dry-run passes AND stdout returns valid TOML with top-level `manifest_version = "1.0"` before any `[[kits]]` table
  SET PREVIEW_STATUS = fail WHEN dry-run returns validation findings
  SET PREVIEW_STATUS = error WHEN dry-run cannot parse/load the legacy manifest, stdout cannot render the generated TOML, or stdout omits/changes `manifest_version`
  SET CURRENT_PREVIEW_TOML = the stdout canonical `.cf-studio-kit.toml` text WHEN PREVIEW_STATUS == pass
  SET CURRENT_PREVIEW_REPORT = the dry-run migration report WHEN PREVIEW_STATUS == pass
```

```pdsl
UNIT KitInitLegacySourcePreviewSuccess
PURPOSE: Render a successful legacy-source preview and wait for approval input.
DO:
  EMIT the migration report, public generated-name preview, and proposed canonical `.cf-studio-kit.toml`
  EMIT_MENU KitInitLegacyApprovalMenu
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT KitInitLegacySourcePreviewFailure
PURPOSE: Render a failed legacy-source preview and wait for retry or cancel.
DO:
  EMIT the normalization findings and blocking error details
  EMIT_MENU KitInitPreviewFailureMenu
  WAIT user.reply
  STOP_TURN
MENU KitInitLegacyApprovalMenu
TITLE: Approve the legacy-source conversion?
OPTIONS:
  1 approve-default -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifest
  2 show-preview -> EMIT CURRENT_PREVIEW_TOML in a fenced `toml` block; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitLegacyApprovalMenu; WAIT user.reply; STOP_TURN
  3 edit -> SET PENDING_EDIT_BRANCH = legacy_manifest; EMIT "Reply with edit commands such as `set metadata.name=<name>`, `set metadata.version=<semver>`, `remove resource id=<id>`, `set resource <id>.kind=<kind>`, `set resource <id>.install_path=<path>`, `set resource <id>.prefix_generated_name=false`, or `preserve field=<field>`."; WAIT user.reply; STOP_TURN
  4 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-4." and EMIT_MENU KitInitLegacyApprovalMenu
MENU KitInitPreviewFailureMenu
TITLE: The manifest preview could not be produced. Fix the source input and retry, or cancel.
OPTIONS:
  1 retry -> CONTINUE KitInitLegacySourcePreview
  2 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-2." and EMIT_MENU KitInitPreviewFailureMenu
```

```pdsl
UNIT KitInitDiscoveryRun
PURPOSE: Discover candidate kit resources read-only through cf-explore before proposing a new canonical manifest.
WHEN:
  REQUIRE TARGET_SOURCE == discovery
DO:
  INVOKE skill `cf-explore` with intent=discover candidate kit resources for a read-only manifest proposal and return_context=true, scoped to TARGET_DIR and known_paths = TARGET_DIR
  RUN KitInitDiscoveryRunClassifyResult
  CONTINUE KitInitDiscoveryProposal WHEN DISCOVERY_STATUS == provided
  CONTINUE KitInitDiscoveryRunFailure WHEN DISCOVERY_STATUS != provided
RULES:
  ALWAYS use cf-explore in return-context mode for discovery instead of direct filesystem prompt guessing
  ALWAYS keep discovery read-only
  NEVER synthesize a new manifest proposal without verified non-empty resource_context
```

```pdsl
UNIT KitInitDiscoveryRunClassifyResult
PURPOSE: Classify the discovery result and persist whether resource context is usable.
DO:
  SET DISCOVERY_STATUS = provided WHEN cf-explore returns resource_context with one or more candidate resource paths and evidence summaries
  SET DISCOVERY_STATUS = empty WHEN cf-explore returns no candidate resources
  SET DISCOVERY_STATUS = error WHEN cf-explore fails or returns no usable resource_context
  SET RESOURCE_CONTEXT = provided WHEN DISCOVERY_STATUS == provided
```

```pdsl
UNIT KitInitDiscoveryRunFailure
PURPOSE: Present the discovery failure menu and wait for the next choice.
DO:
  EMIT_MENU KitInitDiscoveryFailureMenu
  WAIT user.reply
  STOP_TURN
MENU KitInitDiscoveryFailureMenu
TITLE: Discovery did not return candidate kit resources. Retry, provide manual guidance, or cancel.
OPTIONS:
  1 retry -> CONTINUE KitInitDiscoveryRun
  2 guidance -> SET PENDING_MANUAL_GUIDANCE = true; EMIT "Reply with resource seed commands such as `add resource id=<id> kind=<kind> source=<path>`, `set metadata.name=<name>`, `set metadata.version=<semver>`, or `exclude source=<path>`."; WAIT user.reply; STOP_TURN
  3 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitDiscoveryFailureMenu
```

```pdsl
UNIT KitInitDiscoveryProposal
PURPOSE: Classify discovered resources, build a conservative canonical proposal, and gate the write on approval.
WHEN:
  REQUIRE TARGET_SOURCE == discovery
  AND RESOURCE_CONTEXT == provided
DO:
  RUN KitInitDiscoveryClassifyCandidates
  RUN KitInitDiscoveryBindArtifacts
  RUN KitInitDiscoverySynthesizeProposal
  RUN KitInitDiscoveryPreviewRender
RULES:
  ALWAYS classify discovered candidates into the public and supporting groups before proposing a manifest
  ALWAYS classify structural validation rule files as `kind = "constraints"` when their source path, id, or evidence identifies constraints semantics
  ALWAYS encode template/example/checklist/rules-to-artifact-kind relationships as explicit nested metadata on the constraints resource; never rely on resource ID naming conventions such as `<kind>_template`
  ALWAYS keep the proposal conservative and report ambiguity instead of guessing
  ALWAYS propose a default manifest before any write when no legacy manifest is present
  ALWAYS use top-level `manifest_version = "1.0"` plus `[[kits]]` + `[[kits.resources]]`; never emit `[kit]` or top-level `[[resources]]`
  ALWAYS follow KitGeneratedNamePreviewContract before the approval menu renders any public generated-name preview
  ALWAYS treat missing or unsupported canonical `manifest_version` as a blocking validation failure, not a recoverable warning
  NEVER write `.cf-studio-kit.toml` before the approval menu resolves
MENU KitInitDiscoveryApprovalMenu
TITLE: Approve the proposed canonical manifest for this folder?
OPTIONS:
  1 approve-default -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifest
  2 show-preview -> EMIT CURRENT_PREVIEW_TOML in a fenced `toml` block; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitDiscoveryApprovalMenu; WAIT user.reply; STOP_TURN
  3 edit -> SET PENDING_EDIT_BRANCH = discovery; EMIT "Reply with edit commands such as `set metadata.name=<name>`, `add resource id=<id> kind=<kind> source=<path>`, `remove resource id=<id>`, `set resource <id>.aliases=<a,b>`, `set resource <id>.install_path=<path>`, `set resource <id>.prefix_generated_name=false`, `bind artifact <KIND>.template=<resource-id>`, `bind artifact <KIND>.examples=<resource-id>`, or `exclude source=<path>`."; WAIT user.reply; STOP_TURN
  4 rerun-discovery -> CONTINUE KitInitDiscoveryRun
  5 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-5." and EMIT_MENU KitInitDiscoveryApprovalMenu
```

```pdsl
UNIT KitGeneratedNamePreviewContract
PURPOSE: Keep the generated-name preview wording and scope consistent across legacy and discovery proposal approvals.
RULES:
  <!-- @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview -->
  ALWAYS show a generated-name preview before approval for every public skill, agent, rule, and nested subagent: include resource/subagent id, kind, final generated name, and whether it is default-prefixed or `prefix_generated_name = false` as-is
  ALWAYS call out that `prefix_generated_name = false` is the manifest option to publish a public resource or nested subagent name as-is
  <!-- @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview -->
```

```pdsl
UNIT KitInitDiscoveryClassifyCandidates
PURPOSE: Load the discovery context and classify candidate resources before proposal synthesis.
DO:
  RUN ResourceContextMemory
  RUN classify candidates from RESOURCE_CONTEXT into public skills, agents, and rules, plus supporting templates, checklists, scripts, directories, and other
```

```pdsl
UNIT KitInitDiscoveryBindArtifacts
PURPOSE: Derive explicit artifact-kind bindings for discovered constraints resources before manifest synthesis.
DO:
  RUN derive explicit artifact-kind bindings for every constraints resource from RESOURCE_CONTEXT evidence:
    - template/checklist/rules/example files are bound to artifact kinds only when the kind is explicit in file metadata, constraints kind names, or an unambiguous per-kind layout such as `artifacts/<KIND>/template.md`
    - bindings point to resource IDs, never filesystem paths
    - ambiguous files remain unbound and are reported as ambiguities
```

```pdsl
UNIT KitInitDiscoverySynthesizeProposal
PURPOSE: Build the conservative canonical manifest proposal and its preview artifacts from discovery results.
DO:
  RUN KitInitDiscoveryProposalBaseShape
  RUN KitInitDiscoveryProposalResourceMapping
  RUN KitInitDiscoveryProposalPublicEntryPolicy
  RUN KitInitDiscoveryProposalFinalizePreview
```

```pdsl
UNIT KitInitDiscoveryProposalBaseShape
PURPOSE: Synthesize the canonical kit-level manifest structure and default metadata.
DO:
  RUN synthesize the proposal's canonical top-level kit structure from discovered candidates and explicit local metadata only:
    - top-level `manifest_version = "1.0"` is required before any `[[kits]]` table
    - missing or unknown `manifest_version` is blocking; report that the user should update Constructor Studio with `pipx upgrade constructor-studio` and retry
    - canonical shape is always `[[kits]]` + nested `[[kits.resources]]`, even when the file declares exactly one kit
    - add multiple `[[kits]]` entries only when the user explicitly asks for several kits or discovery returns clearly separate kit packages under TARGET_DIR
    - multi-kit proposals require unique kit slugs; each kit owns its own resource ID namespace
    - slug = explicit kit slug from discovered metadata, else target folder basename normalized to kebab-case
    - name = explicit kit display name from discovered metadata, else the slug
    - version = explicit semantic-version-compatible metadata, else `0.1.0`
```

```pdsl
UNIT KitInitDiscoveryProposalResourceMapping
PURPOSE: Synthesize the resource-level manifest entries and artifact bindings for the proposal.
DO:
  RUN synthesize canonical resource entries and artifact bindings from discovered candidates:
    - each `[[kits.resources]]` includes required `id`, `kind`, and `source`
    - `constraints.toml`, resource id `constraints`, and TOML files described as structural validation rules / heading outlines / ID kinds / cross-references are classified as `kind = "constraints"`; never classify them as `other`
    - constraints resources that have known artifact kinds and known sibling resources MUST include an `artifacts` table that maps artifact kinds to resource IDs: `artifacts.<KIND>.template = "<template-resource-id>"`, `artifacts.<KIND>.examples = "<example-resource-id>"`, `artifacts.<KIND>.rules = "<rules-resource-id>"`, and `artifacts.<KIND>.checklist = "<checklist-resource-id>"` when each resource is known
    - artifact binding values are resource IDs in the same kit namespace; never write paths in `artifacts.<KIND>.*`
    - omit an artifact binding when the resource-kind relationship is not known; report that `validate-kits` will warn and skip template/example self-check for that artifact kind until the binding is added
    - `install_path` is included only when the path can be expressed as a normalized relative path under TARGET_DIR without symlink escape or absolute segments
```

```pdsl
UNIT KitInitDiscoveryProposalPublicEntryPolicy
PURPOSE: Apply public-resource generation policy to the synthesized manifest proposal.
DO:
  RUN apply public-resource generation policy to the synthesized proposal:
    - `public = true` is used only for skills, agents, and rules; public resources become agent-facing generated skills/agents/rules, while non-public resources are installed/bound only
    - `prefix_generated_name = false` may be used only for public resources whose generated agent/skill/rule name must be exactly the resource `id`; the default is omitted/true and generates `cf-{kit-slug}-{id}`
    - `generated_targets = ["installed"]` is used only for public resources with no explicit target
    - workflow-like public entry points are normalized to `kind = "skill"` only when file content or discovered metadata identifies them as cf-* entry points
```

```pdsl
UNIT KitInitDiscoveryProposalFinalizePreview
PURPOSE: Store the synthesized discovery manifest preview and ambiguity report for approval.
DO:
  SET CURRENT_PREVIEW_TOML = the proposed `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the discovery classification and proposal ambiguity report
```

```pdsl
UNIT KitInitDiscoveryPreviewRender
PURPOSE: Render the discovery proposal preview and gate the write on approval.
DO:
  EMIT the discovery classification, proposal ambiguities, public generated-name preview, and proposed `.cf-studio-kit.toml` preview
  EMIT_MENU KitInitDiscoveryApprovalMenu
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT KitInitManualGuidanceProposal
PURPOSE: Turn user-provided manual resource guidance into a fresh manifest proposal when discovery returned no usable context.
WHEN:
  REQUIRE PENDING_MANUAL_GUIDANCE == true
DO:
  CONTINUE KitInitManualGuidanceParseAndValidate
  CONTINUE KitInitManualGuidanceHandleInvalid
  CONTINUE KitInitManualGuidanceSynthesizePreview
```

```pdsl
UNIT KitInitManualGuidanceParseAndValidate
PURPOSE: Parse manual guidance and determine whether it is valid enough to synthesize a proposal.
DO:
  RUN parse the user reply as manual candidate resources, optional multiple kit declarations, resource kinds, metadata defaults, aliases, install paths, generated targets, and exclusions
  RUN parse optional artifact binding guidance such as `bind artifact <KIND>.template=<resource-id>`, `bind artifact <KIND>.examples=<resource-id>`, `bind artifact <KIND>.rules=<resource-id>`, and `bind artifact <KIND>.checklist=<resource-id>`
  RUN reject guidance that references sources outside TARGET_DIR, uses unsupported resource kinds, creates duplicate IDs, proposes an unsupported `manifest_version`, binds an artifact role to an unknown resource ID, binds artifact metadata outside a constraints resource, or omits every candidate resource
```

```pdsl
UNIT KitInitManualGuidanceHandleInvalid
PURPOSE: Re-prompt for manual guidance when the supplied guidance is invalid.
DO:
  EMIT rejected guidance with reasons and EMIT_MENU KitInitManualGuidanceRetryMenu WHEN guidance is invalid
  WAIT user.reply WHEN guidance is invalid
  STOP_TURN WHEN guidance is invalid
```

```pdsl
UNIT KitInitManualGuidanceSynthesizePreview
PURPOSE: Build and render the manual-guidance proposal preview after validation succeeds.
DO:
  RUN synthesize a conservative canonical proposal from the accepted manual guidance using the same canonical shape and containment rules as KitInitDiscoveryProposal, including top-level `manifest_version = "1.0"`
  SET CURRENT_PREVIEW_TOML = the proposed `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the manual guidance classification and ambiguity report
  SET PENDING_MANUAL_GUIDANCE = unset
  CONTINUE KitInitManualGuidanceRenderPreview
RULES:
  ALWAYS produce a fresh proposal from manual guidance before entering the approval menu
  ALWAYS preserve user-provided artifact bindings as constraints-resource `artifacts.<KIND>.*` resource-ID references
  NEVER treat manual guidance as edits to a missing preview
  NEVER write from manual guidance directly
```

```pdsl
UNIT KitInitManualGuidanceRenderPreview
PURPOSE: Render the manual-guidance proposal preview and wait for approval input.
DO:
  EMIT the manual classification, proposal ambiguities, public generated-name preview, and proposed `.cf-studio-kit.toml` preview
  EMIT_MENU KitInitDiscoveryApprovalMenu
  WAIT user.reply
  STOP_TURN
MENU KitInitManualGuidanceRetryMenu
TITLE: Manual guidance could not produce a safe manifest proposal. Revise it, rerun discovery, or cancel.
OPTIONS:
  1 revise -> WAIT user.reply; STOP_TURN
  2 rerun-discovery -> SET PENDING_MANUAL_GUIDANCE = unset; CONTINUE KitInitDiscoveryRun
  3 cancel -> SET PENDING_MANUAL_GUIDANCE = unset; STOP_TURN
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitManualGuidanceRetryMenu
```

```pdsl
UNIT KitInitApplyUserEdits
PURPOSE: Apply user-supplied manifest edits, re-render the preview, and return to the correct approval gate.
WHEN:
  REQUIRE PENDING_EDIT_BRANCH != unset
DO:
  RUN KitInitApplyUserEditsValidate
  CONTINUE KitInitApplyUserEditsInvalid WHEN any requested edit is invalid
  RUN KitInitApplyUserEditsApplyValid
  CONTINUE KitInitApplyUserEditsRender
RULES:
  ALWAYS return edited manifests to a preview approval menu before any write
  ALWAYS preserve top-level `manifest_version = "1.0"` after applying edits
  ALWAYS preserve artifact bindings as resource-ID references under the constraints resource, not as paths or naming-derived links
  ALWAYS recompute and show the public generated-name preview after applying edits and before returning to approval
  ALWAYS reject unsafe or unsupported edits instead of guessing
  NEVER write from an edit reply directly
```

```pdsl
UNIT KitInitApplyUserEditsValidate
PURPOSE: Parse the requested manifest edits and reject unsafe or unsupported changes.
DO:
  RUN parse the user reply as requested manifest edits: metadata changes, kit additions/removals for multi-kit manifests, resource additions/removals, kind changes, aliases, install paths, generated targets, artifact bindings, and fields to preserve
  RUN reject edits that would reference sources outside TARGET_DIR, introduce duplicate kit slugs, introduce duplicate resource IDs within the same kit, use unsupported resource kinds, set `prefix_generated_name = false` on a non-public resource, bind an artifact role to an unknown resource ID, put artifact bindings on a non-constraints resource, remove required `manifest_version = "1.0"`, set an unsupported `manifest_version`, or contradict canonical manifest shape
```

```pdsl
UNIT KitInitApplyUserEditsInvalid
PURPOSE: Present invalid edit reasons and wait for a revised edit choice.
DO:
  EMIT the rejected edits with reasons
  EMIT_MENU KitInitEditRetryMenu
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT KitInitApplyUserEditsApplyValid
PURPOSE: Apply valid edits and store the revised manifest preview artifacts.
DO:
  RUN apply valid edits to CURRENT_PREVIEW_TOML
  RUN re-render the proposed `.cf-studio-kit.toml`
  SET CURRENT_PREVIEW_TOML = the revised `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the revised preview report and remaining ambiguities
```

```pdsl
UNIT KitInitApplyUserEditsRender
PURPOSE: Render the revised preview and route back to the matching approval menu.
DO:
  EMIT the revised public generated-name preview, revised manifest preview, and remaining ambiguities
  CONTINUE KitInitApplyUserEditsRenderLegacy WHEN PENDING_EDIT_BRANCH == legacy_manifest
  CONTINUE KitInitApplyUserEditsRenderDiscovery WHEN PENDING_EDIT_BRANCH == discovery
```

```pdsl
UNIT KitInitApplyUserEditsRenderLegacy
PURPOSE: Return an edited legacy-source preview to its approval menu.
DO:
  EMIT_MENU KitInitLegacyApprovalMenu
  SET PENDING_EDIT_BRANCH = unset
  WAIT user.reply
  STOP_TURN
```

```pdsl
UNIT KitInitApplyUserEditsRenderDiscovery
PURPOSE: Return an edited discovery preview to its approval menu.
DO:
  EMIT_MENU KitInitDiscoveryApprovalMenu
  SET PENDING_EDIT_BRANCH = unset
  WAIT user.reply
  STOP_TURN
MENU KitInitEditRetryMenu
TITLE: Some edits cannot be applied safely. Revise the edit request, keep the previous preview, or cancel.
OPTIONS:
  1 revise -> WAIT user.reply; STOP_TURN
  2 keep-preview -> EMIT CURRENT_PREVIEW_TOML; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitLegacyApprovalMenu WHEN PENDING_EDIT_BRANCH == legacy_manifest; EMIT_MENU KitInitDiscoveryApprovalMenu WHEN PENDING_EDIT_BRANCH == discovery; WAIT user.reply; STOP_TURN
  3 cancel -> SET PENDING_EDIT_BRANCH = unset; STOP_TURN
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitEditRetryMenu
```

```pdsl
UNIT KitInitValidateWrittenManifest
PURPOSE: Validate the canonical manifest after it has been written and report deterministic status.
WHEN:
  REQUIRE TARGET_SOURCE == legacy_manifest OR TARGET_SOURCE == discovery
DO:
  RUN `{cfs_cmd} kit normalize <target> --dry-run`
  RUN inspect the normalized manifest report for constraints resources with artifact kinds but no explicit template/example bindings; report these as actionable warnings because `validate-kits` will skip self-check for unknown relationships
  EMIT the validation report, manifest summary, and any warnings WHEN the dry-run passes
  EMIT the validation findings and the path that needs revision WHEN the dry-run reports fail or error
  CONTINUE KitInitNextActions WHEN the dry-run passes
  STOP_TURN WHEN the dry-run reports fail or error
RULES:
  ALWAYS validate a newly written `.cf-studio-kit.toml` through dry-run normalization before reporting completion
  NEVER skip validation after a write
  NEVER report success when the dry-run reports fail or error
```

```pdsl
UNIT KitInitNextActions
PURPOSE: Offer context-grounded next actions after a kit manifest write validates successfully.
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md
  RUN NextActionsOffer
RULES:
  ALWAYS run only after KitInitValidateWrittenManifest reports a passing dry-run validation
```
