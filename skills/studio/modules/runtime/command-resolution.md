# Command Resolution

```pdsl
UNIT CommandResolution
PURPOSE: Resolve the {cfs_cmd} command and remember its capabilities before invoking any cfs command.
WHEN:
  REQUIRE a {cfs_cmd} invocation is needed
DO:
  SET {cfs_cmd} = cfs WHEN cfs is available on PATH
  SET {cfs_cmd} = python {cf-studio-path}/.core/skills/studio/scripts/studio.py WHEN cfs is not available on PATH
  RUN CliCapabilities WHEN remembered tool commands is unset
RULES:
  ALWAYS resolve {cfs_cmd} before invoking any cfs command
  ALWAYS run CliCapabilities before any workflow invokes {cfs_cmd} directly or through a loaded module
```

```pdsl
UNIT CliCapabilities
PURPOSE: Discover and remember the tool's available commands and prefer them for relevant tasks.
DO:
  RUN {cfs_cmd} --help to obtain the list of available commands and capabilities
  SET remembered tool commands = the commands returned by {cfs_cmd} --help
RULES:
  ALWAYS run {cfs_cmd} --help to discover available commands and remember them for the session
  ALWAYS prefer a remembered {cfs_cmd} command over an ad-hoc approach when one fits the task
```
