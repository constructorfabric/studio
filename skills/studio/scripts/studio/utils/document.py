"""
Studio Validator - Document Utilities

Functions for working with documents and file paths.
"""

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-datamodel
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

_CPT_ID_RE = re.compile(r"(cpt-[a-z0-9][a-z0-9-]+)")
_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
_CODE_FENCE_RE = re.compile(r"^\s*```")

_ID_DEF_RE = re.compile(
    r"^(?:"
    r"\*\*ID\*\*:\s*`(?P<id>cpt-[a-z0-9][a-z0-9-]+)`"
    r"|"
    r"(?:`(?P<priority_only2>p\d+)`\s*-\s*)?\*\*ID\*\*:\s*`(?P<id4>cpt-[a-z0-9][a-z0-9-]+)`"
    r"|"
    r"`(?P<priority_only>p\d+)`\s*-\s*\*\*ID\*\*:\s*`(?P<id2>cpt-[a-z0-9][a-z0-9-]+)`"
    r"|"
    r"[-*]\s+(?P<task>\[\s*[xX]?\s*\])\s*(?:`(?P<priority>p\d+)`\s*-\s*)?\*\*ID\*\*:\s*`(?P<id3>cpt-[a-z0-9][a-z0-9-]+)`"
    r")\s*$"
)
_ID_REF_RE = re.compile(
    r"^(?:(?P<task>\[\s*[xX]?\s*\])\s*(?:`(?P<priority>p\d+)`\s*-\s*|\-\s*)|`(?P<priority_only>p\d+)`\s*-\s*)?"
    r"`(?P<id>cpt-[a-z0-9][a-z0-9-]+)`\s*$"
)
_BACKTICK_ID_RE = re.compile(r"`(cpt-[a-z0-9][a-z0-9-]+)`")

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-scan-cdsl-datamodel
_CDSL_LINE_RE = re.compile(
    r"^\s*(?:\d+\.\s+|-\s+)\[\s*(?P<check>[xX ])\s*\]\s*-\s*`(?P<phase>(?:p\d+|ph-\d+))`\s*-\s*.+\s*-\s*`inst-(?P<inst>[a-z0-9-]+)`\s*$"
)
_CDSL_PHASE_NUM_RE = re.compile(r"^(?:p|ph-)(?P<num>\d+)$")
# @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-scan-cdsl-datamodel


def _iter_non_fenced_lines(lines: List[str]):
    """Yield non-empty lines outside fenced code blocks."""
    in_fence = False
    for idx0, raw in enumerate(lines):
        if _CODE_FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = raw.strip()
        if stripped:
            yield idx0, raw, stripped


def _build_id_hit(
    match: re.Match[str],
    *,
    idx0: int,
    hit_type: str,
    id_group_names: Tuple[str, ...],
    priority_group_names: Tuple[str, ...],
) -> Dict[str, object]:
    """Create a normalized ID hit entry from a regex match."""
    priority = next((match.group(name) for name in priority_group_names if match.group(name)), None)
    id_value = next((match.group(name) for name in id_group_names if match.group(name)), None)
    checked = (match.group("task") or "").lower().find("x") != -1
    hit: Dict[str, object] = {
        "id": id_value,
        "line": idx0 + 1,
        "type": hit_type,
        "checked": checked,
        "has_task": match.group("task") is not None,
        "has_priority": priority is not None and str(priority).strip(),
    }
    if priority:
        hit["priority"] = priority
    return hit


def _normalize_reference_candidate(stripped: str) -> str:
    """Drop simple list markers before matching a reference-only line."""
    for prefix in ("- ", "* "):
        if stripped.startswith(prefix):
            return stripped[2:].strip()
    return stripped


def _extract_phase_number(match: re.Match[str]) -> Optional[int]:
    """Extract a numeric CDSL phase when present."""
    phase_raw = str(match.group("phase") or "").strip()
    phase_match = _CDSL_PHASE_NUM_RE.match(phase_raw)
    if not phase_match:
        return None
    return int(phase_match.group("num"))

def _normalize_cpt_id_from_line(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped:
        return None

    # Common decorations: backticks or "**ID**: `...`"
    if stripped.startswith("**ID**:"):
        matches = _CPT_ID_RE.findall(stripped)
        return matches[0] if matches else None

    if stripped.startswith("`") and stripped.endswith("`") and len(stripped) > 2:
        stripped = stripped.strip("`").strip()

    if stripped.startswith("cpt-"):
        m = _CPT_ID_RE.fullmatch(stripped)
        return m.group(1) if m else None

    matches = _CPT_ID_RE.findall(stripped)
    return matches[0] if matches else None
# @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-datamodel

# @cpt-algo:cpt-studio-algo-traceability-validation-scan-ids:p1
def scan_cpt_ids(path: Path) -> List[Dict[str, object]]:
    """Scan a file for Studio IDs by scanning document text.

    Heuristics:
    - Only scans outside fenced code blocks (```...```).
    - Treats `**ID**: `...`` and task list `**ID**:` lines as *definitions*.
    - Treats lines like `` `cpt-...` `` / checkbox variants as *references*.
    - Treats any `` `cpt-...` `` occurrence as a *reference* (unless it was a definition line).
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-read-file
    lines = read_text_safe(path)
    if lines is None:
        return []
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-read-file

    hits: List[Dict[str, object]] = []

    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-foreach-line
    for idx0, raw, stripped in _iter_non_fenced_lines(lines):
        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-match-def
        m = _ID_DEF_RE.match(stripped)
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-match-def
        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-if-def
        if m:
            hits.append(_build_id_hit(
                m,
                idx0=idx0,
                hit_type="definition",
                id_group_names=("id", "id2", "id3", "id4"),
                priority_group_names=("priority", "priority_only", "priority_only2"),
            ))
            continue
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-if-def

        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-match-ref
        # Reference line format (optionally checkbox / priority).
        stripped_ref = _normalize_reference_candidate(stripped)
        mref = _ID_REF_RE.match(stripped_ref)
        if mref:
            hits.append(_build_id_hit(
                mref,
                idx0=idx0,
                hit_type="reference",
                id_group_names=("id",),
                priority_group_names=("priority", "priority_only"),
            ))
            continue
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-match-ref

        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-match-inline
        # Generic inline backticked references.
        for mm in _BACKTICK_ID_RE.finditer(raw):
            hits.append({"id": mm.group(1), "line": idx0 + 1, "type": "reference", "checked": False})
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-match-inline
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-foreach-line

    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-return-hits
    return hits
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-return-hits

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-headings
def headings_by_line(path: Path) -> List[List[str]]:
    """Return active markdown heading titles for each line (1-indexed).

    Headings are detected outside fenced code blocks.
    """
    lines = read_text_safe(path)
    if lines is None:
        return [[]]

    out: List[List[str]] = [[] for _ in range(len(lines) + 1)]
    stack: List[Tuple[int, str]] = []
    in_fence = False
    for idx0, raw in enumerate(lines):
        line_no = idx0 + 1
        if _CODE_FENCE_RE.match(raw):
            in_fence = not in_fence
            out[line_no] = [t for _, t in stack]
            continue
        if not in_fence:
            m = _HEADING_RE.match(raw)
            if m:
                level = len(m.group(1))
                title = str(m.group(2) or "").strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
        out[line_no] = [t for _, t in stack]
    return out
# @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-headings

# @cpt-algo:cpt-studio-algo-traceability-validation-scan-cdsl:p1
def scan_cdsl_instructions(path: Path) -> List[Dict[str, object]]:
    """Scan a file for CDSL instruction lines by scanning document text.

    Parent ID binding rule:
    - The instruction is bound to the most recent ID *definition* encountered above it
      ("first defined id above before CDSL"), if any.

    Returns hits with keys:
      - type: "cdsl"
      - checked: bool
      - phase: int
      - inst: str (without "inst-" prefix)
      - parent_id: Optional[str]
      - line: int (1-based)
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-read-file
    lines = read_text_safe(path)
    if lines is None:
        return []
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-read-file

    hits: List[Dict[str, object]] = []
    last_defined_id: Optional[str] = None

    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-foreach-cdsl
    for idx0, raw, stripped in _iter_non_fenced_lines(lines):
        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-track-parent
        mdef = _ID_DEF_RE.match(stripped)
        if mdef:
            id_value = mdef.group("id") or mdef.group("id2") or mdef.group("id3") or mdef.group("id4")
            if id_value:
                last_defined_id = id_value
            continue
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-track-parent

        m = _CDSL_LINE_RE.match(raw)
        if not m:
            continue

        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-extract-inst
        phase = _extract_phase_number(m)
        if phase is None:
            continue
        checked = str(m.group("check") or " ").strip().lower() == "x"
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-extract-inst

        # @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-associate-parent
        hits.append({
            "type": "cdsl",
            "checked": checked,
            "phase": phase,
            "inst": str(m.group("inst")),
            "parent_id": last_defined_id,
            "line": idx0 + 1,
        })
        # @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-associate-parent
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-foreach-cdsl

    # @cpt-begin:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-return-cdsl
    return hits
    # @cpt-end:cpt-studio-algo-traceability-validation-scan-cdsl:p1:inst-return-cdsl

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-get-content
def get_content_scoped(
    path: Path,
    *,
    id_value: str,
) -> Optional[Tuple[str, int, int]]:
    """Best-effort get-content fallback for artifacts.

    Supported formats:
      1) Hash-fence scope blocks:
         ##
         cpt-...
         content...
         ##

         Variant where IDs act as delimiters inside the same fence:
         ##
         cpt-a
         content A
         cpt-b
         content B
         ##

      2) Markdown heading scopes:
         ### cpt-...
         content...

    Returns:
        (text, start_line, end_line) with 1-based inclusive line numbers, or None.
    """
    lines = read_text_safe(path)
    if lines is None:
        return None

    wanted = id_value.strip()

    def emit(text_lines: List[str], start_idx: int, end_idx: int) -> Optional[Tuple[str, int, int]]:
        # Trim surrounding empties for a stable output payload.
        while text_lines and not text_lines[0].strip():
            text_lines = text_lines[1:]
            start_idx += 1
        while text_lines and not text_lines[-1].strip():
            text_lines = text_lines[:-1]
            end_idx -= 1
        text = "\n".join(text_lines).strip()
        if not text:
            return None
        return (text, start_idx + 1, end_idx + 1)

    scoped = _get_hash_fence_scoped(lines, wanted, emit)
    if scoped is not None:
        return scoped

    scoped = _get_heading_scoped(lines, wanted, emit)
    if scoped is not None:
        return scoped

    scoped = _get_definition_scoped(lines, wanted, emit)
    if scoped is not None:
        return scoped

    return None
# @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-get-content


def _get_hash_fence_scoped(lines, wanted, emit):
    """Resolve content from hash-fence-delimited sections."""
    fence_idxs = [i for i, ln in enumerate(lines) if ln.strip() in {"##", "###"}]
    for start_i, end_i in zip(fence_idxs[0::2], fence_idxs[1::2]):
        if end_i <= start_i + 1:
            continue
        boundaries = [
            (rel_idx, sid)
            for rel_idx, ln in enumerate(lines[start_i + 1 : end_i])
            if (sid := _normalize_cpt_id_from_line(ln))
        ]
        if not boundaries:
            continue

        scoped = _emit_hash_fence_segment(lines, boundaries, start_i, end_i, wanted, emit)
        if scoped is not None:
            return scoped
    return None


def _emit_hash_fence_segment(lines, boundaries, start_i, end_i, wanted, emit):
    """Emit the matching segment inside one hash-fence block."""
    for index, (boundary_rel, sid) in enumerate(boundaries):
        if sid != wanted:
            continue
        seg_start = start_i + boundary_rel + 2
        seg_end = end_i - 1
        if index + 1 < len(boundaries):
            next_rel, _ = boundaries[index + 1]
            seg_end = start_i + next_rel
        if seg_start > seg_end:
            return None
        return emit(lines[seg_start : seg_end + 1], seg_start, seg_end)
    return None


def _get_heading_scoped(lines, wanted, emit):
    """Resolve content from a heading whose title includes the wanted ID."""
    for idx, line in enumerate(lines):
        heading_match = _HEADING_RE.match(line)
        if not heading_match:
            continue
        level = len(heading_match.group(1))
        title = heading_match.group(2)
        if not _heading_matches_wanted_id(title, wanted):
            continue
        return _emit_heading_scope(lines, idx, level, emit)
    return None


def _heading_matches_wanted_id(title: str, wanted: str) -> bool:
    """Return whether a heading title names the wanted ID."""
    matches = _CPT_ID_RE.findall(title)
    stripped_title = title.strip()
    return (
        wanted in matches
        or wanted == stripped_title
        or wanted == stripped_title.strip("`").strip()
    )


def _emit_heading_scope(lines, start_idx, level, emit):
    """Emit content below a heading until the next heading at same or higher level."""
    start = start_idx + 1
    end = len(lines) - 1
    for idx in range(start_idx + 1, len(lines)):
        next_heading = _HEADING_RE.match(lines[idx])
        if next_heading and len(next_heading.group(1)) <= level:
            end = idx - 1
            break
    if start > end:
        return None
    return emit(lines[start : end + 1], start, end)


def _get_definition_scoped(lines, wanted, emit):
    """Resolve content below an ID definition inside its surrounding heading scope."""
    last_heading_level: Optional[int] = None
    in_fence = False

    for idx, line in enumerate(lines):
        if _CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            last_heading_level = len(heading_match.group(1))
            continue

        definition_match = _ID_DEF_RE.match(line.strip())
        if not definition_match:
            continue
        id_found = (
            definition_match.group("id")
            or definition_match.group("id2")
            or definition_match.group("id3")
            or definition_match.group("id4")
        )
        if id_found != wanted:
            continue
        return _emit_definition_scope(lines, idx, last_heading_level, emit)
    return None


def _emit_definition_scope(lines, start_idx, heading_level, emit):
    """Emit content after a definition until the next delimiter."""
    start = start_idx + 1
    end = len(lines) - 1
    cutoff_level = heading_level if heading_level is not None else 6
    in_fence = False
    for idx in range(start_idx + 1, len(lines)):
        if _CODE_FENCE_RE.match(lines[idx]):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _ID_DEF_RE.match(lines[idx].strip()):
            end = idx - 1
            break
        next_heading = _HEADING_RE.match(lines[idx])
        if next_heading and len(next_heading.group(1)) <= cutoff_level:
            end = idx - 1
            break
    if start > end:
        return None
    return emit(lines[start : end + 1], start, end)

# @cpt-begin:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-file-utils
def iter_text_files(
    root: Path,
    *,
    includes: Optional[List[str]] = None,
    excludes: Optional[List[str]] = None,
    max_bytes: int = 1_000_000,
) -> List[Path]:
    """
    Iterate over text files in directory.

    Args:
        root: Root directory to search
        includes: Glob patterns to include
        excludes: Glob patterns to exclude
        max_bytes: Maximum file size in bytes

    Returns:
        List of file paths
    """
    import os
    import fnmatch

    excludes = excludes or []

    skip_dirs = {
        ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "node_modules", "target", "dist", "build", ".venv", "venv",
    }

    out: List[Path] = []
    root = root.resolve()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(_iter_visible_dirs(dirnames, skip_dirs))

        for fn in sorted(filenames):
            fp = Path(dirpath) / fn
            rel = _relative_posix_or_none(fp, root)
            if rel is None:
                continue
            if _should_skip_text_file(fp, rel, includes, excludes, max_bytes, fnmatch):
                continue
            out.append(fp)

    return out


def _iter_visible_dirs(dirnames, skip_dirs):
    """Yield subdirectories that should be traversed."""
    return (dirname for dirname in dirnames if dirname not in skip_dirs and not dirname.startswith("."))


def _relative_posix_or_none(path: Path, root: Path) -> Optional[str]:
    """Return root-relative POSIX path or None when outside the root."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _should_skip_text_file(
    path: Path,
    rel: str,
    includes: Optional[List[str]],
    excludes: List[str],
    max_bytes: int,
    fnmatch_module,
) -> bool:
    """Return whether a candidate file should be excluded from scanning."""
    if excludes and any(fnmatch_module.fnmatch(rel, pattern) for pattern in excludes):
        return True
    if includes is not None and not any(fnmatch_module.fnmatch(rel, pattern) for pattern in includes):
        return True
    try:
        return path.stat().st_size > max_bytes
    except OSError:
        return True

def read_text_safe(path: Path) -> Optional[List[str]]:
    """
    Safely read text file to lines.

    Args:
        path: File path to read

    Returns:
        List of lines or None if error
    """
    import os

    try:
        raw = path.read_bytes()
    except OSError:
        return None

    if b"\x00" in raw:
        return None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="ignore")

    if os.linesep != "\n":
        text = text.replace("\r\n", "\n")

    return text.splitlines()

def to_relative_posix(path: Path, root: Path) -> str:
    """
    Convert path to relative POSIX string from root.

    Args:
        path: Path to convert
        root: Root path

    Returns:
        Relative POSIX path string
    """
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.as_posix()
    return rel.as_posix()

__all__ = [
    "iter_text_files",
    "read_text_safe",
    "to_relative_posix",
    "get_content_scoped",
    "scan_cpt_ids",
    "scan_cdsl_instructions",
    "headings_by_line",
]
# @cpt-end:cpt-studio-algo-traceability-validation-scan-ids:p1:inst-scan-ids-file-utils
