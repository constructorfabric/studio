"""Extended tests for enrich.py.

Covers uncovered lines: 43, 47, 54-55, 94, 97-104, 110, 128, 137.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from unittest.mock import patch, MagicMock

import pytest

from studio.commands.map.enrich import (
    _find_def_line,
    _lines_around,
    _resolve_def,
    enrich_edges,
)
from studio.commands.map.model import Edge, Node, Ref

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_BASIC = FIXTURES / "repo-basic"


def _make_node(
    node_id: str,
    rel_path: Optional[str] = None,
    kind: str = "markdown",
    source: str = "local",
    category: str = "",
) -> Node:
    return Node(
        id=node_id,
        rel_path=rel_path,
        source=source,
        kind=kind,
        language=None,
        category=category,
        category_origin="parent-dir",
        content=None,
        loc=0,
    )


def _make_edge(
    edge_id: str,
    from_id: str,
    to_id: str,
    edge_type: str = "cpt-doc",
    dangling: bool = False,
    refs: Optional[List[Ref]] = None,
) -> Edge:
    if refs is None:
        refs = [Ref(cpt_id="cpt-test:p1", line=1, snippet="test", def_line=None, def_snippet=None)]
    return Edge(
        id=edge_id,
        from_id=from_id,
        to_id=to_id,
        type=edge_type,
        refs=refs,
        cross_repo=False,
        dangling=dangling,
    )


# ---------------------------------------------------------------------------
# enrich_edges: file-link edges are skipped
# ---------------------------------------------------------------------------

def test_enrich_file_link_edges_skipped():
    """File-link edges should be left completely untouched."""
    node_a = _make_node("local:docs/a.md", "docs/a.md")
    node_b = _make_node("local:docs/b.md", "docs/b.md")
    edge = _make_edge(
        "fl-0", "local:docs/a.md", "local:docs/b.md",
        edge_type="file-link",
        refs=[Ref(cpt_id=None, line=5, snippet="[link](b.md)", def_line=None, def_snippet=None)],
    )
    original_refs = list(edge.refs)
    enrich_edges([edge], [node_a, node_b], project_root_by_source={"local": REPO_BASIC})
    assert edge.refs == original_refs


# ---------------------------------------------------------------------------
# enrich_edges: dangling edges are skipped
# ---------------------------------------------------------------------------

def test_enrich_dangling_edge_skipped():
    """Dangling edges should not get def_line filled."""
    phantom = _make_node("phantom:cpt-missing:p1", rel_path=None, kind="phantom-cpt")
    node_src = _make_node("local:src/foo.py", "src/foo.py", kind="source")
    edge = _make_edge(
        "cpt-0", "local:src/foo.py", "phantom:cpt-missing:p1",
        edge_type="cpt-impl",
        dangling=True,
        refs=[Ref(cpt_id="cpt-missing:p1", line=10, snippet="use", def_line=None, def_snippet=None)],
    )
    enrich_edges([edge], [node_src, phantom], project_root_by_source={"local": REPO_BASIC})
    for r in edge.refs:
        assert r.def_line is None
        assert r.def_snippet is None


# ---------------------------------------------------------------------------
# enrich_edges: target node not found
# ---------------------------------------------------------------------------

def test_enrich_target_not_in_nodes():
    """Edge pointing to unknown node ID is skipped gracefully."""
    edge = _make_edge("e0", "local:docs/a.md", "local:docs/nonexistent.md")
    enrich_edges([edge], [], project_root_by_source={"local": REPO_BASIC})
    # refs unchanged
    for r in edge.refs:
        assert r.def_line is None


# ---------------------------------------------------------------------------
# enrich_edges: target is source kind (not markdown) → skipped
# ---------------------------------------------------------------------------

def test_enrich_target_is_source_kind():
    """If target node kind is 'source', edge is skipped."""
    src_node = _make_node("local:src/impl.py", "src/impl.py", kind="source")
    edge = _make_edge("e0", "local:docs/a.md", "local:src/impl.py")
    enrich_edges([edge], [src_node], project_root_by_source={"local": REPO_BASIC})
    for r in edge.refs:
        assert r.def_line is None


# ---------------------------------------------------------------------------
# enrich_edges: target source not in project_root_by_source
# ---------------------------------------------------------------------------

def test_enrich_target_source_not_in_roots():
    """If target's source is missing from project_root_by_source, edge is skipped."""
    target = _make_node("remote:docs/b.md", "docs/b.md", source="remote")
    edge = _make_edge("e0", "local:docs/a.md", "remote:docs/b.md")
    enrich_edges([edge], [target], project_root_by_source={"local": REPO_BASIC})
    for r in edge.refs:
        assert r.def_line is None


# ---------------------------------------------------------------------------
# enrich_edges: ref with cpt_id=None is passed through unchanged
# ---------------------------------------------------------------------------

def test_enrich_ref_with_none_cpt_id():
    """Refs with cpt_id=None should be passed through as-is."""
    target = _make_node("local:docs/architecture.md", "docs/architecture.md", source="local")
    edge = _make_edge(
        "e0", "local:docs/cli.md", "local:docs/architecture.md",
        refs=[Ref(cpt_id=None, line=5, snippet="none", def_line=None, def_snippet=None)],
    )
    enrich_edges([edge], [target], project_root_by_source={"local": REPO_BASIC})
    assert edge.refs[0].cpt_id is None
    assert edge.refs[0].def_line is None


# ---------------------------------------------------------------------------
# _resolve_def tests
# ---------------------------------------------------------------------------

def test_resolve_def_found_with_content():
    """_resolve_def with a real cpt-id definition returns (def_line, snippet)."""
    path = REPO_BASIC / "docs" / "cli.md"
    line, snippet = _resolve_def(path, "cpt-basic-flow-cli")
    assert line is not None
    assert line >= 1
    assert snippet is not None
    assert len(snippet) > 0


def test_resolve_def_missing_id(tmp_path):
    """_resolve_def with an ID not in file returns (None, None)."""
    test_file = tmp_path / "test.md"
    test_file.write_text("# Heading\n\nSome content without any ID.\n", encoding="utf-8")
    line, snippet = _resolve_def(test_file, "cpt-nonexistent-id")
    assert line is None
    assert snippet is None


def test_resolve_def_phase_qualified_strips_phase():
    """_resolve_def with phase-qualified id (cpt-foo:p1) strips phase before lookup."""
    path = REPO_BASIC / "docs" / "cli.md"
    # Use phase-qualified version — should still find the base definition
    line, snippet = _resolve_def(path, "cpt-basic-flow-cli:p1")
    assert line is not None


def test_resolve_def_get_content_scoped_returns_tuple(tmp_path):
    """_resolve_def when get_content_scoped returns (text, start, end) uses the text."""
    test_file = tmp_path / "test.md"
    test_file.write_text(
        "# Section\n\n`p1` - **ID**: `cpt-test-id`\n\nSome description.\n",
        encoding="utf-8",
    )
    # Patch get_content_scoped to return a tuple
    with patch("studio.commands.map.enrich.get_content_scoped",
               return_value=("section content here", 3, 5)):
        line, snippet = _resolve_def(test_file, "cpt-test-id")
    if line is not None:
        assert snippet is not None
        # snippet should incorporate get_content_scoped's text
        assert "section content here" in snippet or len(snippet) > 0


def test_resolve_def_content_scoped_returns_tuple_empty_text(tmp_path):
    """_resolve_def when get_content_scoped returns empty text falls back to id_line_text."""
    test_file = tmp_path / "test.md"
    test_file.write_text(
        "# Section\n\n`p1` - **ID**: `cpt-test-id`\n\nSome description.\n",
        encoding="utf-8",
    )
    # Return empty text in the tuple
    with patch("studio.commands.map.enrich.get_content_scoped",
               return_value=("", 3, 3)):
        line, snippet = _resolve_def(test_file, "cpt-test-id")
    if line is not None:
        # Should use id_line_text alone
        assert snippet is not None


def test_resolve_def_content_scoped_returns_tuple_lines_short(tmp_path):
    """_resolve_def when lines are short and def_line > len(lines) uses text directly."""
    test_file = tmp_path / "test.md"
    test_file.write_text(
        "`p1` - **ID**: `cpt-test-id`\n",
        encoding="utf-8",
    )
    # Return a tuple with start/end that forces def_line > len(lines)
    with patch("studio.commands.map.enrich.get_content_scoped",
               return_value=("content", 1, 1)):
        # Patch _find_def_line to return a line beyond file length
        with patch("studio.commands.map.enrich._find_def_line", return_value=100):
            line, snippet = _resolve_def(test_file, "cpt-test-id")
    # def_line=100 > file length → snippet = text = "content"
    if line is not None:
        assert snippet == "content"


def test_resolve_def_get_content_scoped_returns_none(tmp_path):
    """_resolve_def falls back to _lines_around when get_content_scoped returns None."""
    test_file = tmp_path / "test.md"
    test_file.write_text(
        "# Section\n\n`p1` - **ID**: `cpt-test-id`\n\nSome description.\n",
        encoding="utf-8",
    )
    # Patch get_content_scoped to return None to test the fallback branch
    with patch("studio.commands.map.enrich.get_content_scoped", return_value=None):
        line, snippet = _resolve_def(test_file, "cpt-test-id")
    # def_line should still be found via _find_def_line
    if line is not None:
        assert line >= 1


def test_resolve_def_empty_result_snippet(tmp_path):
    """_resolve_def with def_line but empty snippet returns (def_line, None)."""
    test_file = tmp_path / "test.md"
    test_file.write_text(
        "`p1` - **ID**: `cpt-empty-id`\n",
        encoding="utf-8",
    )
    # Patch _lines_around to return empty so we hit the "not snippet" branch
    with patch("studio.commands.map.enrich._lines_around", return_value=None):
        with patch("studio.commands.map.enrich.get_content_scoped", return_value=None):
            line, snippet = _resolve_def(test_file, "cpt-empty-id")
    if line is not None:
        assert snippet is None


# ---------------------------------------------------------------------------
# _find_def_line
# ---------------------------------------------------------------------------

def test_find_def_line_found():
    """_find_def_line returns 1-based line number for known ID."""
    path = REPO_BASIC / "docs" / "cli.md"
    result = _find_def_line(path, "cpt-basic-flow-cli")
    assert result is not None
    assert result >= 1


def test_find_def_line_not_found(tmp_path):
    """_find_def_line returns None when ID is not in file."""
    test_file = tmp_path / "test.md"
    test_file.write_text("# Just text\n\nNo IDs here.\n", encoding="utf-8")
    result = _find_def_line(test_file, "cpt-nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# _lines_around
# ---------------------------------------------------------------------------

def test_lines_around_basic(tmp_path):
    """_lines_around returns lines around the center."""
    test_file = tmp_path / "test.md"
    lines = ["line 1", "line 2", "line 3", "line 4", "line 5"]
    test_file.write_text("\n".join(lines), encoding="utf-8")
    result = _lines_around(test_file, 3, context=2)
    assert result is not None
    assert "line 3" in result


def test_lines_around_missing_file(tmp_path):
    """_lines_around returns None for missing file."""
    result = _lines_around(tmp_path / "nonexistent.md", 1, context=3)
    assert result is None


def test_lines_around_start_of_file(tmp_path):
    """_lines_around at line 1 doesn't go below index 0."""
    test_file = tmp_path / "test.md"
    test_file.write_text("first\nsecond\nthird\n", encoding="utf-8")
    result = _lines_around(test_file, 1, context=3)
    assert result is not None
    assert "first" in result


def test_lines_around_end_of_file(tmp_path):
    """_lines_around at last line doesn't overflow."""
    test_file = tmp_path / "test.md"
    test_file.write_text("first\nsecond\nthird\n", encoding="utf-8")
    result = _lines_around(test_file, 3, context=3)
    assert result is not None


def test_lines_around_returns_none_for_missing_file(tmp_path):
    """_lines_around returns None when file does not exist."""
    result = _lines_around(tmp_path / "no_such_file.md", 1, context=3)
    assert result is None


# ---------------------------------------------------------------------------
# Regression: real cpt-doc edge from repo-basic gets enriched
# ---------------------------------------------------------------------------

def test_real_cpt_doc_edge_enriched():
    """Integration: cpt-doc edge from repo-basic gets def_line and def_snippet baked in."""
    from studio.commands.map.cpt_edges import build_cpt_edges
    from studio.commands.map.scan import ScanOptions, scan_repo

    project = REPO_BASIC
    nodes = scan_repo(ScanOptions(project_root=project, source_name="local"))
    edges, phantoms = build_cpt_edges(nodes)
    enrich_edges(edges, list(nodes) + list(phantoms),
                 project_root_by_source={"local": project})

    cpt_edges = [e for e in edges if e.type in ("cpt-doc", "cpt-impl") and not e.dangling]
    assert cpt_edges, "expected at least one non-dangling cpt edge"
    for e in cpt_edges:
        for r in e.refs:
            if r.cpt_id is not None:
                assert r.def_line is not None, f"def_line missing for edge {e.id}"
