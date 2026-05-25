"""Tests for markdown file-link extraction."""
from pathlib import Path

from studio.commands.map.links import extract_file_links
from studio.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def test_overview_links_to_architecture():
    project_root = FIXTURES / "repo-basic"
    nodes = scan_repo(ScanOptions(project_root=project_root, source_name="local"))
    edges = extract_file_links(nodes, project_root=project_root)
    pairs = {(e.from_id, e.to_id) for e in edges}
    assert ("local:docs/overview.md", "local:docs/architecture.md") in pairs


def test_architecture_links_to_cli():
    project_root = FIXTURES / "repo-basic"
    nodes = scan_repo(ScanOptions(project_root=project_root, source_name="local"))
    edges = extract_file_links(nodes, project_root=project_root)
    pairs = {(e.from_id, e.to_id) for e in edges}
    assert ("local:docs/architecture.md", "local:docs/cli.md") in pairs


def test_no_self_links():
    project_root = FIXTURES / "repo-basic"
    nodes = scan_repo(ScanOptions(project_root=project_root, source_name="local"))
    edges = extract_file_links(nodes, project_root=project_root)
    for e in edges:
        assert e.from_id != e.to_id


def test_source_nodes_never_originate_or_target_file_links():
    project_root = FIXTURES / "repo-basic"
    nodes = scan_repo(ScanOptions(project_root=project_root, source_name="local"))
    edges = extract_file_links(nodes, project_root=project_root)
    md_ids = {n.id for n in nodes if n.kind == "markdown"}
    for e in edges:
        assert e.from_id in md_ids
        assert e.to_id in md_ids
        assert e.type == "file-link"
