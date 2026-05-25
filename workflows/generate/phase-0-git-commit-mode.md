---
cf: true
type: workflow-fragment
parent: workflows/generate.md
description: "Invoke when the GIT_COMMIT_MODE session flag is unset and the orchestrator must probe the user once per chat session to determine how write-capable sub-agents are permitted to interact with git."
---

<!-- toc -->

- [Phase 0.x: GIT_COMMIT_MODE Probe](#phase-0x-gitcommitmode-probe)
- [Mode Semantics](#mode-semantics)

<!-- /toc -->

## Phase 0.x: GIT_COMMIT_MODE Probe

**Session-scoped flag**: `GIT_COMMIT_MODE` is probed once per chat session.
- If already set from an earlier workflow run in this chat, skip this step entirely.
- External-entry handoffs (briefs_only stop + resume in a new chat) MUST re-probe.
- Do NOT re-probe on subsequent `/cf-generate` runs within the same chat.

If `GIT_COMMIT_MODE` is unset, emit exactly this menu and end the turn (hard interaction boundary — MUST NOT proceed until the user replies):

Why this input is needed: write-capable sub-agents require an explicit git permission boundary so they cannot accidentally commit or stage changes without your intent.

```text
How should write-capable sub-agents interact with git in this session?

| Option | Mode     | Permitted git operations                                                   |
|--------|----------|---------------------------------------------------------------------------|
| 1      | commit   | git add + git commit (one commit at end, follow CONTRIBUTING guide if found) |
| 2      | stage    | git add only — no commit, push, reset, rebase, stash, or checkout --      |
| 3      | none     | No git operations at all — working-tree edits only                        |

Suggested: 3 (safest — no accidental commits; use 1 when a CONTRIBUTING guide exists and you want commits created automatically).

Reply with 1, 2, or 3.
```

After emitting the prompt, MUST end the assistant turn immediately. Absence of
a reply is NOT option `3`. Replies are trimmed of leading/trailing whitespace
before matching. Accept only a **complete token** `1`, `2`, or `3` (for
example, `option 2 please` is valid because `2` appears as its own token;
`12`, `v3`, or `mode-2x` are not valid because the digit is embedded inside a
larger token). `2.` still counts as token `2`.

Reply parsing:

| Reply (case-insensitive, trimmed) | Action |
|---|---|
| contains complete token `1` | Set `GIT_COMMIT_MODE=commit` |
| contains complete token `2` | Set `GIT_COMMIT_MODE=stage` |
| contains complete token `3` | Set `GIT_COMMIT_MODE=none` |
| anything else | Re-emit the prompt; do NOT proceed |

## Mode Semantics

Mode semantics (carried into every write-capable sub-agent dispatch payload):

- `commit` — sub-agents MAY `git add` files they wrote and create one commit at the end. Commit message and process MUST follow the project CONTRIBUTING guide when one was discovered (`CONTRIBUTING_GUIDE` is non-null). MUST NOT `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`.
- `stage`  — sub-agents MAY `git add` files they wrote. MUST NOT `git commit`, `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`.
- `none`   — sub-agents MUST NOT run `git commit`, `git push`, `git reset`, `git rebase`, `git stash`, `git checkout --`, or `git add`. Leave changes as uncommitted, unstaged working-tree edits only.

`GIT_COMMIT_MODE` is orthogonal to the Phase-Skip Gate. The Phase-Skip Gate guards write tool calls (`Edit`/`Write`/etc.); `GIT_COMMIT_MODE` guards git tool calls. Both apply simultaneously.
