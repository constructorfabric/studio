---
cf: true
type: requirement
name: Raw-Input Overflow Rule
version: 1.1
purpose: Shared overflow routing rule for analyze and generate workflows
---

# Raw-Input Overflow Rule

```pdsl
UNIT OVERFLOW_ROUTE
PURPOSE: Detect oversized direct input and present an explicit routing choice before any execution.
STATE:
  - SET threshold_lines: 500
WHEN:
  - REQUIRE lines(user_prompt + provided_files) > threshold_lines
DO:
  - EMIT_MENU
      MENU:
        TITLE: Input exceeds 500 lines — choose how to proceed
        OPTIONS:
          (a) Invoke skill `cf-plan`
          (b) Stop before direct execution
  - DISPATCH (a) -> INPUT_MATERIALIZE
  - DISPATCH (b) -> STOP_TURN
  - CONTINUE only if a downstream workflow explicitly preserves the direct-workflow branch after this menu
RULES:
  - NEVER silently continue in direct-workflow mode when threshold is exceeded
  - ALWAYS present this menu before any execution
  - ALWAYS give this offer precedence over the single-context bypass check (Phase 1.2 in plan.md)
  - ALWAYS remain on the plan path once the user selects (a), even if the later bypass check would permit skipping plan compilation
ON_ERROR:
  no_choice_received -> STOP_TURN
```

```pdsl
UNIT INPUT_MATERIALIZE
PURPOSE: Obtain explicit user approval then materialize and chunk oversized raw input into the plan directory.
STATE:
  - SET plan_input_dir: {cf-studio-path}/.plans/{task-slug}/input/
  - SET max_lines_per_chunk: 300
  - SET threshold_lines: 500
WHEN:
  - REQUIRE user has selected the cf-plan path (via OVERFLOW_ROUTE menu, or while already on the plan path and raw task input exceeds threshold_lines)
DO:
  - REQUIRE explicit user approval before creating plan_input_dir or executing the write-capable chunk-input command
  - RUN (write-capable, after approval):
      {cfs_cmd} --json chunk-input [<path> ...] --output-dir {plan_input_dir} [--include-stdin] [--stdin-label <label>] --max-lines 300 --threshold-lines 500
  - LOAD resulting chunk files as the authoritative raw-input package for the plan
  - REQUIRE chunk file count > 0; if zero chunks produced, EMIT warning to user and route to ON_ERROR no_chunks_produced before any write-capable action
  - DISPATCH to plan decomposition with original request scope preserved
RULES:
  - NEVER create plan_input_dir or execute the write-capable chunk-input command without explicit user approval
  - NEVER treat the user's selection of cf-plan as implicit authorization for directory creation or chunking
  - ALWAYS pass --include-stdin when direct prompt text must be packaged together with provided files
  - ALWAYS request explicit confirmation immediately before the write-capable invocation
ON_ERROR:
  approval_denied -> STOP_TURN
  chunk_command_fails -> STOP_TURN
  no_chunks_produced -> EMIT "chunking produced no output files; original request scope preserved" and STOP_TURN
```

Canonical write-capable invocation (executed only after explicit approval):

```
{cfs_cmd} --json chunk-input [<path> ...] --output-dir {cf-studio-path}/.plans/{task-slug}/input [--include-stdin] [--stdin-label <label>] --max-lines 300 --threshold-lines 500
```

Read-only signature/reuse check (no files written, no approval required):

```
{cfs_cmd} --json chunk-input [<path> ...] --output-dir {cf-studio-path}/.plans/{task-slug}/input [--include-stdin] --dry-run
```

Positional `<path>` arguments enumerate provided files (zero, one, or many); pass `--include-stdin` to additionally read direct prompt text from stdin alongside files; if no positional paths are given, the command reads stdin only (no `--include-stdin` needed) and the direct prompt is preserved as `direct-prompt.md` in the output directory.

**Applies to**: analyze workflow (direct analysis mode), generate workflow (direct generation mode).

**Plan workflow note**: `INPUT_MATERIALIZE` governs both the analyze/generate-overflow routing case and the case where raw task input exceeds `500` lines while already executing the plan workflow — the same approval gate applies in both contexts.
