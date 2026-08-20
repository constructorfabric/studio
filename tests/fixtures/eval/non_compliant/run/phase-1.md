```toml
[phase]
number = 1
total = 2
depends_on = []
output_files = ["step-1.out"]
```

# Phase 1

## Preamble

Structurally scoreable, but the manifest declares two phases while only phase-1.md is
present — so both the reference scorer (missing `phase-2.md`) and the structural scorer
(manifest vs. files, phase total vs. count) report the run as non-compliant.

## What

Produce the first artifact.

## Rules

The missing declared phase is the deliberate defect.
