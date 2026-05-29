---
description: Invoke when the generate-author selector chooses prompt-engineer-smart for prompt/workflow/agent/skill changes that affect state, routing, handoffs, sub-agent contracts, validation criteria, or multi-file prompt semantics.
---

# Generate Prompt Engineer Smart Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_DOMAIN = prompt-workflow
AUTHOR_TIER = prompt-engineer-smart

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the smart prompt
engineer role to the dispatched sub-agent, but the sub-agent receives only that
final prompt and MUST NOT open prompt files from disk.
