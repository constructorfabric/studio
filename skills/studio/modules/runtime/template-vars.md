# Template Variable Resolution

```pdsl
UNIT TemplateVarResolution
PURPOSE: Resolve unknown template variables before asking the user.
WHEN:
  REQUIRE an unknown `{...}` template variable is encountered
DO:
  RUN {cfs_cmd} resolve-vars
  WAIT for the user to provide the value WHEN the variable still cannot be found
  CONTINUE once the value is provided
RULES:
  ALWAYS try `{cfs_cmd} resolve-vars` before asking the user for a template variable value
```
