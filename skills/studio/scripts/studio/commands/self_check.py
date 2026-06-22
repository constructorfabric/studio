"""
Self-Check Command — validate kit examples against their own templates/constraints.

Ensures kit integrity by verifying that generated templates and examples
pass the same heading contract and constraint checks used for user artifacts.

@cpt-flow:cpt-studio-flow-developer-experience-self-check:p1
@cpt-algo:cpt-studio-algo-developer-experience-self-check:p1
@cpt-dod:cpt-studio-dod-developer-experience-self-check:p1
"""

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..utils.artifacts_meta import ArtifactsMeta
from ..utils.constraints import (
    error as constraints_error,
    heading_constraint_ids_by_line,
    validate_artifact_file,
    validate_headings_contract,
)
from ..utils import error_codes as EC
from ..utils.document import read_text_safe

logger = logging.getLogger(__name__)


def _warn_self_check(message: str) -> None:
    logger.warning("self-check: %s", message)


@dataclass
class _KitConstraintsLoad:
    """Resolved constraints inputs for one kit."""

    constraints: object
    errors: List[object]
    path: Optional[Path]


@dataclass
class _KitCheckContext:
    """Resolved filesystem and constraints context for one kit."""

    kit_id: str
    kit_obj: object
    kit_base: Path
    artifacts_dir: Path
    raw_map: object
    constraints: object
    constraints_path: Optional[Path]
    constraint_errors: List[object]


def _get_constraints_for_kind(kit_constraints: object, kind_u: str) -> object:
    """Return loaded constraints for one artifact kind."""
    by_kind = getattr(kit_constraints, "by_kind", None) if kit_constraints is not None else None
    if by_kind and kind_u in by_kind:
        return by_kind[kind_u]
    return None


def _find_occurrences(lines: List[str], needle: str) -> List[int]:
    """Return 1-based line numbers containing a substring."""
    if not needle:
        return []
    return [idx0 + 1 for idx0, raw in enumerate(lines) if needle in raw]


def _find_definition_occurrences(lines: List[str], template_id: str) -> List[int]:
    """Return 1-based line numbers containing a definition placeholder."""
    if not template_id:
        return []
    hits: List[int] = []
    for idx0, raw in enumerate(lines):
        if "**ID**" not in raw:
            continue
        if f"`{template_id}`" in raw:
            hits.append(idx0 + 1)
    return hits


def _active_headings_at(headings_at: object, line_no: int) -> List[str]:
    """Return normalized active headings for a line index."""
    if headings_at is None or line_no >= len(headings_at):
        return []
    return [str(h).strip() for h in headings_at[line_no]]


def _kind_from_pattern(pattern: str) -> Optional[str]:
    """Extract ID kind from a template pattern like cpt-{system}-KIND-{slug}."""
    token_stream = pattern
    if not token_stream.startswith("cpt-"):
        return None
    token_stream = token_stream[4:]
    while token_stream.startswith("{"):
        end = token_stream.find("}")
        if end < 0:
            return None
        token_stream = token_stream[end + 1:]
        if token_stream.startswith("-"):
            token_stream = token_stream[1:]
    dash_index = token_stream.find("-")
    token = (token_stream[:dash_index] if dash_index >= 0 else token_stream).strip().lower()
    return token if token else None


def _known_defined_kinds(constraints_for_kind: object) -> set[str]:
    """Return all ID kinds defined in one artifact kind's constraints."""
    return {
        str(getattr(id_constraint, "kind", "") or "").strip().lower()
        for id_constraint in (getattr(constraints_for_kind, "defined_id", None) or [])
        if str(getattr(id_constraint, "kind", "") or "").strip()
    }


def _known_all_kinds(kit_constraints: object) -> set[str]:
    """Return all ID kinds defined anywhere in a kit."""
    known_kinds: set[str] = set()
    by_kind = getattr(kit_constraints, "by_kind", None) if kit_constraints is not None else None
    if not by_kind:
        return known_kinds
    for kind_constraints in by_kind.values():
        for id_constraint in (getattr(kind_constraints, "defined_id", None) or []):
            kind_name = str(getattr(id_constraint, "kind", "") or "").strip().lower()
            if kind_name:
                known_kinds.add(kind_name)
    return known_kinds


def _append_missing_definition_placeholder(
    issues: Dict[str, List[Dict[str, object]]],
    *,
    required: bool,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    id_kind: str,
    template_id: str,
) -> None:
    """Record a missing definition-placeholder issue at the appropriate severity."""
    issue = constraints_error(
        "template",
        "Template missing ID placeholder for defined kind"
        if required else
        "Template missing optional ID placeholder for defined kind",
        path=template_path,
        line=1,
        kit_id=kit_id,
        artifact_kind=kind_u,
        id_kind=id_kind,
        id_kind_template=template_id,
    )
    target = "errors" if required else "warnings"
    issues[target].append(issue)


def _allowed_heading_names(id_constraint: object) -> List[str]:
    return [
        str(heading).strip()
        for heading in (getattr(id_constraint, "headings", None) or [])
        if str(heading).strip()
    ]


def _append_missing_template_id_issue(
    issues: Dict[str, List[Dict[str, object]]],
    *,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    id_kind: str,
) -> None:
    issues["errors"].append(constraints_error(
        "template",
        "ID kind has no template in constraints.toml",
        path=template_path,
        line=1,
        kit_id=kit_id,
        artifact_kind=kind_u,
        id_kind=id_kind,
    ))


def _collect_outside_heading_hits(
    *,
    headings_at: object,
    occurrences: List[int],
    allowed_norm: set[str],
) -> List[Tuple[int, List[str]]]:
    outside_hits: List[Tuple[int, List[str]]] = []
    for line_no in occurrences:
        active = _active_headings_at(headings_at, line_no)
        if any(active_heading.lower() in allowed_norm for active_heading in active):
            continue
        outside_hits.append((line_no, active))
    return outside_hits


def _check_defined_id_placeholders(
    *,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    constraints_for_kind: object,
    lines: List[str],
    headings_at: object,
) -> Dict[str, List[Dict[str, object]]]:
    """Validate definition placeholders required by one template."""
    issues: Dict[str, List[Dict[str, object]]] = {"errors": [], "warnings": []}
    for id_constraint in (getattr(constraints_for_kind, "defined_id", None) or []):
        id_kind = str(getattr(id_constraint, "kind", "") or "").strip().lower()
        if not id_kind:
            continue
        template_id = str(getattr(id_constraint, "template", "") or "").strip()
        if not template_id:
            _append_missing_template_id_issue(
                issues,
                template_path=template_path,
                kit_id=kit_id,
                kind_u=kind_u,
                id_kind=id_kind,
            )
            continue

        occurrences = _find_definition_occurrences(lines, template_id)
        if not occurrences:
            _append_missing_definition_placeholder(
                issues,
                required=bool(getattr(id_constraint, "required", False)),
                template_path=template_path,
                kit_id=kit_id,
                kind_u=kind_u,
                id_kind=id_kind,
                template_id=template_id,
            )
            continue

        allowed_norm = {heading.lower() for heading in _allowed_heading_names(id_constraint)}
        if not allowed_norm or headings_at is None:
            continue
        for line_no, active in _collect_outside_heading_hits(
            headings_at=headings_at,
            occurrences=occurrences,
            allowed_norm=allowed_norm,
        ):
            issues["errors"].append(constraints_error(
                "template",
                "ID placeholder not under required headings",
                path=template_path,
                line=line_no,
                kit_id=kit_id,
                artifact_kind=kind_u,
                id_kind=id_kind,
                id_kind_template=template_id,
                headings=sorted(allowed_norm),
                found_headings=active,
            ))
    return issues


def _check_template_pattern_kinds(  # pylint: disable=too-many-locals
    *,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    constraints_for_kind: object,
    kit_constraints: object,
    lines: List[str],
) -> List[Dict[str, object]]:
    """Validate that all template ID patterns refer to registered kinds."""
    errors: List[Dict[str, object]] = []
    template_pattern = re.compile(r"`(cpt-[^`]*\{[^`]*)`")
    defined_kinds = _known_defined_kinds(constraints_for_kind)
    all_kinds = _known_all_kinds(kit_constraints)
    for idx0, raw in enumerate(lines):
        for match in template_pattern.finditer(raw):
            issue = _template_pattern_kind_issue(
                raw=raw,
                found=match.group(1),
                line_no=idx0 + 1,
                defined_kinds=defined_kinds,
                all_kinds=all_kinds,
                template_path=template_path,
                kit_id=kit_id,
                kind_u=kind_u,
            )
            if issue is not None:
                errors.append(issue)
    return errors


def _template_pattern_kind_issue(
    *,
    raw: str,
    found: str,
    line_no: int,
    defined_kinds: set[str],
    all_kinds: set[str],
    template_path: Path,
    kit_id: str,
    kind_u: str,
) -> Optional[Dict[str, object]]:
    """Return a single invalid-kind issue for one template placeholder, if any."""
    found_kind = _kind_from_pattern(found)
    if not found_kind:
        return None
    is_definition = "**ID**" in raw
    known_kinds = defined_kinds if is_definition else all_kinds
    if found_kind in known_kinds:
        return None
    issue_code = EC.TEMPLATE_DEF_KIND_NOT_IN_CONSTRAINTS if is_definition else EC.TEMPLATE_REF_KIND_NOT_IN_CONSTRAINTS
    issue_kind = "definition" if is_definition else "reference"
    return constraints_error(
        "template",
        f"Template has {issue_kind} `{found}` whose kind `{found_kind}` is not in constraints",
        code=issue_code,
        path=template_path,
        line=line_no,
        kit_id=kit_id,
        artifact_kind=kind_u,
        id_kind_template=found,
    )


def _build_reference_expectations(  # pylint: disable=too-many-locals
    *,
    constraints_for_kind: object,
    kind_u: str,
    kit_constraints: object,
) -> Dict[Tuple[str, str], Dict[str, object]]:
    """Collect reference placeholders the target template is expected to expose."""
    expectations: Dict[Tuple[str, str], Dict[str, object]] = {}
    defined_kinds_here = _known_defined_kinds(constraints_for_kind)
    by_kind = getattr(kit_constraints, "by_kind", None) if kit_constraints is not None else None
    if not by_kind:
        return expectations
    for source_constraints in by_kind.values():
        for id_constraint in (getattr(source_constraints, "defined_id", None) or []):
            id_kind = str(getattr(id_constraint, "kind", "") or "").strip().lower()
            template_id = str(getattr(id_constraint, "template", "") or "").strip()
            if not id_kind or not template_id or id_kind in defined_kinds_here:
                continue
            references = getattr(id_constraint, "references", None) or {}
            rule = references.get(kind_u)
            if rule is None or getattr(rule, "coverage", None) is False:
                continue
            allowed = [
                str(heading).strip()
                for heading in (getattr(rule, "headings", None) or [])
                if str(heading).strip()
            ]
            key = (id_kind, template_id)
            target = expectations.setdefault(
                key,
                {"required": False, "allowed": set()},
            )
            target["required"] = bool(target["required"]) or (getattr(rule, "coverage", None) is True)
            target["allowed"].update(heading.lower() for heading in allowed)
    return expectations


def _append_missing_reference_issue(
    issues: Dict[str, List[Dict[str, object]]],
    target: str,
    *,
    required: bool,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    id_kind: str,
    template_id: str,
) -> None:
    issues[target].append(constraints_error(
        "template",
        (
            "Template missing required reference placeholder"
            if required
            else "Template missing optional reference placeholder"
        ),
        path=template_path,
        line=1,
        kit_id=kit_id,
        artifact_kind=kind_u,
        id_kind=id_kind,
        id_kind_template=template_id,
    ))


def _check_reference_placeholders(  # pylint: disable=too-many-locals
    *,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    expectations: Dict[Tuple[str, str], Dict[str, object]],
    lines: List[str],
    headings_at: object,
) -> Dict[str, List[Dict[str, object]]]:
    """Validate required and optional cross-artifact reference placeholders."""
    issues: Dict[str, List[Dict[str, object]]] = {"errors": [], "warnings": []}
    for (id_kind, template_id), expectation in expectations.items():
        occurrences = _find_occurrences(lines, template_id)
        required = bool(expectation.get("required"))
        if not occurrences:
            target = "errors" if required else "warnings"
            _append_missing_reference_issue(
                issues,
                target,
                required=required,
                template_path=template_path,
                kit_id=kit_id,
                kind_u=kind_u,
                id_kind=id_kind,
                template_id=template_id,
            )
            continue

        issue = _required_reference_heading_issue(
            headings_at=headings_at,
            occurrences=occurrences,
            allowed_norm=set(expectation.get("allowed") or set()),
            required=required,
            template_path=template_path,
            kit_id=kit_id,
            kind_u=kind_u,
            id_kind=id_kind,
            template_id=template_id,
        )
        if issue is not None:
            issues["errors"].append(issue)
    return issues


def _required_reference_heading_issue(  # pylint: disable=too-many-arguments
    *,
    headings_at: object,
    occurrences: List[int],
    allowed_norm: set[str],
    required: bool,
    template_path: Path,
    kit_id: str,
    kind_u: str,
    id_kind: str,
    template_id: str,
) -> Optional[Dict[str, object]]:
    """Return a heading-placement issue for one required reference, if any."""
    if not required or not allowed_norm or headings_at is None:
        return None
    outside_hits = _collect_outside_heading_hits(
        headings_at=headings_at,
        occurrences=occurrences,
        allowed_norm=allowed_norm,
    )
    if len(outside_hits) != len(occurrences):
        return None
    error_line, active = outside_hits[0] if outside_hits else (1, [])
    return constraints_error(
        "template",
        "Required reference placeholder not under required headings",
        path=template_path,
        line=error_line,
        kit_id=kit_id,
        artifact_kind=kind_u,
        id_kind=id_kind,
        id_kind_template=template_id,
        headings=sorted(allowed_norm),
        found_headings=active,
    )


def _check_template_constraints_consistency(
    *,
    template_path: Path,
    kind: str,
    kit_id: str,
    kit_base: Path,
    kit_constraints: object,
    artifacts_meta: ArtifactsMeta,
    constraints_path: Optional[Path] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """Validate template structure, placeholder kinds, and reference placeholders."""
    issues: Dict[str, List[Dict[str, object]]] = {"errors": [], "warnings": []}
    if kit_constraints is None:
        return issues

    kind_u = str(kind).strip().upper()
    constraints_for_kind = _get_constraints_for_kind(kit_constraints, kind_u)
    if constraints_for_kind is None:
        return issues

    report = validate_headings_contract(
        path=template_path,
        constraints=constraints_for_kind,
        registered_systems=artifacts_meta.get_all_system_prefixes(),
        artifact_kind=kind_u,
        constraints_path=_resolve_constraints_path(kit_base, constraints_path),
        kit_id=str(kit_id),
    )
    issues["errors"].extend(list(report.get("errors", []) or []))
    issues["warnings"].extend(list(report.get("warnings", []) or []))
    if issues["errors"]:
        return issues

    lines = _load_template_lines(template_path)
    if lines is None:
        issues["errors"].append(constraints_error(
            "template",
            "Template file could not be read",
            path=template_path,
            line=1,
            kit_id=str(kit_id),
            artifact_kind=kind_u,
        ))
        return issues

    headings_at = None
    if getattr(constraints_for_kind, "headings", None):
        headings_at = heading_constraint_ids_by_line(template_path, constraints_for_kind.headings)

    definition_issues = _check_defined_id_placeholders(
        template_path=template_path,
        kit_id=str(kit_id),
        kind_u=kind_u,
        constraints_for_kind=constraints_for_kind,
        lines=lines,
        headings_at=headings_at,
    )
    issues["errors"].extend(definition_issues["errors"])
    issues["warnings"].extend(definition_issues["warnings"])
    issues["errors"].extend(_check_template_pattern_kinds(
        template_path=template_path,
        kit_id=str(kit_id),
        kind_u=kind_u,
        constraints_for_kind=constraints_for_kind,
        kit_constraints=kit_constraints,
        lines=lines,
    ))

    reference_issues = _check_reference_placeholders(
        template_path=template_path,
        kit_id=str(kit_id),
        kind_u=kind_u,
        expectations=_build_reference_expectations(
            constraints_for_kind=constraints_for_kind,
            kind_u=kind_u,
            kit_constraints=kit_constraints,
        ),
        lines=lines,
        headings_at=headings_at,
    )
    issues["errors"].extend(reference_issues["errors"])
    issues["warnings"].extend(reference_issues["warnings"])
    return issues


def _resolve_constraints_path(
    kit_base: Path,
    constraints_path: Optional[Path],
) -> Optional[Path]:
    """Resolve the constraints file path used for heading-contract reporting."""
    if constraints_path is not None:
        return constraints_path
    try:
        return (kit_base / "constraints.toml").resolve()
    except OSError as exc:
        _warn_self_check(f"failed to resolve constraints path under {kit_base}: {exc}")
        return None


def _load_template_lines(template_path: Path) -> Optional[List[str]]:
    """Read template text for secondary placeholder validation."""
    return read_text_safe(template_path)


def _load_kit_constraints(
    *,
    kit_obj: object,
    kit_base: Path,
    load_constraints_files,
    load_constraints_toml,
) -> _KitConstraintsLoad:
    """Load constraints for one kit from explicit paths or local constraints.toml."""
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-load-constraints
    explicit_constraints_paths = [
        Path(path_value)
        for path_value in (getattr(kit_obj, "constraints_paths", None) or [])
        if path_value
    ]
    explicit_constraints_path = getattr(kit_obj, "constraints_path", None)
    if explicit_constraints_path and not explicit_constraints_paths:
        explicit_constraints_paths = [Path(explicit_constraints_path)]

    constraints_path = explicit_constraints_paths[0] if explicit_constraints_paths else None
    if explicit_constraints_paths:
        constraints, errors = load_constraints_files(explicit_constraints_paths)
        return _KitConstraintsLoad(constraints=constraints, errors=list(errors), path=constraints_path)

    constraints, errors = load_constraints_toml(kit_base)
    try:
        constraints_path = (kit_base / "constraints.toml").resolve()
    except OSError as exc:
        _warn_self_check(f"failed to resolve constraints path under {kit_base}: {exc}")
        constraints_path = None
    return _KitConstraintsLoad(constraints=constraints, errors=list(errors), path=constraints_path)
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-load-constraints


def _iter_kinds_to_check(raw_map: object, artifacts_dir: Path) -> List[str]:
    """Resolve artifact kinds to validate for one kit."""
    if isinstance(raw_map, dict) and raw_map:
        return sorted([
            str(kind_name).strip()
            for kind_name in raw_map.keys()
            if isinstance(kind_name, str) and str(kind_name).strip()
        ])
    if artifacts_dir.is_dir():
        return sorted([entry.name for entry in artifacts_dir.iterdir() if entry.is_dir()])
    return []


def _build_kit_context(
    *,
    kit_id: object,
    kit_obj: object,
    adapter_dir: Path,
    project_root: Path,
    load_constraints_files,
    load_constraints_toml,
) -> Optional[_KitCheckContext]:
    """Resolve on-disk paths and loaded constraints for one kit."""
    if kit_obj is None:
        return None
    kit_path_str = str(getattr(kit_obj, "path", "") or "").strip()
    if not kit_path_str:
        return None
    kit_base = (adapter_dir / kit_path_str).resolve()
    if not kit_base.is_dir():
        kit_base = (project_root / kit_path_str).resolve()
    artifacts_dir = kit_base / "artifacts"
    constraints_load = _load_kit_constraints(
        kit_obj=kit_obj,
        kit_base=kit_base,
        load_constraints_files=load_constraints_files,
        load_constraints_toml=load_constraints_toml,
    )
    return _KitCheckContext(
        kit_id=str(kit_id),
        kit_obj=kit_obj,
        kit_base=kit_base,
        artifacts_dir=artifacts_dir,
        raw_map=getattr(kit_obj, "artifacts", None) or {},
        constraints=constraints_load.constraints,
        constraints_path=constraints_load.path,
        constraint_errors=constraints_load.errors,
    )


def _append_constraints_load_failure(
    results: List[Dict[str, object]],
    *,
    kit_id: str,
    kit_base: Path,
    constraints_path: Optional[Path],
    constraint_errors: List[object],
) -> None:
    """Record a failed constraints load as one result item."""
    results.append({
        "kit": kit_id,
        "kind": None,
        "status": "FAIL",
        "error_count": len(constraint_errors),
        "errors": [constraints_error(
            "constraints",
            "Invalid constraints.toml",
            path=(constraints_path or (kit_base / "constraints.toml")),
            line=1,
            errors=list(constraint_errors),
        )],
    })


def _validate_example_paths(
    *,
    example_paths: List[Path],
    kind: str,
    kit_id: str,
    constraints_for_kind: object,
    constraints_path: Optional[Path],
) -> Dict[str, List[Dict[str, object]]]:
    """Validate example artifacts for one kind."""
    issues: Dict[str, List[Dict[str, object]]] = {"errors": [], "warnings": []}
    for example_path in example_paths:
        report = validate_artifact_file(
            artifact_path=example_path,
            artifact_kind=str(kind),
            constraints=constraints_for_kind,
            registered_systems=None,
            constraints_path=constraints_path,
            kit_id=str(kit_id),
        )
        issues["errors"].extend(list(report.get("errors", []) or []))
        issues["warnings"].extend(list(report.get("warnings", []) or []))
    return issues


def _build_kind_result(
    *,
    kit_ctx: _KitCheckContext,
    kind: str,
    template_path: Optional[Path],
    example_paths: List[Path],
    artifacts_meta: ArtifactsMeta,
    verbose: bool,
) -> Dict[str, object]:
    """Validate one kit artifact kind and build the result item."""
    kind_u = str(kind).upper()
    item: Dict[str, object] = {
        "kit": kit_ctx.kit_id,
        "kind": kind,
        "example_path": example_paths[0].as_posix() if example_paths else None,
        "example_paths": [path.as_posix() for path in example_paths],
        "examples_checked": len(example_paths),
        "status": "PASS",
    }
    issues: Dict[str, List[Dict[str, object]]] = {"errors": [], "warnings": []}
    if template_path is not None and template_path.is_file():
        # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-validate-template
        # @cpt-begin:cpt-studio-algo-developer-experience-self-check:p1:inst-validate-headings
        # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-check-consistency
        report = _check_template_constraints_consistency(
            template_path=template_path,
            kind=kind,
            kit_id=kit_ctx.kit_id,
            kit_base=kit_ctx.kit_base,
            kit_constraints=kit_ctx.constraints,
            artifacts_meta=artifacts_meta,
            constraints_path=kit_ctx.constraints_path,
        )
        issues["errors"].extend(report["errors"])
        issues["warnings"].extend(report["warnings"])
        # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-check-consistency
        # @cpt-end:cpt-studio-algo-developer-experience-self-check:p1:inst-validate-headings
        # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-validate-template

    if example_paths:
        # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-validate-example
        issues_for_examples = _validate_example_paths(
            example_paths=example_paths,
            kind=kind,
            kit_id=kit_ctx.kit_id,
            constraints_for_kind=_get_constraints_for_kind(kit_ctx.constraints, kind_u),
            constraints_path=kit_ctx.constraints_path,
        )
        issues["errors"].extend(issues_for_examples["errors"])
        issues["warnings"].extend(issues_for_examples["warnings"])
        # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-validate-example

    if issues["errors"]:
        item["status"] = "FAIL"
        item["error_count"] = len(issues["errors"])
        item["errors"] = issues["errors"]
    if issues["warnings"]:
        item["warning_count"] = len(issues["warnings"])
        if issues["errors"] or bool(verbose):
            item["warnings"] = issues["warnings"]
    return item


# @cpt-begin:cpt-studio-algo-developer-experience-self-check:p1:inst-locate-files
def _resolve_kit_kind_paths(  # pylint: disable=too-many-locals
    *,
    kit_obj: object,
    kind: str,
    adapter_dir: Path,
    project_root: Path,
    artifacts_dir: Path,
    explicit_kind: bool,
) -> Tuple[Optional[Path], Optional[Path]]:
    """Resolve template and examples paths for one kit artifact kind."""
    template_path: Optional[Path] = None
    examples_dir: Optional[Path] = None
    try:
        rel = kit_obj.get_template_path(kind)
        if str(rel or "").strip():
            candidate = (adapter_dir / rel).resolve()
            template_path = candidate if candidate.is_file() else (project_root / rel).resolve()
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Failed to resolve template path for kit kind %s: %s", kind, exc)
        template_path = None
    try:
        rel = kit_obj.get_examples_path(kind)
        if str(rel or "").strip():
            candidate = (adapter_dir / rel).resolve()
            examples_dir = candidate if candidate.exists() else (project_root / rel).resolve()
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Failed to resolve examples path for kit kind %s: %s", kind, exc)
        examples_dir = None

    kind_dir = artifacts_dir / kind
    if template_path is None and not explicit_kind:
        template_path = (kind_dir / "template.md").resolve()
    if examples_dir is None and not explicit_kind:
        examples_dir = (kind_dir / "examples").resolve()
    return template_path, examples_dir


def _collect_example_paths(examples_dir: Optional[Path]) -> List[Path]:
    """Return markdown example paths from a file or directory."""
    if examples_dir is None:
        return []
    try:
        if not examples_dir.exists():
            return []
        if examples_dir.is_file():
            return [examples_dir]
        return sorted([p for p in Path(examples_dir).glob("*.md") if p.is_file()])
    except OSError as exc:
        _warn_self_check(f"failed to enumerate examples in {examples_dir}: {exc}")
        return []
# @cpt-end:cpt-studio-algo-developer-experience-self-check:p1:inst-locate-files


def _is_explicit_kind(raw_map: object, normalized_kind: str) -> bool:
    return bool(
        isinstance(raw_map, dict)
        and str(normalized_kind).upper() in {
            str(key).strip().upper()
            for key in raw_map.keys()
        }
    )


def _collect_kit_results(
    *,
    kit_ctx: _KitCheckContext,
    adapter_dir: Path,
    project_root: Path,
    artifacts_meta: ArtifactsMeta,
    verbose: bool,
) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-for-each-kind
    for kind in _iter_kinds_to_check(kit_ctx.raw_map, kit_ctx.artifacts_dir):
        normalized_kind = str(kind).strip()
        if not normalized_kind:
            continue
        template_path, examples_dir = _resolve_kit_kind_paths(
            kit_obj=kit_ctx.kit_obj,
            kind=normalized_kind,
            adapter_dir=adapter_dir,
            project_root=project_root,
            artifacts_dir=kit_ctx.artifacts_dir,
            explicit_kind=_is_explicit_kind(kit_ctx.raw_map, normalized_kind),
        )
        results.append(_build_kind_result(
            kit_ctx=kit_ctx,
            kind=normalized_kind,
            template_path=template_path,
            example_paths=_collect_example_paths(examples_dir),
            artifacts_meta=artifacts_meta,
            verbose=verbose,
        ))
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-for-each-kind
    return results


# @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-user-self-check
def run_self_check_from_meta(  # pylint: disable=too-many-locals
    *,
    project_root: Path,
    adapter_dir: Path,
    artifacts_meta: ArtifactsMeta,
    kit_filter: Optional[str] = None,
    verbose: bool = False,
) -> Tuple[int, Dict[str, object]]:
    """Run self-check using already-loaded registry metadata.

    This is used by both the CLI `self-check` command and by `validate` to fail-fast.
    It does NOT do studio/project discovery.
    """
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-user-self-check
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-load-registry
    from ..utils.constraints import load_constraints_files, load_constraints_toml
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-load-registry

    kits = getattr(artifacts_meta, "kits", None) or {}
    if not isinstance(kits, dict) or not kits:
        return 1, {
            "status": "ERROR",
            "message": "No kits defined in artifacts.toml",
            "project_root": project_root.as_posix(),
            "studio_dir": adapter_dir.as_posix(),
        }

    results: List[Dict[str, object]] = []
    overall_status = "PASS"
    kits_checked = 0
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-for-each-kit
    for kit_id, kit_obj in kits.items():
        if kit_filter and str(kit_id) != str(kit_filter):
            continue
        kit_status, kit_items, kit_increment = _run_single_kit_self_check(
            kit_id=kit_id,
            kit_obj=kit_obj,
            adapter_dir=adapter_dir,
            project_root=project_root,
            artifacts_meta=artifacts_meta,
            load_constraints_files=load_constraints_files,
            load_constraints_toml=load_constraints_toml,
            verbose=verbose,
        )
        if kit_status is None:
            continue
        kits_checked += kit_increment
        if kit_status == "FAIL":
            overall_status = "FAIL"
        results.extend(kit_items)
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-for-each-kit

    out = {
        "status": overall_status,
        "project_root": project_root.as_posix(),
        "studio_dir": adapter_dir.as_posix(),
        "kits_checked": kits_checked,
        "templates_checked": len(results),
        "results": results,
    }
    # @cpt-begin:cpt-studio-flow-developer-experience-self-check:p1:inst-return-self-check
    return (0 if overall_status == "PASS" else 2), out
    # @cpt-end:cpt-studio-flow-developer-experience-self-check:p1:inst-return-self-check


def _run_single_kit_self_check(
    *,
    kit_id: str,
    kit_obj: object,
    adapter_dir: Path,
    project_root: Path,
    artifacts_meta: ArtifactsMeta,
    load_constraints_files,
    load_constraints_toml,
    verbose: bool,
) -> Tuple[Optional[str], List[Dict[str, object]], int]:
    """Return status, emitted items, and kit-count increment for one kit."""
    kit_ctx = _build_kit_context(
        kit_id=kit_id,
        kit_obj=kit_obj,
        adapter_dir=adapter_dir,
        project_root=project_root,
        load_constraints_files=load_constraints_files,
        load_constraints_toml=load_constraints_toml,
    )
    if kit_ctx is None:
        return None, [], 0
    if kit_ctx.constraint_errors:
        failures: List[Dict[str, object]] = []
        _append_constraints_load_failure(
            failures,
            kit_id=kit_ctx.kit_id,
            kit_base=kit_ctx.kit_base,
            constraints_path=kit_ctx.constraints_path,
            constraint_errors=kit_ctx.constraint_errors,
        )
        return "FAIL", failures, 1
    items = _collect_kit_results(
        kit_ctx=kit_ctx,
        adapter_dir=adapter_dir,
        project_root=project_root,
        artifacts_meta=artifacts_meta,
        verbose=verbose,
    )
    status = "FAIL" if any(item.get("status") == "FAIL" for item in items) else "PASS"
    return status, items, 1
