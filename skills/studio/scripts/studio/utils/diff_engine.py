"""
Resource Diff Engine for Studio.

Compares a source kit directory against the user's installed copy,
classifies files, shows unified diffs, and prompts per file with
[a]ccept / [d]ecline / [A]ccept all / [D]ecline all / [m]odify.
Entry point: ``file_level_kit_update()``.

"""

# @cpt-begin:cpt-studio-algo-kit-diff-display:p1:inst-diff-datamodel
import difflib
import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .toc import _expand_blank_line_region

@dataclass
class DiffReport:
    """Result of comparing two directory states."""
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Return whether the diff contains any changes."""
        return bool(self.added or self.removed or self.modified)
# @cpt-end:cpt-studio-algo-kit-diff-display:p1:inst-diff-datamodel


# @cpt-begin:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-explicit-prune
def _prune_fingerprint(resource_id: str, rel_path: str, dest: Path) -> str:
    payload = f"{resource_id}\n{rel_path}\n{dest.as_posix()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
# @cpt-end:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-explicit-prune


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

# @cpt-algo:cpt-studio-algo-kit-diff-display:p1
def show_file_diff(
    rel_path: str,
    old_content: bytes,
    new_content: bytes,
    prefix: str = "        ",
) -> None:
    """Show unified diff for a single file to stderr."""
    # @cpt-begin:cpt-studio-algo-kit-diff-display:p1:inst-show-file-diff
    try:
        old_lines = old_content.decode("utf-8").splitlines(keepends=True)
        new_lines = new_content.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        sys.stderr.write(f"{prefix}(binary file \u2014 diff not shown)\n")
        return

    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"old/{rel_path}",
        tofile=f"new/{rel_path}",
        lineterm="",
    ))
    if not diff:
        return
    for line in diff:
        line_s = line.rstrip("\n")
        if line_s.startswith("+++") or line_s.startswith("---"):
            sys.stderr.write(f"{prefix}{line_s}\n")
        elif line_s.startswith("+"):
            sys.stderr.write(f"{prefix}\033[32m{line_s}\033[0m\n")
        elif line_s.startswith("-"):
            sys.stderr.write(f"{prefix}\033[31m{line_s}\033[0m\n")
        elif line_s.startswith("@@"):
            sys.stderr.write(f"{prefix}\033[36m{line_s}\033[0m\n")
    # @cpt-end:cpt-studio-algo-kit-diff-display:p1:inst-show-file-diff


# @cpt-begin:cpt-studio-algo-kit-conflict-merge:p1:inst-merge-datamodel
def _get_editor() -> str:
    """Return the user's preferred editor: $VISUAL → $EDITOR → vi."""
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"


_CONFLICT_MARKER_OURS = "<<<<<<< installed (yours)"
_CONFLICT_MARKER_SEP = "======="
_CONFLICT_MARKER_THEIRS = ">>>>>>> upstream (source)"
# @cpt-end:cpt-studio-algo-kit-conflict-merge:p1:inst-merge-datamodel


# @cpt-algo:cpt-studio-algo-kit-conflict-merge:p1
def _has_conflict_markers(text: str) -> bool:
    """Return True if *text* still contains unresolved git conflict markers.

    Uses line-start matching to avoid false positives from ``=======``
    appearing as markdown content mid-line.
    """
    # @cpt-begin:cpt-studio-algo-kit-conflict-merge:p1:inst-detect-markers
    for line in text.splitlines():
        if (
            line.startswith("<<<<<<<")
            or line.startswith("=======")
            or line.startswith(">>>>>>>")
        ):
            return True
    return False
    # @cpt-end:cpt-studio-algo-kit-conflict-merge:p1:inst-detect-markers


def _build_conflict_content(
    _rel_path: str,
    old_text: str,
    new_text: str,
) -> str:
    """Build file content with git-style conflict markers.

    For each differing hunk the output contains::

        <<<<<<< installed (yours)
        ... user lines ...
        =======
        ... upstream lines ...
        >>>>>>> upstream (source)

    Identical regions are emitted as-is.  The result is valid input for
    any editor with merge-conflict resolution UI (VS Code, IntelliJ,
    Vim fugitive, etc.).
    """
    # @cpt-begin:cpt-studio-algo-kit-conflict-merge:p1:inst-build-conflicts
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    parts: List[str] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.extend(old_lines[i1:i2])
        elif tag == "replace":
            parts.append(_CONFLICT_MARKER_OURS + "\n")
            parts.extend(old_lines[i1:i2])
            parts.append(_CONFLICT_MARKER_SEP + "\n")
            parts.extend(new_lines[j1:j2])
            parts.append(_CONFLICT_MARKER_THEIRS + "\n")
        elif tag == "delete":
            parts.append(_CONFLICT_MARKER_OURS + "\n")
            parts.extend(old_lines[i1:i2])
            parts.append(_CONFLICT_MARKER_SEP + "\n")
            parts.append(_CONFLICT_MARKER_THEIRS + "\n")
        elif tag == "insert":
            parts.append(_CONFLICT_MARKER_OURS + "\n")
            parts.append(_CONFLICT_MARKER_SEP + "\n")
            parts.extend(new_lines[j1:j2])
            parts.append(_CONFLICT_MARKER_THEIRS + "\n")

    return "".join(parts)
    # @cpt-end:cpt-studio-algo-kit-conflict-merge:p1:inst-build-conflicts


def _prompt_unresolved(rel_path: str) -> str:
    """Prompt user when conflict markers remain after editing.

    Returns one of: ``"retry"``, ``"accept"``, ``"decline"``.
    """
    # @cpt-begin:cpt-studio-algo-kit-conflict-merge:p1:inst-prompt-unresolved
    sys.stderr.write(
        f"    \033[33m\u26a0 {rel_path}: unresolved conflict markers remain\033[0m\n"
        "      Reply with `r`, `a`, or `d`.\n"
        "      Suggested: `r` if you want to keep editing; use `a` to accept upstream or `d` to keep your current copy.\n"
        "      `r` = reopen the editor. `a` = accept upstream content. `d` = decline this change and keep your installed copy.\n"
        "      \033[1m[r]\033[0metry editing  "
        "\033[1m[a]\033[0mccept upstream  "
        "\033[1m[d]\033[0mecline (keep yours)  "
    )
    sys.stderr.flush()
    try:
        response = input().strip().lower()
    except EOFError:
        return "decline"
    if response == "r":
        return "retry"
    if response == "a":
        return "accept"
    return "decline"
    # @cpt-end:cpt-studio-algo-kit-conflict-merge:p1:inst-prompt-unresolved


def _open_editor_for_file(  # pylint: disable=too-many-return-statements
    rel_path: str,
    old_content: bytes,
    new_content: bytes,
) -> Optional[bytes]:
    """Open editor for manual file merge using git conflict markers.

    Writes a file with ``<<<<<<<``/``=======``/``>>>>>>>`` markers for
    every differing region.  After the editor closes:

    - If no conflict markers remain → return the resolved content.
    - If markers still present → re-prompt: retry / accept upstream / decline.
    - Empty file → abort (return None).

    Returns edited bytes, *new_content* (accept upstream), or None (decline).
    """
    # @cpt-begin:cpt-studio-algo-kit-conflict-merge:p1:inst-open-editor
    try:
        old_text = old_content.decode("utf-8")
        new_text = new_content.decode("utf-8")
    except UnicodeDecodeError:
        sys.stderr.write("    (binary file \u2014 cannot edit)\n")
        return None

    conflict_text = _build_conflict_content(rel_path, old_text, new_text)
    editor = _get_editor()
    suffix = Path(rel_path).suffix or ".md"

    while True:
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix,
                prefix="studio-merge-",
                delete=False, encoding="utf-8",
            ) as tmp:
                tmp.write(conflict_text)
                tmp_path = tmp.name

            cmd = shlex.split(editor)
            subprocess.check_call(cmd + [tmp_path])

            with open(tmp_path, encoding="utf-8") as f:
                edited = f.read()
        except FileNotFoundError:
            sys.stderr.write(f"    editor not found: {editor}\n")
            return None
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            sys.stderr.write(f"    editor failed: {exc}\n")
            return None
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if not edited.strip():
            return None

        # @cpt-begin:cpt-studio-algo-kit-conflict-merge:p1:inst-resolve-loop
        if not _has_conflict_markers(edited):
            return edited.encode("utf-8")

        decision = _prompt_unresolved(rel_path)
        if decision == "retry":
            conflict_text = edited
            continue
        if decision == "accept":
            return new_content
        return None
        # @cpt-end:cpt-studio-algo-kit-conflict-merge:p1:inst-resolve-loop
    # @cpt-end:cpt-studio-algo-kit-conflict-merge:p1:inst-open-editor


# ---------------------------------------------------------------------------
# Kit file-level update  (cpt-studio-algo-kit-file-update)
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-file-enumerate:p1:inst-enum-datamodel
_KIT_EXCLUDE_FILES = frozenset({"conf.toml", "blueprint_hashes.toml"})
_KIT_EXCLUDE_DIRS = frozenset({"blueprints", "__pycache__", ".prev"})

# Default content items when no explicit filter is provided
_DEFAULT_CONTENT_DIRS: Optional[Tuple[str, ...]] = None
_DEFAULT_CONTENT_FILES: Optional[Tuple[str, ...]] = None
# @cpt-end:cpt-studio-algo-kit-file-enumerate:p1:inst-enum-datamodel


# @cpt-algo:cpt-studio-algo-kit-file-enumerate:p1
# @cpt-algo:cpt-studio-algo-kit-snapshot:p1
def _enumerate_kit_files(
    dir_path: Path,
    *,
    exclude_files: frozenset = _KIT_EXCLUDE_FILES,
    exclude_dirs: frozenset = _KIT_EXCLUDE_DIRS,
    content_dirs: Optional[Tuple[str, ...]] = None,
    content_files: Optional[Tuple[str, ...]] = None,
) -> Dict[str, bytes]:
    """Enumerate files in a kit directory.

    Returns ``{relative_posix_path: content_bytes}``.

    When *content_dirs* / *content_files* are provided, **only** files whose
    top-level directory is in *content_dirs* or whose name matches a
    *content_files* entry are included (include-only mode).  Otherwise the
    legacy exclude-based filtering is applied.
    """
    # @cpt-begin:cpt-studio-algo-kit-file-enumerate:p1:inst-walk-dir
    # @cpt-begin:cpt-studio-algo-kit-snapshot:p1:inst-read-files
    files: Dict[str, bytes] = {}
    if not dir_path.is_dir():
        return files

    use_include = content_dirs is not None or content_files is not None
    include_dirs = set(content_dirs) if content_dirs else set()
    include_files = set(content_files) if content_files else set()

    for f in sorted(dir_path.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(dir_path)

        # @cpt-begin:cpt-studio-algo-kit-file-enumerate:p1:inst-include-filter
        if use_include:
            # Include-only: top-level dir must be in content_dirs,
            # or file at root must be in content_files.
            top = rel.parts[0] if len(rel.parts) > 1 else None
            if top and top in include_dirs:
                pass  # included via directory
            elif len(rel.parts) == 1 and rel.name in include_files:
                pass  # included via file name
            else:
                continue
        # @cpt-end:cpt-studio-algo-kit-file-enumerate:p1:inst-include-filter
        else:
            # @cpt-begin:cpt-studio-algo-kit-file-enumerate:p1:inst-exclude-filter
            if rel.name in exclude_files:
                continue
            if any(part in exclude_dirs for part in rel.parts):
                continue
            # @cpt-end:cpt-studio-algo-kit-file-enumerate:p1:inst-exclude-filter

        # @cpt-begin:cpt-studio-algo-kit-file-enumerate:p1:inst-read-bytes
        try:
            files[str(rel)] = f.read_bytes()
        except OSError:
            pass
        # @cpt-end:cpt-studio-algo-kit-file-enumerate:p1:inst-read-bytes
    return files
    # @cpt-end:cpt-studio-algo-kit-snapshot:p1:inst-read-files
    # @cpt-end:cpt-studio-algo-kit-file-enumerate:p1:inst-walk-dir


# @cpt-algo:cpt-studio-algo-kit-file-classify:p1
def _classify_kit_files(
    source_files: Dict[str, bytes],
    user_files: Dict[str, bytes],
) -> DiffReport:
    """Classify files between source and user kit directories.

    Returns a DiffReport with added/removed/modified/unchanged lists.
    """
    # @cpt-begin:cpt-studio-algo-kit-file-classify:p1:inst-classify
    report = DiffReport()
    all_paths = sorted(set(source_files) | set(user_files))
    for p in all_paths:
        getattr(report, _classify_kit_file_state(p, source_files, user_files)).append(p)
    return report
    # @cpt-end:cpt-studio-algo-kit-file-classify:p1:inst-classify


def _classify_kit_file_state(
    rel_path: str,
    source_files: Dict[str, bytes],
    user_files: Dict[str, bytes],
) -> str:
    """Return the DiffReport bucket name for a single relative path."""
    in_source = rel_path in source_files
    in_user = rel_path in user_files
    if in_source and not in_user:
        return "added"
    if in_user and not in_source:
        return "removed"
    if source_files[rel_path] == user_files[rel_path]:
        return "unchanged"
    return "modified"


# @cpt-algo:cpt-studio-algo-kit-interactive-review:p1
def _prompt_kit_file(  # pylint: disable=too-many-return-statements
    rel_path: str,
    state: Dict[str, bool],
) -> str:
    """Interactive prompt for kit file review.

    Returns one of: ``"accept"``, ``"decline"``, ``"modify"``.

    Respects ``accept_all`` / ``decline_all`` flags in *state* to skip
    prompting for remaining files.
    """
    # @cpt-begin:cpt-studio-algo-kit-interactive-review:p1:inst-check-bulk
    if state.get("accept_all"):
        return "accept"

    if state.get("decline_all"):
        return "decline"
    # @cpt-end:cpt-studio-algo-kit-interactive-review:p1:inst-check-bulk

    # @cpt-begin:cpt-studio-algo-kit-interactive-review:p1:inst-prompt
    sys.stderr.write(
        f"    {rel_path}\n"
        "      Reply with `a`, `d`, `A`, `D`, or `m`.\n"
        "      Suggested: `a` when the upstream change looks correct as shown; use `m` when you want to merge manually.\n"
        "      `a` = accept this file. `d` = keep your copy. `A` = accept this and all remaining files. `D` = decline this and all remaining files. `m` = open an editor to merge manually.\n"
        "      \033[1m[a]\033[0mccept  "
        "\033[1m[d]\033[0mecline  "
        "\033[1m[A]\033[0mccept all  "
        "\033[1m[D]\033[0mecline all  "
        "\033[1m[m]\033[0modify  "
    )
    sys.stderr.flush()
    try:
        response = input().strip()
    except EOFError:
        return "decline"
    if response == "a":
        return "accept"

    if response == "d":
        return "decline"

    if response == "A":
        state["accept_all"] = True
        return "accept"

    if response == "D":
        state["decline_all"] = True
        return "decline"

    if response == "m":
        return "modify"

    return "decline"
    # @cpt-end:cpt-studio-algo-kit-interactive-review:p1:inst-prompt


def _show_kit_update_summary(report: DiffReport, prefix: str = "    ") -> None:
    """Print kit update summary to stderr with colour coding."""
    # @cpt-begin:cpt-studio-algo-kit-diff-display:p1:inst-show-summary
    counts = []
    if report.added:
        counts.append(f"\033[32m{len(report.added)} added\033[0m")
    if report.removed:
        counts.append(f"\033[31m{len(report.removed)} removed\033[0m")
    if report.modified:
        counts.append(f"\033[33m{len(report.modified)} modified\033[0m")
    counts.append(f"{len(report.unchanged)} unchanged")
    sys.stderr.write(f"{prefix}Kit files: {', '.join(counts)}\n")

    for p in report.added:
        sys.stderr.write(f"{prefix}  \033[32m+ {p}\033[0m  (new)\n")
    for p in report.removed:
        sys.stderr.write(f"{prefix}  \033[31m- {p}\033[0m  (deleted upstream)\n")
    for p in report.modified:
        sys.stderr.write(f"{prefix}  \033[33m~ {p}\033[0m\n")
    # @cpt-end:cpt-studio-algo-kit-diff-display:p1:inst-show-summary


# ---------------------------------------------------------------------------
# TOC handling for kit file diffs
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-kit-toc-handling:p1:inst-toc-datamodel
_TOC_MARKER_START = "<!-- toc -->"
_TOC_MARKER_END = "<!-- /toc -->"
_TOC_HEADING_RE = re.compile(r"^##\s+Table of Contents\s*$")
_HEADING_RE_TOC = re.compile(r"^#{1,6}\s")
# @cpt-end:cpt-studio-algo-kit-toc-handling:p1:inst-toc-datamodel


# @cpt-algo:cpt-studio-algo-kit-toc-handling:p1
def _strip_toc_for_diff(content: bytes) -> Tuple[bytes, str]:
    """Strip TOC sections from file content for cleaner diff comparison.

    Returns ``(stripped_content, toc_format)`` where *toc_format* is:

    - ``"markers"`` — ``<!-- toc -->`` / ``<!-- /toc -->`` block was stripped
    - ``"heading"`` — ``## Table of Contents`` section was stripped
    - ``""`` — no TOC found
    """
    # @cpt-begin:cpt-studio-algo-kit-toc-handling:p1:inst-strip-toc
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content, ""

    lines = text.split("\n")
    marker_range = _find_marker_toc_range(lines)
    if marker_range is not None:
        return _remove_toc_range(lines, marker_range, "markers")

    heading_range = _find_heading_toc_range(lines)
    if heading_range is not None:
        return _remove_toc_range(lines, heading_range, "heading")

    return content, ""
    # @cpt-end:cpt-studio-algo-kit-toc-handling:p1:inst-strip-toc


def _expand_toc_range(lines: List[str], start: int, end: int) -> Tuple[int, int]:
    """Expand a TOC range to absorb surrounding blank lines."""
    return _expand_blank_line_region(lines, start, end)


def _remove_toc_range(lines: List[str], span: Tuple[int, int], toc_format: str) -> Tuple[bytes, str]:
    """Remove a TOC span from text lines and return encoded content plus format."""
    start, end = _expand_toc_range(lines, *span)
    new_lines = lines[:start] + lines[end:]
    return "\n".join(new_lines).encode("utf-8"), toc_format


def _find_marker_toc_range(lines: List[str]) -> Optional[Tuple[int, int]]:
    """Find a marker-based TOC span, returning [start, end) indexes."""
    start_idx = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == _TOC_MARKER_START and start_idx is None:
            start_idx = index
        elif stripped == _TOC_MARKER_END and start_idx is not None:
            return start_idx, index + 1
    return None


def _find_heading_toc_range(lines: List[str]) -> Optional[Tuple[int, int]]:
    """Find a heading-based TOC span, returning [start, end) indexes."""
    for index, line in enumerate(lines):
        if not _TOC_HEADING_RE.match(line):
            continue
        toc_end = len(lines)
        for next_index in range(index + 1, len(lines)):
            if _HEADING_RE_TOC.match(lines[next_index]) or lines[next_index].strip() == "---":
                toc_end = next_index
                break
        return index, toc_end
    return None


def _prompt_toc_regen(rel_path: str) -> str:
    """Ask user whether to regenerate TOC for a file.

    Returns ``"yes"`` or ``"no"``.
    """
    # @cpt-begin:cpt-studio-algo-kit-toc-handling:p1:inst-prompt-regen
    sys.stderr.write(
        f"\n      TOC detected in \033[1m{rel_path}\033[0m.\n"
        "      Why this input is needed: decide whether to rewrite the table of contents after applying this change.\n"
        "      Reply with `y` to regenerate the TOC or `n` to keep the current file content as written.\n"
        "      Suggested: `y` when you want headings and TOC to stay in sync automatically.\n"
        f"      Regenerate? [\033[32my\033[0m]es / [\033[31mn\033[0m]o: "
    )
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except EOFError:
        return "no"
    if answer in ("y", "yes"):
        return "yes"
    return "no"
    # @cpt-end:cpt-studio-algo-kit-toc-handling:p1:inst-prompt-regen


def _prompt_toc_error_continue(rel_path: str, err: Exception) -> bool:
    """After TOC regen fails, ask user whether to continue or stop.

    Returns True to continue processing, False to stop.
    """
    # @cpt-begin:cpt-studio-algo-kit-toc-handling:p1:inst-handle-error
    sys.stderr.write(
        f"\n      \033[31mTOC regeneration failed for {rel_path}: {err}\033[0m\n"
        "      Previous content was restored.\n"
        "      Reply with `c` to continue updating other files or `s` to stop the update now.\n"
        "      Suggested: `c` when this file can be fixed later without blocking the rest of the update.\n"
        f"      [\033[32mc\033[0m]ontinue / [\033[31ms\033[0m]top: "
    )
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except EOFError:
        return False
    return answer != "s"
    # @cpt-end:cpt-studio-algo-kit-toc-handling:p1:inst-handle-error


def _regenerate_toc(content: bytes, toc_format: str) -> bytes:
    """Regenerate TOC in file content based on detected format.

    Uses ``insert_toc_markers`` for marker-based TOC and
    ``insert_toc_heading`` for heading-based TOC.

    Raises on failure (caller handles rollback).
    """
    # @cpt-begin:cpt-studio-algo-kit-toc-handling:p1:inst-regenerate
    from .toc import insert_toc_markers, insert_toc_heading

    text = content.decode("utf-8")
    if toc_format == "markers":
        result = insert_toc_markers(text, max_level=3)
    else:  # "heading"
        result = insert_toc_heading(text, max_heading_level=3, numbered=True)
    return result.encode("utf-8")
    # @cpt-end:cpt-studio-algo-kit-toc-handling:p1:inst-regenerate


# @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-build-target-mapping
def _target_path_for_bound_resource(
    src_rel_path: str,
    user_dir: Path,
    resource_bindings: Dict[str, Path],
    source_to_resource_id: Dict[str, str],
    resource_info: Dict[str, Any],
) -> Path:
    """Return the target path for a source file with optional resource binding."""
    res_id = source_to_resource_id.get(src_rel_path)
    if not res_id or res_id not in resource_bindings:
        return user_dir / src_rel_path

    binding_path = resource_bindings[res_id]
    info = resource_info.get(res_id)
    if not info or getattr(info, "type", "") != "directory":
        if binding_path.is_dir():
            sys.stderr.write(
                f"    [warn] file resource binding is a directory: "
                f"binding_path={binding_path}, src_rel_path={src_rel_path}\n"
            )
            return binding_path / src_rel_path.split("/")[-1]
        return binding_path

    source_base = getattr(info, "source_base", "")
    if src_rel_path.startswith(source_base + "/"):
        rel_within_dir = src_rel_path[len(source_base) + 1:]
        return binding_path / rel_within_dir

    try:
        rel_within_dir = Path(src_rel_path).relative_to(source_base).as_posix()
        return binding_path / rel_within_dir
    except ValueError:
        sys.stderr.write(
            f"    [debug] directory resource fallback: "
            f"source_base={source_base}, src_rel_path={src_rel_path}, "
            f"binding_path={binding_path}\n"
        )
        return binding_path / src_rel_path.split("/")[-1]


def _build_target_mapping(
    source_files: Dict[str, bytes],
    user_dir: Path,
    resource_bindings: Optional[Dict[str, Path]],
    source_to_resource_id: Optional[Dict[str, str]],
    resource_info: Optional[Dict[str, Any]],
) -> Dict[str, Path]:
    """Build source-relative path to absolute target path mapping."""
    if not resource_bindings or not source_to_resource_id or not resource_info:
        return {src_rel_path: user_dir / src_rel_path for src_rel_path in source_files}
    return {
        src_rel_path: _target_path_for_bound_resource(
            src_rel_path,
            user_dir,
            resource_bindings,
            source_to_resource_id,
            resource_info,
        )
        for src_rel_path in source_files
    }


def _read_file_if_available(path: Path) -> Optional[bytes]:
    """Read a file path, returning None when it cannot be read."""
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except (OSError, IOError):
        return None


def _read_bound_directory_resource(
    source_base: str,
    binding_path: Path,
    user_files: Dict[str, bytes],
    target_mapping: Dict[str, Path],
) -> None:
    """Populate user files from a directory resource binding."""
    for fpath in binding_path.rglob("*"):
        content = _read_file_if_available(fpath)
        if content is None:
            continue
        src_rel_path = f"{source_base}/{fpath.relative_to(binding_path).as_posix()}"
        if src_rel_path in user_files:
            continue
        user_files[src_rel_path] = content
        target_mapping[src_rel_path] = fpath


def _read_bound_file_resource(
    source_base: str,
    binding_path: Path,
    resource_type: str,
    user_files: Dict[str, bytes],
    target_mapping: Dict[str, Path],
) -> None:
    """Populate user files from a file-like resource binding."""
    fpath = binding_path
    if resource_type == "file" and binding_path.is_dir():
        fpath = binding_path / source_base.split("/")[-1]
    content = _read_file_if_available(fpath)
    if content is None or source_base in user_files:
        return
    user_files[source_base] = content
    target_mapping[source_base] = fpath


def _read_bound_resource_files(
    resource_bindings: Dict[str, Path],
    resource_info: Dict[str, Any],
    user_files: Dict[str, bytes],
    target_mapping: Dict[str, Path],
) -> None:
    """Populate user files discovered through explicit resource bindings."""
    for res_id, binding_path in resource_bindings.items():
        info = resource_info.get(res_id)
        if not info:
            continue

        source_base = getattr(info, "source_base", "")
        resource_type = getattr(info, "type", "")
        if resource_type == "directory" and binding_path.is_dir():
            _read_bound_directory_resource(
                source_base,
                binding_path,
                user_files,
                target_mapping,
            )
            continue

        _read_bound_file_resource(
            source_base,
            binding_path,
            resource_type,
            user_files,
            target_mapping,
        )
# @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-build-target-mapping


def _collect_enum_kwargs(
    content_dirs: Optional[Tuple[str, ...]],
    content_files: Optional[Tuple[str, ...]],
) -> Dict[str, Any]:
    """Build optional include filters for kit file enumeration."""
    enum_kw: Dict[str, Any] = {}
    if content_dirs is not None:
        enum_kw["content_dirs"] = content_dirs
    if content_files is not None:
        enum_kw["content_files"] = content_files
    return enum_kw


def _filter_source_files_for_resources(
    source_files: Dict[str, bytes],
    strict_resource_files: bool,
    resource_bindings: Optional[Dict[str, Path]],
    source_to_resource_id: Optional[Dict[str, str]],
    resource_info: Optional[Dict[str, Any]],
) -> Dict[str, bytes]:
    """Apply strict resource-file filtering when requested."""
    if not strict_resource_files:
        return source_files
    if not resource_bindings or not source_to_resource_id or not resource_info:
        return {}
    return {
        rel_path: content
        for rel_path, content in source_files.items()
        if rel_path in source_to_resource_id
    }


def _collect_user_files(
    target_mapping: Dict[str, Path],
    user_dir: Path,
    enum_kw: Dict[str, Any],
    resource_bindings: Optional[Dict[str, Path]],
    resource_info: Optional[Dict[str, Any]],
) -> Dict[str, bytes]:
    """Enumerate current user files, including bound resources outside user_dir."""
    user_files: Dict[str, bytes] = {}
    for src_rel_path, target_path in target_mapping.items():
        content = _read_file_if_available(target_path)
        if content is not None:
            user_files[src_rel_path] = content
    if resource_bindings and resource_info:
        _read_bound_resource_files(resource_bindings, resource_info, user_files, target_mapping)
    mapped_target_paths = {target_path.resolve() for target_path in target_mapping.values()}
    for rel_path, content in _enumerate_kit_files(user_dir, **enum_kw).items():
        if rel_path in user_files:
            continue
        candidate_target = (user_dir / rel_path).resolve()
        if candidate_target in mapped_target_paths:
            continue
        user_files[rel_path] = content
        target_mapping.setdefault(rel_path, user_dir / rel_path)
    return user_files


def _strip_toc_maps(
    source_files: Dict[str, bytes],
    user_files: Dict[str, bytes],
) -> Tuple[Dict[str, bytes], Dict[str, bytes], Dict[str, str]]:
    """Build stripped-content views plus detected TOC formats."""
    source_stripped: Dict[str, bytes] = {}
    user_stripped: Dict[str, bytes] = {}
    toc_formats: Dict[str, str] = {}

    for key, value in source_files.items():
        stripped, fmt = _strip_toc_for_diff(value)
        source_stripped[key] = stripped
        if fmt:
            toc_formats[key] = fmt

    for key, value in user_files.items():
        stripped, fmt = _strip_toc_for_diff(value)
        user_stripped[key] = stripped
        if fmt and key not in toc_formats:
            toc_formats[key] = fmt
    return source_stripped, user_stripped, toc_formats


def _resolve_resource_id(
    rel_path: str,
    source_to_resource_id: Optional[Dict[str, str]],
    resource_info: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Resolve the owning resource id for a source-relative path."""
    resource_id = source_to_resource_id.get(rel_path) if source_to_resource_id else None
    if resource_id is not None or not resource_info:
        return resource_id
    for candidate_id, candidate_info in resource_info.items():
        source_base = getattr(candidate_info, "source_base", "")
        if rel_path == source_base or rel_path.startswith(f"{source_base}/"):
            return candidate_id
    return None


def _approval_tokens_for_overwrite(res_id: Optional[str], rel_path: str, dest: Path, user_dir: Path) -> set[str]:
    """Return all overwrite-approval tokens accepted for a bound file."""
    approval_tokens = {str(res_id), rel_path, dest.as_posix()}
    if len(user_dir.parents) >= 3:
        try:
            approval_tokens.add(dest.relative_to(user_dir.parents[2]).as_posix())
        except ValueError:
            pass
    return approval_tokens


def _decide_noninteractive_action(
    *,
    force: bool,
    auto_approve: bool,
    interactive: bool,
    requires_prune_mode: bool,
    prune_mode: bool,
    has_prune_approval: bool,
    requires_overwrite_approval: bool,
    has_overwrite_approval: bool,
) -> Optional[str]:
    """Return a non-interactive action or None when prompting is still required."""
    if force or auto_approve:
        if requires_prune_mode:
            return "accepted" if prune_mode and has_prune_approval else "declined"
        return "accepted" if not requires_overwrite_approval or has_overwrite_approval else "declined"
    if not interactive:
        if requires_prune_mode and prune_mode and has_prune_approval:
            return "accepted"
        return "declined"
    return None


def _show_change_context(rel_path: str, change_type: str, old_content: bytes, new_content: bytes) -> None:
    """Render the diff context shown before interactive review."""
    if change_type == "added":
        sys.stderr.write(
            f"\n    \033[32m+ {rel_path}\033[0m  (new file, "
            f"{len(new_content)} bytes)\n"
        )
        return
    if change_type == "removed":
        sys.stderr.write(
            f"\n    \033[31m- {rel_path}\033[0m  (deleted upstream, "
            f"{len(old_content)} bytes in your copy)\n"
        )
        return
    sys.stderr.write(f"\n    \033[33m~ {rel_path}\033[0m\n")
    show_file_diff(rel_path, old_content, new_content, prefix="      ")


def _decide_interactive_action(
    rel_path: str,
    change_type: str,
    review_state: Dict[str, bool],
    old_content: bytes,
    new_content: bytes,
    prune_mode: bool,
    prune_fingerprint: str,
) -> Tuple[str, bytes]:
    """Prompt for and resolve an interactive action for a changed file."""
    if change_type == "removed" and prune_fingerprint:
        sys.stderr.write(
            f"\n    \033[31m- {rel_path}\033[0m  (deleted upstream; prune fingerprint {prune_fingerprint})\n"
        )
        if prune_mode:
            decision = _prompt_kit_file(rel_path, review_state)
            return ("accepted" if decision == "accept" else "declined"), new_content
        return "declined", new_content

    _show_change_context(rel_path, change_type, old_content, new_content)
    decision = _prompt_kit_file(rel_path, review_state)
    if decision == "accept":
        return "accepted", new_content
    if decision == "decline":
        return "declined", new_content
    if decision == "modify":
        edited = _open_editor_for_file(rel_path, old_content, new_content)
        if edited is not None:
            return "modified", edited
    return "declined", new_content


def _record_decline_metadata(
    entry: Dict[str, str],
    *,
    requires_overwrite_approval: bool,
    interactive: bool,
    has_overwrite_approval: bool,
    res_id: Optional[str],
    dest: Path,
    requires_prune_mode: bool,
    prune_fingerprint: str,
) -> None:
    """Attach decline metadata used by callers to explain skipped updates."""
    if requires_overwrite_approval and entry["action"] == "declined" and not interactive and not has_overwrite_approval:
        entry["reason"] = (
            f"requires --approve-overwrite {res_id} or --approve-overwrite {dest.as_posix()}"
        )
    if requires_prune_mode and entry["action"] == "declined":
        entry["reason"] = "resource removed upstream; explicit prune mode required"
        entry["prune_fingerprint"] = prune_fingerprint
    elif requires_prune_mode:
        entry["prune_fingerprint"] = prune_fingerprint


def _apply_file_change(
    change_type: str,
    action: str,
    dest: Path,
    dry_run: bool,
    new_content: bytes,
    raw_new_content: bytes,
) -> Tuple[bool, bool]:
    """Apply a file mutation and report whether content was written."""
    wrote_file = False
    wrote_raw = False
    if change_type in {"added", "modified"} and action in {"accepted", "modified"} and not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_data = new_content if action == "modified" else raw_new_content
        dest.write_bytes(write_data)
        wrote_file = True
        wrote_raw = action == "accepted"
    elif change_type == "removed" and action == "accepted" and not dry_run and dest.is_file():
        dest.unlink()
    return wrote_file, wrote_raw


def _append_result_entry(
    change_type: str,
    entry: Dict[str, str],
    result_added: List[Dict[str, str]],
    result_removed: List[Dict[str, str]],
    result_modified: List[Dict[str, str]],
) -> None:
    """Store a per-file result entry in the appropriate result bucket."""
    if change_type == "added":
        result_added.append(entry)
    elif change_type == "removed":
        result_removed.append(entry)
    else:
        result_modified.append(entry)


# @cpt-algo:cpt-studio-algo-kit-file-update:p1
def file_level_kit_update(  # pylint: disable=too-many-arguments,too-many-locals,too-many-statements
    source_dir: Path,
    user_dir: Path,
    *,
    interactive: bool = True,
    auto_approve: bool = False,
    force: bool = False,
    dry_run: bool = False,
    content_dirs: Optional[Tuple[str, ...]] = None,
    content_files: Optional[Tuple[str, ...]] = None,
    resource_bindings: Optional[Dict[str, Path]] = None,
    source_to_resource_id: Optional[Dict[str, str]] = None,
    resource_info: Optional[Dict[str, Any]] = None,
    strict_resource_files: bool = False,
    approved_overwrites: Optional[List[str]] = None,
    prune_mode: bool = False,
    approved_prunes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compare source kit against user's installed copy and apply updates.

    Implements ``cpt-studio-algo-kit-file-update``.

    Args:
        source_dir:    Kit source directory (from cache).
        user_dir:      User's installed kit config directory.
        interactive:   Prompt user per changed file (default True).
        auto_approve:  Accept all changes without prompts.
        force:         Overwrite all files without prompts (alias).
        dry_run:       Show what would be done without writing.
        content_dirs:  If given, only include files under these top-level dirs.
        content_files: If given, only include root-level files matching these names.
        resource_bindings: For manifest-driven kits, maps resource_id -> absolute target path.
        source_to_resource_id: Maps source file rel_path -> resource_id.
        resource_info: Maps resource_id -> ResourceInfo (type, source_base).
        strict_resource_files: If true, ignore source files that are not mapped to a resource.

    Returns dict::

        {
            "status": "current" | "updated",
            "added": [{"path": ..., "action": ...}, ...],
            "removed": [...],
            "modified": [...],
            "unchanged_count": N,
            "accepted": [paths ...],
            "declined": [paths ...],
            "unchanged": N,
        }
    """
    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-enumerate-files
    enum_kw = _collect_enum_kwargs(content_dirs, content_files)
    source_files = _filter_source_files_for_resources(
        _enumerate_kit_files(source_dir, **enum_kw),
        strict_resource_files,
        resource_bindings,
        source_to_resource_id,
        resource_info,
    )
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-enumerate-files

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-build-target-mapping
    target_mapping = _build_target_mapping(
        source_files,
        user_dir,
        resource_bindings,
        source_to_resource_id,
        resource_info,
    )
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-build-target-mapping

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-enumerate-bound-user-files
    # Enumerate user files from target paths (may be outside user_dir)
    user_files = _collect_user_files(
        target_mapping,
        user_dir,
        enum_kw,
        resource_bindings,
        resource_info,
    )
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-enumerate-bound-user-files

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-strip-toc
    # Strip TOC from both sides so diffs only show content changes.
    # TOC is regenerated post-write if the user agrees.
    source_stripped, user_stripped, toc_formats = _strip_toc_maps(source_files, user_files)
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-strip-toc

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-classify-changes
    # Classify using raw content so TOC-only differences are detected.
    # Stripped content is used only for diff display (less noise).
    report = _classify_kit_files(source_files, user_files)
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-classify-changes

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-check-no-changes
    if not report.has_changes:
        return {
            "status": "current",
            "added": [],
            "removed": [],
            "modified": [],
            "unchanged_count": len(report.unchanged),
            "accepted": [],
            "declined": [],
            "unchanged": len(report.unchanged),
        }
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-check-no-changes

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-show-summary
    _show_kit_update_summary(report)
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-show-summary

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-update-datamodel
    result_added: List[Dict[str, str]] = []
    result_removed: List[Dict[str, str]] = []
    result_modified: List[Dict[str, str]] = []

    review_state: Dict[str, bool] = {}
    overwrite_approvals = {
        token.strip() for token in (approved_overwrites or []) if token.strip()
    }
    prune_approvals = {
        token.strip() for token in (approved_prunes or []) if token.strip()
    }

    changed = sorted(
        [(p, "added") for p in report.added]
        + [(p, "removed") for p in report.removed]
        + [(p, "modified") for p in report.modified]
    )
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-update-datamodel

    for rel_path, change_type in changed:
        # Stripped content for diff display, raw content for writing
        old_content = user_stripped.get(rel_path, b"")
        new_content = source_stripped.get(rel_path, b"")
        raw_new_content = source_files.get(rel_path, b"")
        toc_fmt = toc_formats.get(rel_path, "")
        dest = target_mapping.get(rel_path, user_dir / rel_path)
        res_id = _resolve_resource_id(rel_path, source_to_resource_id, resource_info)
        res_info = resource_info.get(res_id) if res_id and resource_info else None
        requires_overwrite_approval = (
            change_type == "modified"
            and bool(res_info)
            and bool(getattr(res_info, "user_modifiable", True))
        )
        # @cpt-begin:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-no-auto-delete
        requires_prune_mode = change_type == "removed" and bool(res_info)
        # @cpt-end:cpt-studio-algo-kit-update-drift-prune:p1:inst-update-no-auto-delete
        prune_fingerprint = (
            _prune_fingerprint(str(res_id), rel_path, dest)
            if requires_prune_mode
            else ""
        )
        has_prune_approval = prune_fingerprint in prune_approvals
        has_overwrite_approval = False
        if requires_overwrite_approval:
            approval_tokens = _approval_tokens_for_overwrite(res_id, rel_path, dest, user_dir)
            has_overwrite_approval = bool(overwrite_approvals.intersection(approval_tokens))

        action = _decide_noninteractive_action(
            force=force,
            auto_approve=auto_approve,
            interactive=interactive,
            requires_prune_mode=requires_prune_mode,
            prune_mode=prune_mode,
            has_prune_approval=has_prune_approval,
            requires_overwrite_approval=requires_overwrite_approval,
            has_overwrite_approval=has_overwrite_approval,
        )
        if action is None:
            action, new_content = _decide_interactive_action(
                rel_path,
                change_type,
                review_state,
                old_content,
                new_content,
                prune_mode if requires_prune_mode else False,
                prune_fingerprint if requires_prune_mode else "",
            )

        # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-apply-changes
        entry = {"path": rel_path, "action": action}
        _record_decline_metadata(
            entry,
            requires_overwrite_approval=requires_overwrite_approval,
            interactive=interactive,
            has_overwrite_approval=has_overwrite_approval,
            res_id=res_id,
            dest=dest,
            requires_prune_mode=requires_prune_mode,
            prune_fingerprint=prune_fingerprint,
        )
        wrote_file, wrote_raw = _apply_file_change(
            change_type,
            action,
            dest,
            dry_run,
            new_content,
            raw_new_content,
        )
        _append_result_entry(
            change_type,
            entry,
            result_added,
            result_removed,
            result_modified,
        )
        # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-apply-changes

        # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-toc-regen
        # Skip TOC regen if we wrote raw source content (already has correct TOC)
        if wrote_file and toc_fmt and not wrote_raw:
            should_regen = auto_approve or force
            if interactive and not should_regen:
                should_regen = _prompt_toc_regen(rel_path) == "yes"
            if should_regen:
                pre_toc_content = dest.read_bytes()
                try:
                    regenerated = _regenerate_toc(pre_toc_content, toc_fmt)
                    dest.write_bytes(regenerated)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    dest.write_bytes(user_files.get(rel_path, pre_toc_content))
                    if interactive:
                        if not _prompt_toc_error_continue(rel_path, exc):
                            break
        # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-toc-regen

    # @cpt-begin:cpt-studio-algo-kit-file-update:p1:inst-build-result
    all_entries = result_added + result_removed + result_modified
    accepted = [e["path"] for e in all_entries if e["action"] in ("accepted", "modified")]
    declined = [e["path"] for e in all_entries if e["action"] == "declined"]
    return {
        "status": "updated",
        "added": result_added,
        "removed": result_removed,
        "modified": result_modified,
        "unchanged_count": len(report.unchanged),
        "accepted": accepted,
        "declined": declined,
        "unchanged": len(report.unchanged),
    }
    # @cpt-end:cpt-studio-algo-kit-file-update:p1:inst-build-result
