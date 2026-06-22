"""
Kit Manifest Parser and Validator

Parses and validates ``manifest.toml`` — the declarative kit installation
manifest.  When present in a kit package root, the manifest governs
installation and update: only declared resources are installed.

@cpt-algo:cpt-studio-algo-kit-manifest-install:p1
@cpt-algo:cpt-studio-algo-project-extensibility-resolve-includes:p1
@cpt-algo:cpt-studio-algo-project-extensibility-merge-components:p1
@cpt-algo:cpt-studio-algo-project-extensibility-section-appending:p1
@cpt-dod:cpt-studio-dod-project-extensibility-includes:p1
"""

# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-datamodel
from __future__ import annotations

import dataclasses
import re
import string
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ._tomllib_compat import tomllib


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ManifestResource:
    """A single resource declared in ``manifest.toml``."""

    id: str
    source: str
    default_path: str
    type: str  # "file" or "directory"
    description: str = ""
    user_modifiable: bool = True
    kind: str = ""
    public: bool = False
    artifact_bindings: Dict[str, Dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Manifest:
    """Parsed representation of a kit ``manifest.toml``."""

    version: str
    root: str
    user_modifiable: bool
    resources: list[ManifestResource] = field(default_factory=list)
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-datamodel


# ---------------------------------------------------------------------------
# Manifest V2 Dataclasses
# @cpt-state:cpt-studio-state-project-extensibility-manifest-layer:p1
# @cpt-dod:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-component-entry
@dataclass(frozen=True)
class ComponentEntry:
    """Base class for V2 manifest component entries."""

    id: str
    description: str = ""
    prompt_file: str = ""
    source: str = ""
    agents: List[str] = field(default_factory=list)
    append: Optional[str] = None  # Trusted content appended to generated output; not sanitized
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-component-entry


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-agent-entry
@dataclass(frozen=True)
class AgentEntry(ComponentEntry):
    """Agent component with extended schema fields."""

    mode: str = "readwrite"
    isolation: bool = False
    model: str = ""
    tools: List[str] = field(default_factory=list)
    disallowed_tools: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    color: str = ""
    memory_dir: str = ""
    role: str = "any"
    target: str = "any"
    provider: str = "anthropic"
    reasoning_effort: Optional[str] = None
    context_window: Optional[str] = None
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-agent-entry


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-skill-entry
@dataclass(frozen=True)
class SkillEntry(ComponentEntry):
    """Skill component entry."""
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-skill-entry


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-workflow-entry
@dataclass(frozen=True)
class WorkflowEntry(ComponentEntry):
    """Workflow component entry."""
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-workflow-entry


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-rule-entry
@dataclass(frozen=True)
class RuleEntry(ComponentEntry):
    """Rule component entry."""
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-rule-entry


def resolve_project_root_from_core_data(
    data: Dict[str, Any],
    studio_dir: Path,
    *,
    default_to_parent: bool,
) -> Optional[Path]:
    """Resolve the effective project root from parsed ``core.toml`` data."""
    raw_root = data.get("project_root")
    if isinstance(raw_root, str) and raw_root.strip():
        root_path = Path(raw_root.strip())
        if root_path.is_absolute():
            return root_path.resolve()
        return (studio_dir / root_path).resolve()
    if default_to_parent:
        return studio_dir.parent.resolve()
    return None


def load_project_root_from_core_toml(
    core_toml: Path,
    studio_dir: Path,
    *,
    default_to_parent: bool,
) -> Optional[Path]:
    """Read ``core.toml`` and resolve its effective project root."""
    data = load_toml_file(core_toml)
    if data is None:
        return None
    return resolve_project_root_from_core_data(
        data,
        studio_dir,
        default_to_parent=default_to_parent,
    )


def load_toml_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load a TOML file into a dict, returning None on failure."""
    if not path.is_file():
        return None
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-manifest-v2
@dataclass(frozen=True)
class ManifestV2:
    """Parsed representation of a V2 manifest.toml."""

    version: str
    includes: List[str] = field(default_factory=list)
    agents: List[AgentEntry] = field(default_factory=list)
    skills: List[SkillEntry] = field(default_factory=list)
    workflows: List[WorkflowEntry] = field(default_factory=list)
    rules: List[RuleEntry] = field(default_factory=list)
    resources: List[ManifestResource] = field(default_factory=list)
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-manifest-v2


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-layer-state
class ManifestLayerState(Enum):
    """State of a manifest layer in the discovery state machine."""

    UNDISCOVERED = "UNDISCOVERED"
    LOADED = "LOADED"
    PARSE_ERROR = "PARSE_ERROR"
    INCLUDE_ERROR = "INCLUDE_ERROR"
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-layer-state


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-manifest-layer
@dataclass(frozen=True)
class ManifestLayer:
    """Envelope for a discovered manifest layer."""

    scope: str
    path: Path
    manifest: Optional[ManifestV2] = None
    state: ManifestLayerState = ManifestLayerState.UNDISCOVERED
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-manifest-layer


# ---------------------------------------------------------------------------
# Manifest V2 Parsing
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-component-helpers
_COMPONENT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_VALID_AGENT_MODES = {"readwrite", "readonly"}
_VALID_AGENT_ROLES = {"generate", "analyze", "planning", "any"}
_VALID_AGENT_TARGETS = {"codebase", "artifacts", "any"}
_VALID_AGENT_PROVIDERS = {"anthropic", "openai"}
_VALID_AGENT_MODEL_TIERS = {
    "cf:tier:cheap", "cf:tier:balanced", "cf:tier:expensive",
    "cf:inherit", "cf:auto",
}
_VALID_AGENT_EFFORTS = {"low", "medium", "high", "max"}
_VALID_AGENT_CONTEXTS = {"low", "medium", "high", "max"}
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-component-helpers


def _ensure_agent_table(path: Path, idx: int, raw: Any) -> Dict[str, Any]:
    """Return an agent table or raise a section-specific error."""
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: [[agents]][{idx}] must be a table")
    return raw


def _validate_agent_null_fields(path: Path, idx: int, agent_id: str, raw: Dict[str, Any]) -> None:
    """Reject TOML nulls for enum-backed agent fields."""
    for field_name in ("mode", "role", "target", "provider"):
        if field_name in raw and raw[field_name] is None:
            raise ValueError(
                f"{path}: [[agents]][{idx}] ('{agent_id}'): "
                f"null is not a valid {field_name}"
            )


def _parse_agent_choice(
    path: Path,
    idx: int,
    agent_id: str,
    raw: Dict[str, Any],
    field_name: str,
    default: str,
    valid: set[str],
) -> str:
    """Parse and validate a required agent enum field."""
    return _validate_agent_choice(
        path,
        idx,
        agent_id,
        field_name,
        str(raw.get(field_name, default)).strip(),
        valid,
    ) or default


def _parse_optional_agent_choice(
    path: Path,
    idx: int,
    agent_id: str,
    raw: Dict[str, Any],
    field_name: str,
    valid: set[str],
) -> Optional[str]:
    """Parse and validate an optional agent enum field."""
    value = raw.get(field_name)
    return _validate_agent_choice(
        path,
        idx,
        agent_id,
        field_name,
        str(value).strip() if value is not None else None,
        valid,
    )


def _parse_agent_entry(path: Path, idx: int, raw: Any) -> AgentEntry:
    """Parse one ``[[agents]]`` entry with schema validation."""
    raw_agent = _ensure_agent_table(path, idx, raw)
    base = _parse_base_fields(raw_agent, manifest_path=path)
    agent_id = base["id"]
    _validate_component_id(path, "agents", idx, agent_id)

    tools = list(raw_agent.get("tools", []))
    disallowed_tools = list(raw_agent.get("disallowed_tools", []))
    if tools and disallowed_tools:
        raise ValueError(
            f"{path}: [[agents]][{idx}] ('{agent_id}'): "
            "tools and disallowed_tools are mutually exclusive"
        )

    _validate_agent_null_fields(path, idx, agent_id, raw_agent)
    raw_model = str(raw_agent.get("model", "")).strip()
    if raw_model.startswith("cf:") and raw_model not in _VALID_AGENT_MODEL_TIERS:
        raise ValueError(
            f"{path}: [[agents]][{idx}] ('{agent_id}'): invalid model {raw_model!r}; "
            f"expected one of {sorted(_VALID_AGENT_MODEL_TIERS)} or a raw provider model id"
        )

    return AgentEntry(
        **base,
        mode=_parse_agent_choice(path, idx, agent_id, raw_agent, "mode", "readwrite", _VALID_AGENT_MODES),
        isolation=bool(raw_agent.get("isolation", False)),
        model=raw_model,
        tools=tools,
        disallowed_tools=disallowed_tools,
        skills=list(raw_agent.get("skills", [])),
        color=str(raw_agent.get("color", "")).strip(),
        memory_dir=str(raw_agent.get("memory_dir", "")).strip(),
        role=_parse_agent_choice(path, idx, agent_id, raw_agent, "role", "any", _VALID_AGENT_ROLES),
        target=_parse_agent_choice(path, idx, agent_id, raw_agent, "target", "any", _VALID_AGENT_TARGETS),
        provider=_parse_agent_choice(
            path,
            idx,
            agent_id,
            raw_agent,
            "provider",
            "anthropic",
            _VALID_AGENT_PROVIDERS,
        ),
        reasoning_effort=_parse_optional_agent_choice(
            path,
            idx,
            agent_id,
            raw_agent,
            "reasoning_effort",
            _VALID_AGENT_EFFORTS,
        ),
        context_window=_parse_optional_agent_choice(
            path,
            idx,
            agent_id,
            raw_agent,
            "context_window",
            _VALID_AGENT_CONTEXTS,
        ),
    )


def _validate_agent_choice(
    path: Path,
    idx: int,
    agent_id: str,
    field_name: str,
    value: Optional[str],
    valid: set[str],
) -> Optional[str]:
    """Validate an optional generated-agent enum field."""
    if value is None:
        return None
    if value not in valid:
        raise ValueError(
            f"{path}: [[agents]][{idx}] ('{agent_id}'): invalid {field_name} {value!r}; "
            f"expected one of {sorted(valid)}"
        )
    return value


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-v2
def parse_manifest_v2(path: Path) -> ManifestV2:
    """Parse a ``manifest.toml`` file and return a ``ManifestV2``.

    Supports both version ``"2.0"`` (component sections) and ``"1.0"``
    (resources-only, backward compatibility wrapper).

    Raises ``ValueError`` on parse errors with path and details.
    """
    if not path.is_file():
        raise ValueError(f"{path}: manifest.toml not found")

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: TOML parse error: {exc}") from exc

    # Determine version — support both [manifest].version and top-level version
    meta = data.get("manifest", {})
    version = meta.get("version")
    if version is None:
        version = data.get("version")
    if not version:
        raise ValueError(f"{path}: missing [manifest].version")
    version = str(version).strip()

    if version == "1.0":
        return _parse_v1_as_v2(path, data)
    if version == "2.0":
        return _parse_v2_sections(path, data)
    raise ValueError(f"{path}: unsupported manifest version '{version}'")
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-v2


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-v1-compat
def _parse_v1_as_v2(_path: Path, data: Dict[str, Any]) -> ManifestV2:
    """Wrap a v1.0 manifest as a ManifestV2 with only resources populated."""
    raw_resources = data.get("resources", [])
    resources: List[ManifestResource] = []
    for r in raw_resources:
        resources.append(ManifestResource(
            id=str(r.get("id", "")).strip(),
            source=str(r.get("source", "")).strip(),
            default_path=str(r.get("default_path", "")).strip(),
            type=str(r.get("type", "")).strip(),
            description=str(r.get("description", "")).strip(),
            user_modifiable=bool(r.get("user_modifiable", True)),
        ))
    return ManifestV2(version="1.0", resources=resources)
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-v1-compat


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-v2-sections
def _parse_v2_sections(path: Path, data: Dict[str, Any]) -> ManifestV2:
    """Parse v2.0 manifest with component sections."""
    meta = data.get("manifest", {})
    # Support includes under [manifest] or at top level
    inc = meta.get("includes")
    if inc is None:
        inc = data.get("includes", [])
    includes = list(inc)

    agents = _parse_agents(path, data.get("agents", []))
    skills = _parse_skills(path, data.get("skills", []))
    workflows = _parse_workflows(path, data.get("workflows", []))
    rules = _parse_rules(path, data.get("rules", []))

    # Backward-compat: v2.0 may still have [[resources]]
    resources = _parse_resources(data.get("resources", []))

    # Reserved sections: accept and ignore [[hooks]] and [[permissions]]

    return ManifestV2(
        version="2.0",
        includes=includes,
        agents=agents,
        skills=skills,
        workflows=workflows,
        rules=rules,
        resources=resources,
    )
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-v2-sections


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-section-helpers
def _validate_component_id(path: Path, section: str, idx: int, cid: str) -> None:
    """Validate a component id matches the required pattern."""
    if not cid:
        raise ValueError(f"{path}: [[{section}]][{idx}].id is required")
    if not _COMPONENT_ID_RE.match(cid):
        raise ValueError(
            f"{path}: [[{section}]][{idx}].id '{cid}' must match "
            "^[a-z][a-z0-9_-]*$"
        )


def _parse_base_fields(raw: Dict[str, Any], manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    """Extract base ComponentEntry fields from a raw TOML dict."""
    raw_append = raw.get("append")
    raw_append_file = raw.get("append_file")
    comp_id = str(raw.get("id", "")).strip()
    if raw_append is not None and raw_append_file is not None:
        raise ValueError(f"Component '{comp_id}': 'append' and 'append_file' are mutually exclusive")
    if raw_append is not None and not isinstance(raw_append, str):
        raise ValueError(f"Component '{comp_id}': 'append' must be a string, got {type(raw_append).__name__}")
    # append_file: read content from a file path relative to the project root
    # (the nearest ancestor directory containing .git).
    # Must be relative — absolute paths are rejected to prevent arbitrary file reads.
    if raw_append_file is not None:
        if not isinstance(raw_append_file, str):
            raise ValueError(
                f"Component '{comp_id}': 'append_file' must be a string, got "
                f"{type(raw_append_file).__name__}"
            )
        if manifest_path is None:
            raise ValueError(f"Component '{comp_id}': 'append_file' requires manifest_path context")
        append_path = Path(raw_append_file)
        if append_path.is_absolute():
            raise ValueError(f"Component '{comp_id}': 'append_file' must be a relative path, got '{raw_append_file}'")
        # Resolve relative to the active checkout root (nearest .git ancestor).
        # In a git worktree, .git is a file pointing at shared metadata; do not
        # follow that pointer for content lookup or worktree-local files would
        # be read from the wrong checkout.
        repo_root = manifest_path.parent
        found_root = False
        while repo_root != repo_root.parent:
            git_entry = repo_root / ".git"
            if git_entry.exists():
                found_root = True
                break
            repo_root = repo_root.parent
        if not found_root:
            raise ValueError(f"Component '{comp_id}': no .git ancestor found for append_file resolution")
        append_path = (repo_root / append_path).resolve()
        # Path containment: resolved path must stay within the repo root
        try:
            append_path.relative_to(repo_root.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Component '{comp_id}': append_file '{raw_append_file}' escapes repo root '{repo_root}'"
            ) from exc
        if not append_path.is_file():
            raise ValueError(f"Component '{comp_id}': append_file '{raw_append_file}' not found at {append_path}")
        raw_append = append_path.read_text(encoding="utf-8")
    return {
        "id": comp_id,
        "description": str(raw.get("description", "")).strip(),
        "prompt_file": str(raw.get("prompt_file", "")).strip(),
        "source": str(raw.get("source", "")).strip(),
        "agents": list(raw.get("agents", [])),
        "append": raw_append,
    }
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-section-helpers


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-agents
def _parse_agents(path: Path, raw_agents: List[Any]) -> List[AgentEntry]:
    """Parse [[agents]] section with extended schema validation."""
    agents: List[AgentEntry] = []
    for idx, raw in enumerate(raw_agents):
        agents.append(_parse_agent_entry(path, idx, raw))
    return agents
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-agents


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-other-sections
def _parse_skills(path: Path, raw_skills: List[Any]) -> List[SkillEntry]:
    """Parse [[skills]] section."""
    skills: List[SkillEntry] = []
    for idx, raw in enumerate(raw_skills):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: [[skills]][{idx}] must be a table")
        base = _parse_base_fields(raw, manifest_path=path)
        _validate_component_id(path, "skills", idx, base["id"])
        skills.append(SkillEntry(**base))
    return skills


def _parse_workflows(path: Path, raw_workflows: List[Any]) -> List[WorkflowEntry]:
    """Parse [[workflows]] section."""
    workflows: List[WorkflowEntry] = []
    for idx, raw in enumerate(raw_workflows):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: [[workflows]][{idx}] must be a table")
        base = _parse_base_fields(raw, manifest_path=path)
        _validate_component_id(path, "workflows", idx, base["id"])
        workflows.append(WorkflowEntry(**base))
    return workflows


def _parse_rules(path: Path, raw_rules: List[Any]) -> List[RuleEntry]:
    """Parse [[rules]] section."""
    rules: List[RuleEntry] = []
    for idx, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: [[rules]][{idx}] must be a table")
        base = _parse_base_fields(raw, manifest_path=path)
        _validate_component_id(path, "rules", idx, base["id"])
        rules.append(RuleEntry(**base))
    return rules


def _parse_resources(raw_resources: List[Any]) -> List[ManifestResource]:
    """Parse [[resources]] section (shared between v1 and v2)."""
    resources: List[ManifestResource] = []
    for r in raw_resources:
        if not isinstance(r, dict):
            continue
        resources.append(ManifestResource(
            id=str(r.get("id", "")).strip(),
            source=str(r.get("source", "")).strip(),
            default_path=str(r.get("default_path", "")).strip(),
            type=str(r.get("type", "")).strip(),
            description=str(r.get("description", "")).strip(),
            user_modifiable=bool(r.get("user_modifiable", True)),
        ))
    return resources
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-parse-other-sections


# ---------------------------------------------------------------------------
# Includes Resolution
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-includes-helpers
# Maximum chain size including the root manifest itself.  The root is counted
# when the chain is seeded (``include_chain = {root_manifest_path}``), so a
# value of 4 allows 3 effective nesting levels beyond the root (root → A → B → C).
_MAX_INCLUDE_DEPTH = 4


def _rewrite_component_paths(
    component: Any,
    included_dir: Path,
    trusted_root: Path,
) -> Any:
    """Return a copy of *component* with prompt_file and source rewritten.

    Paths that are non-empty and not already absolute are made absolute by
    resolving them relative to *included_dir*.  The resolved path must stay
    within *trusted_root* or a ``ValueError`` is raised.
    """
    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-rewrite-paths
    kwargs: Dict[str, Any] = {}
    for fname in ("prompt_file", "source"):
        val: str = getattr(component, fname, "")
        if val and not Path(val).is_absolute():
            resolved = (included_dir / val).resolve()
            try:
                resolved.relative_to(trusted_root)
            except ValueError as exc:
                raise ValueError(
                    f"Component path '{val}' in included manifest escapes trusted root"
                ) from exc
            kwargs[fname] = str(resolved)
        else:
            kwargs[fname] = val
    # Copy all other fields unchanged by rebuilding via __class__
    existing = {f.name: getattr(component, f.name) for f in dataclasses.fields(component)}
    existing.update(kwargs)
    return component.__class__(**existing)
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-rewrite-paths
# @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-includes-helpers


def _initialize_include_resolution(
    manifest_dir: Path,
    include_chain: Optional[Set[Path]],
    include_order: Optional[List[Path]],
    trusted_root: Optional[Path],
) -> tuple[Set[Path], List[Path], Path]:
    """Seed include traversal state for the top-level manifest."""
    if include_chain is None or include_order is None:
        root_manifest_path = (manifest_dir / "manifest.toml").resolve()
        include_chain = {root_manifest_path}
        include_order = [root_manifest_path]
    if trusted_root is None:
        trusted_root = manifest_dir.resolve()
    return include_chain, include_order, trusted_root


def _manifest_component_ids(manifest: ManifestV2) -> set[tuple[str, str]]:
    """Collect component ids keyed by manifest section."""
    return (
        {("agents", component.id) for component in manifest.agents}
        | {("skills", component.id) for component in manifest.skills}
        | {("workflows", component.id) for component in manifest.workflows}
        | {("rules", component.id) for component in manifest.rules}
    )


def _resolve_included_manifest_path(
    manifest_dir: Path,
    include_path_str: str,
    trusted_root: Path,
    include_chain: Set[Path],
    include_order: List[Path],
) -> Path:
    """Resolve one include path and enforce traversal, cycle, and depth guards."""
    resolved = (manifest_dir / include_path_str).resolve()
    try:
        resolved.relative_to(trusted_root)
    except ValueError as exc:
        raise ValueError(
            f"Include path '{include_path_str}' escapes the trusted root "
            f"'{trusted_root}' — path traversal is not allowed"
        ) from exc
    if resolved in include_chain:
        chain_str = " -> ".join(str(path) for path in include_order) + f" -> {resolved}"
        raise ValueError(f"Circular include detected: {chain_str}")
    if len(include_chain) >= _MAX_INCLUDE_DEPTH:
        raise ValueError(
            f"Max include depth of {_MAX_INCLUDE_DEPTH} exceeded "
            f"while resolving '{include_path_str}' "
            f"(chain depth: {len(include_chain)})"
        )
    return resolved


def _rewrite_manifest_components(
    manifest: ManifestV2,
    included_dir: Path,
    trusted_root: Path,
) -> tuple[list[AgentEntry], list[SkillEntry], list[WorkflowEntry], list[RuleEntry]]:
    """Rewrite component file paths from an included manifest to absolute paths."""
    return (
        [_rewrite_component_paths(component, included_dir, trusted_root) for component in manifest.agents],
        [_rewrite_component_paths(component, included_dir, trusted_root) for component in manifest.skills],
        [_rewrite_component_paths(component, included_dir, trusted_root) for component in manifest.workflows],
        [_rewrite_component_paths(component, included_dir, trusted_root) for component in manifest.rules],
    )


def _filter_shadowed_components(
    rewritten_agents: list[AgentEntry],
    rewritten_skills: list[SkillEntry],
    rewritten_workflows: list[WorkflowEntry],
    rewritten_rules: list[RuleEntry],
    shadowed_ids: set[tuple[str, str]],
) -> tuple[list[AgentEntry], list[SkillEntry], list[WorkflowEntry], list[RuleEntry]]:
    """Drop included components shadowed by the including manifest."""
    if not shadowed_ids:
        return rewritten_agents, rewritten_skills, rewritten_workflows, rewritten_rules
    shadowed_agent_ids = {cid for section, cid in shadowed_ids if section == "agents"}
    shadowed_skill_ids = {cid for section, cid in shadowed_ids if section == "skills"}
    shadowed_workflow_ids = {cid for section, cid in shadowed_ids if section == "workflows"}
    shadowed_rule_ids = {cid for section, cid in shadowed_ids if section == "rules"}
    return (
        [component for component in rewritten_agents if component.id not in shadowed_agent_ids],
        [component for component in rewritten_skills if component.id not in shadowed_skill_ids],
        [component for component in rewritten_workflows if component.id not in shadowed_workflow_ids],
        [component for component in rewritten_rules if component.id not in shadowed_rule_ids],
    )


@dataclass
class _IncludeResolutionState:
    agents: List[AgentEntry]
    skills: List[SkillEntry]
    workflows: List[WorkflowEntry]
    rules: List[RuleEntry]
    resources: List[ManifestResource]
    includer_ids: set[tuple[str, str]]
    accumulated_includee_ids: set[tuple[str, str]] = field(default_factory=set)

    @classmethod
    def from_manifest(cls, manifest: ManifestV2) -> "_IncludeResolutionState":
        """Seed mutable include-resolution state from a manifest snapshot."""
        return cls(
            agents=list(manifest.agents),
            skills=list(manifest.skills),
            workflows=list(manifest.workflows),
            rules=list(manifest.rules),
            resources=list(manifest.resources),
            includer_ids=_manifest_component_ids(manifest),
        )


def _merge_included_manifest(
    state: _IncludeResolutionState,
    included_manifest: ManifestV2,
    included_dir: Path,
    trusted_root: Path,
    resolved: Path,
) -> None:
    rewritten_agents, rewritten_skills, rewritten_workflows, rewritten_rules = _rewrite_manifest_components(
        included_manifest,
        included_dir,
        trusted_root,
    )
    included_ids = _manifest_component_ids(
        ManifestV2(
            version=included_manifest.version,
            agents=rewritten_agents,
            skills=rewritten_skills,
            workflows=rewritten_workflows,
            rules=rewritten_rules,
        )
    )
    inter_includee_collisions = state.accumulated_includee_ids & included_ids
    if inter_includee_collisions:
        raise ValueError(
            f"Component ID collision between included manifests at '{resolved}': "
            f"{sorted(inter_includee_collisions)}"
        )
    shadowed_by_includer = state.includer_ids & included_ids
    rewritten_agents, rewritten_skills, rewritten_workflows, rewritten_rules = _filter_shadowed_components(
        rewritten_agents,
        rewritten_skills,
        rewritten_workflows,
        rewritten_rules,
        shadowed_by_includer,
    )
    state.agents.extend(rewritten_agents)
    state.skills.extend(rewritten_skills)
    state.workflows.extend(rewritten_workflows)
    state.rules.extend(rewritten_rules)
    state.resources.extend(included_manifest.resources)
    state.accumulated_includee_ids |= included_ids - shadowed_by_includer


# @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-resolve-includes-header
def resolve_includes(
    manifest: ManifestV2,
    manifest_dir: Path,
    include_chain: Optional[Set[Path]] = None,
    trusted_root: Optional[Path] = None,
    include_order: Optional[List[Path]] = None,
) -> ManifestV2:
    """Resolve the ``includes`` array in *manifest*, merging sub-manifests in.

    Loads each included ``manifest.toml``, rewrites their component paths to
    be absolute (relative to the *included* manifest's directory), checks for
    ID collisions, and merges the included components into the returned
    ``ManifestV2``.

    Args:
        manifest:      Parsed v2 manifest whose ``includes`` list to process.
        manifest_dir:  Directory that contains the current manifest file.
        include_chain: Set of already-visited absolute manifest file paths
                       (used for O(1) circular detection). Pass ``None`` for
                       the initial call.
        trusted_root:  Absolute directory that all include paths must stay
                       within (path-traversal guard). Defaults to
                       ``manifest_dir`` on the initial call and is propagated
                       unchanged through recursion.
        include_order: List of already-visited absolute manifest file paths in
                       traversal order (used to produce readable cycle error
                       messages). Pass ``None`` for the initial call; always
                       kept in sync with *include_chain*.

    Returns:
        A new ``ManifestV2`` instance with all included components merged in.

    Raises:
        ValueError: On path traversal, circular includes, depth exceeded, or
                    ID collision.
    """
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-resolve-includes-header
    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step1-read-includes
    if not manifest.includes:
        return manifest
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step1-read-includes

    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-init-collections
    include_chain, include_order, trusted_root = _initialize_include_resolution(
        manifest_dir,
        include_chain,
        include_order,
        trusted_root,
    )
    state = _IncludeResolutionState.from_manifest(manifest)
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-init-collections

    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2-foreach-include
    for include_path_str in manifest.includes:
        # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.1-resolve-path
        resolved = _resolve_included_manifest_path(
            manifest_dir,
            include_path_str,
            trusted_root,
            include_chain,
            include_order,
        )

        # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.4-parse-included
        included_manifest = parse_manifest_v2(resolved)
        included_dir = resolved.parent
        # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.4-parse-included

        # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.5-recurse
        included_manifest = resolve_includes(
            included_manifest,
            included_dir,
            include_chain | {resolved},
            trusted_root,
            include_order + [resolved],
        )
        # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.5-recurse

        # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.6-rewrite-paths
        _merge_included_manifest(
            state,
            included_manifest,
            included_dir,
            trusted_root,
            resolved,
        )
        # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2.8-merge
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step2-foreach-include

    # @cpt-begin:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step3-return
    return ManifestV2(
        version=manifest.version,
        includes=manifest.includes,
        agents=state.agents,
        skills=state.skills,
        workflows=state.workflows,
        rules=state.rules,
        resources=state.resources,
    )
    # @cpt-end:cpt-studio-algo-project-extensibility-resolve-includes:p1:inst-step3-return


# ---------------------------------------------------------------------------
# Multi-Layer Merging + Section Appending
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-provenance-record
@dataclass
class ProvenanceRecord:
    """Provenance metadata for a merged component.

    Records which layer won and which layers were overridden.
    """

    component_id: str
    component_type: str  # "agents", "skills", "workflows", or "rules"
    winning_scope: str
    winning_path: Path
    overridden: List[Tuple[str, Path]] = field(default_factory=list)
# @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-provenance-record


# @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-merged-components
@dataclass
class MergedComponents:
    """Result of merging multiple manifest layers.

    Contains one dict per component type mapping component IDs to the winning
    component entry, plus provenance metadata for each component.
    """

    agents: Dict[str, AgentEntry] = field(default_factory=dict)
    skills: Dict[str, SkillEntry] = field(default_factory=dict)
    workflows: Dict[str, WorkflowEntry] = field(default_factory=dict)
    rules: Dict[str, RuleEntry] = field(default_factory=dict)
    provenance: Dict[str, ProvenanceRecord] = field(default_factory=dict)
# @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-merged-components


# @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-merge-entry
def _merge_component_entry(
    outer: "ComponentEntry",
    inner: "ComponentEntry",
) -> "ComponentEntry":
    """Merge two component entries from adjacent layers.

    Applies two cross-layer composition rules:
    - **Source inheritance**: if the inner entry has no ``source`` or
      ``prompt_file``, inherit those fields from the outer entry so that an
      append-only inner entry can still locate its base content.
    - **Append accumulation**: concatenate outer ``append`` content (if any)
      before inner ``append`` content so all layer appends are preserved in
      resolution order (outermost first).

    All other fields follow inner-scope-wins (taken from *inner*).
    """
    inherited_source = inner.source or outer.source
    inherited_prompt_file = inner.prompt_file or outer.prompt_file

    parts = []
    if outer.append:
        parts.append(outer.append)
    if inner.append:
        parts.append(inner.append)
    accumulated_append: Optional[str] = "\n".join(parts) if parts else None

    return replace(
        inner,
        source=inherited_source,
        prompt_file=inherited_prompt_file,
        append=accumulated_append,
    )
# @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-merge-entry


# @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-merge-components-header
def merge_components(layers: List[ManifestLayer]) -> MergedComponents:
    """Merge component entries from multiple manifest layers.

    Iterates layers in resolution order (as provided — outermost first).
    Later (inner/higher-priority) layers overwrite earlier layers on the same
    component ID (last-writer-wins / inner-scope-wins).

    Only layers with ``state == ManifestLayerState.LOADED`` are processed.
    Layers with ``None`` manifest are skipped.

    Provenance is recorded for every component: the winning layer scope/path
    and a list of (scope, path) tuples for overridden layers.

    Args:
        layers: List of ``ManifestLayer`` in resolution order, outermost first.

    Returns:
        ``MergedComponents`` with all merged dicts and provenance metadata.
    """
    # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-merge-components-header
    # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step1-init
    merged = MergedComponents()
    # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step1-init

    # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-foreach-layer
    for layer in layers:
        # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2.1-skip-non-loaded
        if layer.state != ManifestLayerState.LOADED or layer.manifest is None:
            continue
        # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2.1-skip-non-loaded

        manifest = layer.manifest

        # Iterate all component sections with their type labels
        # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-inner
        sections: List[Tuple[str, Dict, List]] = [
            ("agents", merged.agents, manifest.agents),
            ("skills", merged.skills, manifest.skills),
            ("workflows", merged.workflows, manifest.workflows),
            ("rules", merged.rules, manifest.rules),
        ]
        for component_type, merged_dict, component_list in sections:
            for component in component_list:
                cid = component.id

                # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-overwrite
                if cid in merged_dict:
                    # Record previous winner as overridden
                    prov_key = f"{component_type}:{cid}"
                    prev_prov = merged.provenance[prov_key]
                    overridden = list(prev_prov.overridden)
                    overridden.insert(0, (prev_prov.winning_scope, prev_prov.winning_path))
                    merged.provenance[prov_key] = ProvenanceRecord(
                        component_id=cid,
                        component_type=component_type,
                        winning_scope=layer.scope,
                        winning_path=layer.path,
                        overridden=overridden,
                    )
                    # Inherit source and accumulate appends from the outer entry
                    component = _merge_component_entry(merged_dict[cid], component)  # type: ignore[arg-type]
                else:
                    # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-newentry
                    prov_key = f"{component_type}:{cid}"
                    merged.provenance[prov_key] = ProvenanceRecord(
                        component_id=cid,
                        component_type=component_type,
                        winning_scope=layer.scope,
                        winning_path=layer.path,
                        overridden=[],
                    )
                    # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-newentry

                merged_dict[cid] = component  # type: ignore[assignment]
                # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-overwrite
        # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-inner
    # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step2-foreach-layer

    # @cpt-begin:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step3-return
    return merged
    # @cpt-end:cpt-studio-algo-project-extensibility-merge-components:p1:inst-step3-return


# @cpt-begin:cpt-studio-algo-project-extensibility-section-appending:p1:inst-appends-header
def apply_section_appends(
    base_content: str,
    components: List[ComponentEntry],
    component_id: str,
    component_type: Optional[str] = None,
) -> str:
    """Compose content by appending pre-merged append content from components.

    Starts with *base_content* (the winning component's content), then looks
    up *component_id* in the already-merged *components* list and appends its
    accumulated ``.append`` field (which was built during layer merging).

    This avoids re-scanning raw layers and prevents double-append.

    Args:
        base_content:   The base content (e.g. prompt file contents) from the
                        winning component definition.
        components:     List of already-merged ``ComponentEntry`` instances
                        (from ``MergedComponents``).
        component_id:   The component ID whose append content to collect.
        component_type: Optional component type (``"agents"``, ``"skills"``,
                        ``"workflows"``, ``"rules"``).  When provided, only
                        components of that type are matched — prevents
                        cross-type ID collisions from injecting wrong content.

    Returns:
        Composed content string.
    """
    # @cpt-end:cpt-studio-algo-project-extensibility-section-appending:p1:inst-appends-header
    # @cpt-begin:cpt-studio-algo-project-extensibility-section-appending:p1:inst-step1-base
    composed = base_content
    # @cpt-end:cpt-studio-algo-project-extensibility-section-appending:p1:inst-step1-base

    # @cpt-begin:cpt-studio-algo-project-extensibility-section-appending:p1:inst-step2-foreach-component
    type_class_map = {
        "agents": AgentEntry,
        "skills": SkillEntry,
        "workflows": WorkflowEntry,
        "rules": RuleEntry,
    }
    expected_cls = type_class_map.get(component_type) if component_type else None
    for component in components:
        if expected_cls is not None and not isinstance(component, expected_cls):
            continue
        if component.id == component_id and component.append:
            composed = composed + "\n" + component.append
            # The component's .append field already contains all accumulated
            # layer appends (built by _merge_component_entry), so we only
            # need to apply it once.
            break
    # @cpt-end:cpt-studio-algo-project-extensibility-section-appending:p1:inst-step2-foreach-component

    # @cpt-begin:cpt-studio-algo-project-extensibility-section-appending:p1:inst-step3-return
    return composed
    # @cpt-end:cpt-studio-algo-project-extensibility-section-appending:p1:inst-step3-return


# ---------------------------------------------------------------------------
# Schema validation helper
# ---------------------------------------------------------------------------

def _validate_schema_manifest_section(manifest: Any, errors: list[str]) -> bool:
    """Validate the top-level manifest section."""
    if not isinstance(manifest, dict):
        errors.append("Missing or invalid [manifest] section")
        return False

    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("[manifest].version is required and must be a non-empty string")

    root = manifest.get("root")
    if root is not None and (not isinstance(root, str) or not root.strip()):
        errors.append("[manifest].root must be a non-empty string when present")

    user_modifiable = manifest.get("user_modifiable")
    if user_modifiable is not None and not isinstance(user_modifiable, bool):
        errors.append("[manifest].user_modifiable must be a boolean when present")
    return True


def _validate_schema_resource_entry(
    res: Any,
    idx: int,
    valid_types: set[str],
    id_chars: set[str],
) -> list[str]:
    """Validate one legacy resource entry."""
    prefix = f"[[resources]][{idx}]"
    if not isinstance(res, dict):
        return [f"{prefix}: must be a table"]

    errors: list[str] = []
    resource_id = res.get("id")
    if not isinstance(resource_id, str) or not resource_id.strip():
        errors.append(f"{prefix}.id is required and must be a non-empty string")
    elif not resource_id[0].islower() or not all(char in id_chars for char in resource_id):
        errors.append(
            f"{prefix}.id '{resource_id}' must match ^[a-z][a-z0-9_]*$ "
            "(lowercase letter start, then lowercase alphanumeric or underscore)"
        )

    source = res.get("source")
    if not isinstance(source, str) or not source.strip():
        errors.append(f"{prefix}.source is required and must be a non-empty string")

    default_path = res.get("default_path")
    if not isinstance(default_path, str) or not default_path.strip():
        errors.append(f"{prefix}.default_path is required and must be a non-empty string")

    resource_type = res.get("type")
    if not isinstance(resource_type, str) or resource_type not in valid_types:
        errors.append(f"{prefix}.type must be one of {sorted(valid_types)}, got {resource_type!r}")

    description = res.get("description")
    if description is not None and not isinstance(description, str):
        errors.append(f"{prefix}.description must be a string when present")

    user_modifiable = res.get("user_modifiable")
    if user_modifiable is not None and not isinstance(user_modifiable, bool):
        errors.append(f"{prefix}.user_modifiable must be a boolean when present")
    return errors


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-schema-validator
def _validate_against_schema(data: Dict[str, Any]) -> List[str]:
    """Validate *data* against ``kit-manifest.schema.json`` (best-effort).

    Uses a lightweight structural check — no third-party jsonschema library.
    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    # --- [manifest] section ---
    manifest = data.get("manifest")
    if not _validate_schema_manifest_section(manifest, errors):
        return errors

    # --- [[resources]] ---
    resources = data.get("resources")
    if resources is None:
        # V1 manifest without resources — allowed; treat as empty.
        return errors
    if not isinstance(resources, list) or not resources:
        errors.append("[[resources]] must be a non-empty array")
        return errors

    valid_types = {"file", "directory"}
    id_chars = set(string.ascii_lowercase + string.digits + "_")

    for idx, res in enumerate(resources):
        errors.extend(_validate_schema_resource_entry(res, idx, valid_types, id_chars))

    return errors
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-schema-validator


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_kit_manifest_path(kit_source: Path) -> Optional[Path]:
    """Return the effective manifest path for a kit source.

    Canonical ``.cf-studio-kit.toml`` always wins when both formats exist.
    Legacy ``manifest.toml`` is only used as a fallback.
    """
    canonical_path = kit_source / ".cf-studio-kit.toml"
    if canonical_path.is_file():
        return canonical_path
    legacy_path = kit_source / "manifest.toml"
    if legacy_path.is_file():
        return legacy_path
    return None


# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-read
def load_manifest(kit_source: Path, kit_slug: str = "") -> Optional[Union[Manifest, ManifestV2]]:
    """Read and parse the effective kit manifest from *kit_source*.

    Returns ``None`` if neither canonical nor legacy manifest exists.
    Canonical ``.cf-studio-kit.toml`` takes precedence over legacy
    ``manifest.toml`` when both are present. V2 manifests are delegated to
    ``parse_manifest_v2`` and return a ``ManifestV2`` instance. Raises
    ``ValueError`` if the selected manifest exists but is invalid.
    """
    manifest_path = resolve_kit_manifest_path(kit_source)
    if manifest_path is None:
        return None
    if manifest_path.name == ".cf-studio-kit.toml":
        return _load_canonical_kit_manifest(kit_source, kit_slug=kit_slug)

    try:
        with open(manifest_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid manifest.toml: {exc}") from exc

    # Detect V2 manifests early and delegate to V2 parser, skipping V1 validation
    meta = data.get("manifest", {})
    _raw_version = meta.get("version", "")
    _version = str(_raw_version).strip()
    if _version == "2.0":
        return parse_manifest_v2(manifest_path)
    if _version:
        meta["version"] = _version

    # Schema-level structural validation (V1 only)
    schema_errors = _validate_against_schema(data)
    if schema_errors:
        raise ValueError(
            f"Invalid manifest.toml: {'; '.join(schema_errors)}"
        )

    meta = data["manifest"]
    raw_resources = data.get("resources", [])

    resources: list[ManifestResource] = []
    for r in raw_resources:
        resources.append(ManifestResource(
            id=str(r["id"]).strip(),
            source=str(r["source"]).strip(),
            default_path=str(r["default_path"]).strip(),
            type=str(r["type"]).strip(),
            description=str(r.get("description", "")).strip(),
            user_modifiable=bool(r.get("user_modifiable", True)),
        ))

    return Manifest(
        version=str(meta["version"]).strip(),
        root=str(meta.get("root", "{cf-studio-path}/config/kits/{slug}")).strip(),
        user_modifiable=bool(meta.get("user_modifiable", True)),
        resources=resources,
    )


def _load_canonical_kit_manifest(kit_source: Path, kit_slug: str = "") -> Optional[Manifest]:
    """Adapt canonical kit metadata into the manifest installer model."""
    canonical_path = kit_source / ".cf-studio-kit.toml"
    if not canonical_path.is_file():
        return None

    from .kit_model import load_canonical_kit_model

    model = load_canonical_kit_model(kit_source, kit_slug=kit_slug)
    if model is None:
        return None

    return Manifest(
        version=model.version or "1",
        root="{cf-studio-path}/config/kits/{slug}",
        user_modifiable=True,
        resources=[
            ManifestResource(
                id=res.id,
                source=res.source,
                default_path=res.install_path,
                type=res.type,
                description=res.description,
                user_modifiable=res.user_modifiable,
                kind=res.kind,
                public=res.public,
                artifact_bindings=res.artifact_bindings,
            )
            for res in model.resources
        ],
    )
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-read


def _validate_manifest_unique_ids(manifest: Manifest) -> list[str]:
    """Validate that manifest resource ids are unique."""
    errors: list[str] = []
    seen_ids: dict[str, int] = {}
    for idx, resource in enumerate(manifest.resources):
        if resource.id in seen_ids:
            errors.append(
                f"Duplicate resource id '{resource.id}' "
                f"(first at index {seen_ids[resource.id]}, again at {idx})"
            )
            continue
        seen_ids[resource.id] = idx
    return errors


def _validate_manifest_source_entry(resource: ManifestResource, kit_source: Path) -> list[str]:
    """Validate one resource source path and type."""
    errors: list[str] = []
    source_path = kit_source / resource.source
    if not source_path.exists():
        return [
            f"Resource '{resource.id}': source path '{resource.source}' "
            "does not exist in kit package"
        ]
    if resource.type == "file" and not source_path.is_file():
        errors.append(
            f"Resource '{resource.id}': type is 'file' but "
            f"source '{resource.source}' is a directory"
        )
    elif resource.type == "directory" and not source_path.is_dir():
        errors.append(
            f"Resource '{resource.id}': type is 'directory' but "
            f"source '{resource.source}' is a file"
        )
    return errors


def _validate_manifest_default_path(resource: ManifestResource) -> list[str]:
    """Validate that the default install path is a safe relative path."""
    errors: list[str] = []
    default_path = resource.default_path
    if default_path.startswith("/") or default_path.startswith("\\"):
        errors.append(
            f"Resource '{resource.id}': default_path '{default_path}' must be a relative path"
        )
    try:
        from pathlib import PurePosixPath
        resolved = PurePosixPath(default_path).as_posix()
    except (ValueError, OSError, NotImplementedError):
        return [f"Resource '{resource.id}': default_path '{default_path}' is not a valid path"]
    if ".." in resolved.split("/"):
        errors.append(
            f"Resource '{resource.id}': default_path '{default_path}' "
            "must not contain '..' path components"
        )
    return errors


def _validate_manifest_source_traversal(resource: ManifestResource) -> list[str]:
    """Reject legacy source paths containing ``..`` traversal."""
    if resource.source and ".." in str(resource.source):
        return [f"Resource '{resource.id}': source path contains '..' traversal: {resource.source}"]
    return []


# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-validate
def validate_manifest(manifest: Manifest, kit_source: Path) -> list[str]:
    """Validate a parsed *manifest* against the actual *kit_source* directory.

    Checks:
    - All resource ``id`` values are unique.
    - All ``source`` paths exist in the kit package.
    - ``default_path`` values are valid relative paths (no ``..`` escapes).
    - ``type`` matches the actual source (file vs directory).

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    errors.extend(_validate_manifest_unique_ids(manifest))

    for resource in manifest.resources:
        errors.extend(_validate_manifest_source_entry(resource, kit_source))
        errors.extend(_validate_manifest_default_path(resource))
        errors.extend(_validate_manifest_source_traversal(resource))

    return errors
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-validate


# ---------------------------------------------------------------------------
# Resource Resolution API
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-to-absolute
def _resolve_binding_path(
    studio_dir: Path,
    identifier: str,
    binding_path: str,
    *,
    allowed_absolute_root: str = "",
) -> Path:
    from ..commands.kit import (
        _is_registered_kit_path_absolute,
        _normalize_path_string,
        _path_is_within,
        _resolve_registered_kit_dir,
        _resolve_same_os_absolute_path,
    )

    normalized_path = _normalize_path_string(binding_path)
    if _is_registered_kit_path_absolute(normalized_path):
        resolved_absolute = _resolve_same_os_absolute_path(normalized_path)
        if resolved_absolute is None:
            raise ValueError(
                f"Resource '{identifier}' binding path '{normalized_path}' is not accessible on this OS"
            )
        normalized_root = _normalize_path_string(allowed_absolute_root)
        resolved_root = (
            _resolve_same_os_absolute_path(normalized_root)
            if normalized_root else None
        )
        if resolved_root is None or not _path_is_within(resolved_absolute, resolved_root):
            raise ValueError(
                f"Resource '{identifier}' binding path '{normalized_path}' is invalid state: "
                "absolute paths must not be persisted in core.toml; use project-relative paths"
            )
        return resolved_absolute
    resolved_path = _resolve_registered_kit_dir(studio_dir, normalized_path)
    if resolved_path is None:
        raise ValueError(
            f"Resource '{identifier}' binding path '{normalized_path}' is not accessible on this OS"
        )
    project_root = _project_root_from_core_toml(studio_dir / "config" / "core.toml", studio_dir)
    if project_root is not None and not _path_is_within(resolved_path, project_root):
        raise ValueError(
            f"Resource '{identifier}' binding path '{normalized_path}' escapes "
            f"the current project root '{project_root}'"
        )
    return resolved_path
# @cpt-end:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-to-absolute


# @cpt-begin:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-read-bindings
def _project_root_from_core_toml(core_toml: Path, studio_dir: Path) -> Optional[Path]:
    return load_project_root_from_core_toml(
        core_toml,
        studio_dir,
        default_to_parent=True,
    )
# @cpt-end:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-read-bindings


def _load_binding_config(core_toml: Path) -> tuple[Optional[Dict[str, Any]], list[str]]:
    """Load ``core.toml`` and return the kits table plus parse errors."""
    if not core_toml.is_file():
        return None, []
    try:
        with open(core_toml, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        return None, [f"Failed to parse {core_toml}: {exc}"]
    except OSError as exc:
        return None, [f"Failed to read {core_toml}: {exc}"]
    kits = data.get("kits")
    if not isinstance(kits, dict):
        return None, []
    return kits, []


def _resolve_registered_manifest_bindings(
    studio_dir: Path,
    slug: str,
    kit_entry: Dict[str, Any],
) -> tuple[dict[str, Path], list[str]]:
    """Resolve bindings for register-mode kits from their installed manifest."""
    kit_root_value = str(kit_entry.get("path") or "").strip()
    if not kit_root_value:
        return {}, [f"Kit '{slug}' is in register mode but has no registered manifest root path"]
    try:
        kit_root = _resolve_binding_path(studio_dir, f"{slug}.path", kit_root_value)
    except ValueError as exc:
        return {}, [str(exc)]

    manifest = load_manifest(kit_root, kit_slug=slug)
    if manifest is None:
        return {}, [f"Kit '{slug}' is in register mode but no canonical or legacy manifest was found at {kit_root}"]

    result: dict[str, Path] = {}
    binding_errors: list[str] = []
    for resource in manifest.resources:
        try:
            result[resource.id] = _resolve_binding_path(
                studio_dir,
                resource.id,
                (Path(kit_root_value) / resource.source).as_posix(),
                allowed_absolute_root=kit_root_value,
            )
        except ValueError as exc:
            binding_errors.append(str(exc))
    return result, binding_errors


def _extract_binding_path(binding: Any) -> str:
    """Extract a resource binding path from either string or table syntax."""
    if isinstance(binding, dict):
        return str(binding.get("path", "")).strip()
    if isinstance(binding, str):
        return binding.strip()
    return ""


def _resolve_declared_resource_bindings(
    studio_dir: Path,
    resources: Dict[str, Any],
    allowed_absolute_root: str,
) -> tuple[dict[str, Path], list[str]]:
    """Resolve direct ``[kits.<slug>.resources]`` bindings."""
    result: dict[str, Path] = {}
    binding_errors: list[str] = []
    for identifier, binding in resources.items():
        binding_path = _extract_binding_path(binding)
        if not binding_path:
            continue
        try:
            result[identifier] = _resolve_binding_path(
                studio_dir,
                identifier,
                binding_path,
                allowed_absolute_root=allowed_absolute_root,
            )
        except ValueError as exc:
            binding_errors.append(str(exc))
    return result, binding_errors


# @cpt-begin:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-read-bindings
def resolve_resource_bindings(
    config_dir: Path, slug: str, studio_dir: Path,
) -> dict[str, Path]:
    """Resolve resource bindings for kit *slug* to absolute paths.

    Reads ``[kits.{slug}.resources]`` from ``core.toml`` in *config_dir*,
    then resolves each relative path against *studio_dir* (the adapter
    directory).  Paths may contain ``..`` components for resources placed
    outside the adapter tree.

    Returns a dict mapping resource identifiers to absolute ``Path`` objects.
    Returns an empty dict if no resources section exists.
    Raises ``ValueError`` if a configured binding path cannot be resolved on
    the current OS.

    @cpt-algo:cpt-studio-algo-kit-manifest-resolve:p1
    """
    result, binding_errors = resolve_resource_bindings_with_errors(
        config_dir,
        slug,
        studio_dir,
    )
    if binding_errors:
        raise ValueError("; ".join(binding_errors))
    return result


def resolve_resource_bindings_with_errors(
    config_dir: Path,
    slug: str,
    studio_dir: Path,
) -> tuple[dict[str, Path], list[str]]:
    """Resolve resource bindings while preserving valid entries and collecting errors."""
    core_toml = config_dir / "core.toml"
    kits, load_errors = _load_binding_config(core_toml)
    if load_errors or kits is None:
        return {}, load_errors
    kit_entry = kits.get(slug)
    if not isinstance(kit_entry, dict):
        return {}, []
    install_mode = str(kit_entry.get("install_mode", "") or "").strip()
    # @cpt-begin:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-register-from-manifest
    if install_mode == "register":
        return _resolve_registered_manifest_bindings(studio_dir, slug, kit_entry)
    # @cpt-end:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-register-from-manifest
    resources = kit_entry.get("resources")
    if not isinstance(resources, dict):
        return {}, []
    # @cpt-end:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-read-bindings

    # @cpt-begin:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-to-absolute
    result, binding_errors = _resolve_declared_resource_bindings(
        studio_dir,
        resources,
        str(kit_entry.get("path", "") or ""),
    )
    # @cpt-end:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-to-absolute

    # @cpt-begin:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-return
    return result, binding_errors
    # @cpt-end:cpt-studio-algo-kit-manifest-resolve:p1:inst-resolve-return


# ---------------------------------------------------------------------------
# Source Path Mapping API
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-resource-info
@dataclass(frozen=True)
class ResourceInfo:
    """Metadata about a manifest resource for target path resolution."""

    type: str  # "file" or "directory"
    source_base: str  # source path in manifest (e.g., "artifacts/ADR")
    user_modifiable: bool = True
# @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-resource-info


def _resolve_relative_source_within_kit(
    kit_source: Path,
    resource_id: str,
    source: str,
    label: str = "source path",
) -> Path:
    """Resolve a relative resource path and enforce kit-root containment."""
    source_rel = Path(source)
    if source_rel.is_absolute():
        raise ValueError(f"Resource '{resource_id}': {label} '{source}' must be relative")
    resolved_source = (kit_source / source_rel).resolve()
    try:
        resolved_source.relative_to(kit_source.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Resource '{resource_id}': {label} '{source}' escapes the kit root"
        ) from exc
    return resolved_source


def _record_directory_resource_files(
    kit_source: Path,
    source_dir: Path,
    resource_id: str,
    source_to_resource_id: Dict[str, str],
) -> None:
    """Map all files inside a directory resource to the same resource id."""
    if not source_dir.is_dir():
        return
    for file_path in source_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(kit_source).as_posix()
            source_to_resource_id[rel_path] = resource_id


def _record_subagent_sources(
    kit_source: Path,
    resource: Any,
    source_to_resource_id: Dict[str, str],
    resource_info: Dict[str, ResourceInfo],
) -> None:
    """Add synthetic file resources for declared subagent sources."""
    for subagent in getattr(resource, "subagents", []) or []:
        if not isinstance(subagent, dict):
            continue
        subagent_source = str(subagent.get("source", "") or "").strip().replace("\\", "/")
        if not subagent_source:
            continue
        resolved_subagent = _resolve_relative_source_within_kit(
            kit_source,
            resource.id,
            subagent_source,
            "subagent source path",
        )
        if not resolved_subagent.is_file():
            continue
        synthetic_id = f"{resource.id}.__subagent__.{subagent_source}"
        resource_info[synthetic_id] = ResourceInfo(
            type="file",
            source_base=subagent_source,
            user_modifiable=resource.user_modifiable,
        )
        source_to_resource_id[subagent_source] = synthetic_id


# @cpt-begin:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-build-mapping-header
# @cpt-algo:cpt-studio-algo-kit-manifest-source-mapping:p1
def build_source_to_resource_mapping(
    kit_source: Path,
    *,
    kit_slug: str = "",
) -> tuple[dict[str, str], dict[str, ResourceInfo]]:
    """Build mapping from source file paths to resource identifiers.

    For manifest-driven kit updates, this mapping allows determining which
    resource binding applies to each source file.

    Args:
        kit_source: Kit source directory (containing manifest.toml).

    Returns:
        Tuple of:
        - source_to_resource_id: Dict mapping each source file's relative path
          to its resource identifier. For directory resources, all files within
          the directory are mapped to the same resource id.
        - resource_info: Dict mapping resource id to ResourceInfo (type and
          source_base path for computing relative paths within directories).

    Returns (empty_dict, empty_dict) if no manifest.toml exists.

    @cpt-begin:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-load-manifest
    """
    manifest = load_manifest(kit_source, kit_slug=kit_slug)
    if manifest is None:
        return {}, {}
    # @cpt-end:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-load-manifest

    source_to_resource_id: Dict[str, str] = {}
    resource_info: Dict[str, ResourceInfo] = {}
    # @cpt-end:cpt-studio-dod-project-extensibility-manifest-v2-schema:p1:inst-build-mapping-header

    # @cpt-begin:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-record-resource-info
    # @cpt-begin:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-map-file-resources
    # @cpt-begin:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-expand-directories
    for res in manifest.resources:
        # @cpt-begin:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-source-mapping-relative-only
        resolved_source = _resolve_relative_source_within_kit(kit_source, res.id, res.source)
        # @cpt-end:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-source-mapping-relative-only
        resource_info[res.id] = ResourceInfo(
            type=res.type,
            source_base=res.source,
            user_modifiable=res.user_modifiable,
        )
        if res.type == "file":
            source_to_resource_id[res.source] = res.id
        elif res.type == "directory":
            _record_directory_resource_files(kit_source, resolved_source, res.id, source_to_resource_id)
        _record_subagent_sources(kit_source, res, source_to_resource_id, resource_info)
    # @cpt-end:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-expand-directories
    # @cpt-end:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-map-file-resources
    # @cpt-end:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-record-resource-info

    # @cpt-begin:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-return-mapping
    return source_to_resource_id, resource_info
    # @cpt-end:cpt-studio-algo-kit-manifest-source-mapping:p1:inst-return-mapping
