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


def test_load_template_vars_subprocess_all_failures(monkeypatch, tmp_path):
    """When every subprocess attempt fails / times out, return {} gracefully."""
    def raise_oserror(*_a, **_k):
        raise OSError("no executable")

    import subprocess
    monkeypatch.setattr(subprocess, "run", raise_oserror)
    result = map_cli._load_template_vars(tmp_path)
    assert result == {}


def test_load_template_vars_returncode_nonzero(monkeypatch, tmp_path):
    """Subprocess returning non-zero rc with no stdout → empty dict."""
    def fake_run(*_a, **_k):
        return SimpleNamespace(returncode=1, stdout="", stderr="error")

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert map_cli._load_template_vars(tmp_path) == {}


def test_load_template_vars_invalid_json(monkeypatch, tmp_path):
    """Subprocess returning invalid JSON → empty dict."""
    def fake_run(*_a, **_k):
        return SimpleNamespace(returncode=0, stdout="{invalid", stderr="")

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert map_cli._load_template_vars(tmp_path) == {}


def test_flatten_vars_with_nested_kits(tmp_path):
    """Kit resources produce three lookup keys: bare, qualified, fully qualified."""
    data = {
        "system": {"project_root": str(tmp_path), "cf-studio-path": str(tmp_path / ".bootstrap")},
        "kits": {
            "sdlc": {
                "adr_template": str(tmp_path / "kits" / "sdlc" / "ADR.md"),
                "non_string": 42,  # skipped
            },
            "broken": "not-a-dict",  # skipped
        },
    }
    flat = map_cli._flatten_vars(data, tmp_path)
    # Bare, kit-qualified, kit-prefix-qualified all present
    assert flat["adr_template"] == "kits/sdlc/ADR.md"
    assert flat["sdlc.adr_template"] == "kits/sdlc/ADR.md"
    assert flat["kits.sdlc.adr_template"] == "kits/sdlc/ADR.md"
    # non_string skipped
    assert "non_string" not in flat
    # broken (string instead of dict) skipped
    assert "broken" not in flat


def test_flatten_vars_legacy_cypilot_path_alias(tmp_path):
    """`cypilot_path` alias is auto-populated from `cf-studio-path`."""
    data = {"system": {"cf-studio-path": str(tmp_path / ".bootstrap")}}
    flat = map_cli._flatten_vars(data, tmp_path)
    assert flat["cf-studio-path"] == ".bootstrap"
    assert flat["cypilot_path"] == ".bootstrap"


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
    """When CLAUDE.md declares cf-studio-path, that adapter is in skip_dirs."""
    (tmp_path / "CLAUDE.md").write_text(
        'cf-studio-path = ".bootstrap"\n', encoding="utf-8"
    )
    skips = map_cli.skip_dirs_for_meta(tmp_path)
    assert ".git" in skips
    assert ".bootstrap" in skips


def test_skip_dirs_for_meta_without_adapter(tmp_path):
    """No CLAUDE.md / AGENTS.md → only the default DEFAULT_SKIP_DIRS."""
    skips = map_cli.skip_dirs_for_meta(tmp_path)
    assert ".git" in skips
    assert len(skips) == 1
