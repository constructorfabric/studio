"""Normalized kit package model and canonical manifest conversion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from . import toml_utils
from ._tomllib_compat import tomllib
from .manifest import Manifest, ManifestResource, ManifestV2, load_manifest

_CANONICAL_MANIFEST = ".cf-studio-kit.toml"
_LEGACY_CONTENT_DIRS = ("artifacts", "codebase", "scripts", "workflows")
_LEGACY_CONTENT_FILES = ("constraints.toml", "SKILL.md", "AGENTS.md")
_PUBLIC_KINDS = {"skill", "agent", "rule"}
_SUPPORTING_KINDS = {
    "template",
    "checklist",
    "script",
    "directory",
    "other",
}
_LEGACY_KIND_ALIASES = {"workflow": "skill"}


# @cpt-begin:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-datamodel
@dataclass(frozen=True)
class KitResource:
    """A normalized resource declared by a kit package."""

    id: str
    kind: str
    source: str
    install_path: str
    type: str
    public: bool = False
    description: str = ""
    user_modifiable: bool = True
    aliases: List[str] = field(default_factory=list)
    generated_targets: List[str] = field(default_factory=list)
    origin: str = ""
    generated_name: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class PublicComponent:
    """A public skill, agent, or rule exposed by a normalized kit."""

    id: str
    kind: str
    source: str
    generated_name: str
    generated_targets: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    origin: str = ""


@dataclass(frozen=True)
class KitModel:
    """Normalized kit metadata and resources."""

    slug: str
    name: str
    version: str
    manifest_source: str
    resources: List[KitResource] = field(default_factory=list)
    public_components: List[PublicComponent] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    manifest_semantic_hash: str = ""
    manifest_bytes_hash: str = ""
    resource_hashes: Dict[str, str] = field(default_factory=dict)
    tool_risk_fingerprint: str = ""
# @cpt-end:cpt-studio-algo-kit-manifest-install:p1:inst-manifest-datamodel


def _require_string(data: Dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: missing or invalid string field '{key}'")
    return value.strip()


def _optional_string(data: Dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Field '{key}' must be a string")
    return value.strip()


def _string_list(value: Any, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Field '{field_name}' must be a list of strings")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"Field '{field_name}' must be a list of strings")
        cleaned = item.strip()
        if cleaned:
            result.append(cleaned)
    return result


def _normalize_kind(kind: str, *, warnings: List[str], resource_id: str) -> str:
    cleaned = kind.strip().lower()
    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-workflow-to-skill
    if cleaned in _LEGACY_KIND_ALIASES:
        warnings.append(
            f"Resource '{resource_id}' uses legacy kind '{cleaned}', normalized to 'skill'",
        )
        cleaned = _LEGACY_KIND_ALIASES[cleaned]
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-workflow-to-skill
    # @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-resource-kinds
    valid = _PUBLIC_KINDS | _SUPPORTING_KINDS
    if cleaned not in valid:
        raise ValueError(
            f"Resource '{resource_id}': invalid kind '{kind}', expected one of {sorted(valid | set(_LEGACY_KIND_ALIASES))}",
        )
    normalized = cleaned
    # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-resource-kinds
    return normalized


def _normalize_public_name(slug: str, resource_id: str) -> str:
    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-prefix-public-names
    prefix = f"cf-{slug}-"
    if resource_id == f"cf-{slug}" or resource_id.startswith(prefix):
        generated_name = resource_id
    else:
        generated_name = f"{prefix}{resource_id}"
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-prefix-public-names
    return generated_name


def _warn_unknown_keys(
    data: Dict[str, Any],
    allowed: set[str],
    context: str,
    warnings: List[str],
) -> None:
    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-warnings
    for key in sorted(set(data) - allowed):
        warnings.append(f"{context}: unknown optional field '{key}' ignored")
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-warnings


def _validate_relative_source(kit_source: Path, resource: KitResource) -> None:
    source_path = PurePosixPath(resource.source)
    if source_path.is_absolute() or ".." in source_path.parts:
        raise ValueError(
            f"Resource '{resource.id}': source '{resource.source}' must be a relative path inside the kit root",
        )
    actual = (kit_source / resource.source).resolve()
    try:
        actual.relative_to(kit_source.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Resource '{resource.id}': source '{resource.source}' escapes the kit root",
        ) from exc
    if not actual.exists():
        raise ValueError(
            f"Resource '{resource.id}': source path '{resource.source}' does not exist",
        )
    if resource.type == "file" and not actual.is_file():
        raise ValueError(
            f"Resource '{resource.id}': type is 'file' but source is not a file",
        )
    if resource.type == "directory" and not actual.is_dir():
        raise ValueError(
            f"Resource '{resource.id}': type is 'directory' but source is not a directory",
        )


def _validate_install_path(resource: KitResource) -> None:
    install_path = PurePosixPath(resource.install_path)
    if install_path.is_absolute() or ".." in install_path.parts:
        raise ValueError(
            f"Resource '{resource.id}': install_path '{resource.install_path}' must be relative and must not contain '..'",
        )


_HASH_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resource_content_hash(kit_source: Path, resource: KitResource) -> str:
    source_path = kit_source / resource.source
    if resource.type == "file":
        return _sha256_bytes(source_path.read_bytes())

    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-directory-hash
    entries: List[Dict[str, str]] = []
    for fpath in sorted(source_path.rglob("*")):
        rel_parts = fpath.relative_to(source_path).parts
        if any(part in _HASH_EXCLUDED_DIRS for part in rel_parts):
            continue
        if fpath.is_file():
            entries.append({
                "path": PurePosixPath(*rel_parts).as_posix(),
                "sha256": _sha256_bytes(fpath.read_bytes()),
            })
    return _sha256_bytes(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-directory-hash


def _semantic_resource_data(resource: KitResource) -> Dict[str, Any]:
    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-resource-id-vs-generated-name
    data = {
        "id": resource.id,
        "kind": resource.kind,
        "source": resource.source,
        "install_path": resource.install_path,
        "type": resource.type,
        "public": resource.public,
        "description": resource.description,
        "user_modifiable": resource.user_modifiable,
        "aliases": resource.aliases,
        "generated_targets": resource.generated_targets,
        "origin": resource.origin,
        "generated_name": resource.generated_name,
    }
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-resource-id-vs-generated-name
    return data


def _public_components(resources: List[KitResource]) -> List[PublicComponent]:
    return [
        PublicComponent(
            id=resource.id,
            kind=resource.kind,
            source=resource.source,
            generated_name=resource.generated_name,
            generated_targets=resource.generated_targets or ["installed"],
            aliases=resource.aliases,
            origin=resource.origin,
        )
        for resource in resources
        if resource.public and resource.kind in _PUBLIC_KINDS
    ]


def _with_hashes(kit_source: Path, model: KitModel) -> KitModel:
    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-hashes
    resource_hashes = {
        resource.id: _resource_content_hash(kit_source, resource)
        for resource in model.resources
    }
    resources = [
        KitResource(
            id=resource.id,
            kind=resource.kind,
            source=resource.source,
            install_path=resource.install_path,
            type=resource.type,
            public=resource.public,
            description=resource.description,
            user_modifiable=resource.user_modifiable,
            aliases=resource.aliases,
            generated_targets=resource.generated_targets,
            origin=resource.origin,
            generated_name=resource.generated_name,
            content_hash=resource_hashes[resource.id],
        )
        for resource in model.resources
    ]
    semantic_data = {
        "slug": model.slug,
        "name": model.name,
        "version": model.version,
        "manifest_source": model.manifest_source,
        "resources": [_semantic_resource_data(resource) for resource in resources],
    }
    manifest_path = kit_source / _CANONICAL_MANIFEST
    manifest_bytes_hash = (
        _sha256_bytes(manifest_path.read_bytes())
        if manifest_path.is_file()
        else _sha256_bytes(json.dumps(semantic_data, sort_keys=True).encode("utf-8"))
    )
    return KitModel(
        slug=model.slug,
        name=model.name,
        version=model.version,
        manifest_source=model.manifest_source,
        resources=resources,
        public_components=_public_components(resources),
        warnings=model.warnings,
        manifest_semantic_hash=_sha256_bytes(
            json.dumps(semantic_data, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        ),
        manifest_bytes_hash=manifest_bytes_hash,
        resource_hashes=resource_hashes,
        tool_risk_fingerprint=_sha256_bytes(b"{}"),
    )
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-hashes


# @cpt-algo:cpt-studio-algo-kit-canonical-manifest:p1
def load_canonical_kit_model(kit_source: Path) -> Optional[KitModel]:
    """Load ``.cf-studio-kit.toml`` from *kit_source* when present."""
    # @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-any-layout
    manifest_path = kit_source / _CANONICAL_MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        data = toml_utils.load(manifest_path)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid {_CANONICAL_MANIFEST}: {exc}") from exc
    # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-any-layout

    warnings: List[str] = []
    # @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-metadata
    meta = data.get("kit")
    if not isinstance(meta, dict):
        raise ValueError(f"{_CANONICAL_MANIFEST}: missing [kit] metadata table")
    _warn_unknown_keys(
        meta,
        {"slug", "name", "version", "description", "source", "targets", "defaults", "compatibility"},
        "[kit]",
        warnings,
    )
    slug = _require_string(meta, "slug", "[kit]")
    name = _optional_string(meta, "name") or slug
    version = _optional_string(meta, "version")
    # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-metadata

    # @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-resource-shape
    raw_resources = data.get("resources", [])
    if not isinstance(raw_resources, list):
        raise ValueError(f"{_CANONICAL_MANIFEST}: resources must be an array of tables")
    resources: List[KitResource] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(raw_resources):
        if not isinstance(raw, dict):
            raise ValueError(f"{_CANONICAL_MANIFEST}: [[resources]][{idx}] must be a table")
        resource_id = _require_string(raw, "id", f"[[resources]][{idx}]")
        if resource_id in seen_ids:
            raise ValueError(f"Duplicate resource id '{resource_id}'")
        seen_ids.add(resource_id)
        # @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-no-binding-path
        if "binding_path" in raw:
            raise ValueError(
                f"Resource '{resource_id}': binding_path is installed state and is not allowed in {_CANONICAL_MANIFEST}",
            )
        # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-no-binding-path
        _warn_unknown_keys(
            raw,
            {
                "id", "kind", "source", "install_path", "type", "public",
                "description", "user_modifiable", "aliases", "generated_targets",
                "origin", "agent", "targets", "permissions",
            },
            f"[[resources]][{idx}]",
            warnings,
        )
        kind = _normalize_kind(
            _require_string(raw, "kind", f"[[resources]][{idx}]"),
            warnings=warnings,
            resource_id=resource_id,
        )
        source = _require_string(raw, "source", f"[[resources]][{idx}]")
        resource_type = _optional_string(raw, "type") or "file"
        if resource_type not in {"file", "directory"}:
            raise ValueError(
                f"Resource '{resource_id}': type must be 'file' or 'directory'",
            )
        install_path = _optional_string(raw, "install_path") or source
        public = bool(raw.get("public", kind in _PUBLIC_KINDS))
        resource = KitResource(
            id=resource_id,
            kind=kind,
            source=source,
            install_path=install_path,
            type=resource_type,
            public=public,
            description=_optional_string(raw, "description"),
            user_modifiable=bool(raw.get("user_modifiable", True)),
            aliases=_string_list(raw.get("aliases"), "aliases"),
            # @cpt-begin:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-generated-targets
            generated_targets=_string_list(raw.get("generated_targets"), "generated_targets") or ["installed"],
            # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-generated-targets
            origin=_optional_string(raw, "origin"),
            generated_name=_normalize_public_name(slug, resource_id) if public else "",
        )
        _validate_relative_source(kit_source, resource)
        _validate_install_path(resource)
        resources.append(resource)
    # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-resource-shape

    return _with_hashes(
        kit_source,
        KitModel(
            slug=slug,
            name=name,
            version=version,
            manifest_source="canonical",
            resources=resources,
            warnings=warnings,
        ),
    )


def _read_conf_metadata(kit_source: Path) -> tuple[str, str]:
    conf_path = kit_source / "conf.toml"
    if not conf_path.is_file():
        return "", ""
    try:
        data = toml_utils.load(conf_path)
    except (OSError, tomllib.TOMLDecodeError):
        return "", ""
    slug = data.get("slug", "")
    version = data.get("version", "")
    return (
        str(slug).strip() if slug else "",
        str(version).strip() if version else "",
    )


def _resource_kind_from_path(source: str, resource_id: str) -> str:
    if source == "SKILL.md":
        return "skill"
    if source == "AGENTS.md":
        return "rule"
    if source.endswith("template.md"):
        return "template"
    if source.endswith("checklist.md"):
        return "checklist"
    if source.startswith("scripts/"):
        return "script"
    if resource_id == "workflows" or source.startswith("workflows/"):
        return "skill"
    return "directory" if "." not in Path(source).name else "other"


def _from_manifest_resource(slug: str, res: ManifestResource, warnings: List[str]) -> KitResource:
    kind = _resource_kind_from_path(res.source, res.id)
    origin = "legacy-workflow" if kind == "skill" and res.source.startswith("workflows/") else ""
    return KitResource(
        id=res.id,
        kind=kind,
        source=res.source,
        install_path=res.default_path,
        type=res.type,
        public=kind in _PUBLIC_KINDS,
        description=res.description,
        user_modifiable=res.user_modifiable,
        origin=origin,
        generated_name=_normalize_public_name(slug, res.id) if kind in _PUBLIC_KINDS else "",
    )


def _load_legacy_manifest_model(kit_source: Path) -> Optional[KitModel]:
    manifest = load_manifest(kit_source)
    if manifest is None:
        return None
    conf_slug, conf_version = _read_conf_metadata(kit_source)
    slug = conf_slug or kit_source.name
    warnings = ["legacy manifest.toml normalized to canonical KitModel"]
    resources: List[KitResource] = []
    if isinstance(manifest, Manifest):
        resources = [
            _from_manifest_resource(slug, res, warnings)
            for res in manifest.resources
        ]
        version = manifest.version or conf_version
    elif isinstance(manifest, ManifestV2):
        version = manifest.version or conf_version
        for res in manifest.resources:
            resources.append(_from_manifest_resource(slug, res, warnings))
        for workflow in manifest.workflows:
            source = workflow.source or workflow.prompt_file
            if source:
                # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-workflow-to-skill
                resources.append(KitResource(
                    id=workflow.id,
                    kind="skill",
                    source=source,
                    install_path=source,
                    type="file",
                    public=True,
                    description=workflow.description,
                    user_modifiable=True,
                    origin="legacy-workflow",
                    generated_name=_normalize_public_name(slug, workflow.id),
                ))
                warnings.append(
                    f"Legacy workflow '{workflow.id}' normalized to public skill resource",
                )
                # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-workflow-to-skill
        for skill in manifest.skills:
            source = skill.source or skill.prompt_file
            if source:
                resources.append(KitResource(
                    id=skill.id,
                    kind="skill",
                    source=source,
                    install_path=source,
                    type="file",
                    public=True,
                    description=skill.description,
                    user_modifiable=True,
                    generated_name=_normalize_public_name(slug, skill.id),
                ))
    else:
        return None

    for resource in resources:
        _validate_relative_source(kit_source, resource)
        _validate_install_path(resource)
    return _with_hashes(
        kit_source,
        KitModel(
            slug=slug,
            name=slug,
            version=version,
            manifest_source="legacy_manifest",
            resources=resources,
            warnings=warnings,
        ),
    )


def _load_layout_model(kit_source: Path) -> KitModel:
    conf_slug, conf_version = _read_conf_metadata(kit_source)
    slug = conf_slug or kit_source.name
    resources: List[KitResource] = []
    for dirname in _LEGACY_CONTENT_DIRS:
        path = kit_source / dirname
        if path.is_dir():
            resources.append(KitResource(
                id=dirname,
                kind="skill" if dirname == "workflows" else "directory",
                source=dirname,
                install_path=dirname,
                type="directory",
                public=dirname == "workflows",
                user_modifiable=True,
                origin="legacy-workflow" if dirname == "workflows" else "",
                generated_name=_normalize_public_name(slug, dirname) if dirname == "workflows" else "",
            ))
    for filename in _LEGACY_CONTENT_FILES:
        path = kit_source / filename
        if path.is_file():
            resource_id = Path(filename).stem.lower()
            kind = _resource_kind_from_path(filename, resource_id)
            resources.append(KitResource(
                id=resource_id,
                kind=kind,
                source=filename,
                install_path=filename,
                type="file",
                public=kind in _PUBLIC_KINDS,
                user_modifiable=True,
                generated_name=_normalize_public_name(slug, resource_id) if kind in _PUBLIC_KINDS else "",
            ))
    if not resources:
        raise ValueError(f"No kit resources found under {kit_source}")
    return _with_hashes(
        kit_source,
        KitModel(
            slug=slug,
            name=slug,
            version=conf_version,
            manifest_source="legacy_layout",
            resources=resources,
            warnings=["legacy layout normalized to canonical KitModel"],
        ),
    )


# @cpt-algo:cpt-studio-algo-kit-model-normalize:p1
def load_kit_model(kit_source: Path, source_hint: str = "") -> KitModel:
    """Load a kit source through canonical, legacy manifest, or layout adapters."""
    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-canonical-manifest
    if source_hint in ("", "manifest"):
        model = load_canonical_kit_model(kit_source)
        if model is not None:
            return model
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-canonical-manifest

    # @cpt-begin:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-precedence
    if source_hint in ("", "manifest"):
        legacy_model = _load_legacy_manifest_model(kit_source)
        if legacy_model is not None:
            return legacy_model
    if source_hint in ("", "layout"):
        return _load_layout_model(kit_source)
    if source_hint == "core":
        raise ValueError("core normalization requires an installed kit registration and is not available for source directories")
    raise ValueError(f"Unsupported normalization source: {source_hint}")
    # @cpt-end:cpt-studio-algo-kit-model-normalize:p1:inst-kitmodel-precedence


def kit_model_to_toml_data(model: KitModel) -> Dict[str, Any]:
    """Convert a KitModel to canonical manifest TOML data."""
    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-convert
    resources: List[Dict[str, Any]] = []
    for resource in model.resources:
        item: Dict[str, Any] = {
            "id": resource.id,
            "kind": resource.kind,
            "source": resource.source,
            "install_path": resource.install_path,
            "type": resource.type,
            "user_modifiable": resource.user_modifiable,
        }
        if resource.public:
            item["public"] = True
        if resource.description:
            item["description"] = resource.description
        if resource.aliases:
            item["aliases"] = resource.aliases
        if resource.generated_targets:
            item["generated_targets"] = resource.generated_targets
        if resource.origin:
            item["origin"] = resource.origin
        if resource.generated_name:
            item["generated_name"] = resource.generated_name
        resources.append(item)
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-convert

    return {
        "kit": {
            "slug": model.slug,
            "name": model.name,
            "version": model.version,
        },
        "resources": resources,
    }


def render_canonical_manifest(model: KitModel) -> str:
    """Render a normalized model as canonical ``.cf-studio-kit.toml``."""
    return toml_utils.dumps(
        kit_model_to_toml_data(model),
        header_comment="Generated by cfs kit normalize. Review before publishing.",
    )


def normalize_kit_source(kit_source: Path, source_hint: str = "") -> tuple[KitModel, str]:
    """Normalize *kit_source* and return the model plus canonical TOML text."""
    # @cpt-begin:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-load-kitmodel
    if not kit_source.is_dir():
        raise ValueError(f"Kit source directory not found: {kit_source}")
    model = load_kit_model(kit_source, source_hint)
    # @cpt-end:cpt-studio-algo-kit-manifest-normalize:p1:inst-normalize-load-kitmodel
    return model, render_canonical_manifest(model)
