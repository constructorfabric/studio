# Kit Generated Name Preview
```pdsl
UNIT KitGeneratedNamePreviewContract
PURPOSE: Keep the generated-name preview wording and scope consistent across legacy and discovery proposal approvals.
RULES:
  <!-- @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview -->
  ALWAYS show a generated-name preview before approval for every public skill, agent, rule, and nested subagent: include resource/subagent id, kind, final generated name, and whether it is default-prefixed or `prefix_generated_name = false` as-is
  ALWAYS call out that `prefix_generated_name = false` is the manifest option to publish a public resource or nested subagent name as-is
  <!-- @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-public-name-preview -->
```
