# Kit Discovery Synthesize

```pdsl
UNIT KitInitDiscoverySynthesizeProposal
PURPOSE: Build the conservative canonical manifest proposal and its preview artifacts from discovery results.
DO:
  RUN KitInitDiscoveryProposalBaseShape
  RUN KitInitDiscoveryProposalResourceMapping
  RUN KitInitDiscoveryProposalPublicEntryPolicy
  RUN KitInitDiscoveryProposalFinalizePreview
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
UNIT KitInitDiscoveryProposalPublicEntryPolicy
PURPOSE: Apply public-resource generation policy to the synthesized manifest proposal.
DO:
  RUN apply public-resource generation policy to the synthesized proposal:
    - `public = true` is used only for skills, agents, and rules; public resources become agent-facing generated skills/agents/rules, while non-public resources are installed/bound only
    - `prefix_generated_name = false` may be used only for public resources whose generated agent/skill/rule name must be exactly the resource `id`; the default is omitted/true and generates `cf-{kit-slug}-{id}`
    - `generated_targets = ["installed"]` is used only for public resources with no explicit target
    - workflow-like public entry points are normalized to `kind = "skill"` only when file content or discovered metadata identifies them as cf-* entry points
UNIT KitInitDiscoveryProposalFinalizePreview
PURPOSE: Store the synthesized discovery manifest preview and ambiguity report for approval.
DO:
  SET CURRENT_PREVIEW_TOML = the proposed `.cf-studio-kit.toml` text; SET CURRENT_PREVIEW_REPORT = the discovery classification and proposal ambiguity report
UNIT KitInitDiscoveryPreviewRender
PURPOSE: Render the discovery proposal preview and gate the write on approval.
DO:
  EMIT the discovery classification, proposal ambiguities, public generated-name preview, and proposed `.cf-studio-kit.toml` preview
  EMIT_MENU KitInitDiscoveryApprovalMenu
  WAIT user.reply
  STOP_TURN
```
