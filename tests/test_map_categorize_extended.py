"""Extended tests for categorize.py.

Covers uncovered lines: 49-50, 54-56, 99-100, 102-103, 145-146.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from studio.commands.map.categorize import (
    CategorizeOptions,
    OverrideCategory,
    OverrideConfig,
    _build_registry_index,
    _glob_match,
    _match_override,
    _match_registry,
    _parent_dir_category,
    categorize_nodes,
)
from studio.commands.map.model import Node

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_BASIC = FIXTURES / "repo-basic"
REPO_NO_REGISTRY = FIXTURES / "repo-no-registry"


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


# ---------------------------------------------------------------------------
# phantom nodes get _undefined category
# ---------------------------------------------------------------------------

def test_phantom_nodes_get_undefined_category():
    """Phantom nodes should always get category=_undefined and origin=phantom."""
    phantom = Node(
        id="phantom:cpt-missing:p1",
        rel_path=None,
        source=None,
        kind="phantom-cpt",
        language=None,
        category="",
        category_origin="parent-dir",
        content=None,
        loc=0,
    )
    categorize_nodes([phantom], CategorizeOptions(
        project_root=REPO_BASIC, override=None,
    ))
    assert phantom.category == "_undefined"
    assert phantom.category_origin == "phantom"


def test_phantom_nodes_with_override_still_get_undefined():
    """Even with an override, phantom nodes get _undefined (phantom check is first)."""
    phantom = Node(
        id="phantom:cpt-unknown:p1",
        rel_path=None,
        source=None,
        kind="phantom-cpt",
        language=None,
        category="",
        category_origin="parent-dir",
        content=None,
        loc=0,
    )
    override = OverrideConfig(categories=[
        OverrideCategory(name="forced", paths=["**"], color=None, background=None),
    ])
    categorize_nodes([phantom], CategorizeOptions(
        project_root=REPO_BASIC, override=override,
    ))
    assert phantom.category == "_undefined"
    assert phantom.category_origin == "phantom"


# ---------------------------------------------------------------------------
# override with color != None vs None
# ---------------------------------------------------------------------------

def test_override_category_with_non_null_color():
    """OverrideCategory with non-null color is stored correctly."""
    cat = OverrideCategory(name="test", paths=["docs/**"], color="#ff0000", background="#eeeeff")
    assert cat.color == "#ff0000"
    assert cat.background == "#eeeeff"


def test_override_category_with_null_color():
    """OverrideCategory with None color is stored correctly."""
    cat = OverrideCategory(name="test", paths=["docs/**"], color=None, background=None)
    assert cat.color is None
    assert cat.background is None


# ---------------------------------------------------------------------------
# _match_override with no override config
# ---------------------------------------------------------------------------

def test_match_override_no_categories():
    """_match_override with empty categories list returns None."""
    override = OverrideConfig(categories=[])
    result = _match_override("docs/a.md", override)
    assert result is None


def test_match_override_single_category_match():
    """_match_override returns category name when path matches."""
    override = OverrideConfig(categories=[
        OverrideCategory(name="infra", paths=["infra/**"], color=None, background=None),
    ])
    result = _match_override("infra/setup.md", override)
    assert result == "infra"


def test_match_override_no_match():
    """_match_override returns None when no pattern matches."""
    override = OverrideConfig(categories=[
        OverrideCategory(name="infra", paths=["infra/**"], color=None, background=None),
    ])
    result = _match_override("docs/a.md", override)
    assert result is None


def test_match_override_multiple_categories_first_wins():
    """_match_override returns the first matching category."""
    override = OverrideConfig(categories=[
        OverrideCategory(name="first", paths=["docs/**"], color=None, background=None),
        OverrideCategory(name="second", paths=["docs/a.md"], color=None, background=None),
    ])
    result = _match_override("docs/a.md", override)
    assert result == "first"


# ---------------------------------------------------------------------------
# _glob_match with ? wildcard
# ---------------------------------------------------------------------------

def test_glob_match_question_mark():
    """_glob_match with ? matches exactly one non-/ character."""
    # Using ** path so we enter the regex branch
    assert _glob_match("doc?/**", "docs/a.md") is True
    assert _glob_match("doc?/**", "documentation/a.md") is False


def test_glob_match_double_star():
    """_glob_match with ** matches any path segments."""
    assert _glob_match("docs/**", "docs/sub/a.md") is True
    assert _glob_match("docs/**", "other/a.md") is False


def test_glob_match_single_star_no_slash():
    """_glob_match with * (no **) matches within segment via fnmatch."""
    # fnmatch.fnmatch uses *, which matches any sequence including /
    assert _glob_match("docs/*.md", "docs/a.md") is True
    # fnmatch.fnmatch allows * to match across /, so this returns True
    assert _glob_match("docs/*.md", "docs/sub/a.md") is True


def test_glob_match_exact_path():
    """_glob_match with exact path matches only that path."""
    assert _glob_match("docs/cli.md", "docs/cli.md") is True
    assert _glob_match("docs/cli.md", "docs/other.md") is False


def test_glob_match_star_in_non_double_star_mode():
    """_glob_match falls through to fnmatch when no **."""
    assert _glob_match("docs/*", "docs/a.md") is True
    assert _glob_match("docs/*", "docs/b.md") is True
    assert _glob_match("docs/*", "other/a.md") is False


def test_glob_match_question_mark_no_double_star(tmp_path):
    """_glob_match with ? but no ** uses fnmatch."""
    # fnmatch.fnmatch handles ? as any single character
    assert _glob_match("docs/?.md", "docs/a.md") is True
    assert _glob_match("docs/?.md", "docs/ab.md") is False


def test_glob_match_regex_special_chars():
    """_glob_match with regex special chars in pattern doesn't fail."""
    # Dots and parens in path names need escaping
    result = _glob_match("docs/my.file/**", "docs/my.file/a.md")
    assert result is True


# ---------------------------------------------------------------------------
# _build_registry_index edge cases
# ---------------------------------------------------------------------------

def test_build_registry_index_no_artifacts_toml(tmp_path):
    """_build_registry_index returns empty list when no artifacts.toml exists."""
    result = _build_registry_index(tmp_path)
    assert result == []


def test_build_registry_index_invalid_toml(tmp_path):
    """_build_registry_index returns empty list when artifacts.toml is broken."""
    (tmp_path / "artifacts.toml").write_bytes(b"\xff\xfe [[[invalid")
    result = _build_registry_index(tmp_path)
    assert result == []


def test_build_registry_index_valid(tmp_path):
    """_build_registry_index with valid artifacts.toml returns entries."""
    (tmp_path / "artifacts.toml").write_text(
        'version = "1.2"\n'
        'project_root = "."\n'
        '[[systems]]\n'
        'slug = "myapp"\n'
        '[[systems.artifacts]]\n'
        'path = "docs/spec.md"\n'
        '[[systems.codebase]]\n'
        'path = "src"\n'
        'extensions = [".py"]\n',
        encoding="utf-8",
    )
    result = _build_registry_index(tmp_path)
    assert len(result) > 0
    paths = [e.path_prefix for e in result]
    assert "docs/spec.md" in paths or any("spec.md" in p for p in paths)


# ---------------------------------------------------------------------------
# _match_registry
# ---------------------------------------------------------------------------

def test_match_registry_exact_match():
    """_match_registry returns category for exact path match."""
    from studio.commands.map.categorize import _RegistryEntry
    index = [_RegistryEntry(path_prefix="docs/spec.md", category="myapp")]
    result = _match_registry("docs/spec.md", index)
    assert result == "myapp"


def test_match_registry_prefix_match():
    """_match_registry returns category when path starts with prefix/."""
    from studio.commands.map.categorize import _RegistryEntry
    index = [_RegistryEntry(path_prefix="src", category="myapp")]
    result = _match_registry("src/module.py", index)
    assert result == "myapp"


def test_match_registry_no_match():
    """_match_registry returns None when no prefix matches."""
    from studio.commands.map.categorize import _RegistryEntry
    index = [_RegistryEntry(path_prefix="docs", category="myapp")]
    result = _match_registry("src/module.py", index)
    assert result is None


# ---------------------------------------------------------------------------
# _parent_dir_category
# ---------------------------------------------------------------------------

def test_parent_dir_category_at_root():
    """File at root level returns _root."""
    result = _parent_dir_category("README.md")
    assert result == "_root"


def test_parent_dir_category_one_level_deep():
    """File one level deep returns parent dir name."""
    result = _parent_dir_category("docs/spec.md")
    assert result == "docs"


def test_parent_dir_category_nested():
    """File nested deeply returns immediate parent dir."""
    result = _parent_dir_category("a/b/c/file.md")
    assert result == "c"


# ---------------------------------------------------------------------------
# categorize_nodes: override.color handling in _match_override
# ---------------------------------------------------------------------------

def test_categorize_with_per_source_roots():
    """categorize_nodes uses per-source registry when source_roots is provided."""
    from studio.commands.map.scan import ScanOptions, scan_repo

    nodes = scan_repo(ScanOptions(project_root=REPO_BASIC, source_name="local"))
    opts = CategorizeOptions(
        project_root=REPO_BASIC,
        override=None,
        source_roots={"local": REPO_BASIC},
    )
    categorize_nodes(nodes, opts)
    by_id = {n.id: n for n in nodes}
    assert by_id["local:docs/cli.md"].category_origin == "registry"


def test_categorize_with_unknown_source_falls_back_to_primary():
    """categorize_nodes uses primary registry when node source not in source_roots."""
    from studio.commands.map.scan import ScanOptions, scan_repo

    nodes = scan_repo(ScanOptions(project_root=REPO_BASIC, source_name="other"))
    opts = CategorizeOptions(
        project_root=REPO_BASIC,
        override=None,
        source_roots={"local": REPO_BASIC},  # "other" is not here
    )
    categorize_nodes(nodes, opts)
    # Should still produce valid categories (falling back to primary = repo-basic registry)
    for n in nodes:
        assert n.category != ""


def test_categorize_no_source_roots():
    """categorize_nodes without source_roots works correctly."""
    from studio.commands.map.scan import ScanOptions, scan_repo

    nodes = scan_repo(ScanOptions(project_root=REPO_BASIC, source_name="local"))
    opts = CategorizeOptions(
        project_root=REPO_BASIC,
        override=None,
        source_roots=None,
    )
    categorize_nodes(nodes, opts)
    for n in nodes:
        assert n.category != ""


def test_categorize_node_with_no_rel_path():
    """Node with rel_path=None falls back to parent-dir logic."""
    node = _make_node("local:orphan", rel_path=None)
    categorize_nodes([node], CategorizeOptions(
        project_root=REPO_BASIC, override=None,
    ))
    assert node.category == "_root"
    assert node.category_origin == "parent-dir"
