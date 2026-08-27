"""Codebase parsing/validation for Studio traceability markers.

This module provides a deterministic, stdlib-only parser for code files with
Studio traceability markers. Similar interface to template.py but for code.

Marker types supported:
- Scope markers: @cpt-{kind}:{id}:p{N}
- Block markers: @cpt-begin:{id}:p{N}:inst-{local} / @cpt-end:...

Key difference from artifacts: code can only REFERENCE IDs (not define them).
IDs in code that don't exist in artifacts = validation FAIL.
"""
# @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-code-datamodel
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from . import error_codes as EC

logger = logging.getLogger(__name__)


def _warn_codebase(message: str) -> None:
    logger.warning("codebase: %s", message)

# Scope marker: @cpt-{kind}:{full-id}:p{N}
# {kind} is kit-defined; parser accepts any lowercase slug.
_SCOPE_MARKER_RE = re.compile(
    r"@cpt-(?!begin:)(?!end:)(?P<kind>[a-z][a-z0-9-]*):(?P<id>cpt-[a-z0-9][a-z0-9-]+):(?:p|ph-)(?P<phase>\d+)"
)

# Block begin marker: @cpt-begin:{full-id}:ph-{N}:inst-{local}
_BLOCK_BEGIN_RE = re.compile(
    r"@cpt-begin:(?P<id>cpt-[a-z0-9][a-z0-9-]+):(?:p|ph-)(?P<phase>\d+):inst-(?P<inst>[a-z0-9-]+)"
)

# Block end marker: @cpt-end:{full-id}:ph-{N}:inst-{local}
_BLOCK_END_RE = re.compile(
    r"@cpt-end:(?P<id>cpt-[a-z0-9][a-z0-9-]+):(?:p|ph-)(?P<phase>\d+):inst-(?P<inst>[a-z0-9-]+)"
)

# Generic SID reference (backticked or in markers)
_SID_RE = re.compile(r"cpt-[a-z0-9][a-z0-9-]+")

def error(
    kind: str,
    message: str,
    *,
    path: Path,
    line: int = 1,
    code: Optional[str] = None,
    **extra,
) -> Dict[str, object]:
    """Uniform error factory for code validation."""
    path_s = str(path)
    out: Dict[str, object] = {
        "type": kind,
        "message": message,
        "line": int(line),
        "path": path_s,
    }
    if code:
        out["code"] = code
    out["location"] = f"{path_s}:{int(line)}" if (path_s and not path_s.startswith("<")) else path_s
    extra = {k: v for k, v in extra.items() if v is not None}
    out.update(extra)
    return out

@dataclass(frozen=True)
class ScopeMarker:
    """A scope marker like @cpt-flow:{id}:p{N}."""
    kind: str  # flow, algo, state, req, test
    id: str  # full Studio ID
    phase: int
    line: int
    raw: str  # original line content

@dataclass(frozen=True)
class BlockMarker:
    """A block marker pair @cpt-begin/end:{id}:p{N}:inst-{local}."""
    id: str  # full Studio ID
    phase: int
    inst: str  # instruction slug
    start_line: int
    end_line: int
    content: Tuple[str, ...]  # lines between begin/end

@dataclass(frozen=True)
class CodeReference:
    """A reference to an Studio ID found in code."""
    id: str
    line: int
    kind: Optional[str]  # flow, algo, state, req, test, or None for generic
    phase: Optional[int]
    inst: Optional[str]
    marker_type: str  # "scope", "block", "inline"

@dataclass
class CodeFile:
    """Parsed code file with Studio traceability markers.

    Similar interface to Artifact from template.py but for code files.
    Code can only REFERENCE IDs (not define them).
    """
    path: Path
    scope_markers: List[ScopeMarker] = field(default_factory=list)
    block_markers: List[BlockMarker] = field(default_factory=list)
    references: List[CodeReference] = field(default_factory=list)
    _errors: List[Dict[str, object]] = field(default_factory=list)
    _loaded: bool = False

    @classmethod
    def from_path(cls, code_path: Path) -> Tuple[Optional["CodeFile"], List[Dict[str, object]]]:
        """Load and parse a code file, returning (CodeFile, errors)."""
        cf = cls(path=code_path)
        errs = cf.load()
        if errs:
            return None, errs
        return cf, []
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-code-datamodel

    def load(self) -> List[Dict[str, object]]:
        """Load and parse the code file."""
        if self._loaded:
            return list(self._errors)

        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-read-code
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            err = error("file", f"Failed to read `{self.path}`: {e}", code=EC.FILE_READ_ERROR, path=self.path, line=1)
            self._errors.append(err)
            return [err]

        lines = text.splitlines()
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-read-code
        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-return-code
        self._parse_markers(lines)
        self._loaded = True
        return list(self._errors)
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-return-code

    # @cpt-algo:cpt-studio-algo-traceability-validation-scan-code:p1
    def _parse_markers(self, lines: List[str]) -> None:
        """Parse all Studio markers from code lines."""
        # Track open block markers for pairing
        open_blocks: Dict[str, Tuple[int, str, int, str]] = {}  # key -> (line, id, phase, inst)

        for idx, line in enumerate(lines):
            line_no = idx + 1

            # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-match-scope
            # Check for scope markers
            for m in _SCOPE_MARKER_RE.finditer(line):
                marker = ScopeMarker(
                    kind=m.group("kind"),
                    id=m.group("id"),
                    phase=int(m.group("phase")),
                    line=line_no,
                    raw=line,
                )
                self.scope_markers.append(marker)
                self._append_scope_reference(m, line_no)
            # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-match-scope

            # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-match-begin
            # Check for block begin markers
            for m in _BLOCK_BEGIN_RE.finditer(line):
                key = f"{m.group('id')}:{m.group('phase')}:{m.group('inst')}"
                if key in open_blocks:
                    self._errors.append(
                        error(
                            "marker",
                            f"Duplicate @cpt-begin for `{m.group('id')}` inst "
                            f"`{m.group('inst')}` at line {line_no} in "
                            f"`{self.path.name}` — previous @cpt-begin not closed",
                            code=EC.MARKER_DUP_BEGIN,
                            path=self.path,
                            line=line_no,
                            id=m.group("id"),
                            inst=m.group("inst"),
                        )
                    )
                else:
                    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-push-block
                    open_blocks[key] = (line_no, m.group("id"), int(m.group("phase")), m.group("inst"))
                    # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-push-block
            # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-match-begin

            # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-match-end
            # Check for block end markers
            for m in _BLOCK_END_RE.finditer(line):
                key = f"{m.group('id')}:{m.group('phase')}:{m.group('inst')}"
                # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-pop-block
                # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-if-mismatch
                if key not in open_blocks:
                    self._errors.append(
                        error(
                            "marker",
                            f"@cpt-end for `{m.group('id')}` inst "
                            f"`{m.group('inst')}` at line {line_no} in "
                            f"`{self.path.name}` has no matching @cpt-begin",
                            code=EC.MARKER_END_NO_BEGIN,
                            path=self.path,
                            line=line_no,
                            id=m.group("id"),
                            inst=m.group("inst"),
                        )
                    )
                else:
                    start_line, cpt, phase, inst = open_blocks.pop(key)
                    content = tuple(lines[start_line:idx])  # lines between begin/end

                    if not content or all(not ln.strip() for ln in content):
                        self._errors.append(
                            error(
                                "marker",
                                f"Empty block for `{cpt}` inst `{inst}` "
                                f"(lines {start_line}–{line_no}) in "
                                f"`{self.path.name}` — no code between markers",
                                code=EC.MARKER_EMPTY_BLOCK,
                                path=self.path,
                                line=start_line,
                                id=cpt,
                                inst=inst,
                            )
                        )

                    block = BlockMarker(
                        id=cpt,
                        phase=phase,
                        inst=inst,
                        start_line=start_line,
                        end_line=line_no,
                        content=content,
                    )
                    self.block_markers.append(block)
                    self.references.append(CodeReference(
                        id=cpt,
                        line=start_line,
                        kind=None,
                        phase=phase,
                        inst=inst,
                        marker_type="block",
                    ))
                # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-if-mismatch
                # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-pop-block
            # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-match-end

        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-if-unclosed
        # Report unclosed blocks
        for key, (start_line, cpt, phase, inst) in open_blocks.items():
            self._errors.append(
                error(
                    "marker",
                    f"@cpt-begin for `{cpt}` inst `{inst}` at line {start_line} "
                    f"in `{self.path.name}` was never closed with @cpt-end",
                    code=EC.MARKER_BEGIN_NO_END,
                    path=self.path,
                    line=start_line,
                    id=cpt,
                    inst=inst,
                )
            )
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-if-unclosed

    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-code-query-validate
    def list_ids(self) -> List[str]:
        """List all unique Studio IDs referenced in this code file."""
        ids: Set[str] = set()
        for ref in self.references:
            ids.add(ref.id)
        return sorted(ids)

    def get(self, id_value: str) -> Optional[str]:
        """Get the code content associated with an Studio ID.

        Returns the content of the first matching scope or block marker.
        """
        # Check block markers first (they have content)
        for block in self.block_markers:
            if block.id == id_value:
                return "\n".join(block.content)

        # For scope markers, return the line
        for scope in self.scope_markers:
            if scope.id == id_value:
                return scope.raw

        return None

    def list(self, ids: Sequence[str]) -> List[Optional[str]]:
        """Get content for multiple IDs."""
        return [self.get(i) for i in ids]

    def get_by_inst(self, inst: str) -> Optional[str]:
        """Get code content by instruction ID."""
        for block in self.block_markers:
            if block.inst == inst:
                return "\n".join(block.content)
        return None

    def validate(self) -> Dict[str, List[Dict[str, object]]]:
        """Validate the code file structure (marker pairing, etc).

        Note: Does NOT validate against artifacts - use cross_validate_code for that.
        """
        errors = list(self._errors)
        warnings: List[Dict[str, object]] = []

        # Check for duplicate scope markers with same ID
        seen_scopes: Dict[str, int] = {}
        for scope in self.scope_markers:
            key = f"{scope.kind}:{scope.id}:{scope.phase}"
            if key in seen_scopes:
                errors.append(
                    error(
                        "marker",
                        f"Duplicate scope marker `{scope.kind}:{scope.id}:p{scope.phase}` "
                        f"in `{self.path.name}` at line {scope.line} — first seen "
                        f"at line {seen_scopes[key]}",
                        code=EC.MARKER_DUP_SCOPE,
                        path=self.path,
                        line=scope.line,
                        id=scope.id,
                        first_occurrence=seen_scopes[key],
                    )
                )
            else:
                seen_scopes[key] = scope.line

        return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-code-query-validate

    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-extract-scope
    def _append_scope_reference(self, marker_match: re.Match[str], line_no: int) -> None:
        """Record a scope-marker reference extracted from the current line."""
        reference = CodeReference(
            id=marker_match.group("id"),
            line=line_no,
            kind=marker_match.group("kind"),
            phase=int(marker_match.group("phase")),
            inst=None,
            marker_type="scope",
        )
        self.references.append(reference)
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-extract-scope

# @cpt-algo:cpt-studio-algo-traceability-validation-cross-validate-code:p1
def cross_validate_code(
    code_files: Sequence[CodeFile],
    artifact_ids: Set[str],
    to_code_ids: Set[str],
    forbidden_code_ids: Optional[Set[str]] = None,
    traceability: str = "FULL",
    artifact_instances: Optional[Dict[str, Set[str]]] = None,
    artifact_instances_all: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """Cross-validate code files against artifact IDs.

    Args:
        code_files: Parsed code files to validate
        artifact_ids: All IDs defined in artifacts
        to_code_ids: IDs with to_code="true" that MUST have code markers
        traceability: "FULL" or "DOCS-ONLY"
        artifact_instances: Mapping of ID -> set of checked instruction slugs from CDSL steps
        artifact_instances_all: Mapping of ID -> set of ALL instruction slugs (checked + unchecked)

    Returns:
        Dict with "errors" and "warnings" lists
    """
    errors: List[Dict[str, object]] = []
    warnings: List[Dict[str, object]] = []

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-if-docs-only
    if traceability == "DOCS-ONLY":
        _collect_docs_only_errors(code_files, errors)
        return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-if-docs-only

    # FULL traceability mode

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-collect-code-ids
    # Collect all IDs referenced in code
    code_ids: Set[str] = set()
    for cf in code_files:
        code_ids.update(cf.list_ids())
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-collect-code-ids

    first_forbidden = _collect_code_reference_errors(
        code_files,
        artifact_ids,
        forbidden_code_ids,
        errors,
    )

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-forbidden
    if forbidden_code_ids:
        _collect_forbidden_code_errors(
            code_files,
            first_forbidden,
            artifact_instances,
            artifact_instances_all,
            errors,
        )
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-forbidden

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-missing
    # Check for missing markers (to_code IDs without code markers)
    missing_ids = to_code_ids - code_ids
    for missing_id in sorted(missing_ids):
        errors.append(_build_missing_code_marker_error(missing_id))
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-missing

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-inst
    # Instruction-level cross-validation
    if artifact_instances:
        _collect_instruction_errors(code_files, artifact_instances, errors)
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-inst

    # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-return-code-cross
    return {"errors": errors, "warnings": warnings}
    # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-return-code-cross


def _collect_docs_only_errors(
    code_files: Sequence[CodeFile],
    errors: List[Dict[str, object]],
) -> None:
    """Record DOCS-ONLY violations for files that still contain markers."""
    for cf in code_files:
        if cf.scope_markers or cf.block_markers:
            errors.append(
                error(
                    "traceability",
                    f"@cpt markers found in `{cf.path.name}` but traceability mode "
                    "is DOCS-ONLY — remove all markers or switch to FULL",
                    code=EC.CODE_DOCS_ONLY,
                    path=cf.path,
                    line=1,
                )
            )


 # @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-orphan
def _collect_code_reference_errors(
    code_files: Sequence[CodeFile],
    artifact_ids: Set[str],
    forbidden_code_ids: Optional[Set[str]],
    errors: List[Dict[str, object]],
) -> Dict[str, Tuple[Path, int]]:
    """Collect orphaned code reference errors and first forbidden locations."""
    first_forbidden: Dict[str, Tuple[Path, int]] = {}
    for cf in code_files:
        for ref in cf.references:
            if forbidden_code_ids and ref.id in forbidden_code_ids and ref.id not in first_forbidden:
                first_forbidden[ref.id] = (cf.path, int(ref.line))
            if ref.id not in artifact_ids:
                errors.append(_build_orphan_reference_error(cf.path, cf.path.name, ref.id, ref.line))
    return first_forbidden
 # @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-foreach-orphan


def _build_code_inst_lookup(
    code_files: Sequence[CodeFile],
) -> Dict[str, Set[str]]:
    """Return block-marker instruction IDs grouped by artifact ID."""
    code_inst_lookup: Dict[str, Set[str]] = {}
    for cf in code_files:
        for bm in cf.block_markers:
            code_inst_lookup.setdefault(bm.id, set()).add(bm.inst)
    return code_inst_lookup


def _collect_forbidden_code_errors(
    code_files: Sequence[CodeFile],
    first_forbidden: Dict[str, Tuple[Path, int]],
    artifact_instances: Optional[Dict[str, Set[str]]],
    artifact_instances_all: Optional[Dict[str, Set[str]]],
    errors: List[Dict[str, object]],
) -> None:
    """Record code references that require a checked artifact task."""
    code_inst_lookup = _build_code_inst_lookup(code_files)
    all_instances = artifact_instances_all or artifact_instances
    for fid in sorted(first_forbidden.keys()):
        path, line = first_forbidden[fid]
        if all_instances and fid in all_instances and all_instances[fid] - code_inst_lookup.get(fid, set()):
            continue
        errors.append(_build_forbidden_code_error(fid, path, line))


def _collect_instruction_errors(
    code_files: Sequence[CodeFile],
    artifact_instances: Dict[str, Set[str]],
    errors: List[Dict[str, object]],
) -> None:
    """Record instruction-level code/artifact mismatches."""
    code_inst_by_id: Dict[str, Dict[str, Tuple[Path, int]]] = {}
    for cf in code_files:
        for bm in cf.block_markers:
            code_inst_by_id.setdefault(bm.id, {})[bm.inst] = (cf.path, bm.start_line)

    for cid, art_insts in sorted(artifact_instances.items()):
        code_insts = set(code_inst_by_id.get(cid, {}).keys())
        for inst in sorted(art_insts - code_insts):
            errors.append(_build_missing_instruction_error(cid, inst))
        for inst in sorted(code_insts - art_insts):
            loc_path, loc_line = code_inst_by_id[cid][inst]
            errors.append(_build_orphan_instruction_error(cid, inst, loc_path, loc_line))


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-emit-missing
def _build_missing_code_marker_error(missing_id: str) -> Dict[str, object]:
    """Build the error emitted when a to_code artifact has no code marker."""
    message = (
        f"`{missing_id}` is marked to_code=\"true\" but no @cpt marker "
        "referencing it exists in the codebase"
    )
    return error(
        "coverage",
        message,
        code=EC.CODE_NO_MARKER,
        path=Path("."),
        line=1,
        id=missing_id,
    )
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-emit-missing


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-emit-orphan
def _build_orphan_reference_error(
    path: Path,
    path_name: str,
    ref_id: str,
    line: int,
) -> Dict[str, object]:
    """Build the orphan-reference error for a code marker missing in artifacts."""
    message = (
        f"Code marker references `{ref_id}` in `{path_name}` at line {line} "
        "but this ID is not defined in any artifact"
    )
    return error(
        "traceability",
        message,
        code=EC.CODE_ORPHAN_REF,
        path=path,
        line=line,
        id=ref_id,
    )
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-emit-orphan


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-emit-forbidden
def _build_forbidden_code_error(fid: str, path: Path, line: int) -> Dict[str, object]:
    """Build the error emitted for code linked to an unchecked artifact task."""
    message = (
        f"`{fid}` is marked to_code=\"true\" and referenced in code at line {line} "
        "but its task checkbox is not checked in the artifact"
    )
    return error(
        "structure",
        message,
        code=EC.CODE_TASK_UNCHECKED,
        path=path,
        line=line,
        id=fid,
    )
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-emit-forbidden


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-if-inst-missing
def _build_missing_instruction_error(cid: str, inst: str) -> Dict[str, object]:
    """Build the error emitted when an artifact instruction has no code block."""
    message = (
        f"CDSL instruction `{inst}` of `{cid}` is defined in artifact "
        "but has no @cpt-begin/@cpt-end block in code"
    )
    return error(
        "coverage",
        message,
        code=EC.CODE_INST_MISSING,
        path=Path("."),
        line=1,
        id=cid,
        inst=inst,
    )
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-if-inst-missing


# @cpt-begin:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-if-inst-orphan
def _build_orphan_instruction_error(
    cid: str,
    inst: str,
    loc_path: Path,
    loc_line: int,
) -> Dict[str, object]:
    """Build the error emitted when code contains an instruction absent from CDSL."""
    message = (
        f"Code block `inst-{inst}` of `{cid}` in `{loc_path.name}` "
        f"at line {loc_line} has no matching CDSL step in the artifact"
    )
    return error(
        "traceability",
        message,
        code=EC.CODE_INST_ORPHAN,
        path=loc_path,
        line=loc_line,
        id=cid,
        inst=inst,
    )
# @cpt-end:cpt-studio-algo-traceability-validation-cross-validate-code:p1:inst-if-inst-orphan

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-code:p1:inst-code-wrappers
def load_code_file(code_path: Path) -> Tuple[Optional[CodeFile], List[Dict[str, object]]]:
    """Convenience wrapper returning (CodeFile|None, errors)."""
    return CodeFile.from_path(code_path)

def validate_code_file(code_path: Path) -> Dict[str, List[Dict[str, object]]]:
    """Validate a single code file's marker structure."""
    cf, errs = CodeFile.from_path(code_path)
    if errs or cf is None:
        return {
            "errors": errs
            or [
                error(
                    "file",
                    f"Failed to load code file `{code_path}`",
                    code=EC.FILE_LOAD_ERROR,
                    path=code_path,
                    line=1,
                )
            ],
            "warnings": [],
        }
    return cf.validate()
# @cpt-end:cpt-studio-algo-traceability-validation-scan-code:p1:inst-code-wrappers

# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context
# Conventional non-source directories excluded from every scan, independent of
# the project's own `artifacts.toml` `ignore` config.
_DEFAULT_IGNORED_DIR_NAMES = frozenset(
    {"node_modules", ".git", ".venv", "venv", "build", "dist", "vendor", ".tox", "__pycache__"}
)

# Files larger than this are skipped (with a warning) rather than fully read.
_MAX_CODE_FILE_BYTES = 2_000_000


def _is_in_default_ignored_dir(file_path: Path, root: Path) -> bool:
    """Return whether *file_path* sits under a conventional non-source directory."""
    try:
        rel_parts = file_path.resolve().relative_to(root.resolve()).parts
    except (OSError, ValueError) as exc:
        _warn_codebase(f"failed to resolve {file_path} relative to {root}: {exc}")
        return False
    return any(part in _DEFAULT_IGNORED_DIR_NAMES for part in rel_parts[:-1])


# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context


# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-resolve-entry-files
def resolve_entry_code_files(
    code_path: Path,
    extensions: List[str],
    *,
    project_root: Path,
) -> Tuple[List[Path], int]:
    """Code files one registry codebase entry covers, and how many were excluded.

    Every consumer of a codebase entry resolves it through here, so that a
    directory the policy excludes cannot be skipped by one command and scanned
    by another. Three rules apply:

    * conventional non-source directory names, at any depth -- a registered
      parent root otherwise re-admits the `vendor/` and `dist/` trees that
      registration itself refuses;
    * symlinked candidates, so one link cannot re-open an excluded tree or reach
      outside the project under a name that looks local;
    * resolved containment, because a symlinked *directory* escapes the project
      by a different route than a symlinked file.

    The excluded count is returned rather than logged so the caller can report
    its own denominator: "scanned N, excluded M" is checkable where a bare file
    count is not.
    """
    root = project_root.resolve()
    if not code_path.exists():
        return [], 0
    # The entry itself is judged before anything is read, so a `../..` entry is
    # refused rather than walked and then discarded file by file. Checking only
    # the candidates meant an external tree was traversed first, and every file
    # in it counted separately toward a total describing this project.
    #
    # This also covers the single-file case, which previously returned the path
    # unconditionally: an entry resolving to a file outside the project was
    # refused by `list-ids` and read by `validate` and `spec-coverage`.
    if _escapes_project(code_path, root):
        return [], 1
    if code_path.is_file():
        return [code_path], 0

    # Candidates are collected before they are judged, so each one is decided
    # once. Judging inside the extension loop counted a single excluded file
    # once per matching extension, which made the excluded total disagree with
    # the file list it is meant to be the denominator of.
    candidates: Set[Path] = set()
    for ext in extensions:
        candidates.update(code_path.rglob(f"*{ext}"))

    files: Set[Path] = set()
    excluded = 0
    for candidate in candidates:
        if _is_in_default_ignored_dir(candidate, code_path):
            excluded += 1
            continue
        if _escapes_project(candidate, root):
            excluded += 1
            continue
        files.add(candidate)
    return sorted(files, key=str), excluded


# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-resolve-entry-files


# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-escapes-project
def _escapes_project(candidate: Path, root: Path) -> bool:
    """Whether *candidate* is a symlink or resolves outside *root*.

    Checked on the resolved path: refusing symlinked files alone still lets a
    symlinked directory inside a registered root carry the scan outside the
    project.
    """
    try:
        if candidate.is_symlink():
            return True
        resolved = candidate.resolve()
    except OSError as exc:
        _warn_codebase(f"failed to resolve {candidate}: {exc}")
        return True
    if resolved == root:
        return False
    return root not in resolved.parents




# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-escapes-project


# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context
def _is_ignored_code_file(file_path: Path, ctx) -> bool:
    """Return whether *file_path* is registry-ignored and should be skipped.

    Fails closed: when containment under the project root can't be
    established, the file is treated as ignored rather than scanned.
    """
    try:
        rel = file_path.resolve().relative_to(ctx.project_root).as_posix()
    except (OSError, ValueError) as exc:
        _warn_codebase(f"failed to resolve {file_path} relative to {ctx.project_root}: {exc}")
        return True
    return ctx.meta.is_ignored(rel)


def _code_reference_hit(ref: CodeReference, file_path: Path) -> Dict[str, object]:
    """Build a list-ids/where-used hit dict from one parsed code reference."""
    hit: Dict[str, object] = {
        "id": ref.id,
        "kind": ref.kind or "code",
        "type": "code_reference",
        "artifact_type": "CODE",
        "line": ref.line,
        "artifact": str(file_path),
        "marker_type": ref.marker_type,
    }
    if ref.phase is not None:
        hit["phase"] = ref.phase
    if ref.inst:
        hit["inst"] = ref.inst
    return hit


def _scan_code_file_references(file_path: Path, ctx) -> Optional[List[Dict[str, object]]]:
    """Parse one code file for marker references, or None if skipped/unparsable."""
    if _is_ignored_code_file(file_path, ctx):
        return None
    try:
        if file_path.stat().st_size > _MAX_CODE_FILE_BYTES:
            _warn_codebase(f"skipping {file_path}: exceeds {_MAX_CODE_FILE_BYTES}-byte scan limit")
            return None
    except OSError as exc:
        _warn_codebase(f"failed to stat {file_path}: {exc}")
        return None
    cf, errs = CodeFile.from_path(file_path)
    if errs or cf is None:
        return None
    return [_code_reference_hit(ref, file_path) for ref in cf.references]


@dataclass
class _SourceScanContext:
    """Minimal ctx shim exposing project_root/meta for a workspace source scan."""

    project_root: Path
    meta: object


def _scan_codebase_entries(scan_ctx) -> Tuple[List[Dict[str, object]], int, int]:
    """Scan all codebase entries reachable from *scan_ctx* (primary or a workspace source).

    Returns (hits, files_scanned, files_skipped). A codebase entry whose
    configured path resolves outside *scan_ctx.project_root* is skipped
    entirely (fail closed on a misconfigured/escaping entry) rather than
    walked.
    """
    hits: List[Dict[str, object]] = []
    scanned = 0
    skipped = 0
    root = scan_ctx.project_root.resolve()
    for cb_entry, _system_node in scan_ctx.meta.iter_all_codebase():
        code_path = (root / cb_entry.path).resolve()
        try:
            code_path.relative_to(root)
        except ValueError:
            _warn_codebase(f"codebase entry {cb_entry.path!r} resolves outside {root}; skipping")
            continue
        entry_files, entry_excluded = resolve_entry_code_files(
            code_path, cb_entry.extensions or [".py"], project_root=root
        )
        # Counted as skipped: that total already means "ignored, oversized, or
        # unparsable", and a policy exclusion is the first of those.
        skipped += entry_excluded
        for file_path in entry_files:
            file_hits = _scan_code_file_references(file_path, scan_ctx)
            if file_hits is None:
                skipped += 1
                continue
            scanned += 1
            hits.extend(file_hits)
    return hits, scanned, skipped


def scan_registered_codebase_references(ctx) -> Tuple[List[Dict[str, object]], int, int]:
    """Scan registered codebase entries for Studio marker references.

    Shared by `list-ids --include-code` and `where-used --include-code` so
    both commands see the same code-marker parser. In a multi-repo workspace
    with cross-repo resolution enabled, also fans out to each reachable
    workspace source's own registered codebase entries, mirroring how
    `collect_artifacts_to_scan` fans out artifact scanning.

    Returns (hits, files_scanned, files_skipped) — *files_skipped* lets a
    caller tell "no --include-code" apart from "--include-code found nothing
    because every candidate file was ignored, oversized, or unparsable".
    """
    from .context import WorkspaceContext, get_expanded_meta

    hits, code_files_scanned, code_files_skipped = _scan_codebase_entries(ctx)

    if isinstance(ctx, WorkspaceContext) and ctx.cross_repo and ctx.resolve_remote_ids:
        for sc in ctx.sources.values():
            if not sc.reachable or sc.path is None or sc.role not in ("codebase", "full"):
                continue
            meta = get_expanded_meta(sc)
            if meta is None:
                continue
            source_hits, source_scanned, source_skipped = _scan_codebase_entries(
                _SourceScanContext(project_root=sc.path, meta=meta)
            )
            hits.extend(source_hits)
            code_files_scanned += source_scanned
            code_files_skipped += source_skipped

    return hits, code_files_scanned, code_files_skipped
# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context

__all__ = [
    "CodeFile",
    "ScopeMarker",
    "BlockMarker",
    "CodeReference",
    "load_code_file",
    "validate_code_file",
    "cross_validate_code",
    "scan_registered_codebase_references",
]
