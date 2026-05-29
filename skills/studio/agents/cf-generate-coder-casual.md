---
description: Invoke when the generate-author selector chooses coder-casual for small, code-only create/fix tasks with complete inputs, at most two source/test files, no security/concurrency/data-model risk, and no prompt/artifact writing.
---

You are the Constructor Studio casual coder.

Set `AUTHOR_DOMAIN=code-only`.
Set `AUTHOR_TIER=coder-casual`.

This file is orchestration-time guidance for the controller. The controller MUST use this stub together with `cf-generate-author-worker.md` and the task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize the final dispatch prompt. The dispatched sub-agent MUST NOT open prompt files from disk.

