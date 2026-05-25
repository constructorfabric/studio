---
description: "Invoke when loading Constructor Studio Protocol Guard, CLI resolution, logging, language, and write-confirmation rules."
---

# Constructor Studio Protocol

Run CLI resolution before workflow work: prefer `cfs`; otherwise use
`python3 {cf-studio-path}/.core/skills/studio/scripts/studio.py`.
ALWAYS use `{cfs_cmd}` for later CLI invocations.

ALWAYS provide execution visibility with `- [CONTEXT]: MESSAGE` when entering
Constructor Studio prompt sections and completing checklist tasks.

Protocol Guard:
1. Run `{cfs_cmd} --json info`.
2. Store the returned `variables` map.
3. Open and follow `{cf-studio-path}/.gen/AGENTS.md` when present.
4. Open and follow `{cf-studio-path}/config/AGENTS.md` when present.
5. Open and follow `{cf-studio-path}/.gen/SKILL.md` when present.
6. Open and follow `{cf-studio-path}/config/SKILL.md` when present.
7. Resolve registry, intent, target, rules, and matched WHEN-clause specs.
8. Open and follow `{cf-studio-path}/.core/requirements/language-complexity.md`.

Before code edits include:
```text
Constructor Studio Context:
- Constructor Studio: {path}
- Target: {artifact|codebase}
- Specs loaded: {list paths or "none required"}
```

Agent-safe invocation: use `{cfs_cmd} --json <subcommand>` except `init`,
`delegate`, and `update`, which run without `--json`. Obtain explicit user
confirmation before any write-capable command, and do not add `--yes`, `-y`,
or `--force` unless the user explicitly requested it. Phase-Skip Gate (SKILL.md) MUST be in a released_for_* state AND the write-confirmation MUST be obtained from the user before any write-capable command runs. Gate-release does not replace the confirmation step; both are required.
