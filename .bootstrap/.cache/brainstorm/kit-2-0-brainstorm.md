# Kit 2.0 Brainstorm — Session State

**Topic:** Kit 2.0 (sub-agents, marketplace, skills, cfs script integration)
**Org:** Constructor Fabric
**Saved at:** Round 6, Q1/8 (session paused for save)

---

## Current Session State

- `round_count`: 5 complete, round 6 in progress
- `BRAINSTORM_MAX_ROUNDS`: 10
- `pending_round_kind`: topic
- `topic_current`: T5 — ScriptInterface / ScriptContext independent versioning
- `round_6_position`: Q1/8 (unanswered — resume here)

---

## Open Questions

| decision_key | description | reason |
|---|---|---|
| `subagent_discovery_host_tools_caching` | Caching walk-up agent scan (TTL + invalidation on kit ops) | user_skipped (round 2) |

---

## Decisions Log

### Rounds 1 + 2 (challenge) — Marketplace & Ecosystem

| decision_key | decision | source |
|---|---|---|
| `marketplace_model_choice` | Hybrid: GitHub owner/repo as primary install mechanism + optional community registry index. Registry must implement a standardized metadata schema (`kit.json`) and maintain index freshness SLA (max 7 days stale). GitHub Release/tag = version authority. | accepted + R2 delta |
| `kit_dependency_resolution` | Declarative kit dependencies in `manifest.toml` with semver constraints. Single-version-per-kit rule. Conflict → fail with full dependency chain visualization in the error message. | accepted + R2 delta |
| `kit_namespace_collision` | MANDATORY `cf-{kit-slug}-{name}` naming everywhere. On slug conflict → interactive rename prompt with suggested `{kit-slug}-{random-short-word}` default. | custom |
| `community_kit_trust_model` | Official marketplace (Constructor Fabric, highest trust) + unofficial marketplaces with delegated trust. Mandatory CLI disclaimer for unofficial kits: "This kit is from an unofficial marketplace; Constructor Fabric does not vet or endorse it." Liability waiver required for unofficial marketplace operators. | custom + R2 delta |
| `kit_script_sandboxing` | Scripts are Python packages satisfying an interface contract. cfs imports the package, validates the interface/protocol, runs if compliant, returns error if not. No subprocess/shell. Security enforced via marketplace vetting at publish time. | custom |
| `kit_revocation_model` | Primary: GitHub. Secondary: Constructor Fabric maintains a **canonical** blocklist for the official marketplace. Community blocklists are advisory only. `--force` to bypass. | accepted + R2 delta |
| `kit_search_discovery_ux` | `cfs kit search <query>` across all configured marketplaces. Results include marketplace source label. `--marketplace <name>` filter. Default search order: official marketplace first, then community registries. `cfs marketplace add/remove/list`. `cfs kit list [--marketplace <name>]`. | accepted + R2 delta |
| `kit_script_invocation_surface` | `cfs script run <name>`, `cfs script list [--kit <slug>]`, `cfs script help <name>` — scripts as first-class CLI citizens. `cfs script help` shows kit owner, marketplace source, package dependencies. | accepted + R2 delta |
| `kit_update_notification_ux` | `cfs kit list --outdated`, version pinning, opt-in auto-update (`--auto`), interactive diff preserved. | accepted |
| `kit_author_incentive_model` | Phase 1: featured placement in official marketplace + monthly newsletter featuring top kits + advisory council access for top contributors. Phase 2: author profiles with metrics, monetization. | custom |
| `first_party_vs_community_kit_strategy` | Core bundles nothing. Constructor Fabric publishes SDLC, testing, docs kits as reference implementations to the official marketplace. Explicit commitment: 2–3 additional first-party kits within 12 months of Kit 2.0 release. | accepted + R2 delta |
| `community_governance_model` | Hybrid: Constructor Fabric owns infrastructure and code of conduct. Elected review board (kit authors + CF rep). Transparent decision log published in registry repo. | accepted |
| `kit_bundled_subagent_support` | Extend `[[agents]]` manifest section for kit-bundled subagents: `name`, `description`, `tools`, `disallowedTools`, `worktree_isolation`. Generate host-tool definitions on `kit install`. Backward compatible. Add `manifest_version` field to signal feature support; v1 clients warn on unknown sections. | accepted + R2 delta |
| `subagent_discovery_host_tools` | Automatic walk-up scan of agent directories (`.claude/agents/`, etc.) on host-tool startup. `kit install` generates host-tool-native files. Consistent with ADR-0019. | accepted |
| `kit_subagent_lifecycle` | Persistent definitions: generated on `install/update`, stored on disk, loaded on IDE startup, removed on `uninstall`, regenerated on next `kit update` when manifest changes. | accepted |
| `kit_semver_enforcement` | Mandatory semver for official marketplace (`v1.0.0` / `1.0.0`). `--dev` flag required for non-semver installs (SHA/branch) to signal non-production use. | accepted + R2 delta |
| `kit_version_constraint_syntax` | npm-style: `^` (>=X <X+1), `~` (>=X.Y <X.Y+1), `=` (exact). Constraints applied at dependency graph resolution time. Clear error on unsatisfiable constraint. `cfs kit validate-constraints <manifest>` tool + comprehensive docs with examples. | accepted + R2 delta |
| `kit_breaking_change_policy` | Major bump required for breaking changes. Checklist (5 categories): (1) resource removal from manifest, (2) agent/skill/workflow contract changes, (3) script signature changes, (4) manifest schema changes, (5) workflow input/output schema changes. Migration guide template for kit authors. | accepted + R2 delta |

---

### Round 3 — Python Script Interface Contract

| decision_key | decision | source |
|---|---|---|
| `script_discovery_mechanism` | `[[scripts]]` section in `manifest.toml` v2.0 with fields: `id`, `source_package`, `entry_point`, `description`, `version_constraint`. Mirrors `[[agents]]`/`[[skills]]` pattern from ADR-0019. | accepted |
| `script_namespace_enforcement` | `cf-{kit-slug}-{name}` convention applies to the **Python package name** (in `pyproject.toml`). Internal module name uses Python notation (`cf_kitslug_name`). Prevents PyPI collisions. | accepted |
| `script_installation_mechanism` | Scripts are Python packages listed as dependencies in the kit's `pyproject.toml`. Installed via pip on `cfs kit install`. Scripts may declare their own dependencies. | accepted |
| `script_interface_contract_definition` | `typing.Protocol` — `ScriptInterface` with required methods: `run(context: ScriptContext) -> ScriptResult` and `help() -> str`. No forced inheritance. Python 3.8+. | accepted |
| `script_interface_validation_strategy` | `inspect.signature()` at import time. Checks: (1) package imports without error, (2) `run()` and `help()` exist as callables, (3) `run()` signature matches contract. `InterfaceError` with clear message on mismatch. Fail fast — no suppression. | accepted |
| `script_capability_boundary` | Scripts may import any packages from cfs and use cfs as a library/SDK. No runtime restrictions. Security is enforced at the marketplace level (vetting at publish time). | custom |
| `script_help_text_source` | Primary: `help()` method return value (part of `ScriptInterface` Protocol). Fallback: `__doc__` of `run()`. Optional supplementary `.md` files. Dynamic `help()` allowed. | accepted |
| `script_authoring_workflow` | `cfs script scaffold <name>` — generates Python package template in kit's `scripts/`: `__init__.py`, `run.py`, `help.py`, `pyproject.toml` with `cf-{kit-slug}-{name}` naming. Validates structure on generation. | accepted |
| `script_error_messages` | Validation error: formatted message with suggestion (e.g., "Expected signature: ..."). Runtime error: user-friendly message + `--verbose` for full traceback. JSON mode always includes full error details. | accepted |
| `script_quality_assessment` | Both required for official marketplace: automated (interface validation via `inspect.signature`, mypy type hints check, docstring presence) + manual security review (what does the script do with cfs SDK?). | accepted |
| `script_marketplace_listing` | Listing includes: script name, description (from `help()`), kit owner, kit GitHub URL, script version, interface version (`ScriptInterface v1`), dependencies, last updated, download count. Searchable by kit, owner, tags. | accepted |
| `script_community_incentive` | Phase 1: featured listing for quality scripts + download stats visible to author + recognition in kit `SKILL.md`. Phase 2: revenue sharing. Mirrors kit incentive model. | accepted |
| `script_manifest_contract` | `[[scripts]]` in `manifest.toml` v2.0: `id`, `source_package`, `entry_point`, `description`, `version_constraint`. `pyproject.toml` declares script packages as pip dependencies. `entry_points` optional for ecosystem interop. | accepted |
| `script_lifecycle_management` | Lazy-loaded on first `cfs script run <name>`. Module cached within process. Cache invalidated on package version change. Keeps cfs startup fast. | accepted |
| `script_invocation_surface` | Arguments passed via a **typed class** (dataclass or pydantic model), not a plain dict. Script declares its args schema; cfs parses CLI flags and instantiates the class. | custom |
| `script_interface_versioning` | Two independent tracks: (1) package semver (increments on any change), (2) interface version (`ScriptInterface v{N}`) — increments only on breaking changes to `run()` or `help()`. Both declared in manifest and shown in marketplace. | accepted |
| `script_breaking_change_policy` | Major bump required for: (1) `run()` signature change (params or return type), (2) `help()` signature change, (3) args class schema change (field removal/rename), (4) `ScriptInterface` version change. Minor: new optional params with defaults. Patch: bugfix, docs. | accepted |
| `script_backward_compatibility_guarantee` | cfs supports the **current + 5 previous** `ScriptInterface` versions. Scripts targeting older versions (>5 back) must be updated or deprecated. | custom |

---

### Round 4 — ScriptContext & ScriptResult Contract

**ScriptContext (final structure):**
```python
@dataclass
class ScriptContext:
    project_root: Path
    studio_path: Path
    logger: logging.Logger
    args: T                       # typed args class instance
    version: int                  # current=1
    invoked_by: str
    invocation_time: datetime
    script_version: str
    kit_metadata: dict[str, semver.Version]  # direct deps only, pinned versions
```
_ScriptContext contains only what `cfs info` shows. Everything else is a direct import from the cfs SDK._

**ScriptResult (final structure):**
```python
@dataclass
class ScriptResult:
    success: bool                           # True iff exit_code == 0
    exit_code: int                          # 0–255; conventions: 0=ok, 1=err, 2=warn, 3+=custom
    output: Union[str, dict, list, None]    # plain mode: indented JSON for dict/list
                                            # dict may contain _redact_keys: list[str]
```
_Buffered output only. Streaming via logger._

| decision_key | decision | source |
|---|---|---|
| `ctx_kit_metadata_structure` | Direct dependencies only, resolved pinned versions as `semver.Version` objects. | accepted |
| `ctx_artifact_registry_interface` | No special artifact API in ScriptContext — scripts import existing cfs classes directly (cfs as SDK). | custom |
| `ctx_capability_boundary_sdk_access` | ScriptContext contains only what `cfs info` shows. Everything else — direct import from cfs SDK. | custom |
| `result_sensitive_data_handling` | `ScriptResult.output` dict may include `_redact_keys: list[str]`. cfs redacts those values in logs and JSON output. | accepted |
| `ctx_logger_interface` | Standard `logging.Logger` with cfs-configured handlers (console + file). JSON structured logging controlled at cfs level, not per-script. | accepted |
| `result_output_format_flexibility` | `Union[str, dict, list, None]`. Plain mode: pretty-print dict/list as indented JSON. JSON mode: passed as-is in `output` field. | accepted |
| `ctx_execution_metadata` | `invoked_by: str`, `invocation_time: datetime`, `script_version: str` in ScriptContext. `request_id` deferred. | accepted |
| `result_success_semantics` | Boolean `success` + `exit_code: int`. `success=True` ↔ `exit_code=0`. Unix-compatible. Scripts use `exit_code` for nuance. | accepted |
| `ctx_version_and_interface_compat` | `ScriptContext.version: int` (current=1). cfs fails with clear error if script requires `version > cfs.ctx_version`. Supports current + 5 previous. | accepted |
| `result_streaming_output` | Buffered output only (`str/dict/list`). For streaming, scripts write to `logger`; cfs captures and buffers. Revisit if streaming becomes critical. | accepted |
| `ctx_backward_compat_guarantees` | ScriptContext fields are **never removed** — only added. New fields must have sensible defaults (`None`, empty dict, etc.). Scripts safely ignore unknown fields. | accepted |
| `ctx_exit_code_range` | 0–255 (Unix standard). Documented conventions: 0=success, 1=error, 2=warning, 3+=custom. Not enforced. | accepted |

---

### Round 5 — Kit Author Scaffolding & DX

**Full kit author workflow:**
```
cfs kit new <name> [--template minimal|full]
  → edit manifest.toml, SKILL.md, artifacts/
cfs kit version bump [major|minor|patch]
cfs kit validate               # syntax, namespaces, interface, deps, circular deps, SKILL.md
cfs kit install --path .       # local test (v1); cfs kit dev (file watch) → p2
cfs kit checklist              # pre-publish readiness (PASS/WARN/FAIL per item with hints)
cfs kit publish --repo <org/repo>  # validate → GitHub Release → marketplace registration
```

| decision_key | decision | source |
|---|---|---|
| `kit_new_scaffold_contents` | Generates: `manifest.toml`, `SKILL.md`, `README.md`, one stub artifact, empty stubs for `scripts/`, `agents/`, `workflows/`. | accepted |
| `kit_slug_reservation_early_check` | Local check against installed kits (mandatory) + optional online check against marketplace. Interactive rename on conflict. `--force` to bypass. | accepted |
| `kit_local_dev_workflow` | `cfs kit install --path ./my-kit` in v1 (symlink or local install). `cfs kit dev` (watch mode) → p2. | accepted |
| `kit_publish_mechanism` | `cfs kit publish --repo <owner/repo>`: validate kit → create GitHub Release with semver tag (via `GITHUB_TOKEN`) → register in marketplace. Fallback: manual PR to registry for p1. | accepted |
| `kit_validate_scope` | Full validation: manifest.toml syntax, semver format, namespace conventions, required files (SKILL.md, README), script interface (`inspect.signature`), agent definitions, version constraint syntax, SKILL.md syntax, workflow references to valid artifact kinds, circular dependency detection. JSON output with per-file errors and warnings. | accepted |
| `kit_semver_enforcement_timing` | `cfs kit new` generates `version = "0.0.1"`. First publish to official marketplace requires explicit bump to `1.0.0` (or `--pre-release` flag for `0.x`). Helper: `cfs kit version bump [major\|minor\|patch]`. | accepted |
| `kit_template_variants` | `cfs kit new <name> --template [minimal\|full]`. `minimal` = manifest + README. `full` = minimal + `scripts/`, `agents/`, `workflows/`, `SKILL.md`, one complete artifact example. Default (no flag): `minimal`. | accepted |
| `kit_author_workflow_checklist` | `cfs kit checklist` — PASS/WARN/FAIL per item: README with usage examples, SKILL.md with agent commands, at least one artifact example, manifest `version` matches git tag (if in repo), semver ≥ 1.0.0. Remediation hints per failing item. | accepted |

---

## Round 6 (in progress) — T5: ScriptInterface / ScriptContext Independent Versioning

**Current position:** Q1/8 — unanswered. Resume from here.

**Question queue with proposed defaults:**

| Q | persona | decision_key | proposed_default |
|---|---|---|---|
| 1 | E1 | `iface_ctx_decoupling_coexistence_model` | Full independence: script declares `interface_version` + `context_version_min/max` separately. Allows adopting new `run()` signature without a context version bump, and vice versa. |
| 2 | E2 | `iface_ctx_decoupling_validation_gates` | cfs rejects if actual `context_version < min` or `> max`. Script must handle optional new context fields gracefully. |
| 3 | E3 | `iface_ctx_decoupling_developer_clarity` | Publish migration guide with examples: v1→v2 interface upgrade without context bump, and v1→v2 context upgrade without interface bump. |
| 4 | E4 | `iface_ctx_decoupling_ecosystem_adoption` | cfs warns if a script declares a range narrower than the platform support window. Encourage wide ranges. |
| 5 | E5 | `iface_ctx_decoupling_subagent_integration` | `cfs.script_metadata(id)` → `{interface_version, context_version_min, context_version_max}`. Subagent checks against its own `context_version` before invoking. |
| 6 | E6 | `iface_ctx_decoupling_backward_compat_matrix` | Both tracks maintain a **5-version window** for symmetry. Symmetric windows simplify reasoning; avoids edge cases. |
| 7 | E1 | `iface_ctx_decoupling_manifest_syntax` | Separate fields in `[[scripts]]`: `interface_version`, `context_version_min`, `context_version_max`. Explicit fields reduce parsing errors and make manifest diffs reviewable. |
| 8 | E2 | `iface_ctx_decoupling_security_implications` | cfs validates version combinations at load time; rejects impossible ranges (e.g., `context_version_max > current + 10`). Signed manifests required for official marketplace. |

**Panel note on conflicts:** Current decision `ctx_version_and_interface_compat` assumes 1:1 coupling ("fail if `version > cfs.ctx_version`"). Decoupling replaces the single required version with a `min/max` range declaration. This needs to be captured as an update to that decision once Q1 is answered.

---

## Topics Not Yet Covered

| label | topic | why it matters |
|---|---|---|
| A | Hook contract in manifest (validation/generation hooks) — v1 or p2? | Kit authors can't plan without a contract |
| B | Kit certification ("Verified Kit") and Constructor Fabric liability boundaries | Official marketplace needs a trust policy |
| C | `kit.lock` — reproducible builds with transitive dependencies | CI/CD and deterministic installs |
