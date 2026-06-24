"""Pylint checker for CPT markers wrapped around a single call-like statement."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Iterable

try:
    from pylint.checkers import BaseRawFileChecker
except ImportError:  # pragma: no cover - local helper import without pylint installed
    class BaseRawFileChecker:  # type: ignore[no-redef]
        """Fallback used by unit tests and local helper scripts."""

        def __init__(self, linter=None) -> None:
            self.linter = linter

_BEGIN_PREFIX = "# @cpt-begin:"
_END_PREFIX = "# @cpt-end:"


def _is_begin_marker(line: str) -> bool:
    return line.lstrip().startswith(_BEGIN_PREFIX)


def _is_end_marker(line: str) -> bool:
    return line.lstrip().startswith(_END_PREFIX)


def _is_ignorable_line(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _read_module_lines(module) -> list[str]:
    stream = getattr(module, "stream", None)
    if callable(stream):
        data = stream()
        if hasattr(data, "read"):
            data = data.read()
        if isinstance(data, bytes):
            return data.decode("utf-8").splitlines()
        return str(data).splitlines()
    file_path = getattr(module, "file", None)
    if not file_path and hasattr(module, "root"):
        root = module.root()
        file_path = getattr(root, "file", None)
    if not file_path:
        return []
    return Path(file_path).read_text(encoding="utf-8").splitlines()


def _is_call_like_statement(source: str) -> bool:
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return False
    if len(tree.body) != 1:
        return False
    stmt = tree.body[0]
    if isinstance(stmt, ast.Expr):
        return isinstance(stmt.value, ast.Call)
    if isinstance(stmt, ast.Return):
        return isinstance(stmt.value, ast.Call)
    if isinstance(stmt, ast.Assign):
        return isinstance(stmt.value, ast.Call)
    if isinstance(stmt, ast.AnnAssign):
        return isinstance(stmt.value, ast.Call)
    return False


def _find_matching_end(lines: list[str], begin_index: int) -> int | None:
    depth = 0
    for index in range(begin_index, len(lines)):
        line = lines[index]
        if _is_begin_marker(line):
            depth += 1
            continue
        if _is_end_marker(line):
            depth -= 1
            if depth == 0:
                return index
    return None


def _wrapped_block(lines: list[str], begin_index: int, end_index: int) -> tuple[int, str] | None:
    first_code_index: int | None = None
    block_lines: list[str] = []
    for index in range(begin_index + 1, end_index):
        line = lines[index]
        if first_code_index is None and _is_ignorable_line(line):
            continue
        if first_code_index is None:
            first_code_index = index
        block_lines.append(line)
    if first_code_index is None or not block_lines:
        return None
    return first_code_index, "\n".join(block_lines).rstrip()


def find_call_wrapped_marker_columns(lines: Iterable[str]) -> list[int]:
    """Return 1-based line numbers for CPT begin markers over one call-like statement."""
    source_lines = list(lines)
    findings: list[int] = []
    for index, line in enumerate(source_lines):
        if not _is_begin_marker(line):
            continue
        end_index = _find_matching_end(source_lines, index)
        if end_index is None:
            continue
        block = _wrapped_block(source_lines, index, end_index)
        if block is not None and _is_call_like_statement(block[1]):
            findings.append(index + 1)
    return findings


class CptMarkerColumnsChecker(BaseRawFileChecker):
    """Detect CPT begin markers wrapped around a single call-like statement."""

    name = "studio-cpt-marker-columns"
    msgs = {
        "W9007": (
            "CPT markers should wrap a real block, not a single call-like statement",
            "stacked-cpt-begin-column",
            "Used when one or more consecutive @cpt-begin markers sit on top of a single "
            "function call, call-return, or call-assignment before the matching @cpt-end markers.",
        ),
    }

    def _report_for_module(self, node) -> None:
        for line_number in find_call_wrapped_marker_columns(_read_module_lines(node)):
            self.add_message("stacked-cpt-begin-column", line=line_number)

    def process_module(self, node) -> None:
        """Raw-file hook used by pylint for module-level source inspection."""
        self._report_for_module(node)


def register(linter) -> None:
    """Register the checker once."""
    for checkers in getattr(linter, "_checkers", {}).values():
        for checker in checkers:
            if getattr(checker, "name", "") == CptMarkerColumnsChecker.name:
                return
    linter.register_checker(CptMarkerColumnsChecker(linter))
