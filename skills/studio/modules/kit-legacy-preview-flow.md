# Kit Legacy Preview Flow
```pdsl
UNIT KitInitLegacySourcePreviewStart
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
