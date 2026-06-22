"""Constraint models and validators for Studio traceability artifacts."""

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import error_codes as EC

@dataclass(frozen=True)
class ReferenceRule:
    """Per-reference validation requirements for a target ID kind."""

    coverage: Optional[bool] = None
    task: Optional[bool] = None
    priority: Optional[bool] = None
    headings: Optional[List[str]] = None

@dataclass(frozen=True)
class HeadingConstraint:
    """Expected heading shape for an artifact kind."""

    level: int
    pattern: Optional[str] = None
    description: Optional[str] = None
    required: bool = True
    multiple: Optional[bool] = None
    numbered: Optional[bool] = None
    id: Optional[str] = None
    prev: Optional[str] = None
    next: Optional[str] = None
    pointer: Optional[str] = None

@dataclass(frozen=True)
class IdConstraint:
    """ID validation contract for one artifact kind."""

    kind: str
    required: bool = True
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    examples: Optional[List[object]] = None
    task: Optional[bool] = None
    priority: Optional[bool] = None
    to_code: Optional[bool] = None
    headings: Optional[List[str]] = None
    references: Optional[Dict[str, ReferenceRule]] = None

def _parse_optional_bool(
    v: object, field: str,
) -> Tuple[Optional[bool], Optional[str]]:
    """Parse a boolean | None constraint field.

    Unified convention:
        true  → True  (required)
        false → False (prohibited)
        None  → None  (allowed / optional)
    """
    if v is None:
        return None, None
    if isinstance(v, bool):
        return v, None
    return None, f"Constraint field '{field}' must be boolean, got {type(v).__name__}"

@dataclass(frozen=True)
class ArtifactKindConstraints:
    """Validation constraints attached to one artifact kind."""

    name: Optional[str]
    description: Optional[str]
    defined_id: List[IdConstraint]
    headings: Optional[List[HeadingConstraint]] = None
    toc: bool = True

@dataclass(frozen=True)
class KitConstraints:
    """Loaded validation constraints for all artifact kinds in a kit."""

    by_kind: Dict[str, ArtifactKindConstraints]


@dataclass(frozen=True)
class ArtifactDefinitionValidationRules:
    """Shared rule context for per-definition artifact validation."""

    kind: str
    artifact_path: Path
    systems_set: set[str]
    all_kind_tokens: set[str]
    composite_nested_by_base: Dict[str, set[str]]
    allowed_defs: set[str]
    constraint_by_kind: Dict[str, IdConstraint]
    headings_at: Sequence[Sequence[str]]
    heading_desc_by_id: Dict[str, str]


@dataclass(frozen=True)
class ArtifactIdentifierPhaseContext:
    """Context bundle for definition/reference extraction within one artifact."""

    defs: List[Dict[str, object]]
    refs: List[Dict[str, object]]
    defs_by_id: Dict[str, Dict[str, object]]
    heading_ctx_for_line: Callable[[int], Tuple[List[str], Optional[int]]]
    scope_end_for_heading_idx: Callable[[Optional[int]], int]
    rules: ArtifactDefinitionValidationRules


@dataclass(frozen=True)
class HeadingErrorContext:
    """Inputs needed to report one heading-validation error."""

    heading_constraint: HeadingConstraint
    idx: int
    artifact_kind: str
    path: Path
    constraints_path: Optional[Path]
    kit_id: Optional[str]


@dataclass(frozen=True)
class HeadingValidationContext:
    """Shared state for validating one artifact's heading constraints."""

    heading_constraints: Sequence[HeadingConstraint]
    by_id: Dict[str, HeadingConstraint]
    artifact_kind: str
    path: Path
    constraints_path: Optional[Path]
    kit_id: Optional[str]
    errors: List[Dict[str, object]]

def error(kind: str, message: str, *, path: Path | str, line: int = 1, code: Optional[str] = None, **extra) -> Dict[str, object]:
    """Build a structured constraint validation error."""
    out: Dict[str, object] = {"type": kind, "message": message, "line": int(line)}
    if code:
        out["code"] = code
    path_s = str(path)
    out["path"] = path_s
    out["location"] = f"{path_s}:{int(line)}" if (path_s and not path_s.startswith("<")) else path_s
    extra = {k: v for k, v in extra.items() if v is not None}
    out.update(extra)
    return out
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel

# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-helpers
def _is_regex_pattern_hc(pat: str) -> bool:
    # Heuristic: treat as regex only if it contains typical regex metacharacters.
    # Note: ( ) are excluded — they commonly appear in natural heading text
    # like "Goals (Business Outcomes)" and should not trigger regex mode.
    return any(ch in pat for ch in ".^$*+?{}[]\\|")


def _compile_heading_patterns(
    heading_constraints: Sequence[HeadingConstraint],
) -> List[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]]:
    compiled: List[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]] = []
    for hc in heading_constraints:
        pat = getattr(hc, "pattern", None)
        if not pat:
            compiled.append((hc, None))
            continue
        pat_s = str(pat)
        if not _is_regex_pattern_hc(pat_s):
            compiled.append((hc, None))
            continue
        try:
            compiled.append((hc, re.compile(pat_s, flags=re.IGNORECASE)))
        except re.error:
            compiled.append((hc, re.compile(r"$^")))
    return compiled


def _find_first_lvl3_id(
    compiled: List[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
    start: int,
    end: int,
) -> Optional[str]:
    """Return the id of the first non-pattern level-3 heading in *compiled[start:end]*."""
    for j in range(start, end):
        hc3, _ = compiled[j]
        if int(getattr(hc3, "level", 0) or 0) != 3:
            continue
        if getattr(hc3, "pattern", None):
            continue
        cid = str(getattr(hc3, "id", "") or "").strip()
        if cid:
            return cid
    return None


def _build_wildcard_lvl3_map(
    compiled: List[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
    idx_by_level: Dict[int, List[int]],
) -> Dict[str, str]:
    wildcard: Dict[str, str] = {}
    lvl2_idxs = idx_by_level.get(2, [])
    for pos, i in enumerate(lvl2_idxs):
        hc2, _ = compiled[i]
        parent_id = str(getattr(hc2, "id", "") or "").strip()
        if not parent_id:
            continue
        next_lvl2 = lvl2_idxs[pos + 1] if pos + 1 < len(lvl2_idxs) else len(compiled)
        cid = _find_first_lvl3_id(compiled, i + 1, next_lvl2)
        if cid:
            wildcard[parent_id] = cid
    return wildcard


def _matches_level_title_hc(
    level: int,
    title_text: str,
    idx: int,
    compiled: List[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
) -> bool:
    hc, rx = compiled[idx]
    if int(getattr(hc, "level", 0) or 0) != int(level):
        return False
    pat = getattr(hc, "pattern", None)
    if not pat:
        return True
    if rx is not None:
        return bool(rx.search(title_text))
    return str(pat).strip().casefold() == str(title_text).strip().casefold()


def _pick_best_heading_match(
    level: int,
    title_text: str,
    idx_by_level: Dict[int, List[int]],
    compiled: List[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
    *,
    include_wildcards: bool = True,
) -> Optional[int]:
    candidates: List[int] = []
    for idx in idx_by_level.get(level, []):
        hc, _ = compiled[idx]
        if not include_wildcards and not getattr(hc, "pattern", None):
            continue
        if _matches_level_title_hc(level, title_text, idx, compiled):
            candidates.append(idx)
    if not candidates:
        return None
    candidates.sort(key=lambda i: (0 if getattr(compiled[i][0], "pattern", None) else 1, i))
    return candidates[0]


def _index_heading_constraints_by_level(
    compiled: Sequence[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
) -> Dict[int, List[int]]:
    idx_by_level: Dict[int, List[int]] = {}
    for idx, (hc, _) in enumerate(compiled):
        idx_by_level.setdefault(int(getattr(hc, "level", 0) or 0), []).append(idx)
    return idx_by_level


def _heading_constraint_id(
    compiled: Sequence[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
    idx: Optional[int],
) -> Optional[str]:
    if idx is None:
        return None
    return str(getattr(compiled[idx][0], "id", "") or "").strip() or None


def _resolve_heading_match(
    heading: Dict[str, object],
    current_lvl2_id: Optional[str],
    idx_by_level: Dict[int, List[int]],
    compiled: Sequence[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
    wildcard_lvl3_by_parent_lvl2_id: Dict[str, str],
) -> Tuple[Optional[str], Optional[str]]:
    lvl = int(heading.get("level", 0) or 0)
    title = str(heading.get("title_text") or "")
    next_lvl2_id = current_lvl2_id

    if lvl == 3:
        idx = _pick_best_heading_match(3, title, idx_by_level, list(compiled), include_wildcards=False)
        matched_id = _heading_constraint_id(compiled, idx)
        if matched_id is None and current_lvl2_id:
            matched_id = wildcard_lvl3_by_parent_lvl2_id.get(current_lvl2_id)
        return matched_id, next_lvl2_id

    idx = _pick_best_heading_match(lvl, title, idx_by_level, list(compiled))
    matched_id = _heading_constraint_id(compiled, idx)
    if lvl == 1:
        next_lvl2_id = None
    elif lvl == 2:
        next_lvl2_id = matched_id
    return matched_id, next_lvl2_id


def _match_heading_ids_by_line(
    headings: Sequence[Dict[str, object]],
    idx_by_level: Dict[int, List[int]],
    compiled: Sequence[Tuple[HeadingConstraint, Optional[re.Pattern[str]]]],
    wildcard_lvl3_by_parent_lvl2_id: Dict[str, str],
) -> Dict[int, str]:
    matched_ids_by_line: Dict[int, str] = {}
    current_lvl2_id: Optional[str] = None
    for heading in headings:
        line_no = int(heading.get("line", 0) or 0)
        level = int(heading.get("level", 0) or 0)
        if line_no <= 0 or level <= 0:
            continue
        matched_id, current_lvl2_id = _resolve_heading_match(
            heading,
            current_lvl2_id,
            idx_by_level,
            compiled,
            wildcard_lvl3_by_parent_lvl2_id,
        )
        if matched_id:
            matched_ids_by_line[line_no] = matched_id
    return matched_ids_by_line


def _build_heading_events_by_line(
    headings: Sequence[Dict[str, object]],
    matched_ids_by_line: Dict[int, str],
) -> Dict[int, Tuple[int, Optional[str]]]:
    events_by_line: Dict[int, Tuple[int, Optional[str]]] = {}
    for heading in headings:
        line_no = int(heading.get("line", 0) or 0)
        level = int(heading.get("level", 0) or 0)
        if line_no <= 0 or level <= 0:
            continue
        events_by_line[line_no] = (level, matched_ids_by_line.get(line_no))
    return events_by_line


def _heading_ids_for_lines(
    line_count: int,
    events_by_line: Dict[int, Tuple[int, Optional[str]]],
) -> List[List[str]]:
    out: List[List[str]] = [[] for _ in range(line_count + 1)]
    stack: List[Tuple[int, str]] = []
    for line_no in range(1, line_count + 1):
        event = events_by_line.get(line_no)
        if event is not None:
            level, heading_id = event
            while stack and stack[-1][0] >= level:
                stack.pop()
            if heading_id:
                stack.append((level, heading_id))
        out[line_no] = [heading_id for _, heading_id in stack]
    return out
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-helpers


# @cpt-algo:cpt-studio-algo-traceability-validation-headings-contract:p1
def heading_constraint_ids_by_line(path: Path, heading_constraints: Sequence[HeadingConstraint]) -> List[List[str]]:
    """Return active heading constraint ids for each line (1-indexed).

    This is similar to document.headings_by_line(), but instead of returning
    raw heading titles, it returns the list of *matched heading constraint ids*
    that are currently in scope at each line.

    Matching uses the same level/pattern rules as validate_headings_contract.
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope
    from .document import read_text_safe

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-init
    lines = read_text_safe(path)
    if lines is None:
        return [[]]

    compiled = _compile_heading_patterns(heading_constraints)
    headings = _scan_headings(path)
    idx_by_level = _index_heading_constraints_by_level(compiled)
    wildcard_lvl3_by_parent_lvl2_id = _build_wildcard_lvl3_map(compiled, idx_by_level)
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-init

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-match-loop
    matched_ids_by_line = _match_heading_ids_by_line(
        headings,
        idx_by_level,
        compiled,
        wildcard_lvl3_by_parent_lvl2_id,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-match-loop

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-stack
    # Convert heading events into a per-line active stack.
    events_by_line = _build_heading_events_by_line(headings, matched_ids_by_line)
    return _heading_ids_for_lines(len(lines), events_by_line)
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-stack
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel
@dataclass(frozen=True)
class ParsedStudioId:
    """Parsed Studio traceability identifier components."""

    system: str
    kind: str
    slug: str
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-parse-cpt-fn
def parse_cpt(
    cpt: str,
    expected_kind: str,
    registered_systems: Iterable[str],
    where_defined: Optional[callable] = None,
    known_kinds: Optional[Iterable[str]] = None,
) -> Optional[ParsedStudioId]:
    """Parse a Studio cpt identifier for an expected kind."""
    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-parse-cpt
    cpt = str(cpt)
    expected_kind = str(expected_kind)
    if not cpt or not cpt.lower().startswith("cpt-") or len(cpt.split("-")) < 3:
        return None

    system = _find_registered_system(cpt, registered_systems)
    if system is None:
        return None

    remainder, rem_parts = _split_cpt_remainder(cpt, system)
    if remainder is None:
        return None

    kinds_set = _known_kind_set(known_kinds)

    if kinds_set is not None and expected_kind.strip().lower() not in kinds_set:
        return None

    parsed = _parse_direct_cpt_match(system, rem_parts, expected_kind)
    if parsed is not None:
        return parsed

    return _parse_composite_cpt_match(
        system=system,
        remainder=remainder,
        expected_kind=expected_kind,
        where_defined=where_defined,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-parse-cpt
# @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-parse-cpt-fn


def _split_cpt_remainder(cpt: str, system: str) -> Tuple[Optional[str], List[str]]:
    remainder = cpt[len(f"cpt-{system}-"):]
    if not remainder:
        return None, []
    rem_parts = [part for part in remainder.split("-") if part]
    if not rem_parts:
        return None, []
    return remainder, rem_parts


def _known_kind_set(known_kinds: Optional[Iterable[str]]) -> Optional[set[str]]:
    if known_kinds is None:
        return None
    return {str(kind).strip().lower() for kind in known_kinds if str(kind).strip()}


def _find_registered_system(cpt: str, registered_systems: Iterable[str]) -> Optional[str]:
    systems = sorted({str(system) for system in registered_systems if str(system).strip()}, key=len, reverse=True)
    return next((system for system in systems if cpt.lower().startswith(f"cpt-{system}-".lower())), None)


def _parse_direct_cpt_match(
    system: str,
    rem_parts: Sequence[str],
    expected_kind: str,
) -> Optional[ParsedStudioId]:
    if rem_parts[0].lower() != expected_kind.lower():
        return None
    slug = "-".join(rem_parts[1:]) if len(rem_parts) > 1 else ""
    return ParsedStudioId(system=system, kind=expected_kind, slug=slug)


def _parse_composite_cpt_match(
    *,
    system: str,
    remainder: str,
    expected_kind: str,
    where_defined: Optional[callable],
) -> Optional[ParsedStudioId]:
    sep = f"-{expected_kind}-"
    idx = remainder.lower().find(sep.lower())
    if idx == -1:
        return None
    left = f"cpt-{system}-" + remainder[:idx]
    if where_defined is not None and not where_defined(left):
        return None
    slug = remainder[idx + len(sep):]
    return ParsedStudioId(system=system, kind=expected_kind, slug=slug)


def _find_kind_marker(remainder: str, kind_tokens: Iterable[str]) -> Optional[str]:
    rem_l = remainder.lower()
    best_pos: Optional[int] = None
    best_kind: Optional[str] = None
    for kt in kind_tokens:
        marker = f"-{kt}-"
        idx = rem_l.find(marker)
        if idx > 0 and (best_pos is None or idx < best_pos):
            best_pos = idx
            best_kind = kt
    return best_kind


def _match_registered_system(cpt: str, systems_set: set[str]) -> Optional[str]:
    matched: Optional[str] = None
    for sys in systems_set:
        prefix = f"cpt-{sys}-"
        if cpt.lower().startswith(prefix):
            if matched is None or len(sys) > len(matched):
                matched = sys
    return matched


def _infer_system_from_kind_tokens(cpt: str, kind_tokens: Iterable[str]) -> Optional[str]:
    remainder = cpt[4:]
    best_pos: Optional[int] = None
    for kt in kind_tokens:
        marker = f"-{kt}-"
        idx = remainder.find(marker)
        if idx > 0 and (best_pos is None or idx > best_pos):
            best_pos = idx
    if best_pos is not None:
        return remainder[:best_pos].lower()
    parts = cpt.split("-")
    return parts[1].lower() if len(parts) >= 3 else None


def _match_system_from_id(cpt: str, systems_set: set[str], kind_tokens: Iterable[str]) -> Optional[str]:
    if not cpt.lower().startswith("cpt-"):
        return None
    if systems_set:
        return _match_registered_system(cpt, systems_set)
    return _infer_system_from_kind_tokens(cpt, kind_tokens)


def _extract_kind_from_cpt(
    cpt: str,
    system: Optional[str],
    kind_tokens: Iterable[str],
    composite_nested_by_base: Dict[str, set[str]],
) -> Optional[str]:
    if not cpt.lower().startswith("cpt-") or system is None:
        return None
    prefix = f"cpt-{system}-"
    if not cpt.lower().startswith(prefix.lower()):
        return None
    remainder, parts = _split_cpt_remainder(cpt, system)
    if remainder is None:
        return None

    base = parts[0].strip().lower()
    nested_kinds = composite_nested_by_base.get(base)
    if nested_kinds and len(parts) >= 4:
        for part in reversed(parts[2:]):
            candidate = part.strip().lower()
            if candidate in nested_kinds and candidate != base:
                return candidate

    normalized_kind_tokens = {str(k).strip().lower() for k in kind_tokens if str(k).strip()}
    if base in normalized_kind_tokens:
        return base

    return _find_kind_marker(remainder, normalized_kind_tokens) or base

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel
@dataclass(frozen=True)
class ArtifactRecord:
    """Artifact file plus its resolved validation constraints."""

    path: Path
    artifact_kind: str
    constraints: Optional[ArtifactKindConstraints] = None


@dataclass(frozen=True)
class DefinitionValidationContext:
    """Shared validation context for a definition hit."""

    hid: str
    id_kind: str
    constraint: IdConstraint
    line: int
    artifact_kind: str
    artifact_path: Path
    id_kind_name: Optional[str]
    id_kind_description: Optional[str]
    id_kind_template: Optional[str]

    def base_fields(self) -> Dict[str, object]:
        """Return common error payload fields for definition validation."""
        return {
            "path": self.artifact_path,
            "line": self.line,
            "artifact_kind": self.artifact_kind,
            "id_kind": self.id_kind,
            "id": self.hid,
            "section": "defined-id",
            "id_kind_name": self.id_kind_name,
            "id_kind_description": self.id_kind_description,
            "id_kind_template": self.id_kind_template,
        }


@dataclass(frozen=True)
class ReferenceCheckContext:
    """Shared validation context for one definition/reference rule pair."""

    did: str
    artifact_kind: str
    target_kind: str
    id_kind: str
    id_meta: Dict[str, object]

    def error_fields(self) -> Dict[str, object]:
        """Return common error payload fields for reference validation."""
        return {
            "id": self.did,
            "artifact_kind": self.artifact_kind,
            "target_kind": self.target_kind,
            "id_kind": self.id_kind,
            **self.id_meta,
        }


@dataclass(frozen=True)
class AllowedHeadingContext:
    """Normalized allowed-heading data for one validation rule."""

    heading_ids: set[str]
    sorted_ids: List[str]
    info: List[Dict[str, object]]


@dataclass(frozen=True)
class CrossReferenceCoverageState:
    """Shared state for cross-artifact reference coverage validation."""

    defs_by_id: Dict[str, List[Dict[str, object]]]
    present_kinds_by_system: Dict[str, set[str]]
    refs_by_system_kind: Dict[str, Dict[str, List[Dict[str, object]]]]
    heading_desc_by_kind: Dict[str, Dict[str, str]]
    errors: List[Dict[str, object]]
    warnings: List[Dict[str, object]]


@dataclass
class CrossArtifactScanIndexes:
    """Indexed scan data reused across cross-artifact validation passes."""

    defs_by_id: Dict[str, List[Dict[str, object]]]
    refs_by_id: Dict[str, List[Dict[str, object]]]
    present_kinds_by_system: Dict[str, set[str]]
    refs_by_system_kind: Dict[str, Dict[str, List[Dict[str, object]]]]
    headings_cache: Dict[str, List[List[str]]]
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-helpers
# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-constraint-hint
def _constraint_hint(c: "IdConstraint") -> str:
    """Build a parenthesised hint string from an IdConstraint's metadata."""
    nm = str(getattr(c, "name", "") or "").strip()
    tpl = str(getattr(c, "template", "") or "").strip()
    desc = str(getattr(c, "description", "") or "").strip()
    parts = ([nm] if nm else []) + ([f"template={tpl}"] if tpl else []) + ([desc] if desc else [])
    return (" (" + "; ".join(parts) + ")") if parts else ""
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-constraint-hint

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-normalize-heading-id
def _normalize_heading_identifier(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_heading_identifiers(values: object) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in values or []:
        normalized = _normalize_heading_identifier(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-normalize-heading-id

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-task-priority
def _validate_task_priority_constraints(
    ctx: DefinitionValidationContext,
    hit: Dict[str, object],
    errors: List[Dict[str, object]],
) -> None:
    has_task = bool(hit.get("has_task", False))
    has_priority = bool(hit.get("has_priority", False))
    tk = getattr(ctx.constraint, "task", None)
    pr = getattr(ctx.constraint, "priority", None)
    hint = _constraint_hint(ctx.constraint)
    base = ctx.base_fields()

    if tk is True and not has_task:
        errors.append(error("constraints",
            f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact is missing required task checkbox `- [ ]`{hint}",
            code=EC.DEF_MISSING_TASK, **base))
    if tk is False and has_task:
        errors.append(error("constraints",
            f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact has task checkbox but kind `{ctx.id_kind}` prohibits task tracking{hint}",
            code=EC.DEF_PROHIBITED_TASK, **base))
    if pr is True and not has_priority:
        errors.append(error("constraints",
            f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact is missing required priority marker{hint}",
            code=EC.DEF_MISSING_PRIORITY, **base))
    if pr is False and has_priority:
        errors.append(error("constraints",
            f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact has priority marker but kind `{ctx.id_kind}` prohibits priority{hint}",
            code=EC.DEF_PROHIBITED_PRIORITY, **base))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-task-priority

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-heading-constraint
def _validate_id_heading_constraint(
    ctx: DefinitionValidationContext,
    headings_at: List[List[str]],
    heading_desc_by_id: Dict[str, str],
    errors: List[Dict[str, object]],
) -> None:
    allowed_headings = _normalize_heading_identifiers(getattr(ctx.constraint, "headings", None) or [])
    if not allowed_headings:
        return
    allowed_norm = set(allowed_headings)
    active_raw = headings_at[ctx.line] if 0 <= ctx.line < len(headings_at) else []
    active_norm = _normalize_heading_identifiers(active_raw)
    if any(a in allowed_norm for a in active_norm):
        return
    allowed_info = [
        {"id": h, "description": heading_desc_by_id.get(h)}
        for h in allowed_headings
    ]

    errors.append(error(
        "constraints",
        f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact is under {active_raw} but must be under one of {allowed_headings}{_constraint_hint(ctx.constraint)}",
        code=EC.DEF_WRONG_HEADINGS,
        **ctx.base_fields(),
        headings=allowed_headings,
        headings_info=allowed_info,
        found_headings=active_raw,
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-heading-constraint
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-helpers


def _build_defs_index(defs: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    defs_by_id: Dict[str, Dict[str, object]] = {}
    for definition in defs:
        did = str(definition.get("id") or "").strip()
        if did and did not in defs_by_id:
            defs_by_id[did] = definition
    return defs_by_id


def _build_heading_descriptions(constraints: ArtifactKindConstraints) -> Dict[str, str]:
    heading_desc_by_id: Dict[str, str] = {}
    for hc in (getattr(constraints, "headings", None) or []):
        hid = _normalize_heading_identifier(getattr(hc, "id", "") or "")
        if not hid:
            continue
        desc = str(getattr(hc, "description", "") or "").strip()
        if desc:
            heading_desc_by_id[hid] = desc
    return heading_desc_by_id


def _resolve_heading_scope_map(
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
) -> List[List[str]]:
    from .document import headings_by_line

    heading_constraints = getattr(constraints, "headings", None)
    if heading_constraints:
        return heading_constraint_ids_by_line(artifact_path, heading_constraints)
    return headings_by_line(artifact_path)


def _build_heading_context_helpers(
    artifact_path: Path,
) -> Tuple[List[Dict[str, object]], callable, callable]:
    headings_scanned = _scan_headings(artifact_path)

    def heading_ctx_for_line(ln: int) -> Tuple[int, Optional[int]]:
        last_idx: Optional[int] = None
        for idx, heading in enumerate(headings_scanned):
            if int(heading.get("line", 0) or 0) <= ln:
                last_idx = idx
                continue
            break
        if last_idx is None:
            return 0, None
        level = int(headings_scanned[last_idx].get("level", 0) or 0)
        return level, last_idx

    def scope_end_for_heading_idx(hidx: int) -> int:
        if hidx < 0 or hidx >= len(headings_scanned):
            return 10**9
        level = int(headings_scanned[hidx].get("level", 0) or 0)
        for idx in range(hidx + 1, len(headings_scanned)):
            next_level = int(headings_scanned[idx].get("level", 0) or 0)
            if next_level <= level:
                return int(headings_scanned[idx].get("line", 1) or 1) - 1
        return 10**9

    return headings_scanned, heading_ctx_for_line, scope_end_for_heading_idx


def _validate_cdsl_parent_child_state(
    *,
    defs: Sequence[Dict[str, object]],
    refs: Sequence[Dict[str, object]],
    kind: str,
    artifact_path: Path,
    errors: List[Dict[str, object]],
    heading_ctx_for_line: callable,
    scope_end_for_heading_idx: callable,
) -> None:
    defs_sorted = sorted(defs, key=lambda d: int(d.get("line", 0) or 0))
    refs_task_sorted = sorted(
        [ref for ref in refs if bool(ref.get("has_task", False))],
        key=lambda ref: int(ref.get("line", 0) or 0),
    )
    for parent in defs_sorted:
        scoped_parent = _resolve_scoped_parent_task(
            parent,
            defs_sorted=defs_sorted,
            refs_task_sorted=refs_task_sorted,
            heading_ctx_for_line=heading_ctx_for_line,
            scope_end_for_heading_idx=scope_end_for_heading_idx,
        )
        if scoped_parent is None:
            continue
        parent_id, children, ref_children = scoped_parent
        if not children and not ref_children:
            continue
        _validate_parent_task_state(
            parent=parent,
            parent_id=parent_id,
            kind=kind,
            artifact_path=artifact_path,
            errors=errors,
            children=children,
            ref_children=ref_children,
        )


def _resolve_scoped_parent_task(
    parent: Dict[str, object],
    *,
    defs_sorted: Sequence[Dict[str, object]],
    refs_task_sorted: Sequence[Dict[str, object]],
    heading_ctx_for_line: callable,
    scope_end_for_heading_idx: callable,
) -> Optional[Tuple[str, List[Dict[str, object]], List[Dict[str, object]]]]:
    if not bool(parent.get("has_task", False)):
        return None
    parent_line = int(parent.get("line", 0) or 0)
    if parent_line <= 0:
        return None
    parent_id = str(parent.get("id") or "").strip()
    if not parent_id:
        return None
    parent_lvl, parent_hidx = heading_ctx_for_line(parent_line)
    if parent_hidx is None:
        return None
    scope_end = scope_end_for_heading_idx(parent_hidx)
    children = _task_children_in_scope(
        defs_sorted,
        parent_line,
        scope_end,
        parent_lvl,
        heading_ctx_for_line,
    )
    ref_children = _refs_in_scope(refs_task_sorted, parent_line, scope_end)
    return parent_id, children, ref_children


def _task_children_in_scope(
    defs_sorted: Sequence[Dict[str, object]],
    parent_line: int,
    scope_end: int,
    parent_lvl: int,
    heading_ctx_for_line: callable,
) -> List[Dict[str, object]]:
    return [
        child
        for child in defs_sorted
        if parent_line < int(child.get("line", 0) or 0) <= scope_end
        and bool(child.get("has_task", False))
        and heading_ctx_for_line(int(child.get("line", 0) or 0))[0] > parent_lvl
    ]


def _refs_in_scope(
    refs_task_sorted: Sequence[Dict[str, object]],
    parent_line: int,
    scope_end: int,
) -> List[Dict[str, object]]:
    return [
        ref for ref in refs_task_sorted
        if parent_line < int(ref.get("line", 0) or 0) <= scope_end
    ]


def _checked_state(items: Sequence[Dict[str, object]]) -> Tuple[bool, bool]:
    checked = [bool(item.get("checked", False)) for item in items]
    return all(checked), any(not value for value in checked)


def _append_parent_all_done_error(
    errors: List[Dict[str, object]],
    parent_id: str,
    child_count: int,
    kind: str,
    artifact_path: Path,
    parent_line: int,
) -> None:
    errors.append(error(
        "structure",
        f"Parent `{parent_id}` is unchecked but all {child_count} nested task-tracked items are checked in {kind} artifact",
        code=EC.PARENT_UNCHECKED_ALL_DONE,
        path=artifact_path,
        line=parent_line,
        id=parent_id,
    ))


def _first_unchecked_item(
    children: Sequence[Dict[str, object]],
    ref_children: Sequence[Dict[str, object]],
    parent: Dict[str, object],
) -> Dict[str, object]:
    for item in list(children) + list(ref_children):
        if not bool(item.get("checked", False)):
            return item
    return parent


def _append_parent_nested_unchecked_error(
    errors: List[Dict[str, object]],
    parent_id: str,
    first: Dict[str, object],
    kind: str,
    artifact_path: Path,
) -> None:
    first_id = str(first.get("id") or "") or parent_id
    errors.append(error(
        "structure",
        f"Parent `{parent_id}` is checked but nested item `{first_id}` (and possibly others) is still unchecked in {kind} artifact",
        code=EC.PARENT_CHECKED_NESTED_UNCHECKED,
        path=artifact_path,
        line=int(first.get("line", 1) or 1),
        id=first_id,
        parent_id=parent_id,
    ))


def _validate_parent_task_state(
    *,
    parent: Dict[str, object],
    parent_id: str,
    kind: str,
    artifact_path: Path,
    errors: List[Dict[str, object]],
    children: Sequence[Dict[str, object]],
    ref_children: Sequence[Dict[str, object]],
) -> None:
    parent_checked = bool(parent.get("checked", False))
    all_children_checked, any_child_unchecked = _checked_state(children)
    all_ref_children_checked, any_ref_child_unchecked = _checked_state(ref_children)
    if all_children_checked and all_ref_children_checked and not parent_checked:
        _append_parent_all_done_error(
            errors,
            parent_id,
            len(children) + len(ref_children),
            kind,
            artifact_path,
            int(parent.get("line", 0) or 0),
        )
    if parent_checked and (any_child_unchecked or any_ref_child_unchecked):
        _append_parent_nested_unchecked_error(
            errors,
            parent_id,
            _first_unchecked_item(children, ref_children, parent),
            kind,
            artifact_path,
        )


def _build_definition_validation_context(
    *,
    hit: Dict[str, object],
    id_kind: str,
    constraint: IdConstraint,
    kind: str,
    artifact_path: Path,
) -> DefinitionValidationContext:
    return DefinitionValidationContext(
        hid=str(hit.get("id") or "").strip(),
        id_kind=id_kind,
        constraint=constraint,
        line=int(hit.get("line", 1) or 1),
        artifact_kind=kind,
        artifact_path=artifact_path,
        id_kind_name=str(getattr(constraint, "name", "") or "").strip() or None,
        id_kind_description=str(getattr(constraint, "description", "") or "").strip() or None,
        id_kind_template=str(getattr(constraint, "template", "") or "").strip() or None,
    )


def _build_artifact_identifier_rules(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    kind: str,
) -> ArtifactDefinitionValidationRules:
    allowed_defs = {constraint.kind.strip().lower() for constraint in (constraints.defined_id or [])}
    constraint_by_kind = {
        constraint.kind.strip().lower(): constraint
        for constraint in (constraints.defined_id or [])
        if isinstance(getattr(constraint, "kind", None), str)
    }
    nested = {
        str(getattr(id_constraint, "kind", "") or "").strip().lower()
        for id_constraint in (constraints.defined_id or [])
        if str(getattr(id_constraint, "kind", "") or "").strip()
    }
    return ArtifactDefinitionValidationRules(
        kind=kind,
        artifact_path=artifact_path,
        systems_set=set(),
        all_kind_tokens=set(allowed_defs),
        composite_nested_by_base={kind.strip().lower(): nested} if nested else {},
        allowed_defs=allowed_defs,
        constraint_by_kind=constraint_by_kind,
        headings_at=_resolve_heading_scope_map(artifact_path, constraints),
        heading_desc_by_id=_build_heading_descriptions(constraints),
    )


def _build_artifact_identifier_phase_context(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    kind: str,
    scan_cpt_ids,
) -> ArtifactIdentifierPhaseContext:
    hits = scan_cpt_ids(artifact_path)
    defs = [hit for hit in hits if str(hit.get("type")) == "definition"]
    refs = [hit for hit in hits if str(hit.get("type")) == "reference"]
    _, heading_ctx_for_line, scope_end_for_heading_idx = _build_heading_context_helpers(artifact_path)
    return ArtifactIdentifierPhaseContext(
        defs=defs,
        refs=refs,
        defs_by_id=_build_defs_index(defs),
        heading_ctx_for_line=heading_ctx_for_line,
        scope_end_for_heading_idx=scope_end_for_heading_idx,
        rules=_build_artifact_identifier_rules(
            artifact_path=artifact_path,
            constraints=constraints,
            kind=kind,
        ),
    )


def _validate_artifact_toc(
    artifact_path: Path,
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> None:
    from .document import read_text_safe as _read_text_safe
    from .toc import validate_toc as _validate_toc

    toc_lines = _read_text_safe(artifact_path)
    if toc_lines is None:
        return
    toc_result = _validate_toc(
        "\n".join(toc_lines),
        artifact_path=artifact_path,
        max_heading_level=3,
    )
    errors.extend(toc_result.get("errors", []))
    warnings.extend(toc_result.get("warnings", []))


def _validate_unchecked_cdsl_steps(
    *,
    cdsl_hits: Sequence[Dict[str, object]],
    defs_by_id: Dict[str, Dict[str, object]],
    kind: str,
    artifact_path: Path,
    errors: List[Dict[str, object]],
) -> None:
    for hit in cdsl_hits:
        if bool(hit.get("checked", False)):
            continue
        pid = str(hit.get("parent_id") or "").strip()
        if not pid:
            continue
        parent_def = defs_by_id.get(pid)
        if not parent_def:
            continue
        if not bool(parent_def.get("has_task", False)):
            continue
        if not bool(parent_def.get("checked", False)):
            continue
        inst_s = str(hit.get("inst") or "").strip()
        errors.append(error(
            "structure",
            f"CDSL step `{pid}`{(' inst ' + inst_s) if inst_s else ''} is unchecked but parent ID is already checked in {kind} artifact",
            code=EC.CDSL_STEP_UNCHECKED,
            path=artifact_path,
            line=int(hit.get("line", 1) or 1),
            id=pid,
            inst=inst_s or None,
        ))


def _validate_artifact_heading_phase(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    registered_systems: Optional[Iterable[str]],
    kind: str,
    constraints_path: Optional[Path],
    kit_id: Optional[str],
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> bool:
    """Run heading validation and return whether later ID validation may continue."""
    if not getattr(constraints, "headings", None):
        return True
    rep = validate_headings_contract(
        path=artifact_path,
        constraints=constraints,
        registered_systems=registered_systems,
        artifact_kind=kind,
        constraints_path=constraints_path,
        kit_id=kit_id,
    )
    errors.extend(rep.get("errors", []))
    warnings.extend(rep.get("warnings", []))
    return not bool(rep.get("errors"))


def _id_kind_hint(c: Optional[IdConstraint]) -> str:
    if c is None:
        return ""
    nm = str(getattr(c, "name", "") or "").strip()
    tpl = str(getattr(c, "template", "") or "").strip()
    desc = str(getattr(c, "description", "") or "").strip()
    parts: List[str] = []
    if nm:
        parts.append(nm)
    if tpl:
        parts.append(f"template={tpl}")
    if desc:
        parts.append(desc)
    return (" (" + "; ".join(parts) + ")") if parts else ""


def _validate_definition_hits(
    *,
    defs: Sequence[Dict[str, object]],
    rules: ArtifactDefinitionValidationRules,
    defs_by_kind: Dict[str, List[Dict[str, object]]],
    errors: List[Dict[str, object]],
) -> None:
    for hit in defs:
        hid = str(hit.get("id") or "").strip()
        if not hid:
            continue
        line = int(hit.get("line", 1) or 1)
        system = _match_system_from_id(hid, rules.systems_set, rules.all_kind_tokens)
        if system is None and rules.systems_set and hid.lower().startswith("cpt-"):
            errors.append(error(
                "constraints",
                f"`{hid}` has unrecognized system prefix (registered: {sorted(rules.systems_set)})",
                code=EC.ID_SYSTEM_UNRECOGNIZED,
                path=rules.artifact_path,
                line=line,
                artifact_kind=rules.kind,
                id=hid,
                registered_systems=sorted(rules.systems_set),
            ))
            continue
        id_kind = _extract_kind_from_cpt(
            hid,
            system,
            rules.all_kind_tokens,
            rules.composite_nested_by_base,
        )
        if not id_kind:
            continue
        defs_by_kind.setdefault(id_kind, []).append(hit)

        if id_kind not in rules.allowed_defs:
            hint = _id_kind_hint(rules.constraint_by_kind.get(id_kind))
            errors.append(error(
                "constraints",
                f"`{hid}` uses kind `{id_kind}` not allowed in {rules.kind} artifact (allowed: {sorted(rules.allowed_defs)}){hint}",
                code=EC.ID_KIND_NOT_ALLOWED,
                path=rules.artifact_path,
                line=line,
                artifact_kind=rules.kind,
                id_kind=id_kind,
                id=hid,
                section="defined-id",
                allowed=sorted(rules.allowed_defs),
            ))

        constraint = rules.constraint_by_kind.get(id_kind)
        if constraint is None:
            continue
        ctx = _build_definition_validation_context(
            hit=hit,
            id_kind=id_kind,
            constraint=constraint,
            kind=rules.kind,
            artifact_path=rules.artifact_path,
        )
        _validate_task_priority_constraints(ctx, hit, errors)
        _validate_id_heading_constraint(ctx, rules.headings_at, rules.heading_desc_by_id, errors)


def _validate_required_defined_ids(
    *,
    kind: str,
    constraints: ArtifactKindConstraints,
    defs_by_kind: Dict[str, List[Dict[str, object]]],
    heading_desc_by_id: Dict[str, str],
    artifact_path: Path,
    errors: List[Dict[str, object]],
) -> None:
    for constraint in constraints.defined_id:
        id_kind = str(getattr(constraint, "kind", "") or "").strip().lower()
        if not id_kind:
            continue
        if not bool(getattr(constraint, "required", True)):
            continue
        if id_kind in defs_by_kind and defs_by_kind[id_kind]:
            continue
        id_headings = [
            heading
            for heading in (getattr(constraint, "headings", None) or [])
            if isinstance(heading, str) and heading.strip()
        ]
        id_headings_info = [
            {"id": heading, "description": heading_desc_by_id.get(heading)}
            for heading in id_headings
        ] if id_headings else None
        errors.append(error(
            "constraints",
            f"{kind} artifact has no `{id_kind}` IDs but at least one is required{_id_kind_hint(constraint)}",
            code=EC.REQUIRED_ID_KIND_MISSING,
            path=artifact_path,
            line=1,
            artifact_kind=kind,
            id_kind=id_kind,
            id_kind_name=str(getattr(constraint, "name", "") or "").strip() or None,
            id_kind_description=str(getattr(constraint, "description", "") or "").strip() or None,
            id_kind_template=str(getattr(constraint, "template", "") or "").strip() or None,
            target_headings=id_headings if id_headings else None,
            target_headings_info=id_headings_info,
        ))


def _validate_artifact_identifier_phase(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    kind: str,
    errors: List[Dict[str, object]],
) -> None:
    from .document import scan_cpt_ids, scan_cdsl_instructions

    context = _build_artifact_identifier_phase_context(
        artifact_path=artifact_path,
        constraints=constraints,
        kind=kind,
        scan_cpt_ids=scan_cpt_ids,
    )
    cdsl_hits = scan_cdsl_instructions(artifact_path)
    _validate_unchecked_cdsl_steps(
        cdsl_hits=cdsl_hits,
        defs_by_id=context.defs_by_id,
        kind=kind,
        artifact_path=artifact_path,
        errors=errors,
    )
    _validate_cdsl_parent_child_state(
        defs=context.defs,
        refs=context.refs,
        kind=kind,
        artifact_path=artifact_path,
        errors=errors,
        heading_ctx_for_line=context.heading_ctx_for_line,
        scope_end_for_heading_idx=context.scope_end_for_heading_idx,
    )
    defs_by_kind: Dict[str, List[Dict[str, object]]] = {}
    _validate_definition_hits(
        defs=context.defs,
        rules=context.rules,
        defs_by_kind=defs_by_kind,
        errors=errors,
    )
    _validate_required_defined_ids(
        kind=kind,
        constraints=constraints,
        defs_by_kind=defs_by_kind,
        heading_desc_by_id=context.rules.heading_desc_by_id,
        artifact_path=artifact_path,
        errors=errors,
    )


# @cpt-algo:cpt-studio-algo-traceability-validation-validate-structure:p1
# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-entry
def validate_artifact_file(
    *,
    artifact_path: Path,
    artifact_kind: str,
    constraints: Optional[ArtifactKindConstraints],
    registered_systems: Optional[Iterable[str]] = None,
    constraints_path: Optional[Path] = None,
    kit_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """Validate one artifact file against structural constraints."""
    errors: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []

    kind = str(artifact_kind).strip().upper()

    if constraints is None:
        return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-entry

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings
    # Phase 1: headings contract
    can_continue = _validate_artifact_heading_phase(
        artifact_path=artifact_path,
        constraints=constraints,
        registered_systems=registered_systems,
        kind=kind,
        constraints_path=constraints_path,
        kit_id=kit_id,
        errors=errors,
        warnings=warnings,
    )
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-headings-fail
    # Stop here: IDs are validated only after outline contract is satisfied.
    if not can_continue:
        return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-headings-fail
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-toc
    # Phase 1b: TOC validation (only when toc=true in constraints)
    if getattr(constraints, "toc", True):
        _validate_artifact_toc(artifact_path, errors, warnings)
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-toc

    _validate_artifact_identifier_phase(
        artifact_path=artifact_path,
        constraints=constraints,
        kind=kind,
        errors=errors,
    )

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-return-structure
    return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-return-structure

# @cpt-algo:cpt-studio-algo-traceability-validation-cross-validate:p1
# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-datamodel
def _id_kind_rule_metadata(ic: object) -> Dict[str, object]:
    """Return user-facing metadata for one ID kind rule."""
    return {
        "id_kind_name": str(getattr(ic, "name", "") or "").strip() or None,
        "id_kind_description": str(getattr(ic, "description", "") or "").strip() or None,
        "id_kind_template": str(getattr(ic, "template", "") or "").strip() or None,
    }


def _validate_required_reference_coverage(
    *,
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
    drow: Dict[str, object],
    refs_in_kind: List[Dict[str, object]],
    system_present_kinds: Iterable[str],
    ctx: ReferenceCheckContext,
    allowed_headings: AllowedHeadingContext,
) -> bool:
    """Validate required reference coverage and return whether to skip later checks."""
    tk = ctx.target_kind
    if bool(drow.get("has_task", False)) and not bool(drow.get("checked", False)):
        return True
    if tk not in system_present_kinds:
        warnings.append(error(
            "constraints",
            f"`{ctx.did}` (defined in {ctx.artifact_kind}) requires reference in `{tk}` artifact but no `{tk}` artifact exists in scope",
            code=EC.REF_TARGET_NOT_IN_SCOPE,
            path=drow.get("artifact_path"),
            line=int(drow.get("line", 1) or 1),
            id=ctx.did,
            artifact_kind=ctx.artifact_kind,
            target_kind=tk,
        ))
        return True
    if not refs_in_kind:
        errors.append(error(
            "constraints",
            f"`{ctx.did}` (defined in {ctx.artifact_kind}, kind `{ctx.id_kind}`) is not referenced from any `{tk}` artifact",
            code=EC.REF_MISSING_FROM_KIND,
            path=drow.get("artifact_path"),
            line=int(drow.get("line", 1) or 1),
            target_headings=allowed_headings.sorted_ids if allowed_headings.heading_ids else None,
            target_headings_info=allowed_headings.info if allowed_headings.heading_ids else None,
            **ctx.error_fields(),
        ))
        return True
    if not allowed_headings.heading_ids:
        return False
    if any(any(h in allowed_headings.heading_ids for h in (rr.get("headings") or [])) for rr in refs_in_kind):
        return False

    first = refs_in_kind[0]
    errors.append(error(
        "constraints",
        f"Reference to `{ctx.did}` in `{tk}` artifact is under {first.get('headings') or []} but must be under one of {allowed_headings.sorted_ids}",
        code=EC.REF_WRONG_HEADINGS,
        path=first.get("artifact_path"),
        line=int(first.get("line", 1) or 1),
        headings=allowed_headings.sorted_ids,
        headings_info=allowed_headings.info,
        found_headings=first.get("headings") or [],
        **ctx.error_fields(),
    ))
    return False


def _validate_prohibited_reference_coverage(
    *,
    errors: List[Dict[str, object]],
    refs_in_kind: List[Dict[str, object]],
    ctx: ReferenceCheckContext,
) -> bool:
    """Validate prohibited reference coverage and return whether it matched."""
    if not refs_in_kind:
        return False
    first = refs_in_kind[0]
    errors.append(error(
        "constraints",
        f"`{ctx.did}` is referenced in `{ctx.target_kind}` artifact but references from `{ctx.target_kind}` are prohibited for {ctx.artifact_kind} IDs",
        code=EC.REF_FROM_PROHIBITED_KIND,
        path=first.get("artifact_path"),
        line=int(first.get("line", 1) or 1),
        **ctx.error_fields(),
    ))
    return True


def _validate_reference_task_rule(
    *,
    errors: List[Dict[str, object]],
    refs_in_kind: List[Dict[str, object]],
    task_rule: Optional[bool],
    ctx: ReferenceCheckContext,
) -> None:
    """Validate reference task checkbox requirements."""
    if task_rule is True:
        rr = next((r for r in refs_in_kind if not bool(r.get("has_task", False))), None)
        if rr is not None:
            errors.append(error(
                "constraints",
                f"Reference to `{ctx.did}` in `{ctx.target_kind}` artifact is missing required task checkbox `- [ ]`",
                code=EC.REF_MISSING_TASK,
                path=rr.get("artifact_path"),
                line=int(rr.get("line", 1) or 1),
                **ctx.error_fields(),
            ))
        return
    if task_rule is False:
        rr = next((r for r in refs_in_kind if bool(r.get("has_task", False))), None)
        if rr is not None:
            errors.append(error(
                "constraints",
                f"Reference to `{ctx.did}` in `{ctx.target_kind}` artifact has task checkbox but task tracking is prohibited",
                code=EC.REF_PROHIBITED_TASK,
                path=rr.get("artifact_path"),
                line=int(rr.get("line", 1) or 1),
                **ctx.error_fields(),
            ))


def _validate_reference_priority_rule(
    *,
    errors: List[Dict[str, object]],
    refs_in_kind: List[Dict[str, object]],
    prio_rule: Optional[bool],
    ctx: ReferenceCheckContext,
) -> None:
    """Validate reference priority marker requirements."""
    if prio_rule is True:
        rr = next((r for r in refs_in_kind if not bool(r.get("has_priority", False))), None)
        if rr is not None:
            errors.append(error(
                "constraints",
                f"Reference to `{ctx.did}` in `{ctx.target_kind}` artifact is missing required priority marker",
                code=EC.REF_MISSING_PRIORITY,
                path=rr.get("artifact_path"),
                line=int(rr.get("line", 1) or 1),
                **ctx.error_fields(),
            ))
        return
    if prio_rule is False:
        rr = next((r for r in refs_in_kind if bool(r.get("has_priority", False))), None)
        if rr is not None:
            errors.append(error(
                "constraints",
                f"Reference to `{ctx.did}` in `{ctx.target_kind}` artifact has priority marker but priority is prohibited",
                code=EC.REF_PROHIBITED_PRIORITY,
                path=rr.get("artifact_path"),
                line=int(rr.get("line", 1) or 1),
                **ctx.error_fields(),
            ))


def _validate_reference_rule(
    *,
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
    drow: Dict[str, object],
    refs_in_kind: List[Dict[str, object]],
    system_present_kinds: Iterable[str],
    ctx: ReferenceCheckContext,
    rule: ReferenceRule,
    allowed_headings: AllowedHeadingContext,
) -> None:
    """Validate one reference rule for a definition row."""
    cov = getattr(rule, "coverage", None)
    if cov is True:
        skip_rest = _validate_required_reference_coverage(
            errors=errors,
            warnings=warnings,
            drow=drow,
            refs_in_kind=refs_in_kind,
            system_present_kinds=system_present_kinds,
            ctx=ctx,
            allowed_headings=allowed_headings,
        )
        if skip_rest:
            return

    if cov is False:
        matched = _validate_prohibited_reference_coverage(
            errors=errors,
            refs_in_kind=refs_in_kind,
            ctx=ctx,
        )
        if matched:
            return

    if not refs_in_kind:
        return
    _validate_reference_task_rule(
        errors=errors,
        refs_in_kind=refs_in_kind,
        task_rule=getattr(rule, "task", None),
        ctx=ctx,
    )
    _validate_reference_priority_rule(
        errors=errors,
        refs_in_kind=refs_in_kind,
        prio_rule=getattr(rule, "priority", None),
        ctx=ctx,
    )


def _build_cross_constraint_indexes(
    artifacts: Sequence[ArtifactRecord],
    errors: List[Dict[str, object]],
) -> Tuple[
    Dict[str, ArtifactKindConstraints],
    Dict[str, set[str]],
    Dict[str, Dict[str, str]],
]:
    constraints_by_artifact_kind: Dict[str, ArtifactKindConstraints] = {}
    missing_constraints_kinds: set[str] = set()
    composite_nested_kinds_by_base_kind: Dict[str, set[str]] = {}
    heading_desc_by_kind: Dict[str, Dict[str, str]] = {}

    for art in artifacts:
        artifact_kind = str(art.artifact_kind).strip().upper()
        constraint = art.constraints
        if constraint is None:
            missing_constraints_kinds.add(artifact_kind)
            continue
        constraints_by_artifact_kind[artifact_kind] = constraint

        hdesc: Dict[str, str] = {}
        for heading_constraint in (getattr(constraint, "headings", None) or []):
            hid = _normalize_heading_identifier(getattr(heading_constraint, "id", "") or "")
            if not hid:
                continue
            desc = str(getattr(heading_constraint, "description", "") or "").strip()
            if desc:
                hdesc[hid] = desc
        heading_desc_by_kind[artifact_kind] = hdesc

    for artifact_kind, constraint in constraints_by_artifact_kind.items():
        base_kind = str(artifact_kind).strip().lower()
        nested = {
            str(getattr(id_constraint, "kind", "")).strip().lower()
            for id_constraint in getattr(constraint, "defined_id", []) or []
            if str(getattr(id_constraint, "kind", "")).strip()
        }
        if nested:
            composite_nested_kinds_by_base_kind[base_kind] = nested

    if missing_constraints_kinds:
        errors.append(error(
            "constraints",
            f"No constraints defined for artifact kinds: {sorted(missing_constraints_kinds)} — add them to constraints.toml",
            code=EC.MISSING_CONSTRAINTS,
            path=Path("<constraints.toml>"),
            line=1,
            kinds=sorted(missing_constraints_kinds),
        ))
    return (
        constraints_by_artifact_kind,
        composite_nested_kinds_by_base_kind,
        heading_desc_by_kind,
    )


def _collect_cross_all_kind_tokens(
    constraints_by_artifact_kind: Dict[str, ArtifactKindConstraints],
) -> set[str]:
    all_kind_tokens: set[str] = set()
    for constraint in constraints_by_artifact_kind.values():
        for id_constraint in (getattr(constraint, "defined_id", None) or []):
            kind = str(getattr(id_constraint, "kind", "") or "").strip().lower()
            if kind:
                all_kind_tokens.add(kind)
        for id_constraint in (getattr(constraint, "referenced_id", None) or []):
            kind = str(getattr(id_constraint, "kind", "") or "").strip().lower()
            if kind:
                all_kind_tokens.add(kind)
    return all_kind_tokens


def _is_external_system_ref(cpt: str, systems_set: set[str]) -> bool:
    if not systems_set:
        return False
    if not cpt.lower().startswith("cpt-"):
        return False
    for system in systems_set:
        if cpt.lower().startswith(f"cpt-{system}-"):
            return False
    return True


def _headings_info_for_kind(
    kind: str,
    heading_ids: Sequence[str],
    heading_desc_by_kind: Dict[str, Dict[str, str]],
) -> List[Dict[str, object]]:
    kind_map = heading_desc_by_kind.get(str(kind).strip().upper(), {})
    out: List[Dict[str, object]] = []
    for hid in heading_ids:
        normalized = _normalize_heading_identifier(hid)
        if not normalized:
            continue
        out.append({"id": normalized, "description": kind_map.get(normalized)})
    return out


def _scan_cross_artifact_hit(
    *,
    hit: Dict[str, object],
    artifact_kind: str,
    artifact_path: Path,
    headings_at: Sequence[Sequence[str]],
    systems_set: set[str],
    all_kind_tokens: set[str],
    composite_nested_kinds_by_base_kind: Dict[str, set[str]],
) -> Optional[Tuple[str, Dict[str, object], Optional[str], str]]:
    hid = str(hit.get("id", "")).strip()
    if not hid:
        return None
    line = int(hit.get("line", 1) or 1)
    system = _match_system_from_id(hid, systems_set, all_kind_tokens)
    id_kind = _extract_kind_from_cpt(
        hid,
        system,
        all_kind_tokens,
        composite_nested_kinds_by_base_kind,
    )
    active_headings = _normalize_heading_identifiers(
        headings_at[line] if 0 <= line < len(headings_at) else []
    )
    return str(hit.get("type")), {
        "id": hid,
        "line": line,
        "checked": bool(hit.get("checked", False)),
        "priority": hit.get("priority"),
        "has_task": bool(hit.get("has_task", False)),
        "has_priority": bool(hit.get("has_priority", False)),
        "artifact_kind": artifact_kind,
        "artifact_path": artifact_path,
        "system": system,
        "id_kind": id_kind,
        "headings": active_headings,
    }, system, hid


def _scan_cross_artifact_rows(
    *,
    artifacts: Sequence[ArtifactRecord],
    systems_set: set[str],
    all_kind_tokens: set[str],
    composite_nested_kinds_by_base_kind: Dict[str, set[str]],
) -> Tuple[
    Dict[str, List[Dict[str, object]]],
    Dict[str, List[Dict[str, object]]],
    Dict[str, set[str]],
    Dict[str, Dict[str, List[Dict[str, object]]]],
]:
    from .document import headings_by_line, scan_cpt_ids

    indexes = CrossArtifactScanIndexes(
        defs_by_id={},
        refs_by_id={},
        present_kinds_by_system={},
        refs_by_system_kind={},
        headings_cache={},
    )

    for art in artifacts:
        artifact_kind = str(art.artifact_kind).strip().upper()
        headings_at = _cross_artifact_headings_at(art, indexes.headings_cache, headings_by_line)
        for hit in scan_cpt_ids(art.path):
            scanned_hit = _scan_cross_artifact_hit(
                hit=hit,
                artifact_kind=artifact_kind,
                artifact_path=art.path,
                headings_at=headings_at,
                systems_set=systems_set,
                all_kind_tokens=all_kind_tokens,
                composite_nested_kinds_by_base_kind=composite_nested_kinds_by_base_kind,
            )
            _record_cross_artifact_hit(
                scanned_hit,
                artifact_kind=artifact_kind,
                defs_by_id=indexes.defs_by_id,
                refs_by_id=indexes.refs_by_id,
                present_kinds_by_system=indexes.present_kinds_by_system,
                refs_by_system_kind=indexes.refs_by_system_kind,
            )

    return (
        indexes.defs_by_id,
        indexes.refs_by_id,
        indexes.present_kinds_by_system,
        indexes.refs_by_system_kind,
    )


def _cross_artifact_headings_at(
    art: ArtifactRecord,
    headings_cache: Dict[str, List[List[str]]],
    headings_by_line: callable,
) -> List[List[str]]:
    hkey = str(art.path)
    if hkey not in headings_cache:
        heading_constraints = getattr(getattr(art, "constraints", None), "headings", None)
        headings_cache[hkey] = (
            heading_constraint_ids_by_line(art.path, heading_constraints)
            if heading_constraints else headings_by_line(art.path)
        )
    return headings_cache[hkey]


def _record_cross_artifact_hit(
    scanned_hit: Optional[Tuple[str, Dict[str, object], Optional[str], str]],
    *,
    artifact_kind: str,
    defs_by_id: Dict[str, List[Dict[str, object]]],
    refs_by_id: Dict[str, List[Dict[str, object]]],
    present_kinds_by_system: Dict[str, set[str]],
    refs_by_system_kind: Dict[str, Dict[str, List[Dict[str, object]]]],
) -> None:
    if scanned_hit is None:
        return
    hit_type, row, system, hid = scanned_hit
    if hit_type == "definition":
        defs_by_id.setdefault(hid, []).append(row)
    elif hit_type == "reference":
        refs_by_id.setdefault(hid, []).append(row)
    else:
        return
    if not system:
        return
    present_kinds_by_system.setdefault(system, set()).add(artifact_kind)
    if hit_type == "reference":
        refs_by_system_kind.setdefault(system, {}).setdefault(artifact_kind, []).append(row)


def _validate_duplicate_definitions(
    defs_by_id: Dict[str, List[Dict[str, object]]],
    errors: List[Dict[str, object]],
) -> None:
    for did, drows in defs_by_id.items():
        if len(drows) < 2:
            continue
        paths = {str(drow.get("artifact_path", "")) for drow in drows}
        if len(paths) < 2:
            continue
        sorted_paths = sorted(paths)
        for drow in drows:
            other_paths = [path for path in sorted_paths if path != str(drow.get("artifact_path", ""))]
            errors.append(error(
                "structure",
                f"Duplicate definition of `{did}` — also defined in: {', '.join(other_paths)}",
                code=EC.DUPLICATE_DEFINITION,
                path=drow.get("artifact_path"),
                line=int(drow.get("line", 1) or 1),
                id=did,
            ))


def _validate_reference_definitions_exist(
    *,
    refs_by_id: Dict[str, List[Dict[str, object]]],
    defs_by_id: Dict[str, List[Dict[str, object]]],
    systems_set: set[str],
    errors: List[Dict[str, object]],
) -> None:
    for rid, rows in refs_by_id.items():
        if _is_external_system_ref(rid, systems_set):
            continue
        if rid in defs_by_id:
            continue
        for row in rows:
            errors.append(error(
                "structure",
                f"Reference to `{rid}` has no matching definition in any artifact",
                code=EC.REF_NO_DEFINITION,
                path=row.get("artifact_path"),
                line=int(row.get("line", 1) or 1),
                id=rid,
            ))


def _validate_checked_reference_consistency(
    *,
    refs_by_id: Dict[str, List[Dict[str, object]]],
    defs_by_id: Dict[str, List[Dict[str, object]]],
    errors: List[Dict[str, object]],
) -> None:
    for rid, rows in refs_by_id.items():
        defs = defs_by_id.get(rid, [])
        for row in rows:
            if not bool(row.get("has_task", False)):
                continue
            if not bool(row.get("checked", False)):
                continue
            for drow in defs:
                if not bool(drow.get("has_task", False)):
                    continue
                if bool(drow.get("checked", False)):
                    continue
                errors.append(error(
                    "structure",
                    f"Reference to `{rid}` is checked [x] but its definition is still unchecked",
                    code=EC.REF_DONE_DEF_NOT_DONE,
                    path=row.get("artifact_path"),
                    line=int(row.get("line", 1) or 1),
                    id=rid,
                ))


def _validate_definition_completion_consistency(
    *,
    refs_by_id: Dict[str, List[Dict[str, object]]],
    defs_by_id: Dict[str, List[Dict[str, object]]],
    errors: List[Dict[str, object]],
) -> None:
    for rid, rows in refs_by_id.items():
        defs = defs_by_id.get(rid, [])
        if not defs:
            continue
        defs_with_task = [drow for drow in defs if bool(drow.get("has_task", False))]
        if defs_with_task and all(bool(drow.get("checked", False)) for drow in defs_with_task):
            for row in rows:
                if not bool(row.get("has_task", False)):
                    continue
                if bool(row.get("checked", False)):
                    continue
                errors.append(error(
                    "structure",
                    f"Definition of `{rid}` is checked [x] but reference in {row.get('artifact_kind', '?')} artifact is still unchecked",
                    code=EC.DEF_DONE_REF_NOT_DONE,
                    path=row.get("artifact_path"),
                    line=int(row.get("line", 1) or 1),
                    id=rid,
                    def_artifact_kind=defs_with_task[0].get("artifact_kind"),
                ))
        if any(bool(drow.get("has_task", False)) for drow in defs):
            continue
        for row in rows:
            if not bool(row.get("has_task", False)):
                continue
            errors.append(error(
                "structure",
                f"Reference to `{rid}` has task checkbox but its definition has no task tracking",
                code=EC.REF_TASK_DEF_NO_TASK,
                path=row.get("artifact_path"),
                line=int(row.get("line", 1) or 1),
                id=rid,
            ))


def _defs_in_artifact_file(
    art: ArtifactRecord,
    defs_by_id: Dict[str, List[Dict[str, object]]],
) -> List[Dict[str, object]]:
    return [
        drow
        for rows in defs_by_id.values()
        for drow in rows
        if str(drow.get("artifact_path")) == str(art.path) and drow.get("system") is not None
    ]


def _validate_artifact_definitions_against_constraints(
    *,
    art: ArtifactRecord,
    constraint: ArtifactKindConstraints,
    defs_in_file: Sequence[Dict[str, object]],
    heading_desc_by_kind: Dict[str, Dict[str, str]],
    errors: List[Dict[str, object]],
) -> None:
    artifact_kind = str(art.artifact_kind).strip().upper()
    allowed_kinds = {
        str(getattr(id_constraint, "kind", "")).strip().lower()
        for id_constraint in getattr(constraint, "defined_id", []) or []
    }
    for drow in defs_in_file:
        id_kind = str(drow.get("id_kind") or "").lower()
        if not id_kind:
            continue
        if allowed_kinds and id_kind not in allowed_kinds:
            errors.append(error(
                "constraints",
                f"`{drow.get('id')}` uses kind `{id_kind}` not allowed in {artifact_kind} artifact",
                code=EC.ID_KIND_NOT_ALLOWED,
                path=art.path,
                line=int(drow.get("line", 1) or 1),
                artifact_kind=artifact_kind,
                id_kind=id_kind,
                id=str(drow.get("id")),
            ))

    for id_constraint in getattr(constraint, "defined_id", []) or []:
        _validate_artifact_required_id_kind(
            art=art,
            artifact_kind=artifact_kind,
            id_constraint=id_constraint,
            defs_in_file=defs_in_file,
            heading_desc_by_kind=heading_desc_by_kind,
            errors=errors,
        )


def _validate_artifact_required_id_kind(
    *,
    art: ArtifactRecord,
    artifact_kind: str,
    id_constraint: IdConstraint,
    defs_in_file: Sequence[Dict[str, object]],
    heading_desc_by_kind: Dict[str, Dict[str, str]],
    errors: List[Dict[str, object]],
) -> None:
    id_kind = str(getattr(id_constraint, "kind", "")).strip().lower()
    is_required = bool(getattr(id_constraint, "required", True))
    defs_of_kind = [drow for drow in defs_in_file if str(drow.get("id_kind") or "").lower() == id_kind]
    if is_required and id_kind and not defs_of_kind:
        id_headings = _normalize_heading_identifiers(getattr(id_constraint, "headings", None) or [])
        errors.append(error(
            "constraints",
            f"{artifact_kind} artifact has no `{id_kind}` IDs but at least one is required",
            code=EC.REQUIRED_ID_KIND_MISSING,
            path=art.path,
            line=1,
            artifact_kind=artifact_kind,
            id_kind=id_kind,
            id_kind_name=str(getattr(id_constraint, "name", "") or "").strip() or None,
            id_kind_description=str(getattr(id_constraint, "description", "") or "").strip() or None,
            id_kind_template=str(getattr(id_constraint, "template", "") or "").strip() or None,
            target_headings=id_headings if id_headings else None,
            target_headings_info=(
                _headings_info_for_kind(artifact_kind, id_headings, heading_desc_by_kind)
                if id_headings else None
            ),
        ))
        return

    allowed_headings = set(_normalize_heading_identifiers(getattr(id_constraint, "headings", None) or []))
    if not allowed_headings or not defs_of_kind:
        return
    allowed_sorted = sorted(allowed_headings)
    for drow in defs_of_kind:
        active = drow.get("headings") or []
        if any(heading in allowed_headings for heading in active):
            continue
        errors.append(error(
            "constraints",
            f"`{drow.get('id')}` (kind `{id_kind}`) in {artifact_kind} artifact is under {drow.get('headings') or []} but must be under one of {allowed_sorted}",
            code=EC.DEF_WRONG_HEADINGS,
            path=art.path,
            line=int(drow.get("line", 1) or 1),
            artifact_kind=artifact_kind,
            id_kind=id_kind,
            id=str(drow.get("id")),
            headings=allowed_sorted,
            headings_info=_headings_info_for_kind(
                artifact_kind,
                allowed_sorted,
                heading_desc_by_kind,
            ),
            found_headings=active,
            id_kind_name=str(getattr(id_constraint, "name", "") or "").strip() or None,
            id_kind_description=str(getattr(id_constraint, "description", "") or "").strip() or None,
            id_kind_template=str(getattr(id_constraint, "template", "") or "").strip() or None,
        ))


def _validate_cross_artifact_coverage(
    *,
    artifacts: Sequence[ArtifactRecord],
    constraints_by_artifact_kind: Dict[str, ArtifactKindConstraints],
    defs_by_id: Dict[str, List[Dict[str, object]]],
    heading_desc_by_kind: Dict[str, Dict[str, str]],
    errors: List[Dict[str, object]],
) -> None:
    for art in artifacts:
        artifact_kind = str(art.artifact_kind).strip().upper()
        constraint = constraints_by_artifact_kind.get(artifact_kind)
        if constraint is None:
            continue
        defs_in_file = _defs_in_artifact_file(art, defs_by_id)
        _validate_artifact_definitions_against_constraints(
            art=art,
            constraint=constraint,
            defs_in_file=defs_in_file,
            heading_desc_by_kind=heading_desc_by_kind,
            errors=errors,
        )


def _allowed_heading_context(
    target_kind: str,
    rule: ReferenceRule,
    heading_desc_by_kind: Dict[str, Dict[str, str]],
) -> AllowedHeadingContext:
    heading_ids = set(_normalize_heading_identifiers(getattr(rule, "headings", None) or []))
    sorted_ids = sorted(heading_ids)
    return AllowedHeadingContext(
        heading_ids=heading_ids,
        sorted_ids=sorted_ids,
        info=_headings_info_for_kind(target_kind, sorted_ids, heading_desc_by_kind),
    )


def _validate_id_constraint_reference_rules(
    artifact_kind: str,
    id_kind: str,
    id_meta: Dict[str, object],
    refs_rules: Dict[str, ReferenceRule],
    state: CrossReferenceCoverageState,
) -> None:
    for did, drows in state.defs_by_id.items():
        for drow in drows:
            if str(drow.get("artifact_kind")) != artifact_kind:
                continue
            if str(drow.get("id_kind") or "").lower() != id_kind:
                continue
            system = drow.get("system")
            if system is None:
                continue

            system_present_kinds = state.present_kinds_by_system.get(system, set())
            system_refs_by_kind = state.refs_by_system_kind.get(system, {})
            for target_kind, rule in refs_rules.items():
                target_kind_s = str(target_kind).strip().upper()
                refs_in_kind = [
                    row
                    for row in system_refs_by_kind.get(target_kind_s, [])
                    if str(row.get("id")) == did
                ]
                _validate_reference_rule(
                    errors=state.errors,
                    warnings=state.warnings,
                    drow=drow,
                    refs_in_kind=refs_in_kind,
                    system_present_kinds=system_present_kinds,
                    ctx=ReferenceCheckContext(
                        did=did,
                        artifact_kind=artifact_kind,
                        target_kind=target_kind_s,
                        id_kind=id_kind,
                        id_meta=id_meta,
                    ),
                    rule=rule,
                    allowed_headings=_allowed_heading_context(
                        target_kind_s,
                        rule,
                        state.heading_desc_by_kind,
                    ),
                )


def _validate_cross_reference_coverage_rules(
    *,
    constraints_by_artifact_kind: Dict[str, ArtifactKindConstraints],
    defs_by_id: Dict[str, List[Dict[str, object]]],
    present_kinds_by_system: Dict[str, set[str]],
    refs_by_system_kind: Dict[str, Dict[str, List[Dict[str, object]]]],
    heading_desc_by_kind: Dict[str, Dict[str, str]],
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> None:
    state = CrossReferenceCoverageState(
        defs_by_id=defs_by_id,
        present_kinds_by_system=present_kinds_by_system,
        refs_by_system_kind=refs_by_system_kind,
        heading_desc_by_kind=heading_desc_by_kind,
        errors=errors,
        warnings=warnings,
    )
    for artifact_kind, constraint in constraints_by_artifact_kind.items():
        for id_constraint in getattr(constraint, "defined_id", []) or []:
            id_kind = str(getattr(id_constraint, "kind", "")).strip().lower()
            id_meta = _id_kind_rule_metadata(id_constraint)
            refs_rules = getattr(id_constraint, "references", None) or {}
            if not isinstance(refs_rules, dict):
                continue
            _validate_id_constraint_reference_rules(
                artifact_kind,
                id_kind,
                id_meta,
                refs_rules,
                state,
            )


def cross_validate_artifacts(
    artifacts: Sequence[ArtifactRecord],
    registered_systems: Optional[Iterable[str]] = None,
    known_kinds: Optional[Iterable[str]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """Cross-validate references between artifact records."""
    _ = known_kinds
    errors: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []
    constraints_by_artifact_kind, composite_nested_kinds_by_base_kind, heading_desc_by_kind = (
        _build_cross_constraint_indexes(artifacts, errors)
    )
    systems_set = {str(system).lower() for system in registered_systems} if registered_systems is not None else set()
    _cross_all_kind_tokens = _collect_cross_all_kind_tokens(constraints_by_artifact_kind)
    defs_by_id, refs_by_id, present_kinds_by_system, refs_by_system_kind = _scan_cross_artifact_rows(
        artifacts=artifacts,
        systems_set=systems_set,
        all_kind_tokens=_cross_all_kind_tokens,
        composite_nested_kinds_by_base_kind=composite_nested_kinds_by_base_kind,
    )
    _validate_duplicate_definitions(defs_by_id, errors)
    _validate_reference_definitions_exist(
        refs_by_id=refs_by_id,
        defs_by_id=defs_by_id,
        systems_set=systems_set,
        errors=errors,
    )
    _validate_checked_reference_consistency(
        refs_by_id=refs_by_id,
        defs_by_id=defs_by_id,
        errors=errors,
    )
    _validate_definition_completion_consistency(
        refs_by_id=refs_by_id,
        defs_by_id=defs_by_id,
        errors=errors,
    )
    _validate_cross_artifact_coverage(
        artifacts=artifacts,
        constraints_by_artifact_kind=constraints_by_artifact_kind,
        defs_by_id=defs_by_id,
        heading_desc_by_kind=heading_desc_by_kind,
        errors=errors,
    )
    _validate_cross_reference_coverage_rules(
        constraints_by_artifact_kind=constraints_by_artifact_kind,
        defs_by_id=defs_by_id,
        present_kinds_by_system=present_kinds_by_system,
        refs_by_system_kind=refs_by_system_kind,
        heading_desc_by_kind=heading_desc_by_kind,
        errors=errors,
        warnings=warnings,
    )

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-return-cross
    return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-return-cross

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-constraints-helpers
def _parse_examples(v: object) -> Tuple[Optional[List[object]], Optional[str]]:
    if v is None:
        return None, None
    if not isinstance(v, list):
        return None, "Constraint field 'examples' must be a list"
    return list(v), None

def _parse_reference_rule(obj: object) -> Tuple[Optional[ReferenceRule], Optional[str]]:
    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-ref-rule
    if not isinstance(obj, dict):
        return None, "Reference rule must be an object"
    coverage, cov_err = _parse_optional_bool(obj.get("coverage"), "references.coverage")
    if cov_err:
        return None, cov_err

    task, task_err = _parse_optional_bool(obj.get("task"), "references.task")
    if task_err:
        return None, task_err

    priority, pr_err = _parse_optional_bool(obj.get("priority"), "references.priority")
    if pr_err:
        return None, pr_err

    headings_raw = obj.get("headings")
    headings: Optional[List[str]] = None
    if headings_raw is not None:
        if not isinstance(headings_raw, list) or any(not isinstance(h, str) for h in headings_raw):
            return None, "Reference rule field 'headings' must be list[str]"
        headings = _normalize_heading_identifiers(headings_raw)

    return ReferenceRule(
        coverage=coverage,
        task=task,
        priority=priority,
        headings=headings,
    ), None
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-ref-rule

def _parse_required_bool_field(obj: dict, field: str) -> Tuple[bool, Optional[str]]:
    v = obj.get(field)
    if v is None:
        return True, None
    if isinstance(v, bool):
        return v, None
    return True, f"Constraint field '{field}' must be boolean"


def _parse_optional_string_field(
    obj: Dict[str, object],
    field: str,
    error_prefix: str,
) -> Tuple[Optional[str], Optional[str]]:
    value = obj.get(field)
    if value is not None and not isinstance(value, str):
        return None, f"{error_prefix} field '{field}' must be string"
    return value, None


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _parse_optional_bool_constraint(
    obj: Dict[str, object],
    field: str,
    error_prefix: str,
) -> Tuple[Optional[bool], Optional[str]]:
    value, parse_err = _parse_optional_bool(obj.get(field), field)
    if parse_err:
        return None, f"{error_prefix}: {parse_err}"
    return value, None


def _parse_optional_heading_ids(
    obj: Dict[str, object],
    field: str,
    error_message: str,
) -> Tuple[Optional[List[str]], Optional[str]]:
    headings_raw = obj.get(field)
    if headings_raw is None:
        return None, None
    if not isinstance(headings_raw, list) or any(not isinstance(heading, str) for heading in headings_raw):
        return None, error_message
    return _normalize_heading_identifiers(headings_raw), None


def _parse_direct_bool_field(
    obj: Dict[str, object],
    field: str,
    error_message: str,
) -> Tuple[Optional[bool], Optional[str]]:
    value = obj.get(field)
    if value is not None and not isinstance(value, bool):
        return None, error_message
    return value, None


def _collect_optional_string_fields(
    obj: Dict[str, object],
    fields: Sequence[str],
    error_prefix: str,
) -> Tuple[Optional[Dict[str, Optional[str]]], Optional[str]]:
    values: Dict[str, Optional[str]] = {}
    for field in fields:
        value, err = _parse_optional_string_field(obj, field, error_prefix)
        if err:
            return None, err
        values[field] = value
    return values, None


def _validate_heading_constraint_pattern(pattern: Optional[str]) -> Optional[str]:
    pattern_s = _normalize_optional_text(pattern)
    if not pattern_s:
        return None
    try:
        re.compile(pattern_s)
    except re.error as exc:
        return f"Heading constraint 'pattern' invalid regex: {exc}"
    return None


def _collect_heading_constraint_options(  # pylint: disable=too-many-locals
    obj: Dict[str, object],
) -> Tuple[Optional[Tuple[bool, Optional[bool], Optional[bool]]], Optional[str]]:
    """Parse the boolean-only heading options for one heading constraint."""
    required_bool, req_err = _parse_required_bool_field(obj, "required")
    if req_err:
        return None, "Heading constraint field 'required' must be boolean"
    multiple, err = _parse_optional_bool_constraint(obj, "multiple", "Heading constraint")
    if err:
        return None, err
    numbered, err = _parse_optional_bool_constraint(obj, "numbered", "Heading constraint")
    if err:
        return None, err
    return (bool(required_bool), multiple, numbered), None


def _parse_id_constraint_scalar_fields(
    obj: Dict[str, object],
) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """Parse the non-reference fields for a single ID constraint object."""
    required_bool, req_err = _parse_required_bool_field(obj, "required")
    string_values, string_err = _collect_optional_string_fields(
        obj,
        ("name", "description", "template"),
        "Constraint",
    )
    examples, examples_err = _parse_examples(obj.get("examples"))
    option_values, option_err = _parse_id_constraint_option_fields(obj)
    first_error = _first_constraint_parse_error(
        "Constraint field 'required' must be boolean" if req_err else None,
        string_err,
        examples_err,
        option_err,
    )
    if first_error:
        return None, first_error
    assert string_values is not None
    assert option_values is not None
    return {
        "required": required_bool,
        "name": string_values["name"],
        "description": string_values["description"],
        "template": _normalize_optional_text(string_values["template"]),
        "examples": examples,
        **option_values,
    }, None


def _first_constraint_parse_error(*messages: Optional[str]) -> Optional[str]:
    """Return the first non-empty parse error message."""
    for message in messages:
        if message:
            return message
    return None


def _parse_id_constraint_option_fields(
    obj: Dict[str, object],
) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    """Parse optional boolean/list fields attached to an ID constraint."""
    task, task_err = _parse_optional_bool(obj.get("task"), "task")
    priority, priority_err = _parse_optional_bool(obj.get("priority"), "priority")
    to_code, to_code_err = _parse_direct_bool_field(
        obj,
        "to_code",
        "Constraint field 'to_code' must be boolean",
    )
    headings, headings_err = _parse_optional_heading_ids(
        obj,
        "headings",
        "Constraint field 'headings' must be list[str]",
    )
    first_error = _first_constraint_parse_error(
        task_err,
        priority_err,
        to_code_err,
        headings_err,
    )
    if first_error:
        return None, first_error
    return {
        "task": task,
        "priority": priority,
        "to_code": to_code,
        "headings": headings,
    }, None


def _collect_id_constraint_fields(
    obj: Dict[str, object],
) -> Tuple[Optional[Dict[str, object]], Optional[str]]:
    fields, field_err = _parse_id_constraint_scalar_fields(obj)
    if field_err:
        return None, field_err
    references, ref_err = _parse_references(obj.get("references"))
    if ref_err:
        return None, ref_err
    assert fields is not None
    return {**fields, "references": references}, None


def _validate_artifact_constraint_text_fields(
    kind: str,
    raw: Dict[str, object],
    errors: List[str],
) -> Optional[Dict[str, Optional[str]]]:
    text_fields = {
        "name": raw.get("name"),
        "description": raw.get("description"),
    }
    for field_name, value in text_fields.items():
        if value is not None and not isinstance(value, str):
            errors.append(f"constraints for {kind} field '{field_name}' must be string")
            return None
    return {
        "name": text_fields["name"] if isinstance(text_fields["name"], str) else None,
        "description": (
            text_fields["description"]
            if isinstance(text_fields["description"], str) else None
        ),
    }


def _parse_artifact_kind_constraints(
    kind: str,
    raw: Dict[str, object],
    errors: List[str],
) -> Optional[ArtifactKindConstraints]:
    parsed = _parse_artifact_kind_constraint_parts(kind, raw, errors)
    if parsed is None:
        return None
    text_fields, headings, defined_id, toc_val = parsed

    return ArtifactKindConstraints(
        name=text_fields["name"],
        description=text_fields["description"],
        defined_id=defined_id,
        headings=headings,
        toc=toc_val,
    )


def _parse_artifact_kind_constraint_parts(
    kind: str,
    raw: Dict[str, object],
    errors: List[str],
) -> Optional[Tuple[Dict[str, Optional[str]], Optional[List[HeadingConstraint]], List[IdConstraint], bool]]:
    parsed: Optional[Tuple[Dict[str, Optional[str]], Optional[List[HeadingConstraint]], List[IdConstraint], bool]]
    parsed = None
    if "identifiers" not in raw:
        errors.append(f"constraints for {kind} must include 'identifiers'")
    else:
        text_fields = _validate_artifact_constraint_text_fields(kind, raw, errors)
        if text_fields is not None:
            headings = _parse_kind_headings(kind, raw.get("headings"), errors)
            if headings is not False:
                defined_id, ok = _parse_identifiers_block(raw.get("identifiers"), kind, errors)
                if ok and defined_id is not None:
                    toc_val = _parse_kind_toc(kind, raw.get("toc"), errors)
                    if toc_val is not None:
                        parsed = text_fields, headings, defined_id, toc_val
                elif ok:
                    errors.append(f"constraints for {kind}: identifiers block returned no data")
    return parsed


def _parse_kind_headings(
    kind: str,
    headings_raw: object,
    errors: List[str],
) -> Optional[List[HeadingConstraint]] | bool:
    if headings_raw is None:
        return None
    if not isinstance(headings_raw, list):
        errors.append(f"constraints for {kind} field 'headings' must be a list")
        return False
    parsed_headings: List[HeadingConstraint] = []
    for idx, heading_raw in enumerate(headings_raw):
        pointer = f"/{kind.strip().upper()}/headings/{idx}"
        heading_constraint, heading_err = _parse_heading_constraint(heading_raw, pointer=pointer)
        if heading_err:
            errors.append(f"constraints for {kind} headings[{idx}]: {heading_err}")
            continue
        if heading_constraint is not None:
            parsed_headings.append(heading_constraint)
    return _normalize_heading_ids(parsed_headings, kind, errors)


def _parse_kind_toc(
    kind: str,
    toc_raw: object,
    errors: List[str],
) -> Optional[bool]:
    if toc_raw is None:
        return True
    if not isinstance(toc_raw, bool):
        errors.append(f"constraints for {kind} field 'toc' must be boolean")
        return None
    return toc_raw


def _parse_heading_constraint(obj: object, *, pointer: Optional[str] = None) -> Tuple[Optional[HeadingConstraint], Optional[str]]:
    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-heading
    if not isinstance(obj, dict):
        return None, "Heading constraint must be an object"

    string_values, err = _collect_optional_string_fields(
        obj,
        ("id", "prev", "next", "pattern", "description"),
        "Heading constraint",
    )
    if err:
        return None, err

    level = obj.get("level")
    if not isinstance(level, int) or not 1 <= level <= 6:
        return None, "Heading constraint field 'level' must be integer 1-6"

    options, err = _collect_heading_constraint_options(obj)
    if err or options is None:
        return None, err
    pattern_s = _normalize_optional_text(string_values["pattern"])
    err = _validate_heading_constraint_pattern(pattern_s)
    if err:
        return None, err

    required_bool, multiple, numbered = options

    return HeadingConstraint(
        id=_normalize_heading_identifier(string_values["id"]) or None,
        level=int(level),
        pattern=pattern_s,
        description=_normalize_optional_text(string_values["description"]),
        required=required_bool,
        multiple=multiple,
        numbered=numbered,
        prev=_normalize_heading_identifier(string_values["prev"]) or None,
        next=_normalize_heading_identifier(string_values["next"]) or None,
        pointer=_normalize_optional_text(pointer),
    ), None
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-heading

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-slugify-heading-id
def _slugify_heading_constraint_id(v: str) -> str:
    s = str(v or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-slugify-heading-id

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-references-map
def _parse_references(v: object) -> Tuple[Optional[Dict[str, ReferenceRule]], Optional[str]]:
    if v is None:
        return None, None
    if not isinstance(v, dict):
        return None, "Constraint field 'references' must be an object mapping artifact kinds to rules"
    out: Dict[str, ReferenceRule] = {}
    for k, raw in v.items():
        if not isinstance(k, str) or not k.strip():
            return None, "Constraint field 'references' has non-string artifact kind key"
        rule, err = _parse_reference_rule(raw)
        if err:
            return None, f"references[{k}]: {err}"
        if rule is not None:
            out[k.strip().upper()] = rule
    return out, None
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-references-map
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-constraints-helpers

def _parse_id_constraint(obj: object) -> Tuple[Optional[IdConstraint], Optional[str]]:
    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-id-constraint
    if not isinstance(obj, dict):
        return None, "Constraint entry must be an object"
    kind = obj.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        return None, "Constraint entry missing required 'kind'"

    parsed_fields, err = _collect_id_constraint_fields(obj)
    if err or parsed_fields is None:
        return None, err

    return (
        IdConstraint(
            kind=kind.strip(),
            required=bool(parsed_fields["required"]),
            name=parsed_fields["name"],
            description=parsed_fields["description"],
            template=parsed_fields["template"],
            examples=parsed_fields["examples"],
            task=parsed_fields["task"],
            priority=parsed_fields["priority"],
            to_code=parsed_fields["to_code"],
            headings=parsed_fields["headings"],
            references=parsed_fields["references"],
        ),
        None,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-id-constraint

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-constraints-normalize
# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-assign-heading-ids
def _assign_heading_ids(
    parsed_headings: List[HeadingConstraint],
) -> List[HeadingConstraint]:
    """First pass: ensure every heading has a unique id."""
    seen_ids: set[str] = set()
    out: List[HeadingConstraint] = []
    for hidx, hc in enumerate(parsed_headings):
        eff_id = str(getattr(hc, "id", "") or "").strip()
        if not eff_id:
            base = ""
            if getattr(hc, "pattern", None):
                base = _slugify_heading_constraint_id(str(hc.pattern))
            if not base:
                base = f"level-{int(hc.level)}-{hidx}"
            eff_id = f"h{int(hc.level)}-{base}"
        eff_id = eff_id.strip()
        candidate = eff_id
        n = 2
        while candidate.lower() in seen_ids:
            candidate = f"{eff_id}-{n}"
            n += 1
        eff_id = candidate
        seen_ids.add(eff_id.lower())
        out.append(replace(hc, id=eff_id))
    return out
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-assign-heading-ids

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-link-heading-prev-next
def _link_heading_prev_next(
    out_headings: List[HeadingConstraint],
    kind: str,
    errors: List[str],
) -> List[HeadingConstraint]:
    """Second pass: fill in prev/next links and validate references."""
    by_id: Dict[str, HeadingConstraint] = {str(hc.id): hc for hc in out_headings if getattr(hc, "id", None)}
    normalized: List[HeadingConstraint] = []
    for hidx, hc in enumerate(out_headings):
        prev_id = getattr(hc, "prev", None)
        next_id = getattr(hc, "next", None)
        if not prev_id and hidx > 0:
            prev_id = str(out_headings[hidx - 1].id)
        if not next_id and hidx + 1 < len(out_headings):
            next_id = str(out_headings[hidx + 1].id)
        if prev_id and prev_id not in by_id:
            errors.append(f"constraints for {kind} headings[{hidx}]: prev references unknown heading id '{prev_id}'")
        if next_id and next_id not in by_id:
            errors.append(f"constraints for {kind} headings[{hidx}]: next references unknown heading id '{next_id}'")
        normalized.append(replace(hc, prev=prev_id, next=next_id))
    return normalized
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-link-heading-prev-next

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-normalize-heading-ids
def _normalize_heading_ids(
    parsed_headings: List[HeadingConstraint],
    kind: str,
    errors: List[str],
) -> List[HeadingConstraint]:
    out_headings = _assign_heading_ids(parsed_headings)
    return _link_heading_prev_next(out_headings, kind, errors)
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-normalize-heading-ids

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-normalize-id-entry
def _normalize_id_entry(
    kkind: str, entry: dict, kind: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """Validate and normalise a single identifiers entry.

    Returns ``(normalised_dict, None)`` on success or ``(None, error_msg)`` on failure.
    """
    inferred_kind = kkind.strip()
    if "kind" in entry:
        vv = entry.get("kind")
        if not isinstance(vv, str) or not vv.strip():
            return None, f"constraints for {kind} identifiers[{kkind}]: Constraint entry missing required 'kind'"
        if vv.strip().lower() != inferred_kind.lower():
            return None, f"constraints for {kind} identifiers[{kkind}]: Constraint entry kind does not match identifiers key"
        return dict(entry), None
    normalized = dict(entry)
    normalized["kind"] = inferred_kind
    return normalized, None
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-normalize-id-entry

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-identifier-entry
def _parse_identifier_entry(
    kkind: object,
    entry: object,
    kind: str,
) -> Tuple[Optional[IdConstraint], Optional[str]]:
    if not isinstance(kkind, str) or not kkind.strip():
        return None, f"constraints for {kind} field 'identifiers' has non-string kind key"
    if not isinstance(entry, dict):
        return None, f"constraints for {kind} identifiers[{kkind}]: Constraint entry must be an object"
    normalized, norm_err = _normalize_id_entry(kkind, entry, kind)
    if norm_err:
        return None, norm_err
    constraint, parse_err = _parse_id_constraint(normalized)
    if parse_err:
        return None, f"constraints for {kind} identifiers[{kkind}]: {parse_err}"
    return constraint, None
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-identifier-entry

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-identifiers-block
def _parse_identifiers_block(
    identifiers_raw: object,
    kind: str,
    errors: List[str],
) -> Tuple[Optional[List[IdConstraint]], bool]:
    if not isinstance(identifiers_raw, dict):
        errors.append(f"constraints for {kind} field 'identifiers' must be an object")
        return None, False
    defined_id: List[IdConstraint] = []
    seen_defined: set[str] = set()
    for kkind, entry in identifiers_raw.items():
        c, e = _parse_identifier_entry(kkind, entry, kind)
        if e:
            errors.append(e)
            continue
        if c is None:
            continue
        kk = c.kind.strip().lower()
        if kk in seen_defined:
            errors.append(f"constraints for {kind} identifiers has duplicate kind '{c.kind.strip()}'")
            continue
        seen_defined.add(kk)
        defined_id.append(c)
    return defined_id, True
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-identifiers-block
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-constraints-normalize


# @cpt-algo:cpt-studio-algo-traceability-validation-load-constraints:p1
def parse_kit_constraints(data: object) -> Tuple[Optional[KitConstraints], List[str]]:
    """Parse kit constraints."""
    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-kit
    if data is None:
        return None, []
    if not isinstance(data, dict):
        return None, ["constraints root must be an object mapping artifact kinds to constraints"]

    out: Dict[str, ArtifactKindConstraints] = {}
    errors: List[str] = []

    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-kit-loop
    for kind, raw in data.items():
        # Allow optional JSON Schema metadata keys.
        # Example: {"$schema": "../../schemas/kit-constraints.schema.json", "PRD": {...}}
        if isinstance(kind, str) and kind.strip().startswith("$"):
            continue
        if not isinstance(kind, str) or not kind.strip():
            errors.append("constraints has non-string kind key")
            continue
        if not isinstance(raw, dict):
            errors.append(f"constraints for {kind} must be an object")
            continue
        parsed = _parse_artifact_kind_constraints(kind, raw, errors)
        if parsed is None:
            continue
        out[kind.strip().upper()] = parsed
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-kit-loop

    if errors:
        return None, errors
    return KitConstraints(by_kind=out), []
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-kit

# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-constraints-normalize
def _merge_reference_rule(base: ReferenceRule, incoming: ReferenceRule) -> ReferenceRule:
    return ReferenceRule(
        coverage=incoming.coverage if incoming.coverage is not None else base.coverage,
        task=incoming.task if incoming.task is not None else base.task,
        priority=incoming.priority if incoming.priority is not None else base.priority,
        headings=_merge_unique_strings(base.headings, incoming.headings),
    )


def _merge_unique_strings(base: Optional[List[str]], incoming: Optional[List[str]]) -> Optional[List[str]]:
    merged: List[str] = []
    seen: set[str] = set()
    for value in (base or []) + (incoming or []):
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged or None


def _merge_id_constraint(base: IdConstraint, incoming: IdConstraint) -> IdConstraint:
    references = dict(base.references or {})
    for name, rule in (incoming.references or {}).items():
        references[name] = _merge_reference_rule(references[name], rule) if name in references else rule
    return IdConstraint(
        kind=incoming.kind or base.kind,
        required=base.required if base.required == incoming.required else False,
        name=incoming.name if incoming.name is not None else base.name,
        description=incoming.description if incoming.description is not None else base.description,
        template=incoming.template if incoming.template is not None else base.template,
        examples=(base.examples or []) + (incoming.examples or []) or None,
        task=incoming.task if incoming.task is not None else base.task,
        priority=incoming.priority if incoming.priority is not None else base.priority,
        to_code=incoming.to_code if incoming.to_code is not None else base.to_code,
        headings=_merge_unique_strings(base.headings, incoming.headings),
        references=references or None,
    )


def _merge_artifact_constraints(
    base: ArtifactKindConstraints,
    incoming: ArtifactKindConstraints,
) -> ArtifactKindConstraints:
    by_id_kind = {
        str(c.kind).strip().lower(): c
        for c in (base.defined_id or [])
        if str(getattr(c, "kind", "") or "").strip()
    }
    order = [
        str(c.kind).strip().lower()
        for c in (base.defined_id or [])
        if str(getattr(c, "kind", "") or "").strip()
    ]
    for constraint in incoming.defined_id or []:
        key = str(constraint.kind).strip().lower()
        if not key:
            continue
        if key in by_id_kind:
            by_id_kind[key] = _merge_id_constraint(by_id_kind[key], constraint)
        else:
            by_id_kind[key] = constraint
            order.append(key)
    return ArtifactKindConstraints(
        name=incoming.name if incoming.name is not None else base.name,
        description=incoming.description if incoming.description is not None else base.description,
        defined_id=[by_id_kind[key] for key in order if key in by_id_kind],
        headings=(base.headings or []) + (incoming.headings or []) or None,
        toc=base.toc if base.toc == incoming.toc else False,
    )


def merge_kit_constraints_all_of(constraints: Sequence[KitConstraints]) -> Optional[KitConstraints]:
    """Merge constraints sequentially using allOf-style additive semantics."""
    by_kind: Dict[str, ArtifactKindConstraints] = {}
    for kit_constraints in constraints:
        for kind, incoming in (kit_constraints.by_kind or {}).items():
            normalized = str(kind).strip().upper()
            if not normalized:
                continue
            if normalized in by_kind:
                by_kind[normalized] = _merge_artifact_constraints(by_kind[normalized], incoming)
            else:
                by_kind[normalized] = incoming
    if not by_kind:
        return None
    return KitConstraints(by_kind=by_kind)
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-constraints-normalize

def load_constraints_file(path: Path) -> Tuple[Optional[KitConstraints], List[str]]:
    """Load constraints file."""
    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-load-toml
    path = path.resolve()
    if not path.is_file():
        return None, []
    try:
        from . import toml_utils
        data = toml_utils.load(path)
    except (OSError, ValueError, KeyError) as e:
        return None, [f"Failed to parse {path.name}: {e}"]

    # TOML wraps kinds under "artifacts" key
    artifacts_data = data.get("artifacts", data)
    constraints, errs = parse_kit_constraints(artifacts_data)
    if errs:
        return None, errs
    return constraints, []
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-load-toml


def load_constraints_files(paths: Sequence[Path]) -> Tuple[Optional[KitConstraints], List[str]]:
    """Load constraints files."""
    loaded: List[KitConstraints] = []
    errors: List[str] = []
    for path in paths:
        constraints, errs = load_constraints_file(path)
        if errs:
            errors.extend(f"{path.name}: {err}" for err in errs)
        elif constraints is None:
            errors.append(f"{path.name}: constraints file not found or is not a file")
        if constraints is not None:
            loaded.append(constraints)
    if errors:
        return None, errors
    return merge_kit_constraints_all_of(loaded), []


def load_constraints_toml(kit_root: Path) -> Tuple[Optional[KitConstraints], List[str]]:
    """Load constraints toml."""
    return load_constraints_file((kit_root / "constraints.toml").resolve())


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-headings-datamodel
__all__ = [
    "ReferenceRule",
    "HeadingConstraint",
    "IdConstraint",
    "ArtifactKindConstraints",
    "KitConstraints",
    "ArtifactRecord",
    "ParsedStudioId",
    "cross_validate_artifacts",
    "error",
    "load_constraints_file",
    "load_constraints_files",
    "load_constraints_toml",
    "merge_kit_constraints_all_of",
    "parse_cpt",
    "parse_kit_constraints",
    "validate_artifact_file",
]

_HEADING_LINE_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_HEADING_NUMBER_PREFIX_RE = re.compile(r"^(?P<prefix>\d+(?:\.\d+)*)(?:\.)?\s+(?P<title>.+)$")
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-headings-datamodel

def _scan_headings(path: Path) -> List[Dict[str, object]]:
    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-scan-headings
    from .document import read_text_safe

    lines = read_text_safe(path)
    if lines is None:
        return []

    out: List[Dict[str, object]] = []
    in_fence = False
    for idx0, raw in enumerate(lines):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_LINE_RE.match(raw)
        if not m:
            continue
        level = len(m.group(1))
        raw_title = str(m.group(2) or "").strip()
        numbered = False
        title_text = raw_title
        number_prefix: Optional[str] = None
        number_parts: Optional[List[int]] = None
        mp = _HEADING_NUMBER_PREFIX_RE.match(raw_title)
        if mp:
            numbered = True
            number_prefix = str(mp.group("prefix") or "").strip() or None
            if number_prefix:
                try:
                    number_parts = [int(x) for x in number_prefix.split(".") if x.strip()]
                except ValueError:
                    number_parts = None
            title_text = str(mp.group("title") or "").strip()
        out.append({
            "line": idx0 + 1,
            "level": level,
            "raw_title": raw_title,
            "title_text": title_text,
            "numbered": numbered,
            "number_prefix": number_prefix,
            "number_parts": number_parts,
        })
    return out
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-scan-headings


def _heading_constraint_label(hc: HeadingConstraint) -> str:
    hid = str(getattr(hc, "id", "") or "").strip()
    pat = str(getattr(hc, "pattern", "") or "").strip()
    if pat:
        return f"{hid}({pat})" if hid else pat
    return hid or f"level={int(hc.level)}"


def _heading_constraint_info(hc: Optional[HeadingConstraint]) -> Optional[Dict[str, object]]:
    if hc is None:
        return None
    return {
        "id": getattr(hc, "id", None),
        "level": int(getattr(hc, "level", 0) or 0),
        "pattern": getattr(hc, "pattern", None),
        "description": getattr(hc, "description", None),
        "pointer": getattr(hc, "pointer", None),
    }


def _heading_constraint_source_fields(
    hc: HeadingConstraint,
    idx: int,
    constraints_path: Optional[Path],
    kit_id: Optional[str],
) -> Dict[str, object]:
    pointer = getattr(hc, "pointer", None) or f"/<unknown-kind>/headings/{idx}"
    return {
        "constraints_path": str(constraints_path) if constraints_path is not None else None,
        "constraints_pointer": pointer,
        "kit": kit_id,
        "heading_id": getattr(hc, "id", None),
        "heading_description": getattr(hc, "description", None),
    }


def _heading_context(
    *,
    heading_constraint: HeadingConstraint,
    idx: int,
    artifact_kind: str,
    path: Path,
    constraints_path: Optional[Path],
    kit_id: Optional[str],
) -> HeadingErrorContext:
    return HeadingErrorContext(
        heading_constraint=heading_constraint,
        idx=idx,
        artifact_kind=artifact_kind,
        path=path,
        constraints_path=constraints_path,
        kit_id=kit_id,
    )


def _heading_context_fields(ctx: HeadingErrorContext) -> Dict[str, object]:
    return _heading_constraint_source_fields(
        ctx.heading_constraint,
        ctx.idx,
        ctx.constraints_path,
        ctx.kit_id,
    )


def _neighbor_heading_constraints(
    heading_constraints: Sequence[HeadingConstraint],
    by_id: Dict[str, HeadingConstraint],
    ctx: HeadingErrorContext,
) -> Tuple[Optional[HeadingConstraint], Optional[HeadingConstraint]]:
    prev_id = getattr(ctx.heading_constraint, "prev", None) or (
        heading_constraints[ctx.idx - 1].id if ctx.idx > 0 else None
    )
    next_id = getattr(ctx.heading_constraint, "next", None) or (
        heading_constraints[ctx.idx + 1].id
        if ctx.idx + 1 < len(heading_constraints) else None
    )
    return (
        by_id.get(str(prev_id)) if prev_id else None,
        by_id.get(str(next_id)) if next_id else None,
    )


def _build_heading_constraints_by_id(
    heading_constraints: Sequence[HeadingConstraint],
) -> Dict[str, HeadingConstraint]:
    by_id: Dict[str, HeadingConstraint] = {}
    for heading_constraint in heading_constraints:
        hid = str(getattr(heading_constraint, "id", "") or "").strip()
        if hid and hid not in by_id:
            by_id[hid] = heading_constraint
    return by_id


def _heading_numbering_state(
    heading: Dict[str, object],
) -> Optional[Tuple[Tuple[int, Tuple[Tuple[int, ...], int]], int, str]]:
    parts = heading.get("number_parts")
    if not parts or not isinstance(parts, list) or not all(isinstance(x, int) for x in parts):
        return None
    parent = tuple(parts[:-1])
    key = (int(heading.get("level", 0) or 0), (parent, len(parts)))
    prefix = str(heading.get("number_prefix") or "").strip() or ".".join(str(x) for x in parts)
    return key, int(parts[-1]), prefix


def _check_heading_numbering_sequence(
    *,
    headings: Sequence[Dict[str, object]],
    artifact_kind: str,
    path: Path,
    errors: List[Dict[str, object]],
) -> None:
    last_child_by_key: Dict[Tuple[int, Tuple[Tuple[int, ...], int]], int] = {}
    last_prefix_by_key: Dict[Tuple[int, Tuple[Tuple[int, ...], int]], str] = {}

    for heading in headings:
        numbering_state = _heading_numbering_state(heading)
        if numbering_state is None:
            continue
        key, child, prefix = numbering_state
        parent = key[1][0]

        if key in last_child_by_key:
            expected = int(last_child_by_key[key]) + 1
            if child != expected:
                expected_prefix = ".".join([*(str(x) for x in parent), str(expected)]) if parent else str(expected)
                errors.append(error(
                    "structure",
                    f"Heading `{prefix}` in {artifact_kind} artifact is not consecutive — expected `{expected_prefix}` after `{last_prefix_by_key.get(key)}`",
                    code=EC.HEADING_NUMBER_NOT_CONSECUTIVE,
                    path=path,
                    line=int(heading.get("line", 1) or 1),
                    artifact_kind=artifact_kind,
                    found_prefix=prefix,
                    expected_prefix=expected_prefix,
                    previous_prefix=last_prefix_by_key.get(key),
                ))

        last_child_by_key[key] = child
        last_prefix_by_key[key] = prefix


def _match_heading_constraint(
    heading: Dict[str, object],
    heading_constraint: HeadingConstraint,
) -> bool:
    if int(heading.get("level", 0)) != int(heading_constraint.level):
        return False
    pattern = getattr(heading_constraint, "pattern", None)
    if not pattern:
        return True
    pattern_s = str(pattern).strip()
    title = str(heading.get("title_text") or "").strip()
    if not _is_regex_pattern_hc(pattern_s):
        return pattern_s.casefold() == title.casefold()
    try:
        return re.search(pattern_s, title, flags=re.IGNORECASE) is not None
    except re.error:
        return False


def _scope_end_for_parent_heading(
    headings: Sequence[Dict[str, object]],
    parent_idx: int,
    parent_level: int,
) -> int:
    idx = parent_idx + 1
    while idx < len(headings):
        if int(headings[idx].get("level", 0) or 0) <= parent_level:
            return idx
        idx += 1
    return len(headings)


def _match_scope_for_constraint(
    *,
    headings: Sequence[Dict[str, object]],
    heading_constraint: HeadingConstraint,
    cursor: int,
    last_match_idx_by_level: Dict[int, int],
) -> Tuple[int, int, int]:
    hc_level = int(getattr(heading_constraint, "level", 0) or 0)
    scope_start = cursor
    scope_end = len(headings)
    for level in range(hc_level - 1, 0, -1):
        parent_idx = last_match_idx_by_level.get(level)
        if parent_idx is None:
            continue
        scope_start = max(scope_start, parent_idx + 1)
        scope_end = _scope_end_for_parent_heading(headings, parent_idx, level)
        break
    return hc_level, scope_start, scope_end


def _find_heading_matches_in_scope(
    *,
    headings: Sequence[Dict[str, object]],
    heading_constraint: HeadingConstraint,
    scope_start: int,
    scope_end: int,
) -> Tuple[List[Dict[str, object]], int, int]:
    match_idx = scope_start
    while match_idx < scope_end and not _match_heading_constraint(headings[match_idx], heading_constraint):
        match_idx += 1
    if match_idx >= scope_end:
        return [], scope_start, scope_start
    matches = [headings[match_idx]]
    next_idx = match_idx + 1
    if heading_constraint.multiple is not False:
        while next_idx < scope_end and _match_heading_constraint(headings[next_idx], heading_constraint):
            matches.append(headings[next_idx])
            next_idx += 1
    return matches, match_idx, next_idx


def _append_missing_heading_error(
    *,
    heading_ctx: HeadingValidationContext,
    heading_constraint: HeadingConstraint,
    idx: int,
) -> None:
    ctx = _heading_context(
        heading_constraint=heading_constraint,
        idx=idx,
        artifact_kind=heading_ctx.artifact_kind,
        path=heading_ctx.path,
        constraints_path=heading_ctx.constraints_path,
        kit_id=heading_ctx.kit_id,
    )
    hc_desc = str(getattr(ctx.heading_constraint, "description", "") or "").strip()
    after_hc, before_hc = _neighbor_heading_constraints(
        heading_ctx.heading_constraints,
        heading_ctx.by_id,
        ctx,
    )
    between: List[str] = []
    if after_hc is not None:
        between.append(f"after '{_heading_constraint_label(after_hc)}'")
    if before_hc is not None:
        between.append(f"before '{_heading_constraint_label(before_hc)}'")
    between_s = (" (expected " + " and ".join(between) + ")") if between else ""
    desc_s = (f" ({hc_desc})" if hc_desc else "")
    heading_ctx.errors.append(error(
        "constraints",
        f"Required level-{int(heading_constraint.level)} heading (pattern: `{heading_constraint.pattern}`) missing in {heading_ctx.artifact_kind} artifact{between_s}{desc_s}",
        code=EC.HEADING_MISSING,
        path=ctx.path,
        line=1,
        artifact_kind=ctx.artifact_kind,
        heading_level=int(ctx.heading_constraint.level),
        heading_pattern=ctx.heading_constraint.pattern,
        expected_after=_heading_constraint_info(after_hc),
        expected_before=_heading_constraint_info(before_hc),
        **_heading_context_fields(ctx),
    ))


def _append_multiple_heading_error(
    *,
    heading_ctx: HeadingValidationContext,
    heading_constraint: HeadingConstraint,
    idx: int,
    match_count: int,
    line: int,
) -> None:
    ctx = _heading_context(
        heading_constraint=heading_constraint,
        idx=idx,
        artifact_kind=heading_ctx.artifact_kind,
        path=heading_ctx.path,
        constraints_path=heading_ctx.constraints_path,
        kit_id=heading_ctx.kit_id,
    )
    hc_desc = str(getattr(ctx.heading_constraint, "description", "") or "").strip()
    desc_s = (f" ({hc_desc})" if hc_desc else "")
    heading_ctx.errors.append(error(
        "constraints",
        f"Heading `{ctx.heading_constraint.pattern}` (level {int(ctx.heading_constraint.level)}) appears {match_count} times in {ctx.artifact_kind} artifact but only 1 is allowed{desc_s}",
        code=EC.HEADING_PROHIBITS_MULTIPLE,
        path=ctx.path,
        line=line,
        artifact_kind=ctx.artifact_kind,
        heading_level=int(ctx.heading_constraint.level),
        heading_pattern=ctx.heading_constraint.pattern,
        **_heading_context_fields(ctx),
    ))


def _append_numbering_mismatch_error(
    *,
    heading_constraint: HeadingConstraint,
    idx: int,
    heading: Dict[str, object],
    artifact_kind: str,
    path: Path,
    constraints_path: Optional[Path],
    kit_id: Optional[str],
    errors: List[Dict[str, object]],
) -> None:
    hc_desc = str(getattr(heading_constraint, "description", "") or "").strip()
    desc_s = (f" ({hc_desc})" if hc_desc else "")
    errors.append(error(
        "constraints",
        f"Heading `{heading_constraint.pattern}` (level {int(heading_constraint.level)}) in {artifact_kind} artifact: numbering {'is required but missing' if heading_constraint.numbered is True else 'is prohibited but present'}{desc_s}",
        code=EC.HEADING_NUMBERING_MISMATCH,
        path=path,
        line=int(heading.get("line", 1) or 1),
        artifact_kind=artifact_kind,
        heading_level=int(heading_constraint.level),
        heading_pattern=heading_constraint.pattern,
        numbered=heading_constraint.numbered,
        **_heading_constraint_source_fields(heading_constraint, idx, constraints_path, kit_id),
    ))


def _validate_heading_matches(
    *,
    headings: Sequence[Dict[str, object]],
    heading_constraints: Sequence[HeadingConstraint],
    by_id: Dict[str, HeadingConstraint],
    artifact_kind: str,
    path: Path,
    constraints_path: Optional[Path],
    kit_id: Optional[str],
    errors: List[Dict[str, object]],
) -> None:
    cursor = 0
    last_match_idx_by_level: Dict[int, int] = {}
    heading_ctx = HeadingValidationContext(
        heading_constraints=heading_constraints,
        by_id=by_id,
        artifact_kind=artifact_kind,
        path=path,
        constraints_path=constraints_path,
        kit_id=kit_id,
        errors=errors,
    )

    for idx, heading_constraint in enumerate(heading_constraints):
        cursor = _validate_single_heading_match(
            heading_ctx=heading_ctx,
            headings=headings,
            heading_constraint=heading_constraint,
            idx=idx,
            cursor=cursor,
            last_match_idx_by_level=last_match_idx_by_level,
        )

def _validate_single_heading_match(
    *,
    heading_ctx: HeadingValidationContext,
    headings: Sequence[Dict[str, object]],
    heading_constraint: HeadingConstraint,
    idx: int,
    cursor: int,
    last_match_idx_by_level: Dict[int, int],
) -> int:
    hc_level, scope_start, scope_end = _match_scope_for_constraint(
        headings=headings,
        heading_constraint=heading_constraint,
        cursor=cursor,
        last_match_idx_by_level=last_match_idx_by_level,
    )
    matches, match_idx, next_idx = _find_heading_matches_in_scope(
        headings=headings,
        heading_constraint=heading_constraint,
        scope_start=scope_start,
        scope_end=scope_end,
    )
    if not matches:
        if heading_constraint.required:
            _append_missing_heading_error(
                heading_ctx=heading_ctx,
                heading_constraint=heading_constraint,
                idx=idx,
            )
        return cursor
    cursor = _update_heading_match_state(
        heading_constraint=heading_constraint,
        hc_level=hc_level,
        match_idx=match_idx,
        next_idx=next_idx,
        last_match_idx_by_level=last_match_idx_by_level,
    )
    if heading_constraint.multiple is False and len(matches) > 1:
        _append_multiple_heading_error(
            heading_ctx=heading_ctx,
            heading_constraint=heading_constraint,
            idx=idx,
            match_count=len(matches),
            line=int(matches[1].get("line", 1) or 1),
        )
    if heading_constraint.numbered is None:
        return cursor
    want_numbered = heading_constraint.numbered is True
    for match in matches:
        if bool(match.get("numbered", False)) == want_numbered:
            continue
        _append_numbering_mismatch_error(
            heading_constraint=heading_constraint,
            idx=idx,
            heading=match,
            artifact_kind=heading_ctx.artifact_kind,
            path=heading_ctx.path,
            constraints_path=heading_ctx.constraints_path,
            kit_id=heading_ctx.kit_id,
            errors=heading_ctx.errors,
        )
    return cursor


def _update_heading_match_state(
    *,
    heading_constraint: HeadingConstraint,
    hc_level: int,
    match_idx: int,
    next_idx: int,
    last_match_idx_by_level: Dict[int, int],
) -> int:
    if heading_constraint.multiple is not False:
        cursor = next_idx
        last_idx = next_idx - 1
    else:
        cursor = match_idx + 1
        last_idx = match_idx
    last_match_idx_by_level[hc_level] = last_idx
    for level in list(last_match_idx_by_level.keys()):
        if level > hc_level:
            del last_match_idx_by_level[level]
    return cursor


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-headings-entry
def validate_headings_contract(
    *,
    path: Path,
    constraints: ArtifactKindConstraints,
    registered_systems: Optional[Iterable[str]],  # pylint: disable=unused-argument  # public API; reserved for system-scoped heading validation
    artifact_kind: str,
    constraints_path: Optional[Path] = None,
    kit_id: Optional[str] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """Validate artifact outline against constraints.headings.

    Current behavior is intentionally conservative:
    - Requires that each required heading constraint matches at least once.
    - Enforces multiple/prohibited/required counts for each constraint.
    - Enforces numbered required/prohibited for matched headings.
    """
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-headings-entry
    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-init
    errors: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []

    heading_constraints = getattr(constraints, "headings", None) or []
    if not heading_constraints:
        return {"errors": errors, "warnings": warnings}
    by_id = _build_heading_constraints_by_id(heading_constraints)

    headings = _scan_headings(path)
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-init

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-numbering
    _check_heading_numbering_sequence(
        headings=headings,
        artifact_kind=str(artifact_kind).strip().upper(),
        path=path,
        errors=errors,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-numbering

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings
    _validate_heading_matches(
        headings=headings,
        heading_constraints=heading_constraints,
        by_id=by_id,
        artifact_kind=str(artifact_kind).strip().upper(),
        path=path,
        constraints_path=constraints_path,
        kit_id=kit_id,
        errors=errors,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings
    return {"errors": errors, "warnings": warnings}
