"""Layout determinism and shape."""
from pathlib import Path

from cypilot.commands.map.categorize import CategorizeOptions, categorize_nodes
from cypilot.commands.map.cpt_edges import build_cpt_edges
from cypilot.commands.map.layout import compute_layout
from cypilot.commands.map.links import extract_file_links
from cypilot.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def _pipeline(project):
    nodes = scan_repo(ScanOptions(project_root=project, source_name="local"))
    categorize_nodes(nodes, CategorizeOptions(project_root=project, override=None))
    file_edges = extract_file_links(nodes)
    cpt_edges, phantoms = build_cpt_edges(nodes)
    nodes_all = list(nodes) + list(phantoms)
    edges = list(file_edges) + list(cpt_edges)
    return nodes_all, edges


def test_layout_is_deterministic():
    nodes, edges = _pipeline(FIXTURES / "repo-basic")
    vis1, b1, c1 = compute_layout(nodes, edges, category_style=None)
    vis2, b2, c2 = compute_layout(nodes, edges, category_style=None)
    assert vis1 == vis2
    assert b1 == b2
    assert c1 == c2


def test_layout_emits_one_band_per_category():
    nodes, edges = _pipeline(FIXTURES / "repo-basic")
    _vis, _b, bands = compute_layout(nodes, edges, category_style=None)
    cats = {n.category for n in nodes}
    assert set(bands.keys()) == cats


def test_layout_vis_nodes_match_input():
    nodes, edges = _pipeline(FIXTURES / "repo-basic")
    vis, _b, _bands = compute_layout(nodes, edges, category_style=None)
    assert {v["id"] for v in vis} == {n.id for n in nodes}


def test_layout_phantom_has_red_style():
    nodes, edges = _pipeline(FIXTURES / "repo-dangling")
    vis, _b, _bands = compute_layout(nodes, edges, category_style=None)
    phantom_vis = [v for v in vis if v["id"].startswith("phantom:")]
    assert phantom_vis, "expected at least one phantom vis node"
    p = phantom_vis[0]
    assert p["shape"] == "diamond"
    assert "c41212" in (p.get("color", {}).get("border", "") or "")
