"""Tests for cpt-doc / cpt-impl edges + phantom nodes."""
from pathlib import Path

from studio.commands.map.cpt_edges import build_cpt_edges
from studio.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def test_cpt_doc_edge_from_cli_to_arch():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    edges, phantoms = build_cpt_edges(nodes)
    pairs = {(e.from_id, e.to_id, e.type) for e in edges}
    assert ("local:docs/cli.md", "local:docs/architecture.md", "cpt-doc") in pairs
    assert phantoms == []


def test_cpt_impl_edge_from_runner_py_to_cli_md():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    edges, _phantoms = build_cpt_edges(nodes)
    pairs = {(e.from_id, e.to_id, e.type) for e in edges}
    assert ("local:src/runner.py", "local:docs/cli.md", "cpt-impl") in pairs


def test_cpt_impl_edge_from_rust_to_arch_md():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    edges, _phantoms = build_cpt_edges(nodes)
    pairs = {(e.from_id, e.to_id, e.type) for e in edges}
    assert ("local:src/lib.rs", "local:docs/architecture.md", "cpt-impl") in pairs


def test_dangling_emits_phantom_node():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-dangling", source_name="local"))
    edges, phantoms = build_cpt_edges(nodes)
    assert len(phantoms) == 1
    p = phantoms[0]
    assert p.kind == "phantom-cpt"
    assert p.id == "phantom:cpt-dangling-flow-missing:p1"
    pairs = {(e.from_id, e.to_id, e.type, e.dangling) for e in edges}
    assert ("local:src/bad.py", p.id, "cpt-impl", True) in pairs


def test_no_self_def_to_self_edge():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    edges, _ = build_cpt_edges(nodes)
    for e in edges:
        assert e.from_id != e.to_id
