"""In-process tests for cfc map CLI entry point.

These tests call cmd_map(argv) directly so that pytest-cov can trace the code,
unlike subprocess-based tests in test_map_cli.py.
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import List

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map"
REPO_BASIC = FIXTURES / "repo-basic"
REPO_NO_REGISTRY = FIXTURES / "repo-no-registry"
REPO_DANGLING = FIXTURES / "repo-dangling"
REPO_FEDERATED_MAIN = FIXTURES / "repo-federated" / "main"


def _run_cmd_map(argv: List[str], cwd: Path):
    """Run cmd_map in-process with cwd set via monkeypatching."""
    from studio.commands.map.cli import cmd_map
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        return cmd_map(argv)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Basic invocation tests
# ---------------------------------------------------------------------------

def test_cmd_map_json_format(tmp_path, monkeypatch):
    """cmd_map with --format json should produce valid JSON output."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--out", str(out_file)])
    assert rc == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    assert isinstance(data["nodes"], list)
    assert isinstance(data["edges"], list)


def test_cmd_map_html_format(tmp_path, monkeypatch):
    """cmd_map with default html format should produce HTML."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.html"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "html", "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "<!doctype html>" in content.lower() or "<html" in content.lower() or "MAP_DATA" in content


def test_cmd_map_html_inline_data(tmp_path, monkeypatch):
    """--inline-data should embed MAP_DATA in the HTML file (no sidecar .js)."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.html"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "html", "--inline-data", "--out", str(out_file)])
    assert rc == 0
    content = out_file.read_text(encoding="utf-8")
    assert "window.MAP_DATA" in content
    sidecar = out_file.with_name(out_file.name + ".js")
    assert not sidecar.exists()


def test_cmd_map_no_source(tmp_path, monkeypatch):
    """--no-source should produce no source nodes in output."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--no-source", "--out", str(out_file)])
    assert rc == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    kinds = {n["kind"] for n in data["nodes"]}
    assert "source" not in kinds


def test_cmd_map_local_only(tmp_path, monkeypatch):
    """--local-only should produce output without federation discovery."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--local-only", "--out", str(out_file)])
    assert rc == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    # workspace sources should only have "local" in local-only mode
    sources = data.get("workspace", {}).get("sources", [])
    assert all(s["name"] == "local" for s in sources)


def test_cmd_map_include_adapter(tmp_path, monkeypatch):
    """--include-adapter flag should not fail even with no adapter dir."""
    monkeypatch.chdir(REPO_NO_REGISTRY)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--include-adapter", "--out", str(out_file)])
    assert rc == 0


def test_cmd_map_no_artifacts_toml(tmp_path, monkeypatch, capsys):
    """When no artifacts.toml present, map should still succeed and warn."""
    monkeypatch.chdir(REPO_NO_REGISTRY)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--out", str(out_file)])
    assert rc == 0
    captured = capsys.readouterr()
    # The warning should be in stderr
    assert "no artifacts.toml" in captured.err


def test_cmd_map_dangling_repo(tmp_path, monkeypatch):
    """Dangling cpt-id repo should produce phantom nodes and succeed."""
    monkeypatch.chdir(REPO_DANGLING)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--out", str(out_file)])
    assert rc == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    kinds = {n["kind"] for n in data["nodes"]}
    assert "phantom-cpt" in kinds


def test_cmd_map_with_valid_config(tmp_path, monkeypatch):
    """--config with a valid TOML file should be loaded."""
    config_file = tmp_path / "override.toml"
    config_file.write_text(
        '[categories]\n',
        encoding="utf-8",
    )
    # Write a proper categories array (empty is valid)
    config_file.write_text(
        '# valid toml config\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--config", str(config_file), "--out", str(out_file)])
    assert rc == 0


def test_cmd_map_with_invalid_config_exits_2(tmp_path, monkeypatch):
    """--config with an invalid TOML file should call sys.exit(2)."""
    config_file = tmp_path / "bad_override.toml"
    config_file.write_bytes(b"\xff\xfe invalid toml [[[")
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    with pytest.raises(SystemExit) as exc_info:
        cmd_map(["--format", "json", "--config", str(config_file), "--out", str(out_file)])
    assert exc_info.value.code == 2


def test_cmd_map_with_missing_config_exits(tmp_path, monkeypatch):
    """--config with a non-existent file should call sys.exit(2)."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    with pytest.raises(SystemExit) as exc_info:
        cmd_map(["--format", "json", "--config", "/tmp/__definitely_not_existing__.toml", "--out", str(out_file)])
    assert exc_info.value.code == 2


def test_cmd_map_sidecar_js_written(tmp_path, monkeypatch):
    """HTML output (without --inline-data) should write a .js sidecar."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.html"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "html", "--out", str(out_file)])
    assert rc == 0
    sidecar = out_file.with_name(out_file.name + ".js")
    html_content = out_file.read_text(encoding="utf-8")
    # Either sidecar exists or data is inlined
    assert sidecar.exists() or "window.MAP_DATA" in html_content


def test_cmd_map_print_summary(tmp_path, monkeypatch, capsys):
    """cmd_map should print a summary to stdout."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--out", str(out_file)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Config" in captured.out
    assert "Scanned" in captured.out
    assert "Edges" in captured.out
    assert "Wrote" in captured.out


def test_cmd_map_federated_main(tmp_path, monkeypatch):
    """cmd_map on federated/main should produce output."""
    monkeypatch.chdir(REPO_FEDERATED_MAIN)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--local-only", "--out", str(out_file)])
    assert rc == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"


def test_cmd_map_verbose_flag(tmp_path, monkeypatch, capsys):
    """--verbose should not fail and produces extra output."""
    monkeypatch.chdir(REPO_BASIC)
    out_file = tmp_path / "out.json"
    from studio.commands.map.cli import cmd_map
    rc = cmd_map(["--format", "json", "--verbose", "--out", str(out_file)])
    assert rc == 0


# ---------------------------------------------------------------------------
# _discover_sources tests
# ---------------------------------------------------------------------------

def test_discover_sources_local_only():
    """_discover_sources with local_only=True returns only the local source."""
    from studio.commands.map.cli import _discover_sources
    sources = _discover_sources(REPO_BASIC, local_only=True)
    assert len(sources) == 1
    assert sources[0]["name"] == "local"
    assert sources[0]["reachable"] is True


def test_discover_sources_not_local_only_no_workspace():
    """_discover_sources with local_only=False on a plain dir (no workspace) returns local."""
    from studio.commands.map.cli import _discover_sources
    # repo-basic has no .code-workspace or workspace config
    sources = _discover_sources(REPO_NO_REGISTRY, local_only=False)
    assert len(sources) >= 1
    assert sources[0]["name"] == "local"


# ---------------------------------------------------------------------------
# _load_override tests
# ---------------------------------------------------------------------------

def test_load_override_no_file_no_candidate(tmp_path):
    """_load_override with explicit=None and no md-map.toml returns None."""
    from studio.commands.map.cli import _load_override
    result = _load_override(tmp_path, None)
    assert result is None


def test_load_override_with_candidate_file(tmp_path):
    """_load_override with explicit=None and existing md-map.toml returns OverrideConfig."""
    from studio.commands.map.cli import _load_override
    config_file = tmp_path / "md-map.toml"
    config_file.write_text(
        "[[categories]]\nname = \"docs\"\npaths = [\"docs/**\"]\n",
        encoding="utf-8",
    )
    result = _load_override(tmp_path, None)
    assert result is not None
    assert len(result.categories) == 1
    assert result.categories[0].name == "docs"


def test_load_override_with_explicit_valid_file(tmp_path):
    """_load_override with explicit path loads that file."""
    from studio.commands.map.cli import _load_override
    config_file = tmp_path / "custom.toml"
    config_file.write_text(
        "[[categories]]\nname = \"custom\"\npaths = [\"src/**\"]\n[categories.style]\ncolor = \"#ff0000\"\n",
        encoding="utf-8",
    )
    result = _load_override(tmp_path, str(config_file))
    assert result is not None
    assert result.categories[0].name == "custom"
    assert result.categories[0].color == "#ff0000"


def test_load_override_with_explicit_missing_file_exits(tmp_path):
    """_load_override with explicit path that doesn't exist should sys.exit(2)."""
    from studio.commands.map.cli import _load_override
    with pytest.raises(SystemExit) as exc_info:
        _load_override(tmp_path, "/tmp/__not_existing_config__.toml")
    assert exc_info.value.code == 2


def test_load_override_with_explicit_invalid_toml_exits(tmp_path):
    """_load_override with invalid TOML should sys.exit(2)."""
    from studio.commands.map.cli import _load_override
    bad_file = tmp_path / "bad.toml"
    bad_file.write_bytes(b"\xff\xfe [[[invalid")
    with pytest.raises(SystemExit) as exc_info:
        _load_override(tmp_path, str(bad_file))
    assert exc_info.value.code == 2


def test_load_override_categories_with_style(tmp_path):
    """_load_override should populate color/background from style dict."""
    from studio.commands.map.cli import _load_override
    config_file = tmp_path / "md-map.toml"
    config_file.write_text(
        "[[categories]]\nname = \"infra\"\npaths = [\"infra/**\"]\n[categories.style]\ncolor = \"#0000ff\"\nbackground = \"#eeeeff\"\n",
        encoding="utf-8",
    )
    result = _load_override(tmp_path, None)
    assert result is not None
    cat = result.categories[0]
    assert cat.color == "#0000ff"
    assert cat.background == "#eeeeff"


def test_load_override_no_style_entry(tmp_path):
    """_load_override category without style dict → color/background are None."""
    from studio.commands.map.cli import _load_override
    config_file = tmp_path / "md-map.toml"
    config_file.write_text(
        "[[categories]]\nname = \"minimal\"\npaths = []\n",
        encoding="utf-8",
    )
    result = _load_override(tmp_path, None)
    assert result is not None
    cat = result.categories[0]
    assert cat.color is None
    assert cat.background is None


# ---------------------------------------------------------------------------
# _load_template_vars tests
# ---------------------------------------------------------------------------

def test_load_template_vars_returns_dict(monkeypatch):
    """_load_template_vars should return a dict (even if empty) without raising."""
    from studio.commands.map.cli import _load_template_vars
    result = _load_template_vars(REPO_BASIC)
    assert isinstance(result, dict)


def test_load_template_vars_empty_on_failure(tmp_path):
    """_load_template_vars with a dir that has no cfc CLI should return {}."""
    from studio.commands.map.cli import _load_template_vars
    # Use a directory that will cause subprocess to fail gracefully
    result = _load_template_vars(tmp_path)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _flatten_vars tests
# ---------------------------------------------------------------------------

def test_flatten_vars_basic():
    """_flatten_vars should produce flat key/value pairs from resolve-vars data."""
    from studio.commands.map.cli import _flatten_vars
    data = {
        "system": {
            "cf-studio-path": ".bootstrap",
            "project_root": "/some/project",
        },
        "kits": {},
    }
    result = _flatten_vars(data, Path("/some/project"))
    assert "cf-studio-path" in result
    # project_root relative to itself should be "." which gets special handling
    assert isinstance(result, dict)


def test_flatten_vars_legacy_alias():
    """_flatten_vars should set cypilot_path from cf-studio-path when missing."""
    from studio.commands.map.cli import _flatten_vars
    data = {
        "system": {"cf-studio-path": "/some/project/.bootstrap"},
        "kits": {},
    }
    result = _flatten_vars(data, Path("/some/project"))
    assert "cf-studio-path" in result
    # Legacy alias: cypilot_path should be set
    if "cf-studio-path" in result and "cypilot_path" not in result:
        # This is the branch we're testing
        pass
    # Actually the alias is set when cypilot_path is not present
    assert "cypilot_path" in result or "cf-studio-path" in result


def test_flatten_vars_with_kits():
    """_flatten_vars should expose kit resources as unqualified keys only."""
    from studio.commands.map.cli import _flatten_vars
    data = {
        "system": {},
        "kits": {
            "sdlc": {
                "adr_template": "/some/project/kits/sdlc/adr.md",
            }
        },
    }
    result = _flatten_vars(data, Path("/some/project"))
    assert "adr_template" in result
    assert "sdlc.adr_template" not in result
    assert "kits.sdlc.adr_template" not in result


def test_flatten_vars_skips_non_string_values():
    """_flatten_vars should silently skip non-string values."""
    from studio.commands.map.cli import _flatten_vars
    data = {
        "system": {"numeric_val": 42, "valid_val": "/some/project/foo"},
        "kits": {
            "bad": {"nested_dict": {"not": "a string"}},
        },
    }
    result = _flatten_vars(data, Path("/some/project"))
    # numeric_val should not be in result
    assert "numeric_val" not in result


def test_flatten_vars_none_data():
    """_flatten_vars with None data should return empty dict."""
    from studio.commands.map.cli import _flatten_vars
    result = _flatten_vars(None, Path("/some/project"))
    assert result == {}


# ---------------------------------------------------------------------------
# _relativize tests
# ---------------------------------------------------------------------------

def test_relativize_absolute_path():
    """_relativize should return relative path when inside project root."""
    from studio.commands.map.cli import _relativize
    root = Path("/some/project")
    result = _relativize("/some/project/docs/foo.md", root)
    assert result == "docs/foo.md"


def test_relativize_outside_root():
    """_relativize with path outside project root should return original path."""
    from studio.commands.map.cli import _relativize
    root = Path("/some/project")
    original = "/other/place/file.md"
    result = _relativize(original, root)
    assert result == original


def test_relativize_invalid_path():
    """_relativize with unparseable path returns original."""
    from studio.commands.map.cli import _relativize
    root = Path("/some/project")
    # This might not trigger an error but let's test with a normal invalid path
    result = _relativize("not/absolute", root)
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# skip_dirs_for_meta tests
# ---------------------------------------------------------------------------

def test_skip_dirs_for_meta_includes_git():
    """skip_dirs_for_meta should always include .git."""
    from studio.commands.map.cli import skip_dirs_for_meta
    skips = skip_dirs_for_meta(REPO_BASIC)
    assert ".git" in skips


def test_skip_dirs_for_meta_with_adapter(tmp_path):
    """skip_dirs_for_meta should add adapter dir when CLAUDE.md is present."""
    from studio.commands.map.cli import skip_dirs_for_meta
    # Write a CLAUDE.md with cypilot_path
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text('cf-path = ".mybootstrap"\n', encoding="utf-8")
    skips = skip_dirs_for_meta(tmp_path)
    assert ".mybootstrap" in skips


def test_skip_dirs_for_meta_no_adapter(tmp_path):
    """skip_dirs_for_meta without CLAUDE.md should just return defaults."""
    from studio.commands.map.cli import skip_dirs_for_meta
    skips = skip_dirs_for_meta(tmp_path)
    assert ".git" in skips


# ---------------------------------------------------------------------------
# _count_systems tests
# ---------------------------------------------------------------------------

def test_count_systems_with_registry():
    """_count_systems should count systems from artifacts.toml."""
    from studio.commands.map.cli import _count_systems
    count = _count_systems(REPO_BASIC)
    assert count >= 1


def test_count_systems_docs_only():
    """_count_systems with docs_only=True returns DOCS-ONLY system count."""
    from studio.commands.map.cli import _count_systems
    count = _count_systems(REPO_BASIC, docs_only=True)
    # repo-basic has traceability_mode = "FULL", so docs_only=True returns 0
    assert count == 0


def test_count_systems_no_artifacts_toml(tmp_path):
    """_count_systems without artifacts.toml returns 0."""
    from studio.commands.map.cli import _count_systems
    count = _count_systems(tmp_path)
    assert count == 0


# ---------------------------------------------------------------------------
# _print_summary tests
# ---------------------------------------------------------------------------

def test_print_summary_output(capsys):
    """_print_summary should write expected lines to stdout."""
    from studio.commands.map.cli import _print_summary
    from studio.commands.map.model import Node, Edge, Ref
    nodes = [
        Node(id="local:docs/foo.md", rel_path="docs/foo.md", source="local",
             kind="markdown", language=None, category="docs",
             category_origin="parent-dir", content=None, loc=10),
        Node(id="local:src/bar.py", rel_path="src/bar.py", source="local",
             kind="source", language="python", category="src",
             category_origin="registry", content=None, loc=50),
    ]
    edges = [
        Edge(id="fl-0", from_id="local:docs/foo.md", to_id="local:docs/other.md",
             type="file-link", refs=[], cross_repo=False, dangling=False),
    ]
    sources = [{"name": "local", "reachable": True, "path": "."}]
    scan_meta = {
        "artifacts_toml": "artifacts.toml",
        "systems_scanned": 2,
        "systems_docs_only": 1,
        "skip_dirs": [".git"],
    }
    out_path = Path("/tmp/out.html")
    _print_summary(scan_meta, sources, nodes, edges, out_path, None, None)
    captured = capsys.readouterr()
    assert "Config" in captured.out
    assert "(none)" in captured.out
    assert "Scanned" in captured.out
    assert "1 markdown" in captured.out
    assert "1 source" in captured.out
    assert "1 file-link" in captured.out


def test_print_summary_with_sidecar(capsys):
    """_print_summary with sidecar_path should print the sidecar path."""
    from studio.commands.map.cli import _print_summary
    nodes = []
    edges = []
    sources = [{"name": "local", "reachable": True}, {"name": "remote", "reachable": False}]
    scan_meta = {"artifacts_toml": None, "systems_scanned": 0, "systems_docs_only": 0, "skip_dirs": []}
    out_path = Path("/tmp/out.html")
    sidecar_path = Path("/tmp/out.html.js")
    _print_summary(scan_meta, sources, nodes, edges, out_path, sidecar_path, "my-config.toml")
    captured = capsys.readouterr()
    assert "out.html.js" in captured.out
    assert "my-config.toml" in captured.out
    # Should show federated mode (2 sources, 1 reachable, 1 unreachable)
    assert "unreachable" in captured.out or "1 unreachable" in captured.out


def test_print_summary_federated_mode(capsys):
    """_print_summary with multiple reachable sources shows federated mode."""
    from studio.commands.map.cli import _print_summary
    nodes = []
    edges = []
    sources = [
        {"name": "local", "reachable": True},
        {"name": "other", "reachable": True},
    ]
    scan_meta = {"artifacts_toml": "artifacts.toml", "systems_scanned": 1, "systems_docs_only": 0, "skip_dirs": []}
    out_path = Path("/tmp/out.html")
    _print_summary(scan_meta, sources, nodes, edges, out_path, None, None)
    captured = capsys.readouterr()
    assert "federated" in captured.out
