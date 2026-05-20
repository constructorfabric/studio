"""JSON rendering: shape, determinism, schema."""
import json
import re
from pathlib import Path

from cypilot.commands.map.categorize import CategorizeOptions, categorize_nodes
from cypilot.commands.map.cpt_edges import build_cpt_edges
from cypilot.commands.map.enrich import enrich_edges
from cypilot.commands.map.links import extract_file_links
from cypilot.commands.map.render_json import RenderJsonInput, render_json
from cypilot.commands.map.scan import ScanOptions, scan_repo

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
                                 "nodes", "edges", "dangling_cpt_uses", "categories"}
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
