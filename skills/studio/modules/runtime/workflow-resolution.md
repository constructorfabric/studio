# Workflow Resolution

```pdsl
UNIT WorkflowResolution
PURPOSE: Resolve the available cf-* skills deterministically by discovering core and kit workflows, never from the host, for any unit that needs the skill list.
WHEN:
  REQUIRE the available cf-* skill list is needed
DO:
  LOAD {cf-studio-path}/.core/skills/studio/modules/runtime/command-resolution.md WHEN CommandResolution is not yet loaded
  RUN CommandResolution to resolve {cfs_cmd} WHEN {cfs_cmd} is unset
  RUN enumeration of core workflows at {cf-studio-path}/.core/workflows/*.md
  RUN enumeration of kit workflows from `{cfs_cmd} info --json` at kit_details.<kit>.workflows
  RUN mapping of each discovered workflow to its cf-* skill name: a core workflow file <name>.md maps to cf-<name>; a kit workflow <base> under kit <kit> maps to cf-<kit>-<base>
  ALLOW zero-or-more cf-* skills to be discovered
  EMIT a one-line empty-discovery note WHEN no cf-* skill was discovered
  STOP_TURN WHEN no cf-* skill was discovered
RULES:
  ALWAYS load command-resolution and resolve {cfs_cmd} before invoking `{cfs_cmd} info --json`
  ALWAYS resolve the cf-* skill list deterministically from {cf-studio-path}/.core/workflows/*.md and the kit workflow registry reported by `{cfs_cmd} info --json`
  ALWAYS map core workflows to cf-<name> and kit workflows to cf-<kit>-<base>
  NEVER inspect, probe, or fall back to `.agents/skills` or generated skill wrappers to discover available workflows; wrappers may lag or be incomplete, and canonical workflow discovery starts at {cf-studio-path}/.core/workflows
  NEVER use host-provided skill lists or a cfs CLI skills-list command for WorkflowResolution
  NEVER guess the cf-* skill list
```
