```toml
[phase]
number = 1
total = 1
depends_on = []
input_files = ["plan.toml"]
output_files = ["step-1.out"]
```

# Phase 1

## What

Produce the first artifact.

## Acceptance Criteria

- [ ] `step-1.out` exists in the run directory
- [ ] `step-1.out` names the phase it came from
- [ ] the run recorded a verdict for every criterion above
