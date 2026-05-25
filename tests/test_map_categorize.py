"""Tests for category resolution priority chain."""
from pathlib import Path

from studio.commands.map.categorize import (
    CategorizeOptions, OverrideConfig, OverrideCategory, categorize_nodes,
)
from studio.commands.map.scan import ScanOptions, scan_repo

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"


def test_registry_categorizes_markdown_and_source_under_system_slug():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    categorize_nodes(nodes, CategorizeOptions(project_root=FIXTURES / "repo-basic", override=None))
    by_id = {n.id: n for n in nodes}
    assert by_id["local:docs/cli.md"].category == "basic"
    assert by_id["local:docs/cli.md"].category_origin == "registry"
    assert by_id["local:src/runner.py"].category == "basic"
    assert by_id["local:src/runner.py"].category_origin == "registry"


def test_unregistered_markdown_falls_back_to_parent_dir():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    categorize_nodes(nodes, CategorizeOptions(project_root=FIXTURES / "repo-basic", override=None))
    by_id = {n.id: n for n in nodes}
    assert by_id["local:docs/overview.md"].category == "docs"
    assert by_id["local:docs/overview.md"].category_origin == "parent-dir"


def test_no_registry_falls_back_to_parent_dir():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-no-registry", source_name="local"))
    categorize_nodes(nodes, CategorizeOptions(project_root=FIXTURES / "repo-no-registry", override=None))
    by_id = {n.id: n for n in nodes}
    assert by_id["local:README.md"].category == "_root"
    assert by_id["local:docs/spec.md"].category == "docs"


def test_override_wins_over_registry():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    override = OverrideConfig(categories=[
        OverrideCategory(name="hand-picked", paths=["docs/cli.md"], color=None, background=None),
    ])
    categorize_nodes(nodes, CategorizeOptions(project_root=FIXTURES / "repo-basic", override=override))
    by_id = {n.id: n for n in nodes}
    assert by_id["local:docs/cli.md"].category == "hand-picked"
    assert by_id["local:docs/cli.md"].category_origin == "override"
    assert by_id["local:docs/architecture.md"].category == "basic"


def test_first_listed_override_wins_on_collision():
    nodes = scan_repo(ScanOptions(project_root=FIXTURES / "repo-basic", source_name="local"))
    override = OverrideConfig(categories=[
        OverrideCategory(name="first", paths=["docs/**"], color=None, background=None),
        OverrideCategory(name="second", paths=["docs/cli.md"], color=None, background=None),
    ])
    categorize_nodes(nodes, CategorizeOptions(project_root=FIXTURES / "repo-basic", override=override))
    by_id = {n.id: n for n in nodes}
    assert by_id["local:docs/cli.md"].category == "first"
