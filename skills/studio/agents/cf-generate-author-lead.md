---
description: Invoke when the generate-author selector chooses lead for high-risk or broad generation/fix tasks: cross-system architecture, security/concurrency/data integrity concerns, workflow/agent prompt changes, large finding batches, or uncertain scope where cheaper tiers are likely to fail.
---

# Generate Author Lead Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_TIER = lead

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the lead author role to
the dispatched sub-agent, but the sub-agent receives only that final prompt and
MUST NOT open prompt files from disk.
