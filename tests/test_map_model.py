"""Unit tests for cfc map data model."""
from __future__ import annotations

import json
from cypilot.commands.map.model import Node, Edge, Ref, CptUse, node_id, phantom_id


def test_node_id_format():
    assert node_id(source="local", rel_path="docs/cli.md") == "local:docs/cli.md"
    assert node_id(source="shared-kits", rel_path="src/foo.rs") == "shared-kits:src/foo.rs"


def test_phantom_id_format():
    assert phantom_id("cpt-cypilot-flow-foo:p1") == "phantom:cpt-cypilot-flow-foo:p1"


def test_node_to_dict_markdown():
    n = Node(
        id="local:docs/cli.md",
        rel_path="docs/cli.md",
        source="local",
        kind="markdown",
        language=None,
        category="cli",
        category_origin="registry",
        content="# CLI\n",
        loc=1,
        cpt_defs=["cpt-x:p1"],
        cpt_uses=[],
    )
    d = n.to_dict()
    assert d["id"] == "local:docs/cli.md"
    assert d["kind"] == "markdown"
    assert d["language"] is None
    assert d["cpt_defs"] == ["cpt-x:p1"]


def test_node_to_dict_phantom_has_nulls():
    n = Node(
        id="phantom:cpt-x:p1",
        rel_path=None,
        source=None,
        kind="phantom-cpt",
        language=None,
        category="_undefined",
        category_origin="phantom",
        content=None,
        loc=0,
        cpt_defs=[],
        cpt_uses=[],
    )
    d = n.to_dict()
    assert d["rel_path"] is None and d["source"] is None and d["content"] is None


def test_edge_to_dict_includes_refs():
    e = Edge(
        id="e-1",
        from_id="local:src/foo.rs",
        to_id="local:docs/foo.md",
        type="cpt-impl",
        refs=[Ref(cpt_id="cpt-x:p1", line=10, snippet="...", def_line=3, def_snippet="...")],
        cross_repo=False,
        dangling=False,
    )
    d = e.to_dict()
    assert d["from"] == "local:src/foo.rs"
    assert d["to"] == "local:docs/foo.md"
    assert d["type"] == "cpt-impl"
    assert d["refs"][0]["cpt_id"] == "cpt-x:p1"
    assert d["cross_repo"] is False
    assert d["dangling"] is False


def test_edge_to_dict_json_roundtrip():
    e = Edge(
        id="e-2", from_id="a", to_id="b", type="file-link",
        refs=[Ref(cpt_id=None, line=1, snippet="ref", def_line=None, def_snippet=None)],
        cross_repo=False, dangling=False,
    )
    json.dumps(e.to_dict())  # must not raise
