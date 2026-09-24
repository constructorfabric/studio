"""Constraint models and validators for Studio traceability artifacts."""

# @cpt-state:cpt-studio-state-traceability-validation-report:p1

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-structure-datamodel
from __future__ import annotations

import re
import logging
# `field` is aliased: this module uses `field` as an ordinary local name in the
# constraint parsers, and shadowing the dataclasses helper there reads as a bug.
from dataclasses import dataclass, field as dataclass_field, replace
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from . import error_codes as EC
from .severity import (
    ENTRY_HEADING,
    ENTRY_IDENTIFIER,
    EntryKey,
    EntrySeverity,
    SeverityPolicy,
    SeverityTables,
    apply_policy,
    default_severity,
    entry_key,
    is_stricter,
    merge_severity_tables,
    parse_kit_validation,
    parse_severity_value,
    reject_caller_severity,
)

logger = logging.getLogger(__name__)

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
    #: Severity for the rules this entry owns, overriding the code's default.
    severity: Optional[str] = None
    #: When true, a project may raise this entry's rules but not lower them.
    locked: bool = False

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
    #: Severity for the rules this entry owns, overriding the code's default.
    severity: Optional[str] = None
    #: When true, a project may raise this entry's rules but not lower them.
    locked: bool = False

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
class TocOptions:
    """How deep, and how large, TOC checking looks for one artifact kind.

    ``None`` is "this kind has no opinion", not a value. Storing the engine
    default here instead would make a kit that says nothing about depth
    indistinguishable from one that deliberately asked for today's depth — and
    a `--max-level` on the command line could no longer be told from silence,
    which is the whole precedence question this table exists to answer.
    """

    max_level: Optional[int] = None
    max_section_lines: Optional[int] = None


#: Every option ``[artifacts.<KIND>.validation.toc]`` understands.
_TOC_OPTION_KEYS = frozenset({"max_level", "max_section_lines"})


@dataclass(frozen=True)
class HeadingOrder:
    """Which sections must precede which, held as the pairs the kits stated.

    A kit writes a list, and a list is a chain: every id in it precedes every
    id after it. The shorthand ``order = "declared"`` is the chain of every
    heading the kind declares — the strictness the matcher used to impose on
    every kit implicitly, now an explicit opt-in.

    Pairs rather than a sequence, because two kits' orders have to be added up
    and a sequence cannot hold the sum. Splicing ``("a", "c")`` onto
    ``("b", "c")`` gives ``("a", "c", "b")``, which says c precedes b — the
    reverse of what the second kit wrote — and says a precedes b, which
    neither kit wrote. The union of their pairs says exactly what they said.

    Absent (``ArtifactKindConstraints.order is None``) means the kind imposes
    no order at all. That is the default, because a rule a kit cannot state
    is a rule a kit cannot relax either.
    """

    pairs: FrozenSet[Tuple[str, str]] = frozenset()

    @classmethod
    def from_sequence(cls, ids: Sequence[str]) -> "HeadingOrder":
        """Build the chain one ``order`` list states."""
        return cls(pairs=frozenset(
            (earlier, later)
            for position, earlier in enumerate(ids)
            for later in tuple(ids)[position + 1:]
        ))

    def relates(self, first_id: Optional[str], second_id: Optional[str]) -> bool:
        """Whether this order says ``first_id`` must come before ``second_id``."""
        if not first_id or not second_id or first_id == second_id:
            return False
        return (first_id, second_id) in self.pairs


#: The one non-list value ``order`` accepts.
ORDER_DECLARED = "declared"


@dataclass(frozen=True)
class ArtifactKindConstraints:
    """Validation constraints attached to one artifact kind."""

    name: Optional[str]
    description: Optional[str]
    defined_id: List[IdConstraint]
    headings: Optional[List[HeadingConstraint]] = None
    toc: bool = True
    #: ``[artifacts.<KIND>.validation]`` — this kind's own severity table.
    validation: SeverityTables = dataclass_field(default_factory=SeverityTables)
    #: ``[artifacts.<KIND>.validation.toc]`` — this kind's TOC options.
    toc_options: TocOptions = dataclass_field(default_factory=TocOptions)
    #: ``[artifacts.<KIND>] order`` — the section order this kind enforces.
    order: Optional[HeadingOrder] = None

@dataclass(frozen=True)
class KitConstraints:
    """Loaded validation constraints for all artifact kinds in a kit."""

    by_kind: Dict[str, ArtifactKindConstraints]
    #: Top-level ``[validation]`` — the kit's whole-kit severity table. Lifted
    #: out before the ``artifacts`` unwrap, or it would be read as a kind.
    validation: SeverityTables = dataclass_field(default_factory=SeverityTables)


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
    #: The order this kind declares, or None when it declares none.
    order: Optional[HeadingOrder] = None
    #: Indices of headings some constraint has already matched. Two constraints
    #: must not both claim one section: without this the rescue pass would
    #: re-match a section the cursor pass already consumed and report the
    #: document's only copy as being in two places at once.
    claimed: Set[int] = dataclass_field(default_factory=set)
    #: Indices of headings already reported out of order. A displaced section
    #: carries its subsections with it, so its descendants are not reported
    #: again — one cause, one finding.
    reported_idx: Set[int] = dataclass_field(default_factory=set)
    #: Heading index each matched constraint id landed on, which is what makes
    #: "this section must come after that one" nameable with a line number.
    matched_idx_by_id: Dict[str, int] = dataclass_field(default_factory=dict)
    #: Heading indices whose numbering some constraint has already ruled on.
    #: The numbering check reads a constraint's whole scope, not only the run
    #: it claims, so two constraints with overlapping patterns both see a
    #: heading only one of them takes — and one defect would be reported twice.
    numbering_judged: Set[int] = dataclass_field(default_factory=set)

def error(
    kind: str,
    message: str,
    *,
    path: Path | str,
    line: int = 1,
    code: Optional[str] = None,
    **extra,
) -> Dict[str, object]:
    """Build a structured constraint validation error."""
    # @cpt-begin:cpt-studio-state-traceability-validation-report:p1:inst-error
    out: Dict[str, object] = {"type": kind, "message": message, "line": int(line)}
    if code:
        out["code"] = code
    out["severity"] = default_severity(code)
    reject_caller_severity(extra)
    path_s = str(path)
    out["path"] = path_s
    out["location"] = f"{path_s}:{int(line)}" if (path_s and not path_s.startswith("<")) else path_s
    extra = {k: v for k, v in extra.items() if v is not None}
    out.update(extra)
    return out
    # @cpt-end:cpt-studio-state-traceability-validation-report:p1:inst-error
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
        except re.error as exc:
            logger.warning("Invalid heading regex %r: %s", pat_s, exc)
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


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-match-loop
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
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-resolve-scope-match-loop


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

    matched_ids_by_line = _match_heading_ids_by_line(
        headings,
        idx_by_level,
        compiled,
        wildcard_lvl3_by_parent_lvl2_id,
    )

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


# @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-parse-cpt
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
# @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-parse-cpt


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
    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-match-system
    if not cpt.lower().startswith("cpt-"):
        return None
    if systems_set:
        return _match_registered_system(cpt, systems_set)
    return _infer_system_from_kind_tokens(cpt, kind_tokens)
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-match-system


def _extract_kind_from_cpt(
    cpt: str,
    system: Optional[str],
    kind_tokens: Iterable[str],
    composite_nested_by_base: Dict[str, set[str]],
) -> Optional[str]:
    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-extract-kind
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-extract-kind
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
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-composite-nested
    if nested_kinds and len(parts) >= 4:
        for part in reversed(parts[2:]):
            candidate = part.strip().lower()
            if candidate in nested_kinds and candidate != base:
                return candidate
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-composite-nested

    normalized_kind_tokens = {str(k).strip().lower() for k in kind_tokens if str(k).strip()}
    if base in normalized_kind_tokens:
        return base

    return _find_kind_marker(remainder, normalized_kind_tokens) or base
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-extract-kind
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-extract-kind

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
        errors.append(error(
            "constraints",
            (
                f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact "
                f"is missing required task checkbox `- [ ]`{hint}"
            ),
            code=EC.DEF_MISSING_TASK,
            **base,
        ))
    if tk is False and has_task:
        errors.append(error(
            "constraints",
            (
                f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact has "
                f"task checkbox but kind `{ctx.id_kind}` prohibits task tracking{hint}"
            ),
            code=EC.DEF_PROHIBITED_TASK,
            **base,
        ))
    if pr is True and not has_priority:
        errors.append(error(
            "constraints",
            (
                f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact "
                f"is missing required priority marker{hint}"
            ),
            code=EC.DEF_MISSING_PRIORITY,
            **base,
        ))
    if pr is False and has_priority:
        errors.append(error(
            "constraints",
            (
                f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact has "
                f"priority marker but kind `{ctx.id_kind}` prohibits priority{hint}"
            ),
            code=EC.DEF_PROHIBITED_PRIORITY,
            **base,
        ))
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
        (
            f"`{ctx.hid}` (kind `{ctx.id_kind}`) in {ctx.artifact_kind} artifact is under "
            f"{active_raw} but must be under one of {allowed_headings}"
            f"{_constraint_hint(ctx.constraint)}"
        ),
        code=EC.DEF_WRONG_HEADINGS,
        **ctx.base_fields(),
        headings=allowed_headings,
        headings_info=allowed_info,
        found_headings=active_raw,
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-heading-constraint
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-helpers

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-build-defs-index
def _build_defs_index(defs: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    defs_by_id: Dict[str, Dict[str, object]] = {}
    for definition in defs:
        did = str(definition.get("id") or "").strip()
        if did and did not in defs_by_id:
            defs_by_id[did] = definition
    return defs_by_id
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-build-defs-index


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-heading-desc
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
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-heading-desc


def _resolve_heading_scope_map(
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
) -> List[List[str]]:
    from .document import headings_by_line

    heading_constraints = getattr(constraints, "headings", None)
    if heading_constraints:
        return heading_constraint_ids_by_line(artifact_path, heading_constraints)
    return headings_by_line(artifact_path)

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-cdsl-heading-ctx
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
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-cdsl-heading-ctx


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-parent-child
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
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-parent-child


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-parent-child
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

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-all-done-parent-not
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
        (
            f"Parent `{parent_id}` is unchecked but all {child_count} nested "
            f"task-tracked items are checked in {kind} artifact"
        ),
        code=EC.PARENT_UNCHECKED_ALL_DONE,
        path=artifact_path,
        line=parent_line,
        id=parent_id,
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-all-done-parent-not


def _first_unchecked_item(
    children: Sequence[Dict[str, object]],
    ref_children: Sequence[Dict[str, object]],
    parent: Dict[str, object],
) -> Dict[str, object]:
    for item in list(children) + list(ref_children):
        if not bool(item.get("checked", False)):
            return item
    return parent

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-parent-done-child-not
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
        (
            f"Parent `{parent_id}` is checked but nested item `{first_id}` "
            f"(and possibly others) is still unchecked in {kind} artifact"
        ),
        code=EC.PARENT_CHECKED_NESTED_UNCHECKED,
        path=artifact_path,
        line=int(first.get("line", 1) or 1),
        id=first_id,
        parent_id=parent_id,
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-parent-done-child-not


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
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-parent-child


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-helpers
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
    registered_systems: Optional[Iterable[str]],
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
        systems_set={
            str(system).strip().lower()
            for system in (registered_systems or [])
            if str(system).strip()
        },
        all_kind_tokens=set(allowed_defs),
        composite_nested_by_base={kind.strip().lower(): nested} if nested else {},
        allowed_defs=allowed_defs,
        constraint_by_kind=constraint_by_kind,
        headings_at=_resolve_heading_scope_map(artifact_path, constraints),
        heading_desc_by_id=_build_heading_descriptions(constraints),
    )
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-helpers

#
# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-scan-ids
def _build_artifact_identifier_phase_context(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    kind: str,
    registered_systems: Optional[Iterable[str]],
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
            registered_systems=registered_systems,
        ),
    )
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-scan-ids


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-toc
def _validate_artifact_toc(
    artifact_path: Path,
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
    options: Optional[TocOptions] = None,
) -> None:
    from .document import read_text_safe as _read_text_safe
    from .toc import DEFAULT_MAX_SECTION_LINES, DEFAULT_TOC_MAX_LEVEL
    from .toc import validate_toc as _validate_toc

    toc_lines = _read_text_safe(artifact_path)
    if toc_lines is None:
        return
    options = options or TocOptions()
    toc_result = _validate_toc(
        "\n".join(toc_lines),
        artifact_path=artifact_path,
        max_heading_level=(
            options.max_level if options.max_level is not None else DEFAULT_TOC_MAX_LEVEL),
        max_section_lines=(
            options.max_section_lines if options.max_section_lines is not None
            else DEFAULT_MAX_SECTION_LINES),
    )
    errors.extend(toc_result.get("errors", []))
    warnings.extend(toc_result.get("warnings", []))
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-toc

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-cdsl-mismatch
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
        # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-emit-cdsl-error
        error_record = error(
            "structure",
            (
                f"CDSL step `{pid}`{(' inst ' + inst_s) if inst_s else ''} is "
                f"unchecked but parent ID is already checked in {kind} artifact"
            ),
            code=EC.CDSL_STEP_UNCHECKED,
            path=artifact_path,
            line=int(hit.get("line", 1) or 1),
            id=pid,
            inst=inst_s or None,
        )
        errors.append(error_record)
        # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-emit-cdsl-error
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-cdsl-mismatch

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-cdsl-structure
# CDSL.md step-line grammar: `N. [ ] - `pN` - description - `inst-id``.
#
# Line-shape alone can't tell a malformed CDSL step apart from ordinary content that
# happens to reuse the same `pN` priority-tag shape (DoD checklists, component lists,
# ADR prose). Two signals open a section for validation:
#   1. An explicit `**Steps**:`/`**Transitions**:` label, up to the next heading or
#      bold label — the convention this repo's own FEATURE docs use.
#   2. A heading section whose first real list item (skipping ID definitions/references
#      and other bold labels) is already a *fully well-formed* CDSL line — this covers
#      CDSL.md's own worked examples ("**Algorithm: Name**" / "**Flow: Name**" headers
#      with no "Steps:" label at all) and the bundled SDLC kit's FEATURE example
#      (a bare heading + ID line, straight into numbered steps).
# Checks below only run on lines inside a section opened by one of these two signals.
_CDSL_CANDIDATE_START_RE = re.compile(r"^(?:\d+\.\s+|-\s+)")
_CDSL_HEADING_RE = re.compile(r"^#{1,6}\s")
_CDSL_BOLD_LABEL_LINE_RE = re.compile(r"^\*\*[A-Za-z][A-Za-z0-9 /_-]*\*\*:\s*$")
_CDSL_BLOCK_OPEN_LABELS = ("**Steps**:", "**Transitions**:")
_CDSL_CHECKBOX_TOKEN_RE = re.compile(r"\[\s*[xX ]\s*\]")
_CDSL_PHASE_TOKEN_RE = re.compile(r"`(?:p\d+|ph-\d+)`")
_CDSL_INST_TOKEN_RE = re.compile(r"`inst-[a-z0-9-]+`")
_CDSL_STEP_DESC_RE = re.compile(
    r"`(?:p\d+|ph-\d+)`\s*-\s*(?P<desc>.+?)\s*-\s*`inst-[a-z0-9-]+`\s*$"
)
# S.6 / CL.3 — CDSL.md "Prohibited": function syntax (`fn`, `function`, `async`, `def`).
# `def` is scoped to real function-def shape (`def name(`) because this repo's own
# prose uses "def" as shorthand for "definition" (e.g. "ref done but def not done").
_CDSL_FUNCTION_SYNTAX_RE = re.compile(r"\b(?:fn|function|async)\b|\bdef\s+\w+\s*\(")
# S.7 — CDSL.md "Prohibited": type annotations (`: string`, `<T>`, `-> Type`). The
# `: <type>` form is scoped to a known type-keyword list (rather than any word after
# a colon) to avoid false positives on plain-English apposition like "list: enabled_entities".
# Common English words that double as type names (set/map/list/object/array/any) are
# deliberately excluded — "point: set up" and "resource: map X" are prose, not types.
# The `<T>` generic form excludes SCREAMING_SNAKE_CASE (an underscore anywhere), since
# this repo's own docs use `<ARTIFACT_KIND>`-style angle brackets for placeholder tokens,
# not generics — a real generic type parameter is PascalCase or a single letter (`<T>`).
_CDSL_TYPE_KEYWORDS = "string|str|int|integer|float|double|bool|boolean|void|optional|null|none|dict"
_CDSL_TYPE_ANNOTATION_RE = re.compile(
    rf"(?i:\b:\s*(?:{_CDSL_TYPE_KEYWORDS})\b)|(?:<[A-Z][A-Za-z0-9]*>)|(?:->\s*[A-Za-z_]\w*)"
)
# CL.2 — CDSL.md "Prohibited": language operators (`&&`, `||`, `=>`, `==`).
# Excludes runs of 3+ `=` (git conflict markers like `=======`), which aren't operators.
_CDSL_OPERATOR_RE = re.compile(r"=>|&&|\|\||(?<!=)==(?!=)")
_CDSL_PLACEHOLDER_RE = re.compile(r"\b(?:TODO|FIXME|XXX|TBD)\b|\[PLACEHOLDER\]", re.IGNORECASE)
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-cdsl-structure


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-cdsl-structure
def _cdsl_missing_tokens(stripped: str) -> List[Tuple[str, str]]:
    """Return (error_code, spec_rule) pairs for tokens absent from a candidate step line."""
    missing: List[Tuple[str, str]] = []
    if not _CDSL_CHECKBOX_TOKEN_RE.search(stripped):
        missing.append((EC.CDSL_MISSING_CHECKBOX, "S.3"))
    if not _CDSL_PHASE_TOKEN_RE.search(stripped):
        missing.append((EC.CDSL_MISSING_PHASE_TOKEN, "S.4"))
    if not _CDSL_INST_TOKEN_RE.search(stripped):
        missing.append((EC.CDSL_MISSING_INST_ID, "S.5"))
    return missing
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-cdsl-structure


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
def _append_cdsl_prohibited_syntax_errors(
    *,
    desc: str,
    artifact_path: Path,
    line_no: int,
    step_text: str,
    errors: List[Dict[str, object]],
) -> None:
    """Flag function syntax, type annotations, and operators in a CDSL step description."""
    triggered = False
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    if _CDSL_FUNCTION_SYNTAX_RE.search(desc):
        errors.append(error(
            "structure",
            f"CDSL step uses code/function syntax (S.6), not plain English: `{step_text}`",
            code=EC.CDSL_CODE_SYNTAX,
            path=artifact_path,
            line=line_no,
        ))
        triggered = True
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    if _CDSL_TYPE_ANNOTATION_RE.search(desc):
        errors.append(error(
            "structure",
            f"CDSL step uses a type annotation (S.7), not plain English: `{step_text}`",
            code=EC.CDSL_TYPE_ANNOTATION,
            path=artifact_path,
            line=line_no,
        ))
        triggered = True
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    if _CDSL_OPERATOR_RE.search(desc):
        errors.append(error(
            "structure",
            f"CDSL step uses a language operator (CL.2), not plain English: `{step_text}`",
            code=EC.CDSL_LANGUAGE_OPERATOR,
            path=artifact_path,
            line=line_no,
        ))
        triggered = True
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    if triggered:
        errors.append(error(
            "structure",
            f"CDSL step is not language-agnostic plain English (CL.1/CL.4): `{step_text}`",
            code=EC.CDSL_NOT_PLAIN_ENGLISH,
            path=artifact_path,
            line=line_no,
        ))
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-missing-token
def _validate_cdsl_step_candidate(
    *,
    line_no: int,
    step_text: str,
    artifact_path: Path,
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> None:
    """Validate one CDSL step candidate against CDSL.md's FAIL rules.

    Missing-token findings (S.3/S.4/S.5/CO.4) are reported as warnings rather
    than errors: this repo has pre-existing FEATURE docs authored before the
    inst-id convention (see architecture/features/dependency-mapping.md).
    Promote these to `errors` once that backlog is retrofitted — tracked in
    issue #85, with the current offending files enumerated and enforced by
    `tests/test_cdsl_structure_validate.py::test_cdsl_missing_token_warnings_match_known_backlog_allowlist`.
    """
    missing = _cdsl_missing_tokens(step_text)
    for code, rule in missing:
        warnings.append(error(
            "structure",
            f"CDSL step is missing its {rule} token: `{step_text}`",
            code=code,
            path=artifact_path,
            line=line_no,
        ))
    if missing:
        warnings.append(error(
            "structure",
            f"Incomplete CDSL step line, missing required token(s): `{step_text}`",
            code=EC.CDSL_INCOMPLETE_STEP_LINE,
            path=artifact_path,
            line=line_no,
        ))
        return
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-missing-token

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax
    full_match = _CDSL_STEP_DESC_RE.search(step_text)
    if not full_match:
        return
    _append_cdsl_prohibited_syntax_errors(
        desc=full_match.group("desc"),
        artifact_path=artifact_path,
        line_no=line_no,
        step_text=step_text,
        errors=errors,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-prohibited-syntax


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-duplicate-inst
def _validate_cdsl_duplicate_inst_ids(
    *,
    cdsl_hits: Sequence[Dict[str, object]],
    artifact_path: Path,
    errors: List[Dict[str, object]],
) -> None:
    """Flag a repeated `inst-{id}` under the same parent ID (CO.5)."""
    seen: Dict[Tuple[str, str], int] = {}
    for hit in cdsl_hits:
        pid = str(hit.get("parent_id") or "").strip()
        inst_s = str(hit.get("inst") or "").strip()
        if not pid or not inst_s:
            continue
        key = (pid, inst_s)
        if key in seen:
            errors.append(error(
                "structure",
                f"Duplicate instruction ID (CO.5) `inst-{inst_s}` under `{pid}` (first seen at line {seen[key]})",
                code=EC.CDSL_DUPLICATE_INST_ID,
                path=artifact_path,
                line=int(hit.get("line", 1) or 1),
                id=pid,
                inst=inst_s,
            ))
        else:
            seen[key] = int(hit.get("line", 1) or 1)
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-duplicate-inst


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-cdsl-structure
def _is_real_cdsl_item_start(stripped: str) -> bool:
    """Return whether *stripped* starts a genuine CDSL list item.

    Excludes ID definitions/references, which use the same dash-prefixed
    shape but aren't CDSL steps.
    """
    from .document import _ID_DEF_RE, _ID_REF_RE, _normalize_reference_candidate

    if not _CDSL_CANDIDATE_START_RE.match(stripped):
        return False
    return not (_ID_DEF_RE.match(stripped) or _ID_REF_RE.match(_normalize_reference_candidate(stripped)))


def _section_starts_with_wellformed_cdsl_line(entries: List[Tuple[int, str, str]]) -> bool:
    """Return whether a heading section's first real list item is fully well-formed CDSL.

    Skips any non-list-item pre-amble — blank lines, bold labels/headers of any
    shape (`**Steps**:`, `**Actors**:`, `**Algorithm: Name**`, ...), and plain
    prose (`Input: ...`, `Actor: ...`) — while looking for the first genuine
    CDSL-shaped list item. That item's *full* well-formedness (checkbox +
    phase + inst, all present) is the signal, so ordinary checklists that
    merely start with a numbered item (no inst-id at all) don't qualify. An
    explicit `**Steps**:`/`**Transitions**:` label short-circuits to True.
    """
    from .document import _CDSL_LINE_RE

    for _line_no0, _raw_line, stripped in entries:
        if not stripped:
            continue
        if stripped in _CDSL_BLOCK_OPEN_LABELS:
            return True
        if not _CDSL_CANDIDATE_START_RE.match(stripped):
            continue
        if not _is_real_cdsl_item_start(stripped):
            continue
        return bool(_CDSL_LINE_RE.match(stripped))
    return False


def _iter_cdsl_block_lines(lines: List[str]):  # pylint: disable=too-many-locals,too-many-branches
    """Yield fenced-out lines inside a recognized CDSL section.

    A section (the lines between one heading and the next) is in scope when
    either an explicit `**Steps**:`/`**Transitions**:` label opens it, or its
    first real list item is already fully well-formed CDSL — see
    `_section_starts_with_wellformed_cdsl_line`. Either way, a later bold
    label that isn't a recognized opener (e.g. `**Supporting**:`) still ends
    the scope early within the same section.

    Unlike `document._iter_non_fenced_lines`, blank lines are yielded too (as
    an empty `stripped`) rather than skipped — callers use them as an item
    boundary, so trailing prose after the last step (before any heading or
    label closes the block) isn't folded into it as a continuation.
    """
    from .document import _CODE_FENCE_RE

    entries: List[Tuple[int, str, str]] = []
    in_fence = False
    for line_no0, raw_line in enumerate(lines):
        if _CODE_FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        entries.append((line_no0, raw_line, raw_line.strip()))

    sections: List[Tuple[int, int]] = []
    section_start = 0
    for idx, (_line_no0, _raw_line, stripped) in enumerate(entries):
        if _CDSL_HEADING_RE.match(stripped):
            if idx > section_start:
                sections.append((section_start, idx))
            section_start = idx + 1
    sections.append((section_start, len(entries)))

    for start, end in sections:
        in_scope = _section_starts_with_wellformed_cdsl_line(entries[start:end])
        seen_first_item = False
        for idx in range(start, end):
            line_no0, raw_line, stripped = entries[idx]
            if _CDSL_BOLD_LABEL_LINE_RE.match(stripped):
                if stripped in _CDSL_BLOCK_OPEN_LABELS:
                    in_scope = True
                    seen_first_item = True
                elif seen_first_item:
                    # A non-opening label (e.g. **Supporting**:) only closes scope
                    # once real content has been seen — before that it's pre-amble
                    # (**Actors**:, **Algorithm: Name**, ...), not a closing label.
                    in_scope = False
                continue
            if _is_real_cdsl_item_start(stripped):
                seen_first_item = True
            if in_scope:
                yield line_no0 + 1, raw_line, stripped
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-cdsl-structure

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-cdsl-candidate
def _iter_cdsl_step_candidates(lines: List[str]):
    """Group CDSL-block lines into logical step items, joining continuation lines.

    A new item starts at any numbered/dash list marker; non-item lines that
    follow are continuation text and get folded into the open item, so a step
    description (and its trailing `inst-id` token) may wrap onto later lines.
    A blank line always closes the current item, so trailing prose separated
    from the last step by a blank line is never folded into it.
    """
    current_line_no: Optional[int] = None
    current_parts: List[str] = []
    for line_no, _raw_line, stripped in _iter_cdsl_block_lines(lines):
        if not stripped:
            if current_line_no is not None:
                yield current_line_no, " ".join(current_parts)
            current_line_no = None
            current_parts = []
            continue
        if _CDSL_CANDIDATE_START_RE.match(stripped):
            if current_line_no is not None:
                yield current_line_no, " ".join(current_parts)
            current_line_no = line_no
            current_parts = [stripped]
        elif current_line_no is not None:
            current_parts.append(stripped)
    if current_line_no is not None:
        yield current_line_no, " ".join(current_parts)
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-cdsl-candidate

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-duplicate-inst
def _cdsl_block_line_numbers(lines: List[str]) -> Set[int]:
    """Return the 1-indexed line numbers that fall inside a CDSL Steps:/Transitions: block."""
    return {line_no for line_no, _raw_line, _stripped in _iter_cdsl_block_lines(lines)}
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-duplicate-inst


def _validate_cdsl_structure(
    *,
    artifact_path: Path,
    cdsl_hits: Sequence[Dict[str, object]],
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> None:
    """Enforce CDSL.md's FAIL rules (S.3-7, CL.1-4, CO.4-6) across an artifact."""
    from .document import _ID_DEF_RE, _ID_REF_RE, _normalize_reference_candidate, read_text_safe

    lines = read_text_safe(artifact_path)
    if lines is None:
        return

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-cdsl-candidate
    for line_no, joined_text in _iter_cdsl_step_candidates(lines):
        # Task-tracked ID definitions/references use the same `pN` priority-token
        # shape as a CDSL phase token — exclude anything the ID scanner already
        # classifies as a definition or reference line.
        if _ID_DEF_RE.match(joined_text) or _ID_REF_RE.match(_normalize_reference_candidate(joined_text)):
            continue
        # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-placeholder
        if _CDSL_PLACEHOLDER_RE.search(joined_text):
            errors.append(error(
                "structure",
                f"CDSL step contains a placeholder or TODO marker (CO.6): `{joined_text}`",
                code=EC.CDSL_PLACEHOLDER,
                path=artifact_path,
                line=line_no,
            ))
        # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-cdsl-placeholder
        _validate_cdsl_step_candidate(
            line_no=line_no,
            step_text=joined_text,
            warnings=warnings,
            artifact_path=artifact_path,
            errors=errors,
        )
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-foreach-cdsl-candidate

    # scan_cdsl_instructions scans the whole document, not just Steps:/Transitions:
    # blocks — e.g. Supporting: bullets reuse the same well-formed CDSL line shape.
    # Restrict the duplicate-ID check to hits that actually fall inside a block.
    in_scope_lines = _cdsl_block_line_numbers(lines)
    scoped_hits = [hit for hit in cdsl_hits if int(hit.get("line", 0) or 0) in in_scope_lines]
    _validate_cdsl_duplicate_inst_ids(cdsl_hits=scoped_hits, artifact_path=artifact_path, errors=errors)


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings
def _validate_artifact_heading_phase(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    registered_systems: Optional[Iterable[str]],
    kind: str,
    constraints_path: Optional[Path],
    kit_id: Optional[str],
    policy: Optional[SeverityPolicy] = None,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], bool]:
    """Run heading validation; return its findings and whether ID checks may continue."""
    if not getattr(constraints, "headings", None):
        return [], [], True
    rep = validate_headings_contract(
        path=artifact_path,
        constraints=constraints,
        registered_systems=registered_systems,
        artifact_kind=kind,
        constraints_path=constraints_path,
        kit_id=kit_id,
    )
    heading_errors = list(rep.get("errors", []))
    heading_warnings = list(rep.get("warnings", []))
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-gate-on-errors
    # The gate counts error-severity findings, not findings. A heading rule the
    # project lowered to `warning` used to hide every TOC and identifier
    # finding in the file behind it — the reader saw one advisory note and no
    # sign that two whole phases had been skipped.
    #
    # Resolving here only decides whether to continue; the findings themselves
    # are settled once, at the end of the file's run, so nothing is dropped or
    # counted twice on the way.
    gate = apply_policy(policy, heading_errors + heading_warnings, kind=kind)
    return heading_errors, heading_warnings, not bool(gate.errors)
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-gate-on-errors
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings


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

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-format
def _validate_definition_hits(
    *,
    defs: Sequence[Dict[str, object]],
    rules: ArtifactDefinitionValidationRules,
    defs_by_kind: Dict[str, List[Dict[str, object]]],
    errors: List[Dict[str, object]],
) -> None:
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-defs-loop
    for hit in defs:
        hid = str(hit.get("id") or "").strip()
        if not hid:
            continue
        line = int(hit.get("line", 1) or 1)
        system = _match_system_from_id(hid, rules.systems_set, rules.all_kind_tokens)
        # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-match-system
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
        # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-match-system
        id_kind = _extract_kind_from_cpt(
            hid,
            system,
            rules.all_kind_tokens,
            rules.composite_nested_by_base,
        )
        if not id_kind:
            continue
        defs_by_kind.setdefault(id_kind, []).append(hit)

        # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-kind-hint
        if id_kind not in rules.allowed_defs:
            hint = _id_kind_hint(rules.constraint_by_kind.get(id_kind))
            errors.append(error(
                "constraints",
                (
                    f"`{hid}` uses kind `{id_kind}` not allowed in {rules.kind} artifact "
                    f"(allowed: {sorted(rules.allowed_defs)}){hint}"
                ),
                code=EC.ID_KIND_NOT_ALLOWED,
                path=rules.artifact_path,
                line=line,
                artifact_kind=rules.kind,
                id_kind=id_kind,
                id=hid,
                section="defined-id",
                allowed=sorted(rules.allowed_defs),
            ))
        # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-kind-hint

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
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-defs-loop
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-format

# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-required-check
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
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-validate-id-required-check


def _validate_artifact_identifier_phase(
    *,
    artifact_path: Path,
    constraints: ArtifactKindConstraints,
    kind: str,
    registered_systems: Optional[Iterable[str]],
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> None:
    from .document import scan_cpt_ids, scan_cdsl_instructions

    context = _build_artifact_identifier_phase_context(
        artifact_path=artifact_path,
        constraints=constraints,
        kind=kind,
        registered_systems=registered_systems,
        scan_cpt_ids=scan_cpt_ids,
    )
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-scan-cdsl
    cdsl_hits = scan_cdsl_instructions(artifact_path)
    _validate_unchecked_cdsl_steps(
        cdsl_hits=cdsl_hits,
        defs_by_id=context.defs_by_id,
        kind=kind,
        artifact_path=artifact_path,
        errors=errors,
    )
    _validate_cdsl_structure(
        artifact_path=artifact_path,
        cdsl_hits=cdsl_hits,
        errors=errors,
        warnings=warnings,
    )
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-scan-cdsl
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
    policy: Optional[SeverityPolicy] = None,
) -> Dict[str, object]:
    """Validate one artifact file against structural constraints."""
    errors: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []

    kind = str(artifact_kind).strip().upper()

    if constraints is None:
        return {"errors": errors, "warnings": warnings, "suppressed": 0, "refusals": []}
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-ids-entry

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings
    # Phase 1: headings contract
    heading_errors, heading_warnings, can_continue = _validate_artifact_heading_phase(
        artifact_path=artifact_path,
        constraints=constraints,
        registered_systems=registered_systems,
        kind=kind,
        constraints_path=constraints_path,
        kit_id=kit_id,
        policy=policy,
    )
    errors.extend(heading_errors)
    warnings.extend(heading_warnings)
    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-headings-fail
    # Stop here: IDs are validated only after outline contract is satisfied.
    if not can_continue:
        # @cpt-begin:cpt-studio-state-traceability-validation-report:p1:inst-fail
        # Policy still settles the findings on the way out: the phases that
        # were skipped produced nothing, but what the heading phase found is
        # reported at its configured severity like everything else.
        gated = _apply_artifact_policy(policy, kind, errors, warnings)
        return gated
        # @cpt-end:cpt-studio-state-traceability-validation-report:p1:inst-fail
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-if-headings-fail
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-headings

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-toc
    # Phase 1b: TOC validation (only when toc=true in constraints)
    if getattr(constraints, "toc", True):
        _validate_artifact_toc(
            artifact_path, errors, warnings, getattr(constraints, "toc_options", None))
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-check-toc

    _validate_artifact_identifier_phase(
        artifact_path=artifact_path,
        constraints=constraints,
        kind=kind,
        registered_systems=registered_systems,
        errors=errors,
        warnings=warnings,
    )

    # @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-return-structure
    # @cpt-begin:cpt-studio-state-traceability-validation-report:p1:inst-pass
    report = _apply_artifact_policy(policy, kind, errors, warnings)
    return report
    # @cpt-end:cpt-studio-state-traceability-validation-report:p1:inst-pass
    # @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-return-structure


# @cpt-begin:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-apply-artifact-policy
def _stamp_artifact_kind(kind: str, findings: Iterable[Dict[str, object]]) -> None:
    """Record the artifact kind on every finding from this file.

    Only heading findings carried it before. Without it a per-kind severity
    could never reach a TOC, CDSL or identifier finding, and the command-level
    pass would have no way to tell which kind a finding belongs to.
    """
    for finding in findings:
        finding.setdefault("artifact_kind", kind)


def _apply_artifact_policy(
    policy: Optional[SeverityPolicy],
    kind: str,
    errors: List[Dict[str, object]],
    warnings: List[Dict[str, object]],
) -> Dict[str, object]:
    """Stamp the kind, then settle severity for everything this file produced."""
    _stamp_artifact_kind(kind, errors)
    _stamp_artifact_kind(kind, warnings)
    outcome = apply_policy(policy, list(errors) + list(warnings), kind=kind)
    return {
        "errors": outcome.errors,
        "warnings": outcome.warnings,
        "suppressed": outcome.suppressed,
        "refusals": outcome.refusals,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-validate-structure:p1:inst-apply-artifact-policy

# @cpt-algo:cpt-studio-algo-traceability-validation-cross-validate:p1
# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-datamodel
def _id_kind_rule_metadata(ic: object) -> Dict[str, object]:
    """Return user-facing metadata for one ID kind rule."""
    return {
        "id_kind_name": str(getattr(ic, "name", "") or "").strip() or None,
        "id_kind_description": str(getattr(ic, "description", "") or "").strip() or None,
        "id_kind_template": str(getattr(ic, "template", "") or "").strip() or None,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-datamodel


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules
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
            (
                f"`{ctx.did}` (defined in {ctx.artifact_kind}) requires reference in "
                f"`{tk}` artifact but no `{tk}` artifact exists in scope"
            ),
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
            (
                f"`{ctx.did}` (defined in {ctx.artifact_kind}, kind `{ctx.id_kind}`) "
                f"is not referenced from any `{tk}` artifact"
            ),
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
        (
            f"Reference to `{ctx.did}` in `{tk}` artifact is under "
            f"{first.get('headings') or []} but must be under one of "
            f"{allowed_headings.sorted_ids}"
        ),
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
        (
            f"`{ctx.did}` is referenced in `{ctx.target_kind}` artifact but "
            f"references from `{ctx.target_kind}` are prohibited for "
            f"{ctx.artifact_kind} IDs"
        ),
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
                (
                    f"Reference to `{ctx.did}` in `{ctx.target_kind}` artifact has "
                    "task checkbox but task tracking is prohibited"
                ),
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
                (
                    f"Reference to `{ctx.did}` in `{ctx.target_kind}` artifact has "
                    "priority marker but priority is prohibited"
                ),
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-build-constraints-index
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
            (
                "No constraints defined for artifact kinds: "
                f"{sorted(missing_constraints_kinds)} — add them to constraints.toml"
            ),
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-build-constraints-index

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-collect-kind-tokens
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-collect-kind-tokens

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-external-ref
def _is_external_system_ref(cpt: str, systems_set: set[str]) -> bool:
    if not systems_set:
        return False
    if not cpt.lower().startswith("cpt-"):
        return False
    for system in systems_set:
        if cpt.lower().startswith(f"cpt-{system}-"):
            return False
    return True
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-external-ref

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-headings-info
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-headings-info


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-build-index

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-duplicate-defs
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
                artifact_kind=drow.get("artifact_kind"),
            ))
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-duplicate-defs

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-foreach-ref
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
        # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-if-no-def
        for row in rows:
            errors.append(error(
                "structure",
                f"Reference to `{rid}` has no matching definition in any artifact",
                code=EC.REF_NO_DEFINITION,
                path=row.get("artifact_path"),
                line=int(row.get("line", 1) or 1),
                id=rid,
                artifact_kind=row.get("artifact_kind"),
            ))
        # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-if-no-def
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-foreach-ref

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-foreach-checked-ref
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
            # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-if-ref-done-def-not
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
                    artifact_kind=row.get("artifact_kind"),
                ))
            # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-if-ref-done-def-not
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-foreach-checked-ref

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-foreach-checked-def
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
        # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-if-def-done-ref-not
        defs_with_task = [drow for drow in defs if bool(drow.get("has_task", False))]
        if defs_with_task and all(bool(drow.get("checked", False)) for drow in defs_with_task):
            for row in rows:
                if not bool(row.get("has_task", False)):
                    continue
                if bool(row.get("checked", False)):
                    continue
                errors.append(error(
                    "structure",
                    (
                        f"Definition of `{rid}` is checked [x] but reference in "
                        f"{row.get('artifact_kind', '?')} artifact is still unchecked"
                    ),
                    code=EC.DEF_DONE_REF_NOT_DONE,
                    path=row.get("artifact_path"),
                    line=int(row.get("line", 1) or 1),
                    id=rid,
                    artifact_kind=row.get("artifact_kind"),
                    def_artifact_kind=defs_with_task[0].get("artifact_kind"),
                ))
        # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-if-def-done-ref-not
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
                artifact_kind=row.get("artifact_kind"),
            ))
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-foreach-checked-def


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage
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
            (
                f"`{drow.get('id')}` (kind `{id_kind}`) in {artifact_kind} artifact "
                f"is under {drow.get('headings') or []} but must be under one of "
                f"{allowed_sorted}"
            ),
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules

# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules
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
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-cross-ref-coverage-rules


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
    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage
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
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate:p1:inst-enforce-coverage

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


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-entry-severity
def _parse_entry_severity(
    obj: Dict[str, object],
    label: str,
) -> Tuple[Optional[EntrySeverity], Optional[str]]:
    """Parse ``severity`` and ``locked`` from one constraint entry.

    ``locked`` without a ``severity`` is accepted and meaningful: it locks
    whatever the code's default or the kit's tables already say, which is how a
    kit protects a rule it is content to leave at the built-in severity.
    """
    errors: List[str] = []
    raw_severity = obj.get("severity")
    severity = (
        parse_severity_value(raw_severity, f"{label} field 'severity'", errors)
        if raw_severity is not None else None
    )
    if errors:
        return None, errors[0]
    locked = obj.get("locked", False)
    if not isinstance(locked, bool):
        return None, f"{label} field 'locked' must be boolean"
    return EntrySeverity(severity=severity, locked=locked), None
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-entry-severity


def _collect_heading_constraint_options(  # pylint: disable=too-many-locals
    obj: Dict[str, object],
) -> Tuple[Optional[Tuple[bool, Optional[bool], Optional[bool], EntrySeverity]], Optional[str]]:
    """Parse the boolean-only heading options and the entry's severity policy."""
    required_bool, req_err = _parse_required_bool_field(obj, "required")
    if req_err:
        return None, "Heading constraint field 'required' must be boolean"
    multiple, err = _parse_optional_bool_constraint(obj, "multiple", "Heading constraint")
    if err:
        return None, err
    numbered, err = _parse_optional_bool_constraint(obj, "numbered", "Heading constraint")
    if err:
        return None, err
    entry_severity, err = _parse_entry_severity(obj, "Heading constraint")
    if err or entry_severity is None:
        return None, err
    return (bool(required_bool), multiple, numbered, entry_severity), None


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
    kind_errors: List[str] = []
    where = f"[artifacts.{kind.strip().upper()}.validation]"
    validation = parse_kit_validation(
        raw.get("validation"),
        kind_errors,
        where=where,
        allow_kinds=False,
    )
    toc_options, toc_unknown = _parse_kind_toc_options(raw.get("validation"), where, kind_errors)
    order = _parse_kind_order(raw.get("order"), headings, kind_errors)
    if kind_errors:
        errors.extend(f"constraints for {kind}: {message}" for message in kind_errors)
        return None
    if toc_unknown:
        # Reported through the severity table's channel rather than a second
        # one: `validate-kits` already turns `unknown_keys` into a warning, and
        # a misspelled `max_levl` is the same failure as a misspelled rule code
        # — a setting its author believes is in force that nothing reads.
        validation = replace(
            validation, unknown_keys=tuple(sorted(validation.unknown_keys + tuple(toc_unknown))))

    return ArtifactKindConstraints(
        name=text_fields["name"],
        description=text_fields["description"],
        defined_id=defined_id,
        headings=headings,
        toc=toc_val,
        validation=validation,
        toc_options=toc_options,
        order=order,
    )


def _parse_kind_toc_options(
    validation_raw: object,
    where: str,
    errors: List[str],
) -> Tuple[TocOptions, List[str]]:
    """Parse ``[artifacts.<KIND>.validation.toc]`` into TOC options.

    An unreadable value is an error rather than an absent opinion: it leaves
    the check running to a depth nobody can predict, which is the same reason
    an unreadable severity fails the load instead of being skipped.
    """
    if not isinstance(validation_raw, dict):
        return TocOptions(), []
    raw = validation_raw.get("toc")
    if raw is None:
        return TocOptions(), []
    if not isinstance(raw, dict):
        errors.append(f"{where}.toc must be a table of TOC options")
        return TocOptions(), []
    unknown = [f"{where}.toc.{key}" for key in sorted(raw) if str(key) not in _TOC_OPTION_KEYS]
    return TocOptions(
        max_level=_parse_toc_option_int(raw, "max_level", where, errors, maximum=6),
        max_section_lines=_parse_toc_option_int(raw, "max_section_lines", where, errors),
    ), unknown


def _parse_toc_option_int(
    raw: Dict[str, object],
    name: str,
    where: str,
    errors: List[str],
    *,
    maximum: Optional[int] = None,
) -> Optional[int]:
    """Read one positive-integer TOC option, or None when it is not set."""
    if name not in raw:
        return None
    value = raw.get(name)
    # `bool` is an `int` in Python, so `max_level = true` would otherwise be
    # accepted as depth 1 — a document checked one level deep because someone
    # meant to switch something on.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        bound = f" between 1 and {maximum}" if maximum else " of 1 or more"
        errors.append(f"{where}.toc.{name} must be an integer{bound}")
        return None
    if maximum is not None and value > maximum:
        errors.append(f"{where}.toc.{name} must be an integer between 1 and {maximum}")
        return None
    return value


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-order
def _parse_kind_order(
    raw: object,
    headings: Optional[List[HeadingConstraint]],
    errors: List[str],
) -> Optional[HeadingOrder]:
    """Parse ``[artifacts.<KIND>] order`` into the section order for one kind.

    Read after the headings, because an order is a statement about heading ids
    and the ids only exist once ``_normalize_heading_ids`` has assigned them.
    An id nobody declared fails the load rather than being ignored: a typo in
    an order entry is a section the author believes is being ordered.

    ``order`` selects which of the declared sections are constrained; it cannot
    re-sequence them. That is not a simplification, it is what makes the rule
    enforceable: a section written out of order is found by the rescue pass
    precisely because it failed to match in declaration order, so an ``order``
    that ran against the declarations would be one nothing could check.
    """
    if raw is None:
        return None
    declared_ids = tuple(
        str(hc.id) for hc in (headings or []) if str(getattr(hc, "id", "") or "").strip()
    )
    if isinstance(raw, str):
        # Compared verbatim, not stripped. `kit-constraints.schema.json` pins
        # this value with `const`, so accepting a padded one would make the
        # published schema call invalid a file that loads — the one direction
        # of disagreement that matters, because it is the schema that teams
        # write their editors and preflight checks against. Entries in the list
        # form are still normalised, because they are lookup keys the schema
        # says nothing about.
        if raw != ORDER_DECLARED:
            errors.append(
                f"field 'order' must be a list of heading ids or \"{ORDER_DECLARED}\"")
            return None
        return HeadingOrder.from_sequence(declared_ids)
    if not isinstance(raw, list):
        errors.append(f"field 'order' must be a list of heading ids or \"{ORDER_DECLARED}\"")
        return None
    return _parse_order_ids(raw, declared_ids, errors)


def _parse_order_ids(
    raw: List[object],
    declared_ids: Tuple[str, ...],
    errors: List[str],
) -> Optional[HeadingOrder]:
    """Resolve one ``order`` list against the ids the kind declares."""
    known = {hid.lower(): hid for hid in declared_ids}
    seen: Set[str] = set()
    ids: List[str] = []
    for entry in raw:
        name = entry.strip() if isinstance(entry, str) else ""
        if not name:
            errors.append("field 'order' entries must be non-empty heading ids")
            return None
        key = name.lower()
        if key not in known:
            errors.append(f"field 'order' references unknown heading id '{name}'")
            return None
        if key in seen:
            errors.append(f"field 'order' lists heading id '{name}' more than once")
            return None
        seen.add(key)
        ids.append(known[key])
    return _order_following_declarations(ids, declared_ids, errors)
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-parse-order


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-order-follows-declarations
def _order_following_declarations(
    ids: List[str],
    declared_ids: Tuple[str, ...],
    errors: List[str],
) -> Optional[HeadingOrder]:
    """Refuse an order that puts the declared headings in a different sequence."""
    for position in range(1, len(ids)):
        earlier, later = ids[position - 1], ids[position]
        if declared_ids.index(later) < declared_ids.index(earlier):
            errors.append(
                f"field 'order' puts '{later}' after '{earlier}', but the headings are "
                f"declared the other way round — 'order' chooses which sections are "
                f"constrained, it does not re-sequence them; reorder the headings instead"
            )
            return None
    return HeadingOrder.from_sequence(ids)
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-order-follows-declarations


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


def _parse_heading_constraint(
    obj: object,
    *,
    pointer: Optional[str] = None,
) -> Tuple[Optional[HeadingConstraint], Optional[str]]:
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

    required_bool, multiple, numbered, entry_severity = options

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
        severity=entry_severity.severity,
        locked=entry_severity.locked,
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
    entry_severity, err = _parse_entry_severity(obj, "Constraint entry")
    if err or entry_severity is None:
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
            severity=entry_severity.severity,
            locked=entry_severity.locked,
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
            return (
                None,
                (
                    f"constraints for {kind} identifiers[{kkind}]: Constraint entry "
                    "kind does not match identifiers key"
                ),
            )
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
def parse_kit_constraints(
    data: object,
    validation: Optional[SeverityTables] = None,
) -> Tuple[Optional[KitConstraints], List[str]]:
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
    # The unknown-*kind* check deliberately does not happen here. A kit file is
    # parsed alone, and in a multi-kit project one kit may legitimately scope a
    # severity to a kind a companion kit declares. Only the loader that has
    # every kit in hand can tell that from a typo, so the check lives there.
    return KitConstraints(by_kind=out, validation=validation or SeverityTables()), []
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
        severity=_merge_entry_severity(base.severity, incoming.severity),
        locked=bool(base.locked or incoming.locked),
    )


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-merge-entry-severity
def _merge_entry_severity(base: Optional[str], incoming: Optional[str]) -> Optional[str]:
    """Take the stricter of two entry severities, matching how ``required`` merges.

    Both kits are authorities over an entry they both declare, so the merge
    that cannot quietly relax what one of them meant to enforce is the strict
    one. ``locked`` is a plain OR for the same reason.
    """
    if base is None:
        return incoming
    if incoming is None:
        return base
    return incoming if is_stricter(incoming, base) else base
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-merge-entry-severity


def _merge_artifact_constraints(
    base: ArtifactKindConstraints,
    incoming: ArtifactKindConstraints,
    kind: str,
    errors: List[str],
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
        validation=merge_severity_tables([base.validation, incoming.validation]),
        toc_options=_merge_toc_options(base.toc_options, incoming.toc_options),
        order=_merge_heading_order(base.order, incoming.order, kind, errors),
    )


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-merge-order
def _merge_heading_order(
    base: Optional[HeadingOrder],
    incoming: Optional[HeadingOrder],
    kind: str,
    errors: List[str],
) -> Optional[HeadingOrder]:
    """Add two kits' section orders together, refusing a contradiction.

    Two kits that bind one artifact kind are both authorities over it, so
    their orders add up — each constrains the ids it names and leaves the rest
    free. The sum is the union of what they stated, closed under transitivity:
    one kit's "a before c" and another's "c before b" together mean a before
    b, and a merge that did not say so would leave a relation both kits imply
    unenforced.

    What cannot be added up is a pair the two sequence in opposite directions.
    Keeping either kit's word would enforce an order the other kit's author
    would read as already satisfied, so that fails the load naming the pair,
    the same posture an unreadable severity takes.
    """
    if base is None:
        return incoming
    if incoming is None:
        return base
    merged = _order_closure(base.pairs | incoming.pairs)
    conflict = _first_order_conflict(merged)
    if conflict is not None:
        first, second = conflict
        errors.append(
            f"constraints for {kind}: field 'order' contradicts another kit's order — "
            f"'{first}' is required both before and after '{second}'"
        )
        return base
    return HeadingOrder(pairs=merged)


# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-merge-order


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-order-conflict
def _order_closure(pairs: FrozenSet[Tuple[str, str]]) -> FrozenSet[Tuple[str, str]]:
    """Every precedence that follows from the given ones."""
    after: Dict[str, Set[str]] = {}
    for earlier, later in pairs:
        after.setdefault(earlier, set()).add(later)
    closed: Set[Tuple[str, str]] = set()
    for start in after:
        reached: Set[str] = set()
        pending = list(after[start])
        while pending:
            node = pending.pop()
            if node in reached:
                continue
            reached.add(node)
            pending.extend(after.get(node, ()))
        closed.update((start, node) for node in reached)
    return frozenset(closed)


def _first_order_conflict(pairs: FrozenSet[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    """Name the first id pair the merged order requires in both directions.

    Run over the closure, so a cycle that only closes across three kits is one
    symmetric pair here rather than three relations nobody compared. Sorted,
    because which pair gets named must not depend on set iteration order.
    """
    for earlier, later in sorted(pairs):
        if earlier != later and (later, earlier) in pairs:
            return earlier, later
    return None
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-order-conflict


def _merge_toc_options(base: TocOptions, incoming: TocOptions) -> TocOptions:
    """Combine two kits' TOC options for one kind, strictest-wins.

    The same rule `required` and `severity` merge by, read through what each
    option does: a deeper `max_level` puts more headings under the
    completeness check, and a smaller `max_section_lines` flags more sections.
    A kit with no opinion never loosens one that has one.
    """
    return TocOptions(
        max_level=_strictest_toc_option(base.max_level, incoming.max_level, max),
        max_section_lines=_strictest_toc_option(
            base.max_section_lines, incoming.max_section_lines, min),
    )


def _strictest_toc_option(
    base: Optional[int],
    incoming: Optional[int],
    stricter: Callable[[int, int], int],
) -> Optional[int]:
    """Pick the stricter of two optional bounds, where None is "no opinion"."""
    if base is None:
        return incoming
    if incoming is None:
        return base
    return stricter(base, incoming)


def merge_kit_constraints_all_of(
    constraints: Sequence[KitConstraints],
    errors: Optional[List[str]] = None,
) -> Optional[KitConstraints]:
    """Merge constraints sequentially using allOf-style additive semantics.

    Returns None when the merge cannot be performed at all — two kits ordering
    one pair of sections in opposite directions. That is unconditional, not a
    courtesy to callers who pass ``errors``: a partly-merged model carries one
    arbitrary reading of the contradiction and looks exactly like a successful
    merge, so handing it back to a caller that did not ask for the messages
    would make the silence the caller's problem rather than this function's.

    ``errors``, when given, collects those messages as well, so a caller that
    wants to say *why* the load failed does not have to re-derive it.
    """
    merge_errors: List[str] = []
    by_kind: Dict[str, ArtifactKindConstraints] = {}
    for kit_constraints in constraints:
        for kind, incoming in (kit_constraints.by_kind or {}).items():
            normalized = str(kind).strip().upper()
            if not normalized:
                continue
            if normalized in by_kind:
                by_kind[normalized] = _merge_artifact_constraints(
                    by_kind[normalized], incoming, normalized, merge_errors)
            else:
                by_kind[normalized] = incoming
    if errors is not None:
        errors.extend(merge_errors)
    if not by_kind or merge_errors:
        return None
    return KitConstraints(
        by_kind=by_kind,
        validation=merge_severity_tables([_kit_validation_tables(kc) for kc in constraints]),
    )


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-build-policy
def collect_entry_severities(
    kit_constraints: Iterable[KitConstraints],
) -> Dict[str, Dict[EntryKey, EntrySeverity]]:
    """Index every entry that declares a severity or a lock, by kind and entry key.

    Heading entries are keyed by heading id and identifier entries by ID kind —
    the two fields findings already carry, so a finding can be matched back to
    the entry that produced it without a new key having to be threaded through
    every emission site. The key carries which of the two it is, because the
    same string can legitimately name both a heading and an ID kind and one
    must not inherit the other's severity or lock.
    """
    entries: Dict[str, Dict[EntryKey, EntrySeverity]] = {}
    for kit in kit_constraints:
        for kind, kind_constraints in (getattr(kit, "by_kind", None) or {}).items():
            normalized = str(kind).strip().upper()
            for heading in getattr(kind_constraints, "headings", None) or []:
                _record_entry(
                    entries,
                    normalized,
                    entry_key(ENTRY_HEADING, getattr(heading, "id", None)),
                    getattr(heading, "severity", None),
                    bool(getattr(heading, "locked", False)),
                )
            for identifier in getattr(kind_constraints, "defined_id", None) or []:
                _record_entry(
                    entries,
                    normalized,
                    entry_key(ENTRY_IDENTIFIER, getattr(identifier, "kind", None)),
                    getattr(identifier, "severity", None),
                    bool(getattr(identifier, "locked", False)),
                )
    return entries


def _kit_validation_tables(kit: object) -> SeverityTables:
    """Read a kit's own ``[validation]`` table, tolerating partial stand-ins.

    Callers hand this whatever their context loaded, including the stripped-down
    objects the command tests build, so a missing table means "declares
    nothing" rather than an attribute error.
    """
    table = getattr(kit, "validation", None)
    return table if isinstance(table, SeverityTables) else SeverityTables()


def _record_entry(
    entries: Dict[str, Dict[EntryKey, EntrySeverity]],
    kind: str,
    key: Optional[EntryKey],
    severity: Optional[str],
    locked: bool,
) -> None:
    if key is None or (severity is None and not locked):
        return
    by_entry = entries.setdefault(kind, {})
    existing = by_entry.get(key)
    if existing is None:
        by_entry[key] = EntrySeverity(severity=severity, locked=locked)
        return
    by_entry[key] = EntrySeverity(
        severity=_merge_entry_severity(existing.severity, severity),
        locked=bool(existing.locked or locked),
    )


def _kit_severity_layer(kit: object) -> SeverityTables:
    """One kit's complete severity opinion: whole-kit table plus kind-scoped ones.

    Assembled as a single layer so the merge can compare each kit's *effective*
    value for a kind against every other kit's. Contributing the two tables as
    separate layers, or folding the kind-scoped ones in afterwards, both lose
    the distinction between "this kit's own per-kind override" — which wins by
    specificity — and "another kit's opinion", which wins by strictness.
    """
    whole_kit = _kit_validation_tables(kit)
    by_kind: Dict[str, Dict[str, str]] = {
        kind: dict(table) for kind, table in whole_kit.by_kind.items()
    }
    unknown = list(whole_kit.unknown_keys)
    for kind, kind_constraints in (getattr(kit, "by_kind", None) or {}).items():
        scoped = _kit_validation_tables(kind_constraints)
        unknown.extend(scoped.unknown_keys)
        if scoped.by_code:
            by_kind.setdefault(str(kind).strip().upper(), {}).update(scoped.by_code)
    return SeverityTables(
        by_code=dict(whole_kit.by_code),
        by_kind=by_kind,
        unknown_keys=tuple(sorted(set(unknown))),
    )


def build_severity_policy(
    kit_constraints: Iterable[KitConstraints],
    project: Optional[SeverityTables] = None,
) -> SeverityPolicy:
    """Assemble the policy from every loaded kit plus the project's own table."""
    loaded = list(kit_constraints)
    return SeverityPolicy(
        kit=merge_severity_tables([_kit_severity_layer(kit) for kit in loaded]),
        project=project or SeverityTables(),
        entries=collect_entry_severities(loaded),
    )
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-build-policy
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

    # @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-lift-validation
    # Lifted before the unwrap below. In the legacy unwrapped layout the kinds
    # sit at the top level, so a `[validation]` table left in place would be
    # parsed as an artifact kind named VALIDATION and fail the whole file.
    validation_errors: List[str] = []
    validation = parse_kit_validation(data.get("validation"), validation_errors)
    if validation_errors:
        return None, [f"{path.name}: {message}" for message in validation_errors]
    data = {key: value for key, value in data.items() if key != "validation"}
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-lift-validation

    # TOML wraps kinds under "artifacts" key
    artifacts_data = data.get("artifacts", data)
    constraints, errs = parse_kit_constraints(artifacts_data, validation)
    if errs:
        return None, errs
    return constraints, []
    # @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-load-toml


# @cpt-begin:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-load-toml
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
    merged = merge_kit_constraints_all_of(loaded, errors)
    if errors:
        return None, errors
    return merged, []


def load_constraints_toml(kit_root: Path) -> Tuple[Optional[KitConstraints], List[str]]:
    """Load constraints toml."""
    return load_constraints_file((kit_root / "constraints.toml").resolve())
# @cpt-end:cpt-studio-algo-traceability-validation-load-constraints:p1:inst-load-toml


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-headings-datamodel
__all__ = [
    "ReferenceRule",
    "HeadingConstraint",
    "IdConstraint",
    "ArtifactKindConstraints",
    "HeadingOrder",
    "KitConstraints",
    "TocOptions",
    "ArtifactRecord",
    "ParsedStudioId",
    "build_severity_policy",
    "collect_entry_severities",
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


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-scan-headings
def _parse_heading_numbering(
    raw_title: str,
    path: Path,
) -> Tuple[bool, str, Optional[str], Optional[List[int]]]:
    """Extract numbering metadata from one heading title."""
    numbered = False
    title_text = raw_title
    number_prefix: Optional[str] = None
    number_parts: Optional[List[int]] = None
    match = _HEADING_NUMBER_PREFIX_RE.match(raw_title)
    if not match:
        return numbered, title_text, number_prefix, number_parts

    numbered = True
    number_prefix = str(match.group("prefix") or "").strip() or None
    if number_prefix:
        try:
            number_parts = [int(x) for x in number_prefix.split(".") if x.strip()]
        except ValueError as exc:
            logger.warning(
                "Invalid heading number prefix %r in %s: %s",
                number_prefix,
                path,
                exc,
            )
            number_parts = None
    title_text = str(match.group("title") or "").strip()
    return numbered, title_text, number_prefix, number_parts


def _scan_headings(path: Path) -> List[Dict[str, object]]:
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
        numbered, title_text, number_prefix, number_parts = _parse_heading_numbering(raw_title, path)
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


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-numbering-fn
def _check_heading_numbering_sequence(
    *,
    headings: Sequence[Dict[str, object]],
    artifact_kind: str,
    path: Path,
    errors: List[Dict[str, object]],
) -> None:
    last_child_by_key: Dict[Tuple[int, Tuple[Tuple[int, ...], int]], int] = {}
    last_prefix_by_key: Dict[Tuple[int, Tuple[Tuple[int, ...], int]], str] = {}

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-numbering
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
                    (
                        f"Heading `{prefix}` in {artifact_kind} artifact is not "
                        f"consecutive — expected `{expected_prefix}` after "
                        f"`{last_prefix_by_key.get(key)}`"
                    ),
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
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-numbering
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-numbering-fn


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
    except re.error as exc:
        logger.warning("Invalid heading match regex %r: %s", pattern_s, exc)
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


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-scope
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
    claimed: Set[int],
) -> Tuple[List[Dict[str, object]], int, int]:
    """Find the first consecutive run of headings no other constraint holds.

    ``claimed`` is what keeps the forward walk and the rescue pass from both
    standing on one section. The forward walk cannot reach a claimed heading
    today — every claim lies behind the cursor — but the rule belongs here
    rather than in an invariant three call sites have to keep true.
    """
    match_idx = scope_start
    while match_idx < scope_end and (
        match_idx in claimed
        or not _match_heading_constraint(headings[match_idx], heading_constraint)
    ):
        match_idx += 1
    if match_idx >= scope_end:
        return [], scope_start, scope_start, []
    matches = [headings[match_idx]]
    next_idx = match_idx + 1
    if heading_constraint.multiple is not False:
        while (
            next_idx < scope_end
            and next_idx not in claimed
            and _match_heading_constraint(headings[next_idx], heading_constraint)
        ):
            matches.append(headings[next_idx])
            next_idx += 1
    return matches, match_idx, next_idx, _matches_in_scope(
        headings=headings,
        heading_constraint=heading_constraint,
        scope_start=scope_start,
        scope_end=scope_end,
        claimed=claimed,
    )


def _matches_in_scope(
    *,
    headings: Sequence[Dict[str, object]],
    heading_constraint: HeadingConstraint,
    scope_start: int,
    scope_end: int,
    claimed: Set[int],
) -> List[Tuple[int, Dict[str, object]]]:
    """Every unclaimed heading anywhere in this scope the constraint matches.

    Deliberately not the same list as ``matches``. The run above stops at the
    first heading that does not match, because ``multiple = false`` has always
    meant "not twice in a row" and widening it would report duplicates in
    documents that pass today, including this repository's own DESIGN under
    the shipped kit's repeated component entries.

    The two rules that read this list ask about the section rather than about
    the run. "At least two" asks whether the section repeats within its scope
    at all, and a section that repeats almost always carries its own
    subsections between the copies. ``numbered`` is the spec's "each matching
    heading", which is every copy — checking only the first run left the
    second copy of a repeated section unvalidated whenever anything sat
    between them.
    """
    return [
        (idx, headings[idx]) for idx in range(scope_start, scope_end)
        if idx not in claimed and _match_heading_constraint(headings[idx], heading_constraint)
    ]
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-scope


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-hc-helpers
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
        (
            f"Required level-{int(heading_constraint.level)} heading "
            f"(pattern: `{heading_constraint.pattern}`) missing in "
            f"{heading_ctx.artifact_kind} artifact{between_s}{desc_s}"
        ),
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
        (
            f"Heading `{ctx.heading_constraint.pattern}` "
            f"(level {int(ctx.heading_constraint.level)}) appears {match_count} "
            f"times in {ctx.artifact_kind} artifact but only 1 is allowed{desc_s}"
        ),
        code=EC.HEADING_PROHIBITS_MULTIPLE,
        path=ctx.path,
        line=line,
        artifact_kind=ctx.artifact_kind,
        heading_level=int(ctx.heading_constraint.level),
        heading_pattern=ctx.heading_constraint.pattern,
        **_heading_context_fields(ctx),
    ))


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-requires-multiple
def _append_requires_multiple_heading_error(
    *,
    heading_ctx: HeadingValidationContext,
    heading_constraint: HeadingConstraint,
    idx: int,
    line: int,
) -> None:
    """Report a section the kit expects to repeat that appears exactly once.

    Off by default: "at least two" is true of a kit's repeated-block sections
    and false of every document with a single flow, a single state or a single
    acceptance criterion, so a kit opts in per kind instead of inheriting it.
    """
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
        (
            f"Heading `{ctx.heading_constraint.pattern}` "
            f"(level {int(ctx.heading_constraint.level)}) appears once in "
            f"{ctx.artifact_kind} artifact but at least 2 are required{desc_s}"
        ),
        code=EC.HEADING_REQUIRES_MULTIPLE,
        path=ctx.path,
        line=line,
        artifact_kind=ctx.artifact_kind,
        heading_level=int(ctx.heading_constraint.level),
        heading_pattern=ctx.heading_constraint.pattern,
        **_heading_context_fields(ctx),
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-requires-multiple


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-order-violation
def _ancestor_heading_indices(
    headings: Sequence[Dict[str, object]],
    idx: int,
) -> List[int]:
    """Every heading that contains ``headings[idx]``, nearest first.

    The whole chain, not the nearest one: a section travels with the ancestor
    that moved, however many unconstrained headings sit between them. Checking
    only the immediate parent broke the chain at the first heading no
    constraint names, which is the common shape — a displaced section with a
    plain subheading over its constrained detail.
    """
    ancestors: List[int] = []
    level = int(headings[idx].get("level", 0) or 0)
    for back in range(idx - 1, -1, -1):
        back_level = int(headings[back].get("level", 0) or 0)
        if back_level < level:
            ancestors.append(back)
            level = back_level
    return ancestors


def _matched_heading_info(
    heading_ctx: HeadingValidationContext,
    headings: Sequence[Dict[str, object]],
    matched: Tuple[int, str],
) -> Dict[str, object]:
    """Describe one already-matched section, by constraint and by line."""
    other_idx, other_id = matched
    info = _heading_constraint_info(heading_ctx.by_id.get(other_id)) or {"id": other_id}
    return {**info, "line": int(headings[other_idx].get("line", 1) or 1)}


# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-order-violation


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-order-offender
def _order_offender(
    heading_ctx: HeadingValidationContext,
    headings: Sequence[Dict[str, object]],
    order: HeadingOrder,
    heading_id: str,
    match_idx: int,
) -> Optional[Dict[str, object]]:
    """The nearest matched section this one has ended up in front of.

    Nearest rather than all of them, because one displaced section is one
    finding; naming the section it has to clear makes the fix a single move
    rather than a list to reconcile.

    Only this direction exists. Constraints are walked in declaration order and
    an ``order`` follows the declarations, so every section related to this one
    that has already been matched is one this one is supposed to follow — there
    is no already-matched section it was supposed to precede.
    """
    offenders = [
        (other_idx, other_id)
        for other_id, other_idx in heading_ctx.matched_idx_by_id.items()
        if other_idx > match_idx and order.relates(other_id, heading_id)
    ]
    if not offenders:
        return None
    return _matched_heading_info(heading_ctx, headings, min(offenders))


# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-order-offender


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-order-violation
def _append_order_violation_error(
    *,
    heading_ctx: HeadingValidationContext,
    headings: Sequence[Dict[str, object]],
    heading_constraint: HeadingConstraint,
    idx: int,
    match_idx: int,
) -> None:
    """Report a section that is present but sits on the wrong side of another.

    Only a declared ``order`` can be violated. Without one the rescue stays
    silent: the kit never said where the section goes, so nothing in the
    document contradicts it — and this is the only place that decides so, which
    is why ``_order_offender`` takes the order as an argument rather than
    reading it back off the context and defending itself against ``None``.
    """
    order = heading_ctx.order
    if order is None:
        return
    ancestors = _ancestor_heading_indices(headings, match_idx)
    if any(ancestor in heading_ctx.reported_idx for ancestor in ancestors):
        heading_ctx.reported_idx.add(match_idx)
        return
    heading_id = str(getattr(heading_constraint, "id", "") or "")
    after = _order_offender(heading_ctx, headings, order, heading_id, match_idx)
    if after is None:
        return
    heading_ctx.reported_idx.add(match_idx)
    ctx = _heading_context(
        heading_constraint=heading_constraint,
        idx=idx,
        artifact_kind=heading_ctx.artifact_kind,
        path=heading_ctx.path,
        constraints_path=heading_ctx.constraints_path,
        kit_id=heading_ctx.kit_id,
    )
    line = int(headings[match_idx].get("line", 1) or 1)
    heading_ctx.errors.append(error(
        "constraints",
        (
            f"Section `{heading_id}` (line {line}) in {ctx.artifact_kind} artifact "
            f"must come after `{after['id']}` (line {after['line']})"
        ),
        code=EC.HEADING_ORDER_VIOLATION,
        path=ctx.path,
        line=line,
        artifact_kind=ctx.artifact_kind,
        heading_level=int(ctx.heading_constraint.level),
        heading_pattern=ctx.heading_constraint.pattern,
        heading_line=line,
        expected_after=after,
        **_heading_context_fields(ctx),
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-order-violation


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
        (
            f"Heading `{heading_constraint.pattern}` "
            f"(level {int(heading_constraint.level)}) in {artifact_kind} artifact: "
            "numbering "
            f"{'is required but missing' if heading_constraint.numbered is True else 'is prohibited but present'}"
            f"{desc_s}"
        ),
        code=EC.HEADING_NUMBERING_MISMATCH,
        path=path,
        line=int(heading.get("line", 1) or 1),
        artifact_kind=artifact_kind,
        heading_level=int(heading_constraint.level),
        heading_pattern=heading_constraint.pattern,
        numbered=heading_constraint.numbered,
        **_heading_constraint_source_fields(heading_constraint, idx, constraints_path, kit_id),
    ))
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-hc-helpers


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-fn
def _validate_heading_matches(
    *,
    headings: Sequence[Dict[str, object]],
    heading_ctx: HeadingValidationContext,
) -> None:
    cursor = 0
    last_match_idx_by_level: Dict[int, int] = {}
    heading_constraints = heading_ctx.heading_constraints

    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings
    # @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-loop
    for idx, heading_constraint in enumerate(heading_constraints):
        cursor = _validate_single_heading_match(
            heading_ctx=heading_ctx,
            headings=headings,
            heading_constraint=heading_constraint,
            idx=idx,
            cursor=cursor,
            last_match_idx_by_level=last_match_idx_by_level,
        )
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-loop
    # @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-fn

# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-fn
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
    matches, match_idx, next_idx, scope_matches = _find_heading_matches_in_scope(
        headings=headings,
        heading_constraint=heading_constraint,
        scope_start=scope_start,
        scope_end=scope_end,
        claimed=heading_ctx.claimed,
    )
    if not matches:
        rescued = _rescue_unmatched_heading(
            heading_ctx=heading_ctx,
            headings=headings,
            heading_constraint=heading_constraint,
            idx=idx,
            last_match_idx_by_level=last_match_idx_by_level,
        )
        if rescued is None:
            return cursor
        matches, match_idx, next_idx, scope_matches = rescued
    _claim_heading_matches(
        heading_ctx=heading_ctx,
        heading_constraint=heading_constraint,
        match_idx=match_idx,
        match_count=len(matches),
    )
    # Never backwards: a rescued section sits behind the cursor, and moving the
    # cursor back to it would re-offer sections later constraints have already
    # been measured against.
    cursor = max(cursor, _update_heading_match_state(
        heading_constraint=heading_constraint,
        hc_level=hc_level,
        match_idx=match_idx,
        next_idx=next_idx,
        last_match_idx_by_level=last_match_idx_by_level,
    ))
    _check_matched_heading_rules(
        heading_ctx=heading_ctx,
        heading_constraint=heading_constraint,
        idx=idx,
        matches=matches,
        scope_matches=scope_matches,
    )
    return cursor


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-rescue-unmatched
def _rescue_unmatched_heading(
    *,
    heading_ctx: HeadingValidationContext,
    headings: Sequence[Dict[str, object]],
    heading_constraint: HeadingConstraint,
    idx: int,
    last_match_idx_by_level: Dict[int, int],
) -> Optional[Tuple[List[Dict[str, object]], int, int, List[Tuple[int, Dict[str, object]]]]]:
    """Look behind the cursor for a section that is present but out of place.

    The forward-only cursor cannot tell "this section is missing" from "this
    section was written earlier than the kit declares it", and reported both as
    `heading-missing`. Searching the constraint's parent range from the start
    separates the two: a section found here exists, so it is measured by the
    same `multiple` and `numbered` rules as any other match, and only a kit
    that declared an `order` gets a finding about where it sits.

    Returns the rescued run, or None after reporting the genuinely missing
    section (or staying silent for an optional one, as before).
    """
    _, scope_start, scope_end = _match_scope_for_constraint(
        headings=headings,
        heading_constraint=heading_constraint,
        cursor=0,
        last_match_idx_by_level=last_match_idx_by_level,
    )
    matches, match_idx, next_idx, scope_matches = _find_heading_matches_in_scope(
        headings=headings,
        heading_constraint=heading_constraint,
        scope_start=scope_start,
        scope_end=scope_end,
        claimed=heading_ctx.claimed,
    )
    if not matches:
        if heading_constraint.required:
            _append_missing_heading_error(
                heading_ctx=heading_ctx,
                heading_constraint=heading_constraint,
                idx=idx,
            )
        return None
    _append_order_violation_error(
        heading_ctx=heading_ctx,
        headings=headings,
        heading_constraint=heading_constraint,
        idx=idx,
        match_idx=match_idx,
    )
    return matches, match_idx, next_idx, scope_matches


# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-rescue-unmatched


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-claim-matches
def _claim_heading_matches(
    *,
    heading_ctx: HeadingValidationContext,
    heading_constraint: HeadingConstraint,
    match_idx: int,
    match_count: int,
) -> None:
    """Record which headings this constraint matched, and where it landed."""
    for offset in range(match_count):
        heading_ctx.claimed.add(match_idx + offset)
    heading_id = str(getattr(heading_constraint, "id", "") or "").strip()
    if heading_id:
        heading_ctx.matched_idx_by_id[heading_id] = match_idx
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-claim-matches


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-match-rules
def _check_matched_heading_rules(
    *,
    heading_ctx: HeadingValidationContext,
    heading_constraint: HeadingConstraint,
    idx: int,
    matches: List[Dict[str, object]],
    scope_matches: List[Tuple[int, Dict[str, object]]],
) -> None:
    """Apply the count and numbering rules to one constraint's matched run."""
    if heading_constraint.multiple is False and len(matches) > 1:
        _append_multiple_heading_error(
            heading_ctx=heading_ctx,
            heading_constraint=heading_constraint,
            idx=idx,
            match_count=len(matches),
            line=int(matches[1].get("line", 1) or 1),
        )
    elif heading_constraint.multiple is True and len(scope_matches) < 2:
        _append_requires_multiple_heading_error(
            heading_ctx=heading_ctx,
            heading_constraint=heading_constraint,
            idx=idx,
            line=int(matches[0].get("line", 1) or 1),
        )
    if heading_constraint.numbered is None:
        return
    want_numbered = heading_constraint.numbered is True
    for scope_idx, match in scope_matches:
        # Once per heading, by whichever constraint reaches it first.
        # Numbering is a property of the section, and two constraints whose
        # patterns overlap both see a heading only one of them will claim —
        # without this, that heading is reported twice for one defect.
        if scope_idx in heading_ctx.numbering_judged:
            continue
        heading_ctx.numbering_judged.add(scope_idx)
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
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-check-match-rules


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
# @cpt-end:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-match-headings-fn


# @cpt-begin:cpt-studio-algo-traceability-validation-headings-contract:p1:inst-validate-headings-entry
def validate_headings_contract(
    *,
    path: Path,
    constraints: ArtifactKindConstraints,
    registered_systems: Optional[Iterable[str]],  # pylint: disable=unused-argument
    # public API; reserved for system-scoped heading validation
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

    _check_heading_numbering_sequence(
        headings=headings,
        artifact_kind=str(artifact_kind).strip().upper(),
        path=path,
        errors=errors,
    )

    _validate_heading_matches(
        headings=headings,
        heading_ctx=HeadingValidationContext(
            heading_constraints=heading_constraints,
            by_id=by_id,
            artifact_kind=str(artifact_kind).strip().upper(),
            path=path,
            constraints_path=constraints_path,
            kit_id=kit_id,
            errors=errors,
            order=getattr(constraints, "order", None),
        ),
    )
    return {"errors": errors, "warnings": warnings}
