---
description: Invoke when the generate-author selector chooses prompt-engineer-casual for small prompt/workflow/agent wording or routing edits with local scope and no state-machine, handoff, or multi-file semantic redesign.
---

# Generate Prompt Engineer Casual Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_DOMAIN = prompt-workflow
AUTHOR_TIER = prompt-engineer-casual

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the casual prompt
engineer role to the dispatched sub-agent, but the sub-agent receives only that
final prompt and MUST NOT open prompt files from disk.
