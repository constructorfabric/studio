# Optional Global `cfs` Engine Installation Brainstorm

## Result

Status: wrapped

The brainstorm designed an optional global `cfs` engine mode for Constructor Studio. The key decision is to keep global `cfs` as a thin launcher. It should not become the authority for workflow logic.

## Core Model

Normal commands resolve project-first:

1. Find the project root using the root `AGENTS.md` marker.
2. Read `cf-studio-path`.
3. Use the repo-local `.bootstrap` engine when valid.
4. Fall back to `~/.cf-studio/cache` only when no valid project engine exists.

`init` and `update` remain cache-management exceptions. They intentionally operate on the global cache and must not execute repo-local `.bootstrap`.

## Command Taxonomy

- Proxy-local: `mirror`, `--version`, and explicit proxy diagnostics.
- Cache management: `init`, `update`.
- Delegated normal commands: `validate`, `kit`, `toc`, `info`, `resolve-vars`, `agents`, `generate-agents`, `workspace`, `delegate`, `map`, and similar engine-owned commands.
- Diagnostics: bare `cfs doctor` remains delegated to the selected engine.

## Proxy Diagnostics

Stable command:

```bash
cfs proxy doctor
```

Supported forms:

```bash
cfs proxy doctor --verbose
cfs proxy doctor --json
cfs proxy doctor --json --verbose
```

Do not add a permanent top-level `cfs --proxy-diagnostics`. If it already shipped somewhere, keep it only as a time-boxed deprecated alias.

## JSON Contract

Schema version: `cfs.proxy_doctor.v1`

Top-level fields:

```json
{
  "schema_version": "cfs.proxy_doctor.v1",
  "status": "pass|warn|fail",
  "summary": {
    "message": "...",
    "redacted_count": 0,
    "deprecated_alias_used": false
  },
  "proxy": {
    "command_class": "...",
    "executable_path": "...",
    "detected_root": "...",
    "cf_studio_path": "...",
    "selected_engine": "...",
    "fallback_reason": null,
    "cache_path": "...",
    "provenance": {},
    "trust_state": "trusted|warning|blocked"
  },
  "checks": []
}
```

Use `null` for unavailable values. Do not omit stable fields.

## V1 Checks

Fixed order:

1. `proxy_executable`
2. `workspace_root`
3. `root_agents_marker`
4. `cf_studio_path`
5. `project_skill`
6. `cache_skill`
7. `skill_provenance`
8. `engine_selection`
9. `trust_state`
10. `redaction_policy`
11. `project_code_execution_blocked`

Each check object has exactly these common keys:

```json
{
  "id": "engine_selection",
  "status": "pass|warn|fail",
  "summary": "Stable display sentence.",
  "evidence": [
    {
      "kind": "path|marker|config|provenance|policy|execution|diagnostic|message",
      "name": "selected_engine",
      "value": "...",
      "redacted": false
    }
  ],
  "remediation": null,
  "details": {}
}
```

Rules:

- `summary` is always non-empty.
- `remediation` is `null` only on pass.
- `remediation` is non-empty on warn or fail.
- `details` is always an object.
- Verbose-only data goes under `details.diagnostics`.
- Warnings and failures must include evidence.

## Status And Exit Codes

Top-level status uses worst severity:

- Any `fail` -> `fail`.
- Else any `warn` -> `warn`.
- Else `pass`.

Exit codes:

- `0`: pass or warn.
- `1`: CLI parse or usage error only.
- `2`: diagnostic fail or report/schema contract failure.

Missing project engine is `warn` when a valid cache fallback exists. It is `fail` when no valid engine path exists.

Unknown or untrusted workspace is `warn` if no project-local code was executed.

Redaction leak, malformed JSON, report construction failure, or inability to prove no-exec due to internal diagnostic error is `fail`.

## Human Output

Default:

```text
Proxy doctor: PASS|WARN|FAIL
Selected engine: <engine-id> (<source>)
WARN <check-id>: <summary>
  Remediation: <stable remediation>
FAIL <check-id>: <summary>
  Remediation: <stable remediation>
```

Passing runs with no warnings stop after the selected-engine line.

Verbose:

```text
Proxy doctor: PASS|WARN|FAIL
Selected engine: <engine-id> (<source>)

Resolution trace:
  <redacted trace bullets>

Checks:
  PASS|WARN|FAIL <check-id>: <summary>
    Evidence: <schema-relevant evidence>
    Details: <verbose diagnostics, redacted>
    Remediation: <only for warn/fail>
```

JSON output emits one pretty-printed schema object to stdout. It must not include banners, color, labels, or mixed human text.

`--json --verbose` uses the same schema, field set, and check order. It only enriches `details.diagnostics` and `resolution_trace`.

If report construction fails in JSON mode, emit no partial JSON and write this to stderr:

```text
cfs proxy doctor: failed to produce valid cfs.proxy_doctor.v1 report
```

## Open Follow-Ups

- Freeze golden examples for pass, warn, fail, verbose warn, JSON warn, and JSON verbose fail.
- Define exact per-check `details` fields for all eleven v1 checks.
- Decide the migration window only if a top-level proxy diagnostics alias already exists in released material.

