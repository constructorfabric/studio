# Kit Route Detect

```pdsl
UNIT KitInitRouteRun
PURPOSE: Apply folder-init source precedence and route to the correct read-only or write-gated branch.
WHEN:
  REQUIRE TARGET_DIR != unset
DO:
  RUN KitInitRouteDetectSource
  RUN KitInitRouteSetNormalizeHint
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-existing-manifest.md WHEN TARGET_SOURCE == canonical
  CONTINUE KitInitExistingManifestOffer WHEN TARGET_SOURCE == canonical
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-legacy-preview-flow.md WHEN TARGET_SOURCE == legacy_manifest OR TARGET_SOURCE == legacy_layout
  CONTINUE KitInitLegacySourcePreviewStart WHEN TARGET_SOURCE == legacy_manifest OR TARGET_SOURCE == legacy_layout
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
