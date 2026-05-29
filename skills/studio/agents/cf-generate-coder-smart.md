---
description: Invoke when the generate-author selector chooses coder-smart for code-only tasks that need deeper implementation judgment: behavior changes, tests, refactors, API boundaries, or moderate security/concurrency/data implications, without prompt/workflow authoring.
---

# Generate Coder Smart Dispatch Generator

This file is controller-side tier metadata for synthesizing the final prompt.

AUTHOR_DOMAIN = code-only
AUTHOR_TIER = coder-smart

The controller MUST combine this file with `cf-generate-author-worker.md` and
task-relevant shared mode/rules assets from `SHARED_CONTEXT_PACK` to synthesize
the final dispatch prompt. The final prompt may assign the smart coder role to
the dispatched sub-agent, but the sub-agent receives only that final prompt and
MUST NOT open prompt files from disk.
