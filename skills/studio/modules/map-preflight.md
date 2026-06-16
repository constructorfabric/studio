# Map Preflight

```pdsl
UNIT MapPreflight
PURPOSE: Detect what will be scanned along the federation and source-scanning axes before generating.
DO:
  RUN `{cfs_cmd} --json info`
  CONTINUE MapPreflightInfoFailure WHEN it errors
  SET project_root = the absolute project root path reported by `{cfs_cmd} --json info`
  RUN CHECK for .studio-workspace.toml in the project root (federation axis)
  RUN CHECK for [[systems.codebase]] / [[systems.autodetect.codebase]] entries in {cf-studio-path}/config/artifacts.toml or <project_root>/artifacts.toml (source-scanning axis)
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-execute.md
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-generate-validate.md
  CONTINUE MapPreflightScopeOffer
```

```pdsl
UNIT MapPreflightInfoFailure
PURPOSE: Stop early when Studio info cannot be read.
DO:
  EMIT "Could not read studio info (`{cfs_cmd} --json info` failed) — ensure Studio is initialized with `cfs init`, then retry."
  STOP_TURN
```


```pdsl
UNIT MapPreflightScopeOffer
PURPOSE: Present the discovered map-scope capabilities and wait for scope selection.
DO:
  EMIT the discovered state — Federation: ".studio-workspace.toml present" OR "no workspace config — federation unavailable"; Source scanning: codebase entries found OR "no codebase entries found — source scanning unavailable"
  EMIT_MENU MapScopeMenu
  WAIT user.reply
  STOP_TURN
MENU MapScopeMenu
TITLE: Choose the scan scope across two axes — federation (this repo only vs. include workspace sources) and source scanning (scan code vs. markdown only). Suggested: with-workspace if a workspace + codebase exist; else single-repo if codebase exists; else markdown-only.
OPTIONS:
  1 single-repo -> SET scope = single-repo and CONTINUE MapConfigure
  2 with-workspace | workspace -> REQUIRE .studio-workspace.toml exists, SET scope = with-workspace and CONTINUE MapConfigure
  3 markdown-only | markdown -> SET scope = markdown-only and CONTINUE MapConfigure
  INVALID -> EMIT_MENU MapScopeMenu
```
