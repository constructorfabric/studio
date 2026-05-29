---
description: Invoke when the generate-author selector chooses middle for standard artifact or small code create/fix tasks with clear inputs, moderate cross-references, or small mechanical review-loop batches.
---

# Generate Author Middle Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_TIER = middle

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the middle author role to
the dispatched sub-agent, but the sub-agent receives only that final prompt and
MUST NOT open prompt files from disk.
