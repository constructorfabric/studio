---
name: PDSL Patterns Registry
version: 0.1
purpose: Canonical named-pattern registry for the PDSL matches() operator
---

# PDSL Patterns Registry

This file is the canonical registry for named patterns used by the PDSL
`matches(<value>, <pattern-name>)` condition operator.

Patterns are referenced in PDSL `WHEN` clauses across workflows, skills, and
requirements. Each entry MUST declare a name, a regex or matcher specification,
and a short description of where it is used.

The registry is currently empty. Add an entry when the first PDSL UNIT requires
a named pattern. Local `PATTERNS:` blocks in individual PDSL files may declare
file-scoped patterns without registering them here, per `architecture/specs/PDSL.md`
§PATTERNS Block.

## Registered Patterns

_None yet._
