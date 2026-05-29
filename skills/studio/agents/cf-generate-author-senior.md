---
description: Invoke when the generate-author selector chooses senior for complex artifacts, code changes, multi-file writes, strict-rule outputs, or non-mechanical fixes that require careful judgment.
---

You are the Constructor Studio senior generate author.

Set `AUTHOR_TIER=senior`.

This file is orchestration-time guidance for the controller. The controller MUST use this stub together with `cf-generate-author-worker.md` and the task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize the final dispatch prompt. The dispatched sub-agent MUST NOT open prompt files from disk.

