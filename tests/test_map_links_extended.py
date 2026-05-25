"""Extended tests for markdown file-link extraction (links.py).

Covers uncovered lines: 54, 58, 65, 68, 94-98, 114-118, 129, 133, 138, 147, 150, 156,
167-171, 176, 186, 188-190.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pytest

from studio.commands.map.links import (
    _expand_vars,
    _load_markdown_content,
    _posix_normpath,
    _resolve,
    _slug_candidates,
    extract_file_links,
)
from studio.commands.map.model import Node

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_BASIC = FIXTURES / "repo-basic"


def _make_node(
    node_id: str,
    rel_path: Optional[str] = None,
    kind: str = "markdown",
    source: str = "local",
) -> Node:
    return Node(
        id=node_id,
        rel_path=rel_path,
        source=source,
        kind=kind,
        language=None,
        category="",
        category_origin="parent-dir",
        content=None,
        loc=0,
    )


# ---------------------------------------------------------------------------
# extract_file_links: edge cases for project_root=None
# ---------------------------------------------------------------------------

def test_extract_file_links_no_project_root():
    """extract_file_links with no project_root returns empty list."""
    node = _make_node("local:docs/foo.md", "docs/foo.md")
    result = extract_file_links([node], project_root=None)
    assert result == []


def test_extract_file_links_source_node_is_ignored(tmp_path):
    """Source nodes are skipped by extract_file_links."""
    src_node = _make_node("local:src/foo.py", "src/foo.py", kind="source")
    result = extract_file_links([src_node], project_root=tmp_path)
    assert result == []


def test_extract_file_links_node_no_rel_path(tmp_path):
    """Node with no rel_path is skipped."""
    node = _make_node("local:orphan", rel_path=None)
    result = extract_file_links([node], project_root=tmp_path)
    assert result == []


def test_extract_file_links_node_missing_file(tmp_path):
    """Node with rel_path pointing to missing file is skipped."""
    node = _make_node("local:docs/missing.md", "docs/missing.md")
    result = extract_file_links([node], project_root=tmp_path)
    assert result == []


def test_extract_file_links_empty_file(tmp_path):
    """Empty file produces no edges."""
    (tmp_path / "a.md").write_text("", encoding="utf-8")
    node = _make_node("local:a.md", "a.md")
    result = extract_file_links([node], project_root=tmp_path)
    assert result == []


def test_extract_file_links_external_url_ignored(tmp_path):
    """External http links are not emitted as file-link edges."""
    (tmp_path / "a.md").write_text("[external](http://example.com/foo.md)\n", encoding="utf-8")
    (tmp_path / "foo.md").write_text("# Foo\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    node_foo = _make_node("local:foo.md", "foo.md")
    result = extract_file_links([node_a, node_foo], project_root=tmp_path)
    assert result == []


def test_extract_file_links_https_url_ignored(tmp_path):
    """External https links are not emitted as file-link edges."""
    (tmp_path / "a.md").write_text("[external](https://example.com/foo.md)\n", encoding="utf-8")
    (tmp_path / "foo.md").write_text("# Foo\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    node_foo = _make_node("local:foo.md", "foo.md")
    result = extract_file_links([node_a, node_foo], project_root=tmp_path)
    assert result == []


def test_extract_file_links_anchor_only_ignored(tmp_path):
    """Anchor-only links (#section) are not emitted."""
    (tmp_path / "a.md").write_text("[section](#some-heading)\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    result = extract_file_links([node_a], project_root=tmp_path)
    assert result == []


def test_extract_file_links_target_not_in_known_nodes(tmp_path):
    """Links to unknown targets are skipped."""
    (tmp_path / "a.md").write_text("[unknown](unknown_file.md)\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    result = extract_file_links([node_a], project_root=tmp_path)
    assert result == []


def test_extract_file_links_absolute_target(tmp_path):
    """Absolute targets (/docs/foo.md) resolve correctly."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (tmp_path / "a.md").write_text("[link](/docs/foo.md)\n", encoding="utf-8")
    (docs_dir / "foo.md").write_text("# Foo\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    node_foo = _make_node("local:docs/foo.md", "docs/foo.md")
    result = extract_file_links([node_a, node_foo], project_root=tmp_path)
    pairs = {(e.from_id, e.to_id) for e in result}
    assert ("local:a.md", "local:docs/foo.md") in pairs


def test_extract_file_links_dotdot_path(tmp_path):
    """Links with .. in path resolve using normpath logic."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    sub_dir = docs_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "page.md").write_text("[parent](../parent.md)\n", encoding="utf-8")
    (docs_dir / "parent.md").write_text("# Parent\n", encoding="utf-8")
    node_page = _make_node("local:docs/sub/page.md", "docs/sub/page.md")
    node_parent = _make_node("local:docs/parent.md", "docs/parent.md")
    result = extract_file_links([node_page, node_parent], project_root=tmp_path)
    pairs = {(e.from_id, e.to_id) for e in result}
    assert ("local:docs/sub/page.md", "local:docs/parent.md") in pairs


def test_extract_file_links_template_var_expansion(tmp_path):
    """Template var in link target is expanded before resolution."""
    bootstrap_dir = tmp_path / ".bootstrap"
    bootstrap_dir.mkdir()
    (bootstrap_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("[guide]({cypilot_path}/guide.md)\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    node_guide = _make_node("local:.bootstrap/guide.md", ".bootstrap/guide.md")
    template_vars = {"cypilot_path": ".bootstrap"}
    result = extract_file_links([node_a, node_guide], project_root=tmp_path,
                                template_vars=template_vars)
    pairs = {(e.from_id, e.to_id) for e in result}
    assert ("local:a.md", "local:.bootstrap/guide.md") in pairs


def test_extract_file_links_var_path_prose_pattern(tmp_path):
    """_VAR_PATH_RE prose pattern {var}/path/to/file.md resolves to a node."""
    bootstrap_dir = tmp_path / ".bootstrap"
    bootstrap_dir.mkdir()
    (bootstrap_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (tmp_path / "a.md").write_text(
        "See `{cypilot_path}/spec.md` for details.\n",
        encoding="utf-8",
    )
    node_a = _make_node("local:a.md", "a.md")
    node_spec = _make_node("local:.bootstrap/spec.md", ".bootstrap/spec.md")
    template_vars = {"cypilot_path": ".bootstrap"}
    result = extract_file_links([node_a, node_spec], project_root=tmp_path,
                                template_vars=template_vars)
    pairs = {(e.from_id, e.to_id) for e in result}
    assert ("local:a.md", "local:.bootstrap/spec.md") in pairs


def test_extract_file_links_no_duplicate_edges(tmp_path):
    """Same link target referenced twice in one file produces only one edge."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (tmp_path / "a.md").write_text(
        "[foo](docs/foo.md)\n\n[foo again](docs/foo.md)\n",
        encoding="utf-8",
    )
    (docs_dir / "foo.md").write_text("# Foo\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md")
    node_foo = _make_node("local:docs/foo.md", "docs/foo.md")
    result = extract_file_links([node_a, node_foo], project_root=tmp_path)
    pairs = [(e.from_id, e.to_id) for e in result]
    assert pairs.count(("local:a.md", "local:docs/foo.md")) == 1


def test_extract_file_links_cross_repo_flag(tmp_path):
    """Links between nodes from different sources have cross_repo=True."""
    (tmp_path / "a.md").write_text("[b](b.md)\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md", source="source1")
    node_b = _make_node("source2:b.md", "b.md", source="source2")
    result = extract_file_links([node_a, node_b], project_root=tmp_path)
    cross_repo_edges = [e for e in result if e.cross_repo]
    assert len(cross_repo_edges) == 1


def test_extract_file_links_same_source_not_cross_repo(tmp_path):
    """Links between nodes in same source have cross_repo=False."""
    (tmp_path / "a.md").write_text("[b](b.md)\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    node_a = _make_node("local:a.md", "a.md", source="local")
    node_b = _make_node("local:b.md", "b.md", source="local")
    result = extract_file_links([node_a, node_b], project_root=tmp_path)
    assert all(not e.cross_repo for e in result)


# ---------------------------------------------------------------------------
# _load_markdown_content
# ---------------------------------------------------------------------------

def test_load_markdown_content_existing_file(tmp_path):
    """_load_markdown_content returns content string for existing file."""
    (tmp_path / "test.md").write_text("# Hello\nWorld\n", encoding="utf-8")
    result = _load_markdown_content(tmp_path, "test.md")
    assert result is not None
    assert "Hello" in result


def test_load_markdown_content_missing_file(tmp_path):
    """_load_markdown_content returns None for missing file."""
    result = _load_markdown_content(tmp_path, "nonexistent.md")
    assert result is None


def test_load_markdown_content_empty_file(tmp_path):
    """_load_markdown_content returns None for empty file."""
    (tmp_path / "empty.md").write_text("", encoding="utf-8")
    result = _load_markdown_content(tmp_path, "empty.md")
    # Empty file → read_text_safe returns None or empty → _load returns None
    assert result is None


# ---------------------------------------------------------------------------
# _resolve
# ---------------------------------------------------------------------------

def test_resolve_http_url_returns_none():
    """_resolve returns None for http:// targets."""
    result = _resolve("docs/a.md", "http://example.com/foo", set())
    assert result is None


def test_resolve_https_url_returns_none():
    """_resolve returns None for https:// targets."""
    result = _resolve("docs/a.md", "https://example.com/foo", set())
    assert result is None


def test_resolve_mailto_returns_none():
    """_resolve returns None for mailto: targets."""
    result = _resolve("docs/a.md", "mailto:foo@bar.com", set())
    assert result is None


def test_resolve_empty_target_returns_none():
    """_resolve returns None for empty target."""
    result = _resolve("docs/a.md", "", set())
    assert result is None


def test_resolve_anchor_only_returns_none():
    """_resolve returns None when target becomes empty after stripping fragment."""
    result = _resolve("docs/a.md", "#section", set())
    assert result is None


def test_resolve_query_string_stripped():
    """_resolve strips query string before resolving."""
    known = {"docs/b.md"}
    result = _resolve("docs/a.md", "b.md?query=1", known)
    assert result == "docs/b.md"


def test_resolve_fragment_stripped():
    """_resolve strips fragment before resolving."""
    known = {"docs/b.md"}
    result = _resolve("docs/a.md", "b.md#section", known)
    assert result == "docs/b.md"


def test_resolve_relative_path():
    """_resolve resolves relative paths from source dir."""
    known = {"docs/b.md"}
    result = _resolve("docs/a.md", "b.md", known)
    assert result == "docs/b.md"


def test_resolve_absolute_path():
    """_resolve resolves absolute paths (starting with /)."""
    known = {"docs/b.md"}
    result = _resolve("docs/a.md", "/docs/b.md", known)
    assert result == "docs/b.md"


def test_resolve_no_extension_appends_md():
    """_resolve appends .md when path has no extension."""
    known = {"docs/b.md"}
    result = _resolve("docs/a.md", "b", known)
    assert result == "docs/b.md"


def test_resolve_returns_none_for_unknown():
    """_resolve returns None when path not in known set."""
    known = {"docs/other.md"}
    result = _resolve("docs/a.md", "b.md", known)
    assert result is None


# ---------------------------------------------------------------------------
# _slug_candidates
# ---------------------------------------------------------------------------

def test_slug_candidates_absolute():
    """Absolute target produces base path and .md variant."""
    candidates = _slug_candidates("docs/a.md", "/foo/bar.md")
    assert "foo/bar.md" in candidates


def test_slug_candidates_relative():
    """Relative target is joined with source dir."""
    candidates = _slug_candidates("docs/a.md", "b.md")
    assert "docs/b.md" in candidates


def test_slug_candidates_dotdot():
    """Targets with .. are resolved via normpath."""
    candidates = _slug_candidates("docs/sub/a.md", "../b.md")
    assert "docs/b.md" in candidates


def test_slug_candidates_no_dir():
    """Source at root level still resolves correctly."""
    candidates = _slug_candidates("a.md", "b.md")
    assert "b.md" in candidates


def test_slug_candidates_no_extension_appends_md():
    """When target has no .md extension, a .md variant is added."""
    candidates = _slug_candidates("docs/a.md", "b")
    assert "docs/b" in candidates or "docs/b.md" in candidates
    assert any(c.endswith(".md") for c in candidates)


# ---------------------------------------------------------------------------
# _posix_normpath
# ---------------------------------------------------------------------------

def test_posix_normpath_double_dot():
    """_posix_normpath resolves .. segments."""
    result = _posix_normpath("a/b/../c")
    assert result == "a/c"


def test_posix_normpath_single_dot():
    """_posix_normpath resolves . segments."""
    result = _posix_normpath("a/./b")
    assert result == "a/b"


def test_posix_normpath_double_slash():
    """_posix_normpath collapses double slashes."""
    result = _posix_normpath("a//b")
    assert result == "a/b"


def test_posix_normpath_leading_dotdot():
    """_posix_normpath handles leading .. (can't go above root)."""
    result = _posix_normpath("../a/b")
    assert result == "a/b"


# ---------------------------------------------------------------------------
# _expand_vars
# ---------------------------------------------------------------------------

def test_expand_vars_substitutes_known():
    """_expand_vars substitutes known variables."""
    result = _expand_vars("{foo}/bar.md", {"foo": "baz"})
    assert result == "baz/bar.md"


def test_expand_vars_leaves_unknown():
    """_expand_vars leaves unknown variables intact."""
    result = _expand_vars("{unknown}/bar.md", {"foo": "baz"})
    assert result == "{unknown}/bar.md"


def test_expand_vars_no_braces():
    """_expand_vars with no braces returns original."""
    result = _expand_vars("plain/path.md", {"foo": "baz"})
    assert result == "plain/path.md"


def test_expand_vars_empty_vars():
    """_expand_vars with empty vars dict returns original."""
    result = _expand_vars("{foo}/bar.md", {})
    assert result == "{foo}/bar.md"


def test_expand_vars_multiple_vars():
    """_expand_vars substitutes multiple variables."""
    result = _expand_vars("{a}/{b}/c.md", {"a": "x", "b": "y"})
    assert result == "x/y/c.md"
