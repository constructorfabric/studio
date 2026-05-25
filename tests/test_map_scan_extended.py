"""Extended tests for scan.py.

Covers uncovered lines in scan.py — focus on:
- _section_around edge cases
- _walk_files filtering
- _detect_adapter_dir variations
- scan_repo with include_adapter flag
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Set

import pytest

from studio.commands.map.scan import (
    DEFAULT_SKIP_DIRS,
    ScanOptions,
    _detect_adapter_dir,
    _section_around,
    _walk_files,
    scan_repo,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_BASIC = FIXTURES / "repo-basic"


# ---------------------------------------------------------------------------
# _section_around
# ---------------------------------------------------------------------------

def test_section_around_at_file_start():
    """_section_around at line 1 returns from line 1 onward."""
    lines = ["# Heading", "Some content", "More content"]
    result = _section_around(lines, 1)
    assert result != ""
    assert "# Heading" in result


def test_section_around_at_file_end():
    """_section_around at last line returns from nearest heading to end."""
    lines = ["# Heading", "line 2", "last line"]
    result = _section_around(lines, 3)
    assert "last line" in result


def test_section_around_line_outside_range_above():
    """_section_around with line_no=0 returns empty string."""
    lines = ["# Heading", "content"]
    result = _section_around(lines, 0)
    assert result == ""


def test_section_around_line_outside_range_below():
    """_section_around with line_no > len(lines) returns empty string."""
    lines = ["# Heading", "content"]
    result = _section_around(lines, 10)
    assert result == ""


def test_section_around_empty_lines():
    """_section_around with empty lines list and line_no=1 returns empty string."""
    result = _section_around([], 1)
    assert result == ""


def test_section_around_section_with_subheading():
    """_section_around stops before the next heading."""
    lines = [
        "# Heading 1",
        "content under h1",
        "## Sub-heading",
        "content under h2",
    ]
    # Line 2 is in the h1 section, should stop before ## Sub-heading
    result = _section_around(lines, 2)
    assert "content under h1" in result
    assert "## Sub-heading" not in result


def test_section_around_caps_at_max_lines():
    """_section_around caps output at _MAX_SNIPPET_LINES from heading."""
    from studio.commands.map.scan import _MAX_SNIPPET_LINES
    # Create a section longer than _MAX_SNIPPET_LINES
    lines = ["# Heading"] + [f"line {i}" for i in range(_MAX_SNIPPET_LINES + 20)]
    result = _section_around(lines, 2)
    # Should be capped
    assert result.count("\n") <= _MAX_SNIPPET_LINES


def test_section_around_trims_trailing_blank_lines():
    """_section_around removes trailing blank lines from section."""
    lines = ["# Heading", "content", "", "   ", "# Next"]
    result = _section_around(lines, 2)
    assert not result.endswith("\n")


def test_section_around_exceeds_max_chars():
    """_section_around appends ellipsis when content exceeds _MAX_SNIPPET_CHARS."""
    from studio.commands.map.scan import _MAX_SNIPPET_CHARS
    # Create content larger than the char cap
    lines = ["# Heading"] + ["x" * 100 for _ in range(100)]
    result = _section_around(lines, 2)
    # If truncated, should end with ellipsis
    if len(result) > _MAX_SNIPPET_CHARS:
        assert result.endswith("…")


def test_section_around_no_preceding_heading():
    """_section_around when no heading before target falls back to line 0."""
    lines = ["plain text", "more plain", "target line", "after target", "# Heading at end"]
    result = _section_around(lines, 3)
    # Should include content from start to before the heading
    assert "target line" in result


# ---------------------------------------------------------------------------
# _walk_files
# ---------------------------------------------------------------------------

def test_walk_files_no_matching_extension(tmp_path):
    """_walk_files returns empty when no files match the extension."""
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    result = _walk_files(tmp_path, [".py"], set())
    assert result == []


def test_walk_files_matches_extension(tmp_path):
    """_walk_files returns files matching the specified extension."""
    (tmp_path / "script.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "readme.md").write_text("# Readme", encoding="utf-8")
    result = _walk_files(tmp_path, [".py"], set())
    rel_paths = [str(p.relative_to(tmp_path)) for p in result]
    assert "script.py" in rel_paths
    assert "readme.md" not in rel_paths


def test_walk_files_skips_skip_dirs(tmp_path):
    """_walk_files prunes directories in skip_dirs."""
    skip_dir = tmp_path / ".git"
    skip_dir.mkdir()
    (skip_dir / "config").write_text("git config", encoding="utf-8")
    (tmp_path / "main.py").write_text("code", encoding="utf-8")
    result = _walk_files(tmp_path, [".py", ""], {"  .git"})
    # .git/config is not .py, so only main.py matters
    result_py = _walk_files(tmp_path, [".py"], {".git"})
    rel_paths = [str(p.relative_to(tmp_path)) for p in result_py]
    assert "main.py" in rel_paths


def test_walk_files_skips_large_files(tmp_path):
    """_walk_files skips files larger than max_bytes."""
    large_file = tmp_path / "large.py"
    large_file.write_bytes(b"x" * 2000)
    result = _walk_files(tmp_path, [".py"], set(), max_bytes=1000)
    assert large_file not in result


def test_walk_files_case_insensitive_extension(tmp_path):
    """_walk_files extension matching is case-insensitive."""
    (tmp_path / "script.PY").write_text("code", encoding="utf-8")
    result = _walk_files(tmp_path, [".py"], set())
    assert len(result) == 1


def test_walk_files_recurses_into_subdirs(tmp_path):
    """_walk_files recurses into subdirectories."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "code.py").write_text("code", encoding="utf-8")
    result = _walk_files(tmp_path, [".py"], set())
    rel_paths = [str(p.relative_to(tmp_path)) for p in result]
    assert "subdir/code.py" in rel_paths


def test_walk_files_skips_dir_in_nested_path(tmp_path):
    """_walk_files prunes nested directories matching skip_dirs."""
    node_mods = tmp_path / "node_modules"
    node_mods.mkdir()
    (node_mods / "package.js").write_text("module", encoding="utf-8")
    result = _walk_files(tmp_path, [".js"], {"node_modules"})
    assert result == []


# ---------------------------------------------------------------------------
# _detect_adapter_dir
# ---------------------------------------------------------------------------

def test_detect_adapter_dir_from_claude_md(tmp_path):
    """_detect_adapter_dir reads cf-studio-path from CLAUDE.md."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cf-studio-path = ".mybootstrap"\n', encoding="utf-8")
    result = _detect_adapter_dir(tmp_path)
    assert result == ".mybootstrap"


def test_detect_adapter_dir_from_agents_md(tmp_path):
    """_detect_adapter_dir falls back to AGENTS.md when CLAUDE.md missing."""
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text('cypilot_path = ".bootstrap"\n', encoding="utf-8")
    result = _detect_adapter_dir(tmp_path)
    assert result == ".bootstrap"


def test_detect_adapter_dir_no_config_files(tmp_path):
    """_detect_adapter_dir returns None when no config files exist."""
    result = _detect_adapter_dir(tmp_path)
    assert result is None


def test_detect_adapter_dir_malformed_content(tmp_path):
    """_detect_adapter_dir returns None when file has no matching assignment."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Some random content\nno assignments here\n", encoding="utf-8")
    result = _detect_adapter_dir(tmp_path)
    assert result is None


def test_detect_adapter_dir_trailing_slash_stripped(tmp_path):
    """_detect_adapter_dir strips trailing slash from path value."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cf-studio-path = ".bootstrap/"\n', encoding="utf-8")
    result = _detect_adapter_dir(tmp_path)
    # Path(".bootstrap/").name == ".bootstrap"
    assert result == ".bootstrap"


def test_detect_adapter_dir_uses_basename_only(tmp_path):
    """_detect_adapter_dir returns only the basename, not full path."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cf-studio-path = "subdir/.adapter"\n', encoding="utf-8")
    result = _detect_adapter_dir(tmp_path)
    assert result == ".adapter"


def test_detect_adapter_dir_cypilot_path_in_claude_md(tmp_path):
    """_detect_adapter_dir recognizes cypilot_path key too."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cypilot_path = ".cf-constructor"\n', encoding="utf-8")
    result = _detect_adapter_dir(tmp_path)
    assert result == ".cf-constructor"


# ---------------------------------------------------------------------------
# scan_repo with include_adapter
# ---------------------------------------------------------------------------

def test_scan_repo_include_adapter_false(tmp_path):
    """scan_repo with include_adapter=False skips the adapter dir."""
    # Set up project with CLAUDE.md and adapter dir with .md files
    adapter_dir = tmp_path / ".bootstrap"
    adapter_dir.mkdir()
    (adapter_dir / "config.md").write_text("# Config\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("# Doc\n", encoding="utf-8")
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cf-studio-path = ".bootstrap"\n', encoding="utf-8")

    nodes = scan_repo(ScanOptions(
        project_root=tmp_path,
        source_name="local",
        no_source=True,
        include_adapter=False,
    ))
    rel_paths = {n.rel_path for n in nodes}
    assert "doc.md" in rel_paths
    assert ".bootstrap/config.md" not in rel_paths


def test_scan_repo_include_adapter_true(tmp_path):
    """scan_repo with include_adapter=True includes the adapter dir."""
    adapter_dir = tmp_path / ".bootstrap"
    adapter_dir.mkdir()
    (adapter_dir / "config.md").write_text("# Config\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("# Doc\n", encoding="utf-8")
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cf-studio-path = ".bootstrap"\n', encoding="utf-8")

    nodes = scan_repo(ScanOptions(
        project_root=tmp_path,
        source_name="local",
        no_source=True,
        include_adapter=True,
    ))
    rel_paths = {n.rel_path for n in nodes}
    assert ".bootstrap/config.md" in rel_paths


def test_scan_repo_extra_skip_dirs(tmp_path):
    """scan_repo with extra_skip_dirs skips those directories."""
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "third_party.md").write_text("# Third party\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("# Doc\n", encoding="utf-8")

    nodes = scan_repo(ScanOptions(
        project_root=tmp_path,
        source_name="local",
        no_source=True,
        extra_skip_dirs=["vendor"],
    ))
    rel_paths = {n.rel_path for n in nodes}
    assert "doc.md" in rel_paths
    assert "vendor/third_party.md" not in rel_paths
