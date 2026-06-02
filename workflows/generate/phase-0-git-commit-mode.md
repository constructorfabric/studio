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

```pdsl
UNIT GitCommitModeProbe

PURPOSE:
  Probe GIT_COMMIT_MODE once per chat session before any write-capable sub-agent dispatch.

STATE:
  - SET GIT_COMMIT_MODE: commit | stage | none
    default: unset
    scope: session

WHEN:
  - REQUIRE GIT_COMMIT_MODE == unset

DO:
  - EMIT exactly:
- RUN ---
- RUN Why this input is needed: write-capable sub-agents require an explicit git permission boundary
- RUN so they cannot accidentally commit or stage changes without your intent.

- RUN How should write-capable sub-agents interact with git in this session?

- RUN | Option | Mode     | Permitted git operations                                                   |
- RUN |--------|----------|---------------------------------------------------------------------------|
- RUN | 1      | commit   | git add + git commit (one commit at end, follow CONTRIBUTING guide if found) |
- RUN | 2      | stage    | git add only — no commit, push, reset, rebase, stash, or checkout --      |
- RUN | 3      | none     | No git operations at all — working-tree edits only                        |

- RUN Suggested: 3 (safest — no accidental commits; use 1 when a CONTRIBUTING guide exists and you want commits created automatically).

- RUN Reply with 1, 2, or 3.
- RUN ---
  - WAIT user.reply
  - STOP_TURN

MENU GitCommitModeMenu:
  TITLE: Git commit mode selection
  OPTIONS:
    1 (complete token) -> SET GIT_COMMIT_MODE = commit
                          CONTINUE CurrentWorkflow
    2 (complete token) -> SET GIT_COMMIT_MODE = stage
                          CONTINUE CurrentWorkflow
    3 (complete token) -> SET GIT_COMMIT_MODE = none
                          CONTINUE CurrentWorkflow
  INVALID:
    EMIT re-emit the prompt
    WAIT user.reply
    STOP_TURN

RULES:
  - ALWAYS probe once per chat session
  - ALWAYS skip if GIT_COMMIT_MODE already set from an earlier run in this chat
  - ALWAYS re-probe on external-entry handoffs (briefs_only stop + new chat)
  - NEVER re-probe on subsequent cf-generate runs within the same chat
  - ALWAYS end the assistant turn immediately after emitting the prompt
  - NEVER treat absence of reply as option 3
  - ALWAYS trim replies of leading/trailing whitespace before matching
  - ALWAYS accept complete token only: token 1, 2, or 3 as standalone;
    "option 2 please" is valid (2 appears as own token);
    "12", "v3", "mode-2x" are NOT valid (digit embedded in larger token);
    "2." counts as token 2
```

## Mode Semantics

```pdsl
UNIT GitCommitModeSemantics

PURPOSE:
  Define permitted git operations per GIT_COMMIT_MODE value carried into every
  write-capable sub-agent dispatch payload.

RULES:
  - ALWAYS commit mode:
    - ALWAYS follow project CONTRIBUTING guide when CONTRIBUTING_GUIDE is non-null
    - ALWAYS may git add files written
    - ALWAYS may git commit (one commit at end)
    - NEVER git push, git reset, git rebase, git stash, git checkout --

  - ALWAYS stage mode:
    - ALWAYS may git add files written
    - NEVER git commit, git push, git reset, git rebase, git stash, git checkout --

  - ALWAYS none mode:
    - NEVER run git commit, git push, git reset, git rebase, git stash,
      git checkout --, or git add
    - ALWAYS Leave changes as uncommitted, unstaged working-tree edits only

INVARIANTS:
  - ALWAYS GIT_COMMIT_MODE is orthogonal to CF_PHASE_GATE:
    CF_PHASE_GATE guards write tool calls (Edit/Write/etc.);
    GIT_COMMIT_MODE guards git tool calls; both apply simultaneously
```
