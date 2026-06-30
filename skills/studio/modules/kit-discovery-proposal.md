# Kit Discovery Proposal

```pdsl
UNIT KitInitDiscoveryProposalRun
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
  1 approve-default -> SET APPROVED_PREVIEW = CURRENT_PREVIEW_TOML; RUN write APPROVED_PREVIEW bytes exactly to `<target>/.cf-studio-kit.toml`; RUN verify the written file bytes equal APPROVED_PREVIEW; CONTINUE KitInitValidateWrittenManifestRun
  2 show-preview -> EMIT CURRENT_PREVIEW_TOML in a fenced `toml` block; EMIT CURRENT_PREVIEW_REPORT; EMIT_MENU KitInitDiscoveryApprovalMenu; WAIT user.reply; STOP_TURN
  3 edit -> SET PENDING_EDIT_BRANCH = discovery; EMIT "Reply with edit commands such as `set metadata.name=<name>`, `add resource id=<id> kind=<kind> source=<path>`, `remove resource id=<id>`, `set resource <id>.aliases=<a,b>`, `set resource <id>.install_path=<path>`, `set resource <id>.prefix_generated_name=false`, `bind artifact <KIND>.template=<resource-id>`, `bind artifact <KIND>.examples=<resource-id>`, or `exclude source=<path>`."; WAIT user.reply; STOP_TURN
  4 rerun-discovery -> CONTINUE KitInitDiscoveryRun
  5 cancel -> EMIT "Kit manifest creation cancelled. No files were written."; LOAD {cf-studio-path}/.core/skills/studio/modules/ui/next-actions.md WHEN NextActionsOffer is not yet loaded; RUN NextActionsOffer
  INVALID -> EMIT "Reply 1-5." and EMIT_MENU KitInitDiscoveryApprovalMenu
```
