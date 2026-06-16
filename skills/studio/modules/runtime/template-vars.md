# Template Variable Resolution

```pdsl
UNIT TemplateVarResolution
PURPOSE: Resolve unknown template variables before asking the user.
WHEN:
  REQUIRE an unknown `{...}` template variable is encountered
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md WHEN CommandResolution is not yet loaded
  RUN CommandResolution to resolve {cfs_cmd} WHEN {cfs_cmd} is unset
  RUN {cfs_cmd} resolve-vars
  WAIT for the user to provide the value WHEN the variable still cannot be found
  CONTINUE once the value is provided
RULES:
  ALWAYS load command-resolution and resolve {cfs_cmd} before invoking `{cfs_cmd} resolve-vars`
  ALWAYS try `{cfs_cmd} resolve-vars` before asking the user for a template variable value
```
