# E2E Test Analysis Report

This report is synchronized with the current `*_e2e.py` suite state in `tests/`.

<!-- toc -->

- [Current Snapshot](#current-snapshot)
- [Fully Green Modules](#fully-green-modules)
- [Not Runnable In Current Workspace](#not-runnable-in-current-workspace)
- [Coverage Shape](#coverage-shape)
- [Notes](#notes)

<!-- /toc -->

## Current Snapshot

- Date: `2026-06-20`
- Command: `pytest tests/*_e2e.py -q --tb=no -rA`
- Result: `114 passed`, `1 skipped`, `3 subtests passed`
- Inventory: `14` e2e modules total
- Status split:
  - `12` fully green runnable modules
  - `1` skipped module
  - `1` disabled / no runnable tests module

Scope rules used for this report:

- "Fully green" means every executed test in the module passed in the latest run.
- Skipped and disabled upgrade coverage is listed separately and is not counted as green.

## Fully Green Modules

| Module | Passing tests | Covered surface |
|---|---:|---|
| `tests/test_cli_agents_e2e.py` | 2 | Public `agents` CLI behavior, including read-only OpenAI inspection and missing-root error handling |
| `tests/test_cli_artifact_tools_e2e.py` | 5 | Artifact utility commands: deprecated `generate-resources`, `pdsl validate`, and TOC dry-run/write flows |
| `tests/test_cli_example_kits_e2e.py` | 48 | End-to-end kit lifecycle across canonical, mixed, and legacy fixtures: install, register, normalize, validate, generate, update, interactive overwrite/prune flows, and Git/GitHub provenance |
| `tests/test_cli_gitignore_e2e.py` | 5 | Managed `.gitignore` behavior for init, installed kits, generated public skills, and generated agent proxies |
| `tests/test_cli_kit_utility_e2e.py` | 7 | `chunk-input`, local kit install/update, deprecated `kit migrate`, and manifest-driven agent generation |
| `tests/test_cli_map_public_e2e.py` | 6 | Public `cfs map` JSON/HTML outputs, sidecar behavior, dangling IDs, federated workspace nodes, and invalid-config failure path |
| `tests/test_cli_navigation_e2e.py` | 2 | Navigation/read behavior for both single-project read-only mode and workspace-root source queries without a local adapter |
| `tests/test_cli_setup_e2e.py` | 9 | Setup/config surfaces: `info`, `resolve-vars`, `update` option validation, and `generate-agents` discovery/dry-run/show-layers flows |
| `tests/test_cli_update_e2e.py` | 3 | Exact `update` command error handling and dry-run non-mutation guarantees |
| `tests/test_cli_validate_e2e.py` | 6 | Exact `validate` public CLI scenarios, including artifact-not-in-registry, workspace-root source validation, and cross-artifact reference pass/fail paths |
| `tests/test_cli_validation_e2e.py` | 8 | `validate-toc`, `spec-coverage`, `check-language`, and alias forwarding behavior |
| `tests/test_cli_workspace_diag_e2e.py` | 13 | Workspace init/add/info/sync, delegate dry-run/non-dry-run/error paths, and `doctor` healthy/degraded/JSON exception/fail outputs |

## Not Runnable In Current Workspace

| Module | Current status | Reason |
|---|---|---|
| `tests/test_kit_upgrade_e2e.py` | Skipped | Raises `SkipTest` because local `kits/sdlc/` is not present; the kit moved to a separate repo |
| `tests/test_core_upgrade_e2e.py` | Disabled | `TestCoreUpgradeE2E` is decorated with `@unittest.skip(...)` for the unsupported `v3.x -> 4.0.0` breaking transition |

## Coverage Shape

The suite is still centered on public CLI behavior and observable filesystem effects:

- Read-only validation and diagnostics paths
- Bounded-write setup and bootstrap flows
- Kit lifecycle management, including complex update and overwrite decisions
- Provider/agent generation and managed `.gitignore` integration
- Map generation and workspace/delegation diagnostics
- Error-path guarantees for missing roots, bad selectors, invalid configs, and unreachable workspace sources

The heaviest area remains `tests/test_cli_example_kits_e2e.py`, and it is currently fully green with `48` passing tests.

## Notes

- The report previously reflected older mixed/failing snapshots; the current runnable `*_e2e.py` suite is fully green.
- This version is intentionally a runtime status report for the latest observed suite result, not a static catalog of intended behaviors.
