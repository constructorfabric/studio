---
cf: true
type: project-rule
topic: testing
generated-by: auto-config
version: 1.0
---

# Testing Guidelines


<!-- toc -->

- [Test Stack](#test-stack)
- [How To Run Tests](#how-to-run-tests)
- [Test Layout](#test-layout)
- [Common Test Patterns](#common-test-patterns)
- [Naming and Assertions](#naming-and-assertions)
- [Prompting CI Gate](#prompting-ci-gate)
- [Coverage and Quality Gates](#coverage-and-quality-gates)

<!-- /toc -->

Testing rules extracted from the current Constructor Studio repo.

## Test Stack

- `pytest` is the test framework
- `pytest-cov` is used for coverage reporting
- Coverage target is `90%` per file in CI
- `tests/conftest.py` bootstraps import paths for `tests/`, `skills/studio/scripts/`, and `examples/overwork_alert/src`

## How To Run Tests

```bash
make test
make test-coverage
pytest tests/test_kit.py -v
pytest tests/test_update.py::test_update_command -v
```

Prefer `pytest` for direct test execution. Use `make test` / `make test-coverage` for repo-standard verification.

## Test Layout

The repo has `99` `test_*.py` modules under `tests/` plus shared helpers:

- CLI and integration: `test_cli_integration.py`, `test_cli_helpers.py`, `test_studio_proxy_cli.py`, `test_ui_human_mode.py`, `test_adapter_info.py`
- Core parsing and validation: `test_artifacts_meta.py`, `test_constraints_utils.py`, `test_validate.py`, `test_spec_coverage.py`, `test_toc.py`, `test_context.py`, `test_parsing_utils.py`
- Kit lifecycle: `test_kit.py`, `test_kit_manifest_*.py`, `test_update.py`, `test_migrate_from_cypilot.py`
- Workspace and agents: `test_workspace.py`, `test_subagent_registration.py`, `test_agents_coverage.py`, `test_agents_model_matrix.py`
- Map (19 modules): `test_map_cli.py`, `test_map_scan.py`, `test_map_render_html.py`, `test_map_render_json.py`, and 15 more `test_map_*.py`
- PDSL validation: `test_pdsl_keywords.py`, `test_pdsl_transform_equivalence.py`, `test_pdsl_validate_cli.py`
- Ralphex delegation: `test_ralphex_delegation.py`, `test_ralphex_discover.py`, and 3 more `test_ralphex_*.py`
- Utility and helpers: `test_files_utils.py`, `test_diff_engine.py`, `test_fixing.py`, `test_manifest.py`, and others
- Example coverage: `test_overwork_alert_*.py` (4 modules)

Keep new tests in `tests/`, named `test_<subject>.py`, aligned with the subsystem they verify.

## Common Test Patterns

- Use `TemporaryDirectory()` and `Path` for filesystem-heavy flows
- For CLI tests, switch into the temp project root, call `main([...])`, capture stdout, and assert on parsed JSON output
- Use mocks for context loading, external calls, or side effects that are not the unit under test
- Reuse shared bootstrapping helpers such as `_bootstrap_project_root()` or `_test_helpers.py` utilities when setting up adapter/config state

## Naming and Assertions

- Test functions use `test_<behavior>` naming
- Test classes, when used, follow `Test<Area>` naming
- Assert on exit codes, JSON `status`, and observable filesystem changes rather than incidental implementation details

## Prompting CI Gate

ALWAYS run `make test` as part of `cf-prompting-ci` WHEN any prompt, skill, workflow, or agent instruction file is modified.

`make test` is the project's canonical deterministic test gate — it must pass before prompt changes are considered validated.

NEVER report `cf-prompting-ci` as PASS without first executing and confirming a clean `make test` run.

## Coverage and Quality Gates

`make test-coverage` produces the HTML report in `htmlcov/`. CI also runs validation, version checks, spec coverage, and dead-code detection, so new tests should help keep both deterministic command behavior and coverage thresholds healthy.
