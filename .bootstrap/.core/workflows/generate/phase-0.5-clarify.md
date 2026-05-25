---
name: generate-phase-0.5-clarify
description: "Invoke when the generate workflow reaches Phase 0.5 to clarify output destination and system context before input collection."
purpose: Generate Phase 0.5 — clarify output destination and system context
loaded_by: workflows/generate.md
version: 1.0
---

<!-- toc -->

- [Phase 0.5: Clarify Output & Context](#phase-05-clarify-output--context)

<!-- /toc -->





## Phase 0.5: Clarify Output & Context

If system context is unclear, ask:

```text
Why this input is needed: system selection controls registry placement, ID prefixes, and traceability boundaries.

Which system does this artifact/code belong to?
- {list systems from artifacts.toml}
- Create new system
Suggested: the current or nearest registered system when one owns the target path; otherwise `Create new system`.
Reply with the system name or `Create new system`.
```

Store the selected system for registry placement.

If output destination is unclear, ask:

```text
Why this input is needed: destination controls whether this workflow writes files, updates the registry, or returns a chat-only preview.

Where should the result go?
- File (will be written to disk and registered)
- Chat only (preview, no file created)
- MCP tool / external system (specify as `MCP: <tool>` or `External: <system>`)
Suggested: File for durable artifacts/code changes; Chat only for previews.
Reply with `File`, `Chat only`, `MCP: <tool>`, or `External: <system>`.
```

Then: store the selected system; if file output + using rules, determine the path, plan the `artifacts.toml` entry, and check `UPDATE` vs `CREATE`; for artifacts identify parent references; for code identify design artifacts + requirement IDs + traceability markers; for new IDs use `cpt-{system}-{kind}-{slug}` and verify uniqueness with `{cfs_cmd} --json list-ids`.
