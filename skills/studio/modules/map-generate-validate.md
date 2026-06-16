# Map Generate

```pdsl
UNIT MapGenerate
PURPOSE: Invoke cfs map for the chosen scope and produce the output artifact.
DO:
  RUN `{cfs_cmd} --json map --local-only [--out PATH] [--format html|json] [--config PATH] [--inline-data]` WHEN scope == single-repo
  RUN `{cfs_cmd} --json map [--out PATH] [--format html|json] [--config PATH] [--inline-data]` WHEN scope == with-workspace
  RUN `{cfs_cmd} --json map --no-source [--out PATH] [--format html|json] [--config PATH] [--inline-data]` WHEN scope == markdown-only
  RUN verify the output file exists and its size is reasonable
  EMIT the output path — html opens in a browser; json can be piped to tools like jq
  CONTINUE MapValidate
RULES:
  ALWAYS pass --inline-data only when format == html AND inline_data == true
```

```pdsl
UNIT MapValidate
PURPOSE: Inspect the map for completeness and phantom references.
DO:
  RUN parse the output — html: verify the vis-network graph renders and count nodes/edges via the embedded JSON or the .html.js sidecar; json: verify top-level nodes/edges arrays exist and count them directly
  RUN search for phantom:<cpt-id> nodes or a dangling_cpt_uses array
  RUN verify nodes are color-coded by category
  EMIT a suggestion to run `{cfs_cmd} where-used <cpt-id>` (shows where a cpt is used) or `{cfs_cmd} list-ids` (lists known cpts) WHEN dangling cpts are found
  LOAD {cf-studio-path}/.core/skills/studio/modules/map-next.md
  CONTINUE MapNextSteps
```
