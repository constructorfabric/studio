---
description: Invoke when the generate-author selector chooses junior for simple, bounded create/fix tasks: one file, complete inputs, low-risk prose or mechanical edits, and no architectural/code/security ambiguity.
---

# Generate Author Junior Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_TIER = junior

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the junior author role to
the dispatched sub-agent, but the sub-agent receives only that final prompt and
MUST NOT open prompt files from disk.
