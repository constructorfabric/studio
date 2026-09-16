```toml
[phase]
number = 2
total = 2
depends_on = [1]
input_files = ["plan.toml"]
output_files = ["step-2.out"]
```

# Phase 2

## Preamble

A compliant second phase that depends only on an earlier phase.

## What

Produce the second artifact.

## Rules

Depend backward; declare the output.
