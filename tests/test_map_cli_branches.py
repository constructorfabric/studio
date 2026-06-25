"""Extra cli.py branch coverage: federation, template-var failure, kit flatten, _count_systems exception."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from studio.commands.map import cli as map_cli


def test_discover_sources_skips_unreachable_path(monkeypatch, tmp_path):
    """An unreachable workspace source (path that does not exist) is skipped
    (resolve_source_path returns None) without crashing federation discovery."""
    primary = tmp_path
    fake_ws = SimpleNamespace(
        sources={"missing": SimpleNamespace(role="full")},
        resolve_source_path=lambda name: None,
    )
    with mock.patch.object(
        map_cli, "_discover_sources", wraps=map_cli._discover_sources
    ):
        with mock.patch(
            "studio.utils.workspace.find_workspace_config",
            return_value=(fake_ws, None),
        ):
            sources = map_cli._discover_sources(primary, local_only=False)
    # local only, missing source filtered
    assert any(s["name"] == "local" for s in sources)
    names = [s["name"] for s in sources]
    assert "missing" not in names


def test_discover_sources_includes_reachable_remote(tmp_path):
    """A workspace source pointing at an existing dir surfaces with reachable=True."""
    remote = tmp_path / "remote"
    remote.mkdir()
    fake_ws = SimpleNamespace(
        sources={"remote": SimpleNamespace(role="artifacts")},
        resolve_source_path=lambda name: remote,
    )
    with mock.patch(
        "studio.utils.workspace.find_workspace_config",
        return_value=(fake_ws, None),
    ):
        sources = map_cli._discover_sources(tmp_path, local_only=False)
    by_name = {s["name"]: s for s in sources}
    assert by_name["remote"]["reachable"] is True
    assert by_name["remote"]["role"] == "artifacts"


def test_load_template_vars_resolution_failures(monkeypatch, tmp_path):
    """When resolve-vars loading fails, return {} gracefully."""
    def raise_oserror(*_a, **_k):
        raise OSError("no executable")

    monkeypatch.setattr(map_cli, "load_resolved_variables", raise_oserror)
    result = map_cli._load_template_vars(tmp_path)
    assert result == {}


def test_load_template_vars_context_unavailable(monkeypatch, tmp_path):
    """Missing project/studio context is a silent best-effort miss."""
    def fake_load(*_a, **_k):
        return None, {"status": "ERROR", "message": "No project root found"}

    monkeypatch.setattr(map_cli, "load_resolved_variables", fake_load)
    assert map_cli._load_template_vars(tmp_path) == {}


def test_load_template_vars_missing_data(monkeypatch, tmp_path):
    """A loader that returns no data still yields an empty template-var map."""
    def fake_load(*_a, **_k):
        return None, None

    monkeypatch.setattr(map_cli, "load_resolved_variables", fake_load)
    assert map_cli._load_template_vars(tmp_path) == {}


def test_build_map_graph_loads_template_vars_per_source(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    remote = tmp_path / "remote"
    primary.mkdir()
    remote.mkdir()
    calls: list[Path] = []

    monkeypatch.setattr(
        map_cli,
        "_collect_nodes_for_sources",
        lambda _sources, _args: ([], {"local": primary, "remote": remote}),
    )
    monkeypatch.setattr(map_cli, "categorize_nodes", lambda *_a, **_k: None)
    monkeypatch.setattr(map_cli, "_apply_override_filter", lambda nodes, _override: nodes)
    monkeypatch.setattr(map_cli, "build_cpt_edges", lambda _nodes: ([], []))
    monkeypatch.setattr(map_cli, "_apply_phantom_override", lambda nodes, edges, _override: (nodes, edges))
    monkeypatch.setattr(map_cli, "enrich_edges", lambda *_a, **_k: None)
    monkeypatch.setattr(
        map_cli,
        "_load_template_vars",
        lambda root: calls.append(root) or {"project_root": root.name},
    )
    captured: dict = {}
    monkeypatch.setattr(
        map_cli,
        "extract_file_links",
        lambda nodes, **kwargs: captured.update(kwargs) or [],
    )

    map_cli._build_map_graph(primary, object(), [{"name": "local"}, {"name": "remote"}], None)

    assert calls == [primary, primary, remote]
    assert captured["template_vars_by_source"]["remote"]["project_root"] == "remote"


def test_flatten_vars_with_nested_kits(tmp_path):
    """Canonical variables produce only unqualified lookup keys."""
    data = {
        "system": {"project_root": str(tmp_path), "cf-studio-path": str(tmp_path / ".bootstrap")},
        "variables": {
            "adr_template": str(tmp_path / "kits" / "sdlc" / "ADR.md"),
            "non_string": 42,  # skipped
        },
        "kits": {
            "sdlc": {
                "adr_template": str(tmp_path / "kits" / "other" / "ADR.md"),
            },
            "broken": "not-a-dict",  # skipped
        },
    }
    flat = map_cli._flatten_vars(data, tmp_path)
    assert flat["adr_template"] == "kits/sdlc/ADR.md"
    assert "sdlc.adr_template" not in flat
    assert "kits.sdlc.adr_template" not in flat
    # non_string skipped
    assert "non_string" not in flat
    # broken (string instead of dict) skipped
    assert "broken" not in flat


def test_flatten_vars_legacy_cypilot_path_alias(tmp_path):
    """All path aliases (cf-studio-path, cf-path, studio_path, studio-path) are auto-populated."""
    data = {"system": {"cf-studio-path": str(tmp_path / ".bootstrap")}}
    flat = map_cli._flatten_vars(data, tmp_path)
    assert flat["cf-studio-path"] == ".bootstrap"
    assert flat["cf-path"] == ".bootstrap"
    assert flat["studio_path"] == ".bootstrap"


def test_count_systems_no_artifacts_toml(tmp_path):
    """Without artifacts.toml the function returns 0 without raising."""
    assert map_cli._count_systems(tmp_path) == 0
    assert map_cli._count_systems(tmp_path, docs_only=True) == 0


def test_count_systems_invalid_toml(tmp_path):
    """Broken artifacts.toml triggers the defensive except → 0."""
    art = tmp_path / "artifacts.toml"
    art.write_text("this is not a valid toml [[[", encoding="utf-8")
    assert map_cli._count_systems(tmp_path) == 0


def test_skip_dirs_for_meta_includes_adapter(tmp_path):
    """When CLAUDE.md declares cf-path, that adapter is in skip_dirs."""
    (tmp_path / "CLAUDE.md").write_text(
        'cf-path = ".bootstrap"\n', encoding="utf-8"
    )
    skips = map_cli.skip_dirs_for_meta(tmp_path)
    assert ".git" in skips
    assert ".bootstrap" in skips


def test_skip_dirs_for_meta_without_adapter(tmp_path):
    """No CLAUDE.md / AGENTS.md → only the default DEFAULT_SKIP_DIRS."""
    skips = map_cli.skip_dirs_for_meta(tmp_path)
    assert ".git" in skips
    assert len(skips) == 1
