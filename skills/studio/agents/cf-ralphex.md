---
description: Invoke when delegating a generated Constructor Studio plan to ralphex for autonomous execution — manages the discovery, export, delegation, and handoff lifecycle.
---

This file is the controller-side generator source for ralphex delegation
dispatches. The final dispatch prompt may assign the ralphex delegation role to
the sub-agent and must describe how to manage the lifecycle of delegating
Constructor Studio plans to ralphex for autonomous execution.

NOTES:
  This prompt intentionally bundles CLI Entrypoint, Library Implementation Reference
  (debugging / advanced use only), and Post-Run Handoff into a single agent. The runtime
  orchestration logic lives in code modules (`studio.ralphex_export`), so prompt-level
  decomposition would not reduce agent context — only obscure where to look when debugging.

<!-- toc -->

- [Capability Boundary](#capability-boundary)
- [CLI Entrypoint](#cli-entrypoint)
- [Library Implementation Reference (debugging / advanced use only)](#library-implementation-reference-debugging--advanced-use-only)
- [Post-Run Handoff](#post-run-handoff)
- [Response Completion Gate](#response-completion-gate)

<!-- /toc -->

## Dispatch Generator Contract

This file is a controller-side prompt generator source, not a runtime prompt for the dispatched sub-agent.

The controller MUST use this file to synthesize the final dispatch prompt for
the agent. The final prompt MUST include the task statement, frozen input
payload, task-relevant instruction assets resolved from `SHARED_CONTEXT_PACK`,
allowed resource context, output contract, completion gate, and the explicit
rule that the dispatched sub-agent executes only that final prompt.

The dispatched sub-agent MUST NOT open prompt assets from disk and MUST NOT
rediscover workflows, requirements, specs, AGENTS, SKILL, or kit prompt files.


## Capability Boundary

This agent coordinates discovery, export, delegation, and handoff for ralphex.
Runtime orchestration behavior (subprocess management, process monitoring,
streaming output) is implemented in code modules, not in this prompt. This
prompt defines the delegation workflow steps; the backing Python modules
(`ralphex_discover`, `ralphex_export`) provide the executable implementation.

```pdsl
UNIT RalphexPromptContext

PURPOSE:
  Keep Constructor Studio prompt handling shared-context-pack compliant while
  preserving the delegation boundary.

RULES:
  - ALWAYS rely on the controller to inject `studio_mode_contract` and any other
    required instruction assets into the final dispatch prompt
  - ALWAYS treat the synthesized final dispatch prompt as the sole prompt and
    instruction source
  - NEVER open prompt assets from disk directly
  - ALWAYS keep runtime orchestration in the documented CLI and Python modules;
    this prompt does not redefine subprocess behavior
```

## CLI Entrypoint

```pdsl
UNIT CliEntrypoint

PURPOSE:
  Invoke ralphex delegation via the canonical CLI command.

DO:
  - RUN Run: {cfs_cmd} delegate <plan_dir> [--mode execute|tasks-only|review]
       [--worktree] [--serve] [--dry-run] [--plans-dir <path>]
       [--default-branch <branch>] [--root <path>]

RULES:
  - NEVER add `--json` to `{cfs_cmd} delegate`
  - ALWAYS always invoke as `{cfs_cmd} delegate ...` without `--json`

ON_ERROR:
  exit_code 1 -> report input error (missing plan directory or invalid root)
  exit_code 2 -> report delegation error (ralphex not found or validation failed)
```

NOTES:
  The CLI loads config, invokes `run_delegation()`, and returns exit code 0 on
  success, 1 on input errors, or 2 on delegation errors.

## Library Implementation Reference (debugging / advanced use only)

NOTES:
  Agents invoke the CLI entrypoint above. This section documents the backing
  implementation for debugging; it is not an instruction to execute Python imports.

`run_delegation()` is the backing library function composed by the CLI:
It performs discover → validate → bootstrap gate → persist → review precondition (if needed) → compile/export plan → build command → track lifecycle. The result dict includes `status`, `ralphex_path`, `validation`, `bootstrap`, `plan_file`, `command`, `mode`, `lifecycle_state`, and `error`.

Implementation (for reference):

```python
from studio.ralphex_export import run_delegation

result = run_delegation(
    config=studio_config_dict,            # parsed Constructor Studio config (dict)
    plan_dir="/abs/path/.bootstrap/.plans/<task-slug>",
    repo_root="/abs/path/repo",
    mode="execute",                         # or "review" (skip tasks, review only); set dry_run=True for a no-invoke dry run (returns status="ready").
    default_branch="main",
    config_path=None,                       # optional Path to the active config file
    dry_run=False,                          # True → assemble command without invoking ralphex
)

if result["status"] == "error":
    # inspect result["error"], result["lifecycle_state"]; do not proceed to handoff
    ...
elif result["status"] == "ready":
    # dry_run: inspect result["ralphex_path"], result["validation"],
    # result["bootstrap"], result["plan_file"], result["command"], result["mode"],
    # result["lifecycle_state"]; ralphex was NOT invoked
    ...
else:
    # status is "delegated": ralphex executed successfully (returncode 0)
    # inspect result["ralphex_path"], result["validation"], result["bootstrap"],
    # result["plan_file"], result["command"], result["mode"], result["lifecycle_state"],
    # result["returncode"], result["stdout"], result["stderr"]
    ...
```

Required parameters: `config`, `plan_dir`, `repo_root`. Common optional parameters: `mode`, `default_branch`, `config_path`, `dry_run` (additional knobs — `worktree`, `serve`, `plans_dir_override`, `stream_output` — exist for advanced cases).

```pdsl
UNIT DelegationStatusRouting

PURPOSE:
  Route behavior based on run_delegation() result status.

STATE:
  - SET DELEGATION_STATUS: ready | delegated | error

WHEN:
  - REQUIRE run_delegation() result is available

DO:
  - SET DELEGATION_STATUS = result["status"]

MENU DelegationOutcomeMenu:
  OPTIONS:
    1 "ready" ->
      EMIT assembled command, plan file, mode, and lifecycle_state as dry-run summary
      STOP_TURN
    2 "delegated" ->
      CONTINUE PostRunHandoff
    3 "error" ->
      CONTINUE DelegationErrorHandling

ON_ERROR:
  invalid_status ->
    EMIT "Unknown status in result dict."
    STOP_TURN
```

**Mode selection:**

| Mode | Command | Notes |
|------|---------|-------|
| Execute (full) | `ralphex {plans_dir}/{task}.md` | Tasks + review |
| Tasks-only | `ralphex {plans_dir}/{task}.md --tasks-only` | Execute tasks, skip review |
| Review-only | `ralphex --review [plan.md]` | Review committed changes on feature branch |
| Worktree | `--worktree` flag | Valid only for full and tasks-only modes |
| Dashboard | `--serve` flag | Web dashboard monitoring |

```pdsl
UNIT ReviewModeGeneration

PURPOSE:
  Generate the Constructor Studio review override before invoking ralphex in review mode.

WHEN:
  - REQUIRE mode == "review"

DO:
  - RUN Generate review override at `.ralphex/prompts/cf-review-override.md`
    (references exported Constructor Studio review-contract metadata; does not
     instruct raw prompt-asset reloads)
    (classifies changed files as code or prompt/instruction; applies matching branch)
    (enforces bounded scope: diff against default branch only)
    (enforces completion gates: PASS/PARTIAL/FAIL)
    (enforces residual-risk reporting and remediation-prompt obligations)
    (regenerated on every review-mode delegation — not cached)

RULES:
  - NEVER treat ralphex as a host-tool subagent or new public Constructor Studio analyze CLI
```

```pdsl
UNIT DelegationErrorHandling

PURPOSE:
  Report errors from run_delegation() with context and recovery options.

WHEN:
  - REQUIRE DELEGATION_STATUS == error

DO:
  - EMIT result["error"] and result["lifecycle_state"]
  - REQUIRE result["bootstrap"]["needed"] == true:
    - EMIT "ralphex --init is required"
    - EMIT_MENU BootstrapApprovalMenu
    - WAIT user.reply
    - STOP_TURN
  - REQUIRE result["error"] references review precondition failure:
    - EMIT the precondition (e.g. no commits ahead of default branch)
    - EMIT suggested resolution
    - STOP_TURN
  - EMIT error message, lifecycle state at failure
  - EMIT_MENU RetryOrAbortMenu
  - WAIT user.reply
  - STOP_TURN

RULES:
  - NEVER proceed to Post-Run Handoff when status == "error"

MENU BootstrapApprovalMenu:
  TITLE: |
    ralphex --init is needed before delegation can continue.

    Command/action: ralphex --init
    Target: local delegation runtime configuration for this repository
    Effect: initialize or update ralphex bootstrap files needed to run
    delegation; delegation remains stopped if you cancel.
    Consequence:
      - Reply 1: run `ralphex --init` now, then resume this delegation flow from the bootstrap step.
      - Reply 2: do not initialize ralphex; stop this delegation attempt.

    Reply with exactly one number: 1 to approve this exact initialization, or 2 to abort.
  OPTIONS:
    1 -> run `ralphex --init` with explicit user approval
    2 -> abort delegation
  INVALID:
    EMIT "Reply with exactly one number: 1 or 2."
    WAIT user.reply
    STOP_TURN

MENU RetryOrAbortMenu:
  TITLE: |
    Delegation failed.

    Consequence:
      - Reply 1: retry the same delegation flow against the same plan target.
      - Reply 2: stop here and leave the failed delegation unresolved.

    Reply with exactly one number: 1 to retry or 2 to abort.
  OPTIONS:
    1 -> retry delegation
    2 -> abort
  INVALID:
    EMIT "Reply with exactly one number: 1 or 2."
    WAIT user.reply
    STOP_TURN
```

## Post-Run Handoff

```pdsl
UNIT PostRunHandoff

PURPOSE:
  Execute post-delegation steps and emit the structured handoff report.

WHEN:
  - REQUIRE DELEGATION_STATUS == delegated

DO:
  - RUN Call read_handoff_status(exit_code, output_refs, partial)
     to classify delegation outcome (success / partial / failed)
  - RUN Call check_completed_plans(plans_dir, task_slug)
     to inspect the ralphex-managed `completed/` subdirectory for lifecycle artifacts
  - RUN Call run_validation_commands(commands, cwd=repo_root)
     with validation commands extracted from `## Validation Commands` section of result["plan_file"]
     (each non-empty, non-heading line in that section is one command)
  - RUN Call report_handoff(...) to assemble the delegation summary
  - EMIT the structured Delegation Handoff Report:

     ## Delegation Handoff Report
     - **Status**: {report["status"]} (success | partial | failed)
     - **Plan file**: `{report["plan_file"]}`
     - **Mode**: {report["mode"]}
     - **Validation passed**: {report["validation_passed"]}
     - **Completed plan**: `{report["completed_plan_path"]}` or none
     - **Output refs**: {report["output_refs"] as bulleted list, or "none"}

     ### Next Steps
     - Review output artifacts listed above
     - Invoke skill `cf-analyze` on changed files if validation passed
     - If failed: inspect error output, fix issues, and re-delegate

  - STOP_TURN
```

NOTES:
  Helper functions are imported from `studio.ralphex_export`:
    `read_handoff_status`, `check_completed_plans`, `run_validation_commands`, `report_handoff`.

```pdsl
UNIT BootstrapGate

PURPOSE:
  Block delegation when ralphex is not initialized.

WHEN:
  - REQUIRE result["bootstrap"]["needed"] == true

RULES:
  - ALWAYS report that `.ralphex/config` is missing and `ralphex --init` is required
  - ALWAYS request explicit user approval before running `ralphex --init`
  - NEVER run `ralphex --init` automatically — it is always an opt-in action
```

## Response Completion Gate

```pdsl
UNIT RalphexCompletionGate

RULES:
  - ALWAYS have called run_delegation() and have the result dict available
  - ALWAYS WHEN status == "error":
      ALWAYS report error with lifecycle state, failure reason, and recovery options (retry/abort/bootstrap)
  - ALWAYS WHEN status == "ready" (dry-run):
      ALWAYS report assembled command, plan file, mode, and lifecycle state
      ALWAYS skip Post-Run Handoff (ralphex was not invoked)
  - ALWAYS WHEN status == "delegated":
      ALWAYS have executed Post-Run Handoff steps 1–5
      ALWAYS emit the structured Delegation Handoff Report
  - NEVER end response with only a summary or status update
  - ALWAYS satisfy the `studio_mode_contract` invariant
```
