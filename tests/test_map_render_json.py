"""JSON rendering: shape, determinism, schema."""
import json
import re
from pathlib import Path

from studio.commands.map.categorize import CategorizeOptions, categorize_nodes
from studio.commands.map.cpt_edges import build_cpt_edges
from studio.commands.map.enrich import enrich_edges
from studio.commands.map.layout import compute_layout
from studio.commands.map.links import extract_file_links
from studio.commands.map.render_json import RenderJsonInput, render_json
from studio.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def _build(project):
    nodes = scan_repo(ScanOptions(project_root=project, source_name="local"))
    categorize_nodes(nodes, CategorizeOptions(project_root=project, override=None))
    file_edges = extract_file_links(nodes)
    cpt_edges, phantoms = build_cpt_edges(nodes)
    edges = list(file_edges) + list(cpt_edges)
    nodes_all = list(nodes) + list(phantoms)
    enrich_edges(edges, nodes_all, project_root_by_source={"local": project})
    return nodes_all, edges


def test_json_shape_contains_top_level_keys():
    nodes, edges = _build(FIXTURES / "repo-basic")
    out = render_json(RenderJsonInput(
        nodes=nodes, edges=edges,
        workspace={"primary": "local", "sources": [
            {"name": "local", "path": str(FIXTURES / "repo-basic"), "reachable": True, "role": "full"},
        ]},
        scan={"artifacts_toml": "artifacts.toml", "systems_scanned": 1, "systems_docs_only": 0, "skip_dirs": ["target"]},
    ))
    data = json.loads(out)
    assert set(data.keys()) == {"version", "generated_at", "workspace", "scan",
                                 "nodes", "edges", "dangling_cpt_uses", "categories", "layout"}
    assert data["version"] == "1.0"
    assert data["nodes"] == sorted(data["nodes"], key=lambda n: n["id"])
    assert data["edges"] == sorted(data["edges"], key=lambda e: e["id"])


def test_dangling_section_populated_from_phantoms():
    nodes, edges = _build(FIXTURES / "repo-dangling")
    out = render_json(RenderJsonInput(
        nodes=nodes, edges=edges,
        workspace={"primary": "local", "sources": []},
        scan={"artifacts_toml": "artifacts.toml", "systems_scanned": 1, "systems_docs_only": 0, "skip_dirs": []},
    ))
    data = json.loads(out)
    assert len(data["dangling_cpt_uses"]) >= 1
    entries = {(e["cpt_id"], e["node_id"]) for e in data["dangling_cpt_uses"]}
    assert ("cpt-dangling-flow-missing:p1", "local:src/bad.py") in entries


def test_generated_at_is_iso8601_utc():
    nodes, edges = _build(FIXTURES / "repo-basic")
    out = render_json(RenderJsonInput(
        nodes=nodes, edges=edges,
        workspace={"primary": "local", "sources": []},
        scan={"artifacts_toml": "artifacts.toml", "systems_scanned": 1, "systems_docs_only": 0, "skip_dirs": []},
    ))
    data = json.loads(out)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?$", data["generated_at"])


def test_layout_positions_embedded_in_json():
    """Positions flow end-to-end: compute_layout -> render_json -> layout.vis_nodes."""
    nodes, edges = _build(FIXTURES / "repo-basic")
    vis_nodes, bucket_rects, category_bands = compute_layout(nodes, edges, category_style=None)
    out = render_json(RenderJsonInput(
        nodes=nodes, edges=edges,
        workspace={"primary": "local", "sources": []},
        scan={"artifacts_toml": "artifacts.toml", "systems_scanned": 1, "systems_docs_only": 0, "skip_dirs": []},
        vis_nodes=vis_nodes,
        bucket_rects=bucket_rects,
        category_bands=category_bands,
    ))
    data = json.loads(out)
    assert "layout" in data
    layout = data["layout"]
    assert "vis_nodes" in layout
    assert "bucket_rects" in layout
    assert "category_bands" in layout
    # vis_nodes must be non-empty and each entry must have x and y
    assert len(layout["vis_nodes"]) > 0, "expected non-empty vis_nodes in layout"
    for entry in layout["vis_nodes"]:
        assert "x" in entry, f"missing 'x' in vis_node {entry.get('id')}"
        assert "y" in entry, f"missing 'y' in vis_node {entry.get('id')}"
    # category_bands must cover each category in the dataset
    cats = {n.category for n in nodes}
    assert set(layout["category_bands"].keys()) == cats


def test_layout_empty_when_not_provided():
    """When layout outputs are not provided, layout key still present but empty."""
    nodes, edges = _build(FIXTURES / "repo-basic")
    out = render_json(RenderJsonInput(
        nodes=nodes, edges=edges,
        workspace={"primary": "local", "sources": []},
        scan={"artifacts_toml": "artifacts.toml", "systems_scanned": 1, "systems_docs_only": 0, "skip_dirs": []},
    ))
    data = json.loads(out)
    assert "layout" in data
    layout = data["layout"]
    assert layout["vis_nodes"] == []
    assert layout["bucket_rects"] == {}
    assert layout["category_bands"] == {}
