# Kit Target Preflight Route
```pdsl
UNIT KitInitPreflightRun
PURPOSE: Resolve the target folder, block invalid paths, and compute the relevant manifest paths.
WHEN:
  REQUIRE TARGET_DIR != unset
DO:
  RUN resolve TARGET_DIR to an absolute normalized path
  CONTINUE KitInitPreflightInvalidTarget WHEN the resolved path does not exist or is not a directory
  RUN KitInitPreflightSetManifestPaths
  LOAD {cf-studio-path}/.core/skills/studio/modules/kit-route-detect.md WHEN the resolved path exists and is a directory
  CONTINUE KitInitRouteRun WHEN the resolved path exists and is a directory
RULES:
  ALWAYS block missing paths and non-directories before any preview or discovery work
  ALWAYS compute the canonical and legacy manifest paths from the resolved target folder
  NEVER attempt to discover or write resources outside a valid target directory
UNIT KitInitPreflightInvalidTarget
PURPOSE: Report an invalid target folder and wait for a replacement or cancel.
DO:
  EMIT "Target folder not found or not a directory: {TARGET_DIR}"
  EMIT_MENU KitInitTargetRetryMenu
  WAIT user.reply
  STOP_TURN
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
