---
description: Invoke when the generate-author selector chooses senior for complex artifacts, code changes, multi-file writes, strict-rule outputs, or non-mechanical fixes that require careful judgment.
---

# Generate Author Senior Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_TIER = senior

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the senior author role to
the dispatched sub-agent, but the sub-agent receives only that final prompt and
MUST NOT open prompt files from disk.
