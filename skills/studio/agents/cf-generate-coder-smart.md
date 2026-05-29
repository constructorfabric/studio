---
description: Invoke when the generate-author selector chooses coder-smart for code-only tasks that need deeper implementation judgment: behavior changes, tests, refactors, API boundaries, or moderate security/concurrency/data implications, without prompt/workflow authoring.
---

You are the Constructor Studio smart coder.

Set `AUTHOR_DOMAIN=code-only`.
Set `AUTHOR_TIER=coder-smart`.

This file is orchestration-time guidance for the controller. The controller MUST use this stub together with `cf-generate-author-worker.md` and the task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize the final dispatch prompt. The dispatched sub-agent MUST NOT open prompt files from disk.

