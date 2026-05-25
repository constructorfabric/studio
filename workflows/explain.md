---
cf: true
type: workflow
name: cf-explain
description: Chat-only explain entry point — delegates to analyze.md in EXPLAIN mode.
version: 1.0
purpose: Standalone explain command; pass-through to analyze.md with EXPLAIN mode
---

LOAD skill `cf` IN ANALYZE + EXPLAIN mode, EXPLAIN_MODE=true
