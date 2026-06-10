---
cf: true
type: workflow
name: cf-kit-init
description: "Invoke when user intent is initializing a kit folder, creating or validating .cf-studio-kit.toml, converting legacy manifest.toml, normalizing conf.toml + layout, or discovering resources for a new kit manifest."
version: 0.1
purpose: Initialize a kit root into a canonical .cf-studio-kit.toml through explicit preview, approval, write, and validation gates.
---

# cf-kit-init

This workflow initializes a target kit folder into a canonical `.cf-studio-kit.toml`. It resolves the target folder first, then applies init-time source precedence for that folder: keep an existing canonical manifest read-only, convert a legacy `manifest.toml` through `cfs kit normalize`, or discover candidate resources through `cf-explore`, propose a conservative manifest, gate all writes on user approval, then validate the written manifest through dry-run normalization.

Executor contract: the controller owns filesystem writes, exact-byte preview checks, CLI invocations, and state checkpoints across turns. `cf-explore` owns read-only discovery and returns resource_context; this workflow consumes only resource paths, short summaries, suggested resource kinds, evidence, and missing-context questions from that context.

```pdsl
UNIT KitInitBootstrap
PURPOSE: Ensure the cf skill is loaded before any kit-init work.
STATE:
  SET CFS_INIT: true | false (default false, scope session)
DO:
  EMIT_MENU LoadCfSkillConfirm WHEN CFS_INIT != true
  STOP_TURN WHEN CFS_INIT != true
  RUN verify `{cfs_cmd} kit normalize --help` supports `--from`, `--output`, and `--dry-run`
  EMIT "Required kit normalization command is unavailable; update Constructor Studio, then retry cf-kit-init." WHEN the normalize capability check fails
  STOP_TURN WHEN the normalize capability check fails
  CONTINUE KitInitEntry WHEN CFS_INIT == true
RULES:
  ALWAYS verify the cf skill is loaded, CFS_INIT == true, before any kit-init work
  ALWAYS verify the kit normalize command surface before previewing, writing, or validating a kit manifest
  ALWAYS treat CFS_INIT as false when its value is unknown, ambiguous, or unset
  NEVER proceed past KitInitBootstrap unless CFS_INIT == true is positively confirmed
MENU LoadCfSkillConfirm
TITLE: The cf skill is not loaded. It is the Constructor Studio core that loads the shared rules and routes to cf-* skills, so kit init cannot run without it. Load it now to continue?
OPTIONS:
  1 load -> INVOKE skill `cf` and CONTINUE KitInitBootstrap
  2 stop -> STOP_TURN
  INVALID -> EMIT_MENU LoadCfSkillConfirm
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
  CONTINUE KitInitPreflight WHEN TARGET_DIR != unset
RULES:
  ALWAYS capture the original intent before routing any kit-init branch
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
  1 path:<folder> | path -> Reply `path: <folder>` or send the folder path alone, then CONTINUE KitInitPreflight
  2 cancel -> STOP_TURN
  INVALID -> treat non-empty path-like free text as TARGET_DIR and CONTINUE KitInitPreflight; handle `cancel`, `help`, or non-path text by EMIT "Reply with `path: <folder>`, a path-like folder value, or 2 to cancel." and EMIT_MENU KitInitTargetMenu
```

```pdsl
UNIT KitInitPreflight
PURPOSE: Resolve the target folder, block invalid paths, and compute the relevant manifest paths.
WHEN:
  REQUIRE TARGET_DIR != unset
DO:
  RUN resolve TARGET_DIR to an absolute normalized path
  EMIT "Target folder not found or not a directory: {TARGET_DIR}" WHEN the resolved path does not exist or is not a directory
  EMIT_MENU KitInitTargetRetryMenu WHEN the resolved path does not exist or is not a directory
  WAIT user.reply WHEN the resolved path does not exist or is not a directory
  STOP_TURN WHEN the resolved path does not exist or is not a directory
  SET CANONICAL_MANIFEST = `<target>/.cf-studio-kit.toml`
  SET LEGACY_MANIFEST = `<target>/manifest.toml`
  SET LEGACY_CONF = `<target>/conf.toml`
  CONTINUE KitInitRoute WHEN the resolved path exists and is a directory
RULES:
  ALWAYS block missing paths and non-directories before any preview or discovery work
  ALWAYS compute the canonical and legacy manifest paths from the resolved target folder
  NEVER attempt to discover or write resources outside a valid target directory
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
  SET TARGET_SOURCE = canonical WHEN CANONICAL_MANIFEST exists
  SET TARGET_SOURCE = legacy_manifest WHEN CANONICAL_MANIFEST does not exist AND LEGACY_MANIFEST exists
  SET TARGET_SOURCE = legacy_layout WHEN CANONICAL_MANIFEST does not exist AND LEGACY_MANIFEST does not exist AND (LEGACY_CONF exists OR recognized kit layout directories exist)
  SET TARGET_SOURCE = discovery WHEN CANONICAL_MANIFEST does not exist AND LEGACY_MANIFEST does not exist AND TARGET_SOURCE == unset
  SET NORMALIZE_SOURCE_HINT = manifest WHEN TARGET_SOURCE == legacy_manifest
  SET NORMALIZE_SOURCE_HINT = layout WHEN TARGET_SOURCE == legacy_layout
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
  RUN `{cfs_cmd} kit normalize <target> --from <NORMALIZE_SOURCE_HINT> --dry-run`
  SET PREVIEW_STATUS = pass WHEN dry-run returns a valid manifest preview
  SET PREVIEW_STATUS = fail WHEN dry-run returns validation findings
  SET PREVIEW_STATUS = error WHEN dry-run cannot parse or load the legacy manifest
  SET CURRENT_PREVIEW_TOML = the proposed canonical `.cf-studio-kit.toml` text WHEN PREVIEW_STATUS == pass
  SET CURRENT_PREVIEW_REPORT = the migration report WHEN PREVIEW_STATUS == pass
  EMIT the migration report and proposed canonical `.cf-studio-kit.toml` WHEN PREVIEW_STATUS == pass
  EMIT_MENU KitInitLegacyApprovalMenu WHEN PREVIEW_STATUS == pass
  EMIT the normalization findings and blocking error details WHEN PREVIEW_STATUS != pass
  EMIT_MENU KitInitPreviewFailureMenu WHEN PREVIEW_STATUS != pass
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS treat `<target>/manifest.toml` as the selected legacy input when it exists and `<target>/.cf-studio-kit.toml` does not
  ALWAYS treat `conf.toml + layout` as the selected legacy input when no canonical or legacy manifest exists and layout evidence exists
  ALWAYS preview the normalized canonical manifest before any write
  NEVER write the canonical manifest before the approval menu resolves
MENU KitInitLegacyApprovalMenu
TITLE: Approve the legacy-source conversion?
OPTIONS:
  1 approve-default -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifest
  2 edit -> SET PENDING_EDIT_BRANCH = legacy_manifest; EMIT "Reply with edit commands such as `set metadata.name=<name>`, `set metadata.version=<semver>`, `remove resource id=<id>`, `set resource <id>.kind=<kind>`, `set resource <id>.install_path=<path>`, or `preserve field=<field>`."; WAIT user.reply; STOP_TURN
  3 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-3." and EMIT_MENU KitInitLegacyApprovalMenu
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
  SET DISCOVERY_STATUS = provided WHEN cf-explore returns resource_context with one or more candidate resource paths and evidence summaries
  SET DISCOVERY_STATUS = empty WHEN cf-explore returns no candidate resources
  SET DISCOVERY_STATUS = error WHEN cf-explore fails or returns no usable resource_context
  SET RESOURCE_CONTEXT = provided WHEN DISCOVERY_STATUS == provided
  CONTINUE KitInitDiscoveryProposal WHEN DISCOVERY_STATUS == provided
  EMIT_MENU KitInitDiscoveryFailureMenu WHEN DISCOVERY_STATUS != provided
  WAIT user.reply WHEN DISCOVERY_STATUS != provided
  STOP_TURN WHEN DISCOVERY_STATUS != provided
RULES:
  ALWAYS use cf-explore in return-context mode for discovery instead of direct filesystem prompt guessing
  ALWAYS keep discovery read-only
  NEVER synthesize a new manifest proposal without verified non-empty resource_context
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
  RUN classify candidates from RESOURCE_CONTEXT into public skills, agents, and rules, plus supporting templates, checklists, scripts, directories, and other
  RUN synthesize a conservative canonical proposal using the discovered candidates and explicit local metadata only:
    - default shape is single-kit `[kit]` + `[[resources]]`
    - use multi-kit `[[kits]]` + nested `[[kits.resources]]` only when the user explicitly asks for several kits or discovery returns clearly separate kit packages under TARGET_DIR
    - multi-kit proposals require unique kit slugs; each kit owns its own resource ID namespace
    - slug = explicit kit slug from discovered metadata, else target folder basename normalized to kebab-case
    - name = explicit kit display name from discovered metadata, else the slug
    - version = explicit semantic-version-compatible metadata, else `0.1.0`
    - each `[[resources]]` or `[[kits.resources]]` includes required `id`, `kind`, and `source`
    - `install_path` is included only when the path can be expressed as a normalized relative path under TARGET_DIR without symlink escape or absolute segments
    - `public = true` is used only for skills, agents, and rules
    - `generated_targets = ["installed"]` is used only for public resources with no explicit target
    - workflow-like public entry points are normalized to `kind = "skill"` only when file content or discovered metadata identifies them as cf-* entry points
  SET CURRENT_PREVIEW_TOML = the proposed `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the discovery classification and proposal ambiguity report
  EMIT the discovery classification, proposal ambiguities, and proposed `.cf-studio-kit.toml` preview
  EMIT_MENU KitInitDiscoveryApprovalMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS classify discovered candidates into the public and supporting groups before proposing a manifest
  ALWAYS keep the proposal conservative and report ambiguity instead of guessing
  ALWAYS propose a default manifest before any write when no legacy manifest is present
  ALWAYS keep `[kit]` + `[[resources]]` and `[[kits]]` mutually exclusive in one `.cf-studio-kit.toml`
  NEVER write `.cf-studio-kit.toml` before the approval menu resolves
MENU KitInitDiscoveryApprovalMenu
TITLE: Approve the proposed canonical manifest for this folder?
OPTIONS:
  1 approve-default -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifest
  2 edit -> SET PENDING_EDIT_BRANCH = discovery; EMIT "Reply with edit commands such as `set metadata.name=<name>`, `add resource id=<id> kind=<kind> source=<path>`, `remove resource id=<id>`, `set resource <id>.aliases=<a,b>`, `set resource <id>.install_path=<path>`, or `exclude source=<path>`."; WAIT user.reply; STOP_TURN
  3 rerun-discovery -> CONTINUE KitInitDiscoveryRun
  4 cancel -> STOP_TURN
  INVALID -> EMIT "Reply 1-4." and EMIT_MENU KitInitDiscoveryApprovalMenu
```

```pdsl
UNIT KitInitManualGuidanceProposal
PURPOSE: Turn user-provided manual resource guidance into a fresh manifest proposal when discovery returned no usable context.
WHEN:
  REQUIRE PENDING_MANUAL_GUIDANCE == true
DO:
  RUN parse the user reply as manual candidate resources, optional multiple kit declarations, resource kinds, metadata defaults, aliases, install paths, generated targets, and exclusions
  RUN reject guidance that references sources outside TARGET_DIR, uses unsupported resource kinds, creates duplicate IDs, or omits every candidate resource
  EMIT rejected guidance with reasons and EMIT_MENU KitInitManualGuidanceRetryMenu WHEN guidance is invalid
  WAIT user.reply WHEN guidance is invalid
  STOP_TURN WHEN guidance is invalid
  RUN synthesize a conservative canonical proposal from the accepted manual guidance using the same canonical shape and containment rules as KitInitDiscoveryProposal
  SET CURRENT_PREVIEW_TOML = the proposed `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the manual guidance classification and ambiguity report
  SET PENDING_MANUAL_GUIDANCE = unset
  EMIT the manual classification, proposal ambiguities, and proposed `.cf-studio-kit.toml` preview
  EMIT_MENU KitInitDiscoveryApprovalMenu
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS produce a fresh proposal from manual guidance before entering the approval menu
  NEVER treat manual guidance as edits to a missing preview
  NEVER write from manual guidance directly
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
  RUN parse the user reply as requested manifest edits: metadata changes, kit additions/removals for multi-kit manifests, resource additions/removals, kind changes, aliases, install paths, generated targets, and fields to preserve
  RUN reject edits that would reference sources outside TARGET_DIR, introduce duplicate kit slugs, introduce duplicate resource IDs within the same kit, use unsupported resource kinds, or contradict canonical manifest shape
  EMIT the rejected edits with reasons and EMIT_MENU KitInitEditRetryMenu WHEN any requested edit is invalid
  WAIT user.reply WHEN any requested edit is invalid
  STOP_TURN WHEN any requested edit is invalid
  RUN apply valid edits to CURRENT_PREVIEW_TOML
  RUN re-render the proposed `.cf-studio-kit.toml`
  SET CURRENT_PREVIEW_TOML = the revised `.cf-studio-kit.toml` text
  SET CURRENT_PREVIEW_REPORT = the revised preview report and remaining ambiguities
  EMIT the revised preview and remaining ambiguities
  EMIT_MENU KitInitLegacyApprovalMenu WHEN PENDING_EDIT_BRANCH == legacy_manifest
  EMIT_MENU KitInitDiscoveryApprovalMenu WHEN PENDING_EDIT_BRANCH == discovery
  SET PENDING_EDIT_BRANCH = unset WHEN all valid edits were applied and an approval menu is emitted
  WAIT user.reply
  STOP_TURN
RULES:
  ALWAYS return edited manifests to a preview approval menu before any write
  ALWAYS reject unsafe or unsupported edits instead of guessing
  NEVER write from an edit reply directly
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
  EMIT the validation report, manifest summary, and any warnings WHEN the dry-run passes
  EMIT the validation findings and the path that needs revision WHEN the dry-run reports fail or error
  STOP_TURN
RULES:
  ALWAYS validate a newly written `.cf-studio-kit.toml` through dry-run normalization before reporting completion
  NEVER skip validation after a write
  NEVER report success when the dry-run reports fail or error
```
