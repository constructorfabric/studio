"""Tests for per-edge content baking via get_content_scoped (or manual fallback)."""
from pathlib import Path

from studio.commands.map.cpt_edges import build_cpt_edges
from studio.commands.map.enrich import enrich_edges
from studio.commands.map.links import extract_file_links
from studio.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def test_cpt_edges_get_def_snippet_baked():
    project = FIXTURES / "repo-basic"
    nodes = scan_repo(ScanOptions(project_root=project, source_name="local"))
    edges, phantoms = build_cpt_edges(nodes)
    enrich_edges(edges, list(nodes) + list(phantoms),
                 project_root_by_source={"local": project})

    cpt_edges = [e for e in edges if e.type in ("cpt-doc", "cpt-impl")]
    assert cpt_edges, "no cpt edges to enrich"
    for e in cpt_edges:
        if e.dangling:
            continue
        for r in e.refs:
            assert r.def_line is not None, f"def_line missing for {e.id}"
            assert r.def_snippet, f"def_snippet missing for {e.id}"


def test_file_links_are_unchanged_by_enrich():
    project = FIXTURES / "repo-basic"
    nodes = scan_repo(ScanOptions(project_root=project, source_name="local"))
    edges = extract_file_links(nodes, project_root=project)
    snapshot = [(e.id, e.refs[0].def_line, e.refs[0].def_snippet) for e in edges]
    enrich_edges(edges, list(nodes), project_root_by_source={"local": project})
    after = [(e.id, e.refs[0].def_line, e.refs[0].def_snippet) for e in edges]
    assert snapshot == after  # file-link refs untouched


def test_dangling_edges_have_no_def_snippet():
    project = FIXTURES / "repo-dangling"
    nodes = scan_repo(ScanOptions(project_root=project, source_name="local"))
    edges, phantoms = build_cpt_edges(nodes)
    enrich_edges(edges, list(nodes) + list(phantoms),
                 project_root_by_source={"local": project})
    saw_dangling = False
    for e in edges:
        if e.dangling:
            saw_dangling = True
            for r in e.refs:
                assert r.def_line is None and r.def_snippet is None
    assert saw_dangling, "expected at least one dangling edge"
