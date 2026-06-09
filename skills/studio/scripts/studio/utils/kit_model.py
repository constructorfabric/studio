"""Normalized kit package model and canonical manifest conversion."""

from __future__ import annotations

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


@dataclass(frozen=True)
class KitModel:
    """Normalized kit metadata and resources."""

    slug: str
    name: str
    version: str
    manifest_source: str
    resources: List[KitResource] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
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
    if cleaned in _LEGACY_KIND_ALIASES:
        warnings.append(
            f"Resource '{resource_id}' uses legacy kind '{cleaned}', normalized to 'skill'",
        )
        return _LEGACY_KIND_ALIASES[cleaned]
    valid = _PUBLIC_KINDS | _SUPPORTING_KINDS
    if cleaned not in valid:
        raise ValueError(
            f"Resource '{resource_id}': invalid kind '{kind}', expected one of {sorted(valid | set(_LEGACY_KIND_ALIASES))}",
        )
    return cleaned


def _normalize_public_name(slug: str, resource_id: str) -> str:
    prefix = f"cf-{slug}-"
    if resource_id == f"cf-{slug}" or resource_id.startswith(prefix):
        return resource_id
    return f"{prefix}{resource_id}"


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
            generated_targets=_string_list(raw.get("generated_targets"), "generated_targets"),
            origin=_optional_string(raw, "origin"),
            generated_name=_normalize_public_name(slug, resource_id) if public else "",
        )
        _validate_relative_source(kit_source, resource)
        _validate_install_path(resource)
        resources.append(resource)
    # @cpt-end:cpt-studio-algo-kit-canonical-manifest:p1:inst-canonical-resource-shape

    return KitModel(
        slug=slug,
        name=name,
        version=version,
        manifest_source="canonical",
        resources=resources,
        warnings=warnings,
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
    return KitModel(
        slug=slug,
        name=slug,
        version=version,
        manifest_source="legacy_manifest",
        resources=resources,
        warnings=warnings,
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
    return KitModel(
        slug=slug,
        name=slug,
        version=conf_version,
        manifest_source="legacy_layout",
        resources=resources,
        warnings=["legacy layout normalized to canonical KitModel"],
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
