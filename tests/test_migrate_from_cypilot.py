from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


class _TTYInput:
    def __init__(self, answer: str) -> None:
        self._answer = answer
        self._used = False

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        if self._used:
            return ""
        self._used = True
        return self._answer + "\n"


class _FailingInput:
    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        raise AssertionError("unexpected prompt")


def _legacy_version_file(root: Path, legacy_dir: str = "cypilot") -> Path:
    return root / legacy_dir / ".core" / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py"


def _make_legacy_project(root: Path, legacy_dir: str = "cypilot", version: str = "3.9.0") -> None:
    (root / "AGENTS.md").write_text(
        '<!-- @cpt:root-agents -->\n'
        '```toml\n'
        f'cypilot_path = "{legacy_dir}"\n'
        '```\n'
        '<!-- /@cpt:root-agents -->\n'
        "\n"
        "# Project rules\n",
        encoding="utf-8",
    )
    (root / "CLAUDE.md").write_text(
        '<!-- @cpt:root-agents -->\n'
        '```toml\n'
        f'cypilot_path = "{legacy_dir}"\n'
        '```\n'
        '<!-- /@cpt:root-agents -->\n',
        encoding="utf-8",
    )
    config = root / legacy_dir / "config"
    config.mkdir(parents=True)
    (config / "core.toml").write_text(
        "# Cypilot project configuration\n"
        'version = "1.0"\n'
        'project_root = ".."\n'
        "\n"
        "[kits]\n"
        "[kits.sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:cyberfabric/cyber-pilot-kit-sdlc"\n',
        encoding="utf-8",
    )
    (config / "artifacts.toml").write_text(
        "# Cypilot artifacts registry\n"
        "\n"
        "[[systems]]\n"
        'name = "App"\n'
        'slug = "app"\n'
        'kit = "sdlc"\n',
        encoding="utf-8",
    )
    (config / "AGENTS.md").write_text(
        "These rules are loaded alongside `{cypilot_path}/.gen/AGENTS.md`.\n",
        encoding="utf-8",
    )
    version_file = _legacy_version_file(root, legacy_dir)
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")


def _patch_minimal_constructor_cache(monkeypatch, tmp_path: Path) -> None:
    import studio.commands.init as init_cmd

    cache_dir = tmp_path / "constructor-cache"
    for name in init_cmd.COPY_DIRS:
        (cache_dir / name).mkdir(parents=True)
        (cache_dir / name / ".keep").write_text("", encoding="utf-8")
    for item in init_cmd.COPY_ARCHITECTURE_ITEMS:
        path = cache_dir / "architecture" / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(init_cmd, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(init_cmd, "_install_default_kit", lambda *args, **kwargs: {})


def _make_side_by_side_project(root: Path) -> None:
    _make_legacy_project(root)
    with (root / "AGENTS.md").open("a", encoding="utf-8") as f:
        f.write(
            "\n"
            "<!-- @cf:root-agents -->\n"
            "```toml\n"
            'cf-studio-path = ".cf-constructor"\n'
            "```\n"
            "<!-- /@cf:root-agents -->\n"
        )

    config_dir = root / ".cf-constructor" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "core.toml").write_text(
        'version = "1.0"\n'
        'project_root = ".."\n'
        "\n"
        "[kits]\n",
        encoding="utf-8",
    )


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def followup_update_ok(monkeypatch):
    import studio.commands.migrate_from_cypilot as migration

    monkeypatch.setattr(
        migration,
        "_run_followup_update",
        lambda project_root, *, yes: (0, {"status": "PASS", "project_root": project_root.as_posix()}),
    )


def test_internal_migration_copies_config_and_rewrites_markers(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir="cypilot", skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["from_dir"] == "cypilot"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()

    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cf:root-agents -->" in agents_text
    assert 'cf-studio-path = ".cf-constructor"' in agents_text
    assert "<!-- @cpt:root-agents -->" not in agents_text
    assert "# Project rules" in agents_text

    core_text = (tmp_path / ".cf-constructor" / "config" / "core.toml").read_text(encoding="utf-8")
    assert "studio-kit-sdlc" in core_text
    assert "cyber-pilot-kit-sdlc" not in core_text

    config_agents = (tmp_path / ".cf-constructor" / "config" / "AGENTS.md").read_text(encoding="utf-8")
    assert "{cf-studio-path}" in config_agents
    assert "{cypilot_path}" not in config_agents


def test_internal_migration_force_replace_backs_up_existing_constructor_dir(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    sentinel = tmp_path / ".cf-constructor" / "config" / "user-notes.md"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("preserve this user edit\n", encoding="utf-8")

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        force=True,
        skip_update=True,
    )

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["target_dir"] == "replaced"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()
    assert not sentinel.exists()
    backups = out["backups"]
    dir_backups = [Path(b) for b in backups if Path(b).is_dir()]
    assert len(dir_backups) == 1
    backup_dir = dir_backups[0]
    assert (backup_dir / "config" / "user-notes.md").read_text(encoding="utf-8") == "preserve this user edit\n"


def test_internal_migration_dry_run_force_replace_does_not_backup_or_delete_target(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    sentinel = tmp_path / ".cf-constructor" / "config" / "user-notes.md"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("active user edit\n", encoding="utf-8")

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        force=True,
        dry_run=True,
        skip_update=True,
    )

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["target_dir"] == "replaced"
    assert "backups" not in out
    assert sentinel.read_text(encoding="utf-8") == "active user edit\n"
    assert list(tmp_path.glob(".cf-constructor.*.backup")) == []


def test_internal_migration_force_replace_backup_failure_keeps_existing_constructor_dir(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    sentinel = tmp_path / ".cf-constructor" / "config" / "user-notes.md"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("active user edit\n", encoding="utf-8")
    monkeypatch.setattr(migration, "create_backup", lambda _path: None)

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        force=True,
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert out["actions"]["target_dir"] == "backup_failed"
    assert "backup" in out["message"].lower()
    assert sentinel.read_text(encoding="utf-8") == "active user edit\n"


def test_internal_migration_force_replace_copy_failure_returns_error_and_preserves_root_markers(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    sentinel = tmp_path / ".cf-constructor" / "config" / "user-notes.md"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("active user edit\n", encoding="utf-8")
    agents_before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude_before = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    real_copytree = shutil.copytree

    def fail_legacy_copy(src, dst, *args, **kwargs):
        if Path(src) == tmp_path / "cypilot" and Path(dst) == tmp_path / ".cf-constructor":
            raise shutil.Error("simulated copy failure")
        return real_copytree(src, dst, *args, **kwargs)

    def fail_update(*_args, **_kwargs):
        raise AssertionError("follow-up update must not run after failed replacement")

    monkeypatch.setattr(migration.shutil, "copytree", fail_legacy_copy)
    monkeypatch.setattr(migration, "_run_followup_update", fail_update)

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        force=True,
        skip_update=False,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert out["project_root"] == tmp_path.as_posix()
    assert out["from_dir"] == "cypilot"
    assert out["studio_dir"] == (tmp_path / ".cf-constructor").as_posix()
    assert out["actions"]["target_dir"] == "replace_failed"
    backups = out["backups"]
    assert len(backups) == 1
    assert Path(backups[0]).is_dir()
    assert "update" not in out["actions"]
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_before
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_before
    assert sentinel.read_text(encoding="utf-8") == "active user edit\n"


def test_internal_migration_force_replace_copy_failure_reports_failed_restore(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    sentinel = tmp_path / ".cf-constructor" / "config" / "user-notes.md"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("active user edit\n", encoding="utf-8")
    agents_before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude_before = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    real_copytree = shutil.copytree

    def fail_replace_and_restore_copy(src, dst, *args, **kwargs):
        src_path = Path(src)
        dst_path = Path(dst)
        if dst_path == tmp_path / ".cf-constructor":
            if src_path == tmp_path / "cypilot":
                dst_path.mkdir(parents=True, exist_ok=True)
                (dst_path / "partial-copy.txt").write_text("partial\n", encoding="utf-8")
                raise shutil.Error("simulated replace copy failure")
            raise OSError("simulated restore copy failure")
        return real_copytree(src, dst, *args, **kwargs)

    def fail_update(*_args, **_kwargs):
        raise AssertionError("follow-up update must not run after failed replacement")

    monkeypatch.setattr(migration.shutil, "copytree", fail_replace_and_restore_copy)
    monkeypatch.setattr(migration, "_run_followup_update", fail_update)

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        force=True,
        skip_update=False,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert out["actions"]["target_dir"] == "replace_failed"
    assert out["actions"]["target_dir_restore"] == "restore_failed"
    assert "restore_error" in out
    assert "simulated restore copy failure" in out["restore_error"]
    backups = out["backups"]
    assert len(backups) == 1
    assert Path(backups[0]).is_dir()
    assert "update" not in out["actions"]
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_before
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_before


def test_internal_migration_create_copy_failure_returns_error_and_cleans_partial_target(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    agents_before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude_before = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    def fail_create_copy(src, dst, *args, **kwargs):
        if Path(src) == tmp_path / "cypilot" and Path(dst) == tmp_path / ".cf-constructor":
            Path(dst).mkdir(parents=True)
            (Path(dst) / "partial-copy.txt").write_text("partial\n", encoding="utf-8")
            raise shutil.Error("simulated create copy failure")
        raise AssertionError("unexpected copytree call")

    def fail_update(*_args, **_kwargs):
        raise AssertionError("follow-up update must not run after failed creation")

    monkeypatch.setattr(migration.shutil, "copytree", fail_create_copy)
    monkeypatch.setattr(migration, "_run_followup_update", fail_update)

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        skip_update=False,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert out["project_root"] == tmp_path.as_posix()
    assert out["from_dir"] == "cypilot"
    assert out["studio_dir"] == (tmp_path / ".cf-constructor").as_posix()
    assert out["actions"]["target_dir"] == "create_failed"
    assert out["actions"]["target_dir_cleanup"] == "removed"
    assert "simulated create copy failure" in out["error"]
    assert "update" not in out["actions"]
    assert not (tmp_path / ".cf-constructor").exists()
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_before
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_before


def test_config_markdown_rewrite_contract_covers_all_supported_files(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_config_markdown

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    original = (
        "Path {cypilot_path}\n"
        "Run `cpt validate` before using Cypilot.\n"
        "Use cpt update for prose command tokens.\n"
        # Unsupported spellings and punctuation are intentionally preserved.
        "lowercase cypilot stays.\n"
        "uppercase CYPILOT stays.\n"
        "punctuated cpt. stays.\n"
        "cpt line-start stays.\n"
    )
    for name in ("AGENTS.md", "SKILL.md", "README.md"):
        (config_dir / name).write_text(original, encoding="utf-8")

    changed = _migrate_config_markdown(config_dir)

    assert sorted(changed) == sorted(["AGENTS.md", "SKILL.md", "README.md"])
    for name in changed:
        text = (config_dir / name).read_text(encoding="utf-8")
        assert "Path {cf-studio-path}" in text
        assert "Run `cfs validate` before using Constructor Studio." in text
        assert "Use cfs update for prose command tokens." in text
        assert "lowercase cypilot stays." in text
        assert "uppercase CYPILOT stays." in text
        assert "punctuated cpt. stays." in text
        assert "cpt line-start stays." in text
        assert "{cypilot_path}" not in text


def test_config_markdown_recursive_rules_subdir(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_config_markdown

    config_dir = tmp_path / "config"
    rules_dir = config_dir / "rules"
    rules_dir.mkdir(parents=True)

    # Place a markdown file in the rules subdirectory with legacy placeholders.
    rules_foo = rules_dir / "foo.md"
    rules_foo.write_text(
        "Cypilot is X\n"
        "{cypilot_path}/y\n",
        encoding="utf-8",
    )

    changed = _migrate_config_markdown(config_dir)

    rewritten = rules_foo.read_text(encoding="utf-8")
    assert "Constructor Studio is X" in rewritten
    assert "{cf-studio-path}/y" in rewritten
    assert "Cypilot" not in rewritten
    assert "{cypilot_path}" not in rewritten

    assert "rules/foo.md" in changed
    assert "foo.md" not in changed


def test_config_toml_template_vars_rewrites_cypilot_path_placeholder(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    pr_review_toml = tmp_path / "cypilot" / "config" / "pr-review.toml"
    pr_review_toml.write_text(
        '# pr-review config\n'
        'path = "{cypilot_path}/foo"\n'
        'unrelated = "value"\n',
        encoding="utf-8",
    )

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        skip_update=True,
    )

    assert rc == 0
    assert out["status"] == "PASS"
    migrated_toml = (tmp_path / ".cf-constructor" / "config" / "pr-review.toml").read_text(encoding="utf-8")
    assert 'path = "{cf-studio-path}/foo"' in migrated_toml
    assert "{cypilot_path}" not in migrated_toml
    assert 'unrelated = "value"' in migrated_toml
    assert "pr-review.toml" in out["actions"]["config_toml_template_vars"]


def test_internal_migration_removes_duplicate_legacy_root_blocks(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    duplicate_blocks = (
        "Before legacy block.\n"
        "<!-- @cpt:root-agents -->\n"
        "```toml\n"
        'cypilot_path = "cypilot"\n'
        "```\n"
        "<!-- /@cpt:root-agents -->\n"
        "Between legacy blocks.\n"
        "<!-- @cpt:root-agents -->\n"
        "```toml\n"
        'cypilot_path = ".cpt"\n'
        "```\n"
        "<!-- /@cpt:root-agents -->\n"
        "After legacy block.\n"
    )
    (tmp_path / "AGENTS.md").write_text(duplicate_blocks, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(duplicate_blocks, encoding="utf-8")

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir="cypilot", skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "<!-- @cf:root-agents -->" in text
        assert 'cf-studio-path = ".cf-constructor"' in text
        assert "<!-- @cpt:root-agents -->" not in text
        assert "<!-- /@cpt:root-agents -->" not in text
        assert "Before legacy block." in text
        assert "Between legacy blocks." in text
        assert "After legacy block." in text


def test_internal_migration_preserves_malformed_legacy_root_block_tail(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    malformed_content = (
        "Intro prose.\n"
        "<!-- @cpt:root-agents -->\n"
        "```toml\n"
        'cypilot_path = "cypilot"\n'
        "```\n"
        "This malformed legacy block has no closing marker.\n"
    )
    (tmp_path / "AGENTS.md").write_text(malformed_content, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(malformed_content, encoding="utf-8")

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir="cypilot", skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    assert "warnings" in out
    assert any("AGENTS.md" in warning and "@cpt:root-agents" in warning for warning in out["warnings"])
    assert any("CLAUDE.md" in warning and "@cpt:root-agents" in warning for warning in out["warnings"])
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "<!-- @cf:root-agents -->" in text
        assert 'cf-studio-path = ".cf-constructor"' in text
        assert "<!-- @cpt:root-agents -->" in text
        assert "<!-- /@cpt:root-agents -->" not in text
        assert "Intro prose." in text
        assert "This malformed legacy block has no closing marker." in text


def test_internal_migration_reports_missing_toml_actions_without_failing(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / "cypilot" / "config" / "core.toml").unlink()
    (tmp_path / "cypilot" / "config" / "artifacts.toml").unlink()

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir="cypilot", skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["core_toml"] == "missing"
    assert out["actions"]["artifacts_toml"] == "missing"
    assert out["actions"]["update"] == "skipped"
    assert (tmp_path / ".cf-constructor").is_dir()


def test_internal_migration_reports_invalid_toml_actions_without_failing(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / "cypilot" / "config" / "core.toml").write_text("version = [\n", encoding="utf-8")
    (tmp_path / "cypilot" / "config" / "artifacts.toml").write_text("[[systems]\n", encoding="utf-8")

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir="cypilot", skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["core_toml"] == "invalid"
    assert out["actions"]["artifacts_toml"] == "invalid"
    assert out["actions"]["update"] == "skipped"
    assert (tmp_path / ".cf-constructor").is_dir()


def test_init_migration_root_marker_write_failure_returns_json_without_update(
    tmp_path, capsys, monkeypatch
):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    real_replace_root_block = migration._replace_root_block

    def fail_agents_marker_write(target_file, install_dir):
        if target_file == tmp_path / "AGENTS.md":
            raise OSError("simulated root marker write failure")
        return real_replace_root_block(target_file, install_dir)

    def fail_update(*_args, **_kwargs):
        raise AssertionError("follow-up update must not run after rewrite failure")

    monkeypatch.setattr(migration, "_replace_root_block", fail_agents_marker_write)
    monkeypatch.setattr(migration, "_run_followup_update", fail_update)

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ERROR"
    assert out["project_root"] == tmp_path.as_posix()
    assert out["from_dir"] == "cypilot"
    assert out["studio_dir"] == (tmp_path / ".cf-constructor").as_posix()
    assert out["rewrite_step"] == "root_agents"
    assert out["actions"]["target_dir"] == "created"
    assert out["actions"]["core_toml"] == "updated"
    assert out["actions"]["artifacts_toml"] == "unchanged"
    assert out["actions"]["config_markdown"] == ["AGENTS.md"]
    assert "root_agents" not in out["actions"]
    assert "update" not in out["actions"]
    assert "simulated root marker write failure" in out["error"]
    assert (tmp_path / ".cf-constructor").is_dir()
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


def test_internal_migration_preserves_partial_success_when_followup_update_fails(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    update_result = {"status": "ERROR", "message": "boom"}
    monkeypatch.setattr(migration, "_run_followup_update", lambda project_root, *, yes: (7, update_result))

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir="cypilot", skip_update=False, to_dir=".cf-constructor")

    assert rc == 7
    assert out["status"] == "WARN"
    assert out["actions"]["update"] == "FAIL"
    assert "follow-up update failed" in out["warnings"]
    assert out["update_result"] == update_result
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cf:root-agents -->" in agents_text


def test_internal_migration_removes_legacy_kit_key_when_canonical_exists(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    core_toml = tmp_path / "cypilot" / "config" / "core.toml"
    core_toml.write_text(
        "# Cypilot project configuration\n"
        'version = "1.0"\n'
        'project_root = ".."\n'
        "\n"
        "[kits]\n"
        "[kits.cypilot-sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/cypilot-sdlc"\n'
        'version = "1.0.0"\n'
        'source = "custom-legacy-source"\n'
        "\n"
        "[kits.sdlc]\n"
        'format = "CyberConstructor"\n'
        'path = "config/kits/sdlc"\n'
        'version = "2.0.0"\n'
        'source = "github:constructorfabric/studio-kit-sdlc"\n',
        encoding="utf-8",
    )

    rc, out = migrate_from_cypilot(project_root=tmp_path, skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["actions"]["core_toml"] == "updated"
    migrated_core = (tmp_path / ".cf-constructor" / "config" / "core.toml").read_text(encoding="utf-8")
    assert "cypilot-sdlc" not in migrated_core
    assert "[kits.sdlc]" in migrated_core
    assert "custom-legacy-source" not in migrated_core


def test_internal_migration_promotes_legacy_only_kit_and_normalizes_default_metadata(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    core_toml = tmp_path / "cypilot" / "config" / "core.toml"
    core_toml.write_text(
        "# Cypilot project configuration\n"
        'version = "1.0"\n'
        'project_root = ".."\n'
        "\n"
        "[kits]\n"
        "[kits.cypilot-sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/cypilot-sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:cyberfabric/cyber-pilot-kit-sdlc"\n',
        encoding="utf-8",
    )
    artifacts_toml = tmp_path / "cypilot" / "config" / "artifacts.toml"
    artifacts_toml.write_text(
        "# Cypilot artifacts registry\n"
        "\n"
        "[[systems]]\n"
        'name = "App"\n'
        'slug = "app"\n'
        'kit = "cypilot-sdlc"\n',
        encoding="utf-8",
    )

    rc, out = migrate_from_cypilot(project_root=tmp_path, skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["actions"]["core_toml"] == "updated"
    assert out["actions"]["artifacts_toml"] == "updated"
    migrated_core = (tmp_path / ".cf-constructor" / "config" / "core.toml").read_text(encoding="utf-8")
    assert "cypilot-sdlc" not in migrated_core
    assert "[kits.sdlc]" in migrated_core
    assert 'path = "config/kits/sdlc"' in migrated_core
    assert 'source = "github:constructorfabric/studio-kit-sdlc"' in migrated_core

    migrated_artifacts = (tmp_path / ".cf-constructor" / "config" / "artifacts.toml").read_text(encoding="utf-8")
    assert 'kit = "sdlc"' in migrated_artifacts
    assert "cypilot-sdlc" not in migrated_artifacts


def test_internal_migration_recursively_migrates_child_system_kit_refs(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    artifacts_toml = tmp_path / "cypilot" / "config" / "artifacts.toml"
    artifacts_toml.write_text(
        "# Cypilot artifacts registry\n"
        "\n"
        "[[systems]]\n"
        'name = "App"\n'
        'slug = "app"\n'
        'kit = "cypilot-sdlc"\n'
        "\n"
        "[[systems.children]]\n"
        'name = "Service"\n'
        'slug = "service"\n'
        'kit = "cypilot-sdlc"\n'
        "\n"
        "[[systems.children.children]]\n"
        'name = "Worker"\n'
        'slug = "worker"\n'
        'kit = "cypilot-sdlc"\n',
        encoding="utf-8",
    )

    rc, out = migrate_from_cypilot(project_root=tmp_path, skip_update=True, to_dir=".cf-constructor")

    assert rc == 0, out
    assert out["actions"]["artifacts_toml"] == "updated"
    migrated_artifacts = (tmp_path / ".cf-constructor" / "config" / "artifacts.toml").read_text(encoding="utf-8")
    assert migrated_artifacts.count('kit = "sdlc"') == 3
    assert "cypilot-sdlc" not in migrated_artifacts


def test_internal_migration_dry_run_reports_plan_without_writes(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    agents_before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude_before = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    rc, out = migrate_from_cypilot(project_root=tmp_path, dry_run=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["dry_run"] is True
    assert out["actions"]["target_dir"] == "created"
    assert out["actions"]["core_toml"] == "dry_run"
    assert out["actions"]["artifacts_toml"] == "dry_run"
    assert out["actions"]["config_markdown"] == "dry_run"
    assert out["actions"]["root_agents"] == "dry_run"
    assert out["actions"]["root_claude"] == "dry_run"
    assert out["actions"]["update"] == "dry_run"
    assert not (tmp_path / ".cf-constructor").exists()
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_before
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_before


def test_internal_migration_refuses_existing_target_without_force(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / ".cf-constructor").mkdir()

    rc, out = migrate_from_cypilot(project_root=tmp_path, skip_update=True, to_dir=".cf-constructor")

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "already exists" in out["message"]


def test_internal_migration_rejects_absolute_target_with_force(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    absolute_target = tmp_path / "absolute-target"
    absolute_target.mkdir()
    sentinel = absolute_target / "sentinel.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        to_dir=absolute_target.as_posix(),
        force=True,
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "--to-dir must be a relative path" in out["message"]
    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert not (tmp_path / ".cf-constructor").exists()


def test_internal_migration_rejects_traversal_target_with_force(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    outside_target = tmp_path.parent / f"{tmp_path.name}-outside-target"
    outside_target.mkdir()
    sentinel = outside_target / "sentinel.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        to_dir=f"../{outside_target.name}",
        force=True,
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "inside the project root" in out["message"]
    assert sentinel.read_text(encoding="utf-8") == "keep me"
    assert not (tmp_path / ".cf-constructor").exists()


def test_internal_migration_rejects_absolute_from_dir(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    absolute_source = tmp_path / "absolute-source"
    absolute_source.mkdir()

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir=absolute_source.as_posix(),
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "--from-dir must be a relative path" in out["message"]
    assert not (tmp_path / ".cf-constructor").exists()


def test_internal_migration_rejects_traversal_from_dir(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    outside_source = tmp_path.parent / f"{tmp_path.name}-outside-source"
    outside_source.mkdir()
    sentinel = outside_source / "sentinel.txt"
    sentinel.write_text("external legacy", encoding="utf-8")

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir=f"../{outside_source.name}",
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "inside the project root" in out["message"]
    assert sentinel.read_text(encoding="utf-8") == "external legacy"
    assert not (tmp_path / ".cf-constructor").exists()


@pytest.mark.parametrize("legacy_dir", ["cypilot", ".cypilot", ".cpt", ".bootstrap"])
def test_internal_migration_accepts_common_relative_from_dirs(tmp_path, legacy_dir):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path, legacy_dir=legacy_dir)

    rc, out = migrate_from_cypilot(project_root=tmp_path, from_dir=legacy_dir, skip_update=True, to_dir=".cf-constructor")

    assert rc == 0
    assert out["status"] == "PASS"
    assert out["from_dir"] == legacy_dir
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


def test_init_migrate_yes_migrates_without_prompt(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    monkeypatch.setattr("sys.stdin", _FailingInput())

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=yes",
    ])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "PASS"
    assert out["from_dir"] == "cypilot"
    assert out["actions"]["update"] == "PASS"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


@pytest.mark.parametrize("version", ["3.9.0", "3.10.0"])
def test_supported_legacy_versions_migrate_directly(tmp_path, capsys, monkeypatch, followup_update_ok, version):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version=version)
    monkeypatch.setattr("sys.stdin", _FailingInput())

    def fail_update(_project_root):
        raise AssertionError("supported versions must not run legacy update")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


def test_unsupported_legacy_version_prompts_to_update_then_migrates(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    monkeypatch.setattr("sys.stdin", _TTYInput("y"))

    def update_to_baseline(project_root):
        _legacy_version_file(project_root).write_text('__version__ = "3.9.0"\n', encoding="utf-8")
        return {"status": "PASS", "returncode": 0}

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", update_to_baseline)

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=yes",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "not directly migratable" in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "PASS"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


def test_unsupported_legacy_version_update_to_supported_newer_version_migrates(
    tmp_path, capsys, monkeypatch, followup_update_ok
):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")

    def update_to_supported_newer_version(project_root):
        _legacy_version_file(project_root).write_text('__version__ = "3.10.0"\n', encoding="utf-8")
        return {"status": "PASS", "returncode": 0}

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", update_to_supported_newer_version)

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=yes",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["normalized_legacy_version"] == "3.10.0"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


def test_declining_unsupported_legacy_update_returns_stable_result(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path, version="3.8.4")
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ABORTED"
    assert out["legacy_version"] == "3.8.4"
    assert out["target_legacy_version"] == "3.9.0"
    assert out["actions"]["legacy_update"] == "declined"
    assert not (tmp_path / ".cf-constructor").exists()


def test_init_declined_migration_creates_side_by_side_constructor(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    _patch_minimal_constructor_cache(monkeypatch, tmp_path)
    version_file = _legacy_version_file(tmp_path)
    version_before = version_file.read_text(encoding="utf-8")

    def fail_update(_project_root):
        raise AssertionError("legacy update must not run for side-by-side init")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main([
        "--json",
        "init",
        "--yes",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=no",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["legacy_studio"] == "detected"
    assert out["actions"]["migration"] == "declined"
    assert out["actions"]["migration_decline_action"] == "side_by_side_init"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()
    assert (tmp_path / "cypilot").is_dir()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cpt:root-agents -->" in agents_text
    assert "<!-- @cf:root-agents -->" in agents_text
    assert version_file.read_text(encoding="utf-8") == version_before


def test_init_declined_migration_rejects_legacy_install_dir_without_modifying_it(
    tmp_path, capsys, monkeypatch, followup_update_ok
):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    _patch_minimal_constructor_cache(monkeypatch, tmp_path)
    legacy_dir = tmp_path / "cypilot"
    before = _snapshot_tree(legacy_dir)

    rc = main([
        "--json",
        "init",
        "--yes",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=no",
        "--install-dir",
        "cypilot",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ERROR"
    message = out["message"].lower()
    assert "choose a different --install-dir" in message
    assert "approve migration" in message
    assert out["actions"]["migration"] == "declined"
    assert out["install_dir"] == "cypilot"
    assert out["legacy_studio_dir"] == legacy_dir.as_posix()
    assert _snapshot_tree(legacy_dir) == before
    assert not (legacy_dir / ".gen").exists()
    assert not (legacy_dir / ".core" / "requirements").exists()


def test_interactive_init_declined_migration_creates_side_by_side_constructor(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    _patch_minimal_constructor_cache(monkeypatch, tmp_path)
    version_file = _legacy_version_file(tmp_path)
    version_before = version_file.read_text(encoding="utf-8")
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    def fail_update(_project_root):
        raise AssertionError("legacy update must not run for side-by-side init")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main(["--json", "init", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Existing Cyber Pilot project detected" in captured.err
    assert "Press N to initialize Constructor Studio side-by-side and keep Cyber Pilot unchanged." in captured.err
    assert "not directly migratable" not in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "PASS"
    assert out["actions"]["legacy_studio"] == "detected"
    assert out["actions"]["migration"] == "declined"
    assert out["actions"]["migration_decline_action"] == "side_by_side_init"
    assert (tmp_path / ".cf-studio" / "config" / "core.toml").is_file()
    assert (tmp_path / "cypilot").is_dir()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cpt:root-agents -->" in agents_text
    assert "<!-- @cf:root-agents -->" in agents_text
    assert version_file.read_text(encoding="utf-8") == version_before


def test_non_interactive_unsupported_legacy_does_not_update_without_approval(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")

    def fail_update(_project_root):
        raise AssertionError("non-interactive flow must not auto-update legacy skill")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main([
        "--json",
        "init",
        "--yes",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ABORTED"
    assert out["actions"]["legacy_update"] == "declined"
    assert not (tmp_path / ".cf-constructor").exists()


def test_non_interactive_unsupported_legacy_updates_with_explicit_approval(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")

    def update_to_baseline(project_root):
        _legacy_version_file(project_root).write_text('__version__ = "3.9.0"\n', encoding="utf-8")
        return {"status": "PASS", "returncode": 0}

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", update_to_baseline)

    rc = main([
        "--json",
        "init",
        "--yes",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".cf-constructor",
        "--migrate-from-cypilot=yes",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()


def test_init_dry_run_unsupported_legacy_reports_planned_update_without_running_it(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    version_file = _legacy_version_file(tmp_path)
    version_before = version_file.read_text(encoding="utf-8")

    def fail_update(_project_root):
        raise AssertionError("dry-run must not run legacy update")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--dry-run",
        "--migrate-from-cypilot=yes",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["dry_run"] is True
    assert out["legacy_version"] == "3.8.4"
    assert out["target_legacy_version"] == "3.9.0"
    assert out["actions"]["legacy_update"] == "dry_run"
    assert out["actions"]["target_dir"] == "created"
    assert out["actions"]["root_agents"] == "dry_run"
    assert out["actions"]["update"] == "dry_run"
    assert not (tmp_path / ".cf-constructor").exists()
    assert version_file.read_text(encoding="utf-8") == version_before


def test_failed_update_to_baseline_stops_migration(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    monkeypatch.setattr(
        migration,
        "_run_legacy_update_to_baseline",
        lambda project_root: {"status": "ERROR", "returncode": 7},
    )

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ERROR"
    assert "Failed to update Cyber Pilot skill" in out["message"]
    assert out["actions"]["legacy_update"] == "failed"
    assert not (tmp_path / ".cf-constructor").exists()


def test_interactive_init_prompts_and_accepting_migrates(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    monkeypatch.setattr("sys.stdin", _TTYInput("y"))

    rc = main(["--json", "init", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Existing Cyber Pilot project detected" in captured.err
    assert "Press N to initialize Constructor Studio side-by-side and keep Cyber Pilot unchanged." in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "PASS"
    # RC-24: interactive migration defaults to in-place migration (target =
    # legacy dir name). The _TTYInput stub answers "y" to the migrate-yes/no
    # prompt; the subsequent target-dir prompt exhausts the stub, falls back
    # to EOFError, and accepts the default (the legacy dir name "cypilot").
    assert (tmp_path / "cypilot" / "config" / "core.toml").is_file()


def test_interactive_init_decline_returns_clear_result(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    _patch_minimal_constructor_cache(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    rc = main(["--json", "init", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Existing Cyber Pilot project detected" in captured.err
    assert "Press N to initialize Constructor Studio side-by-side and keep Cyber Pilot unchanged." in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "PASS"
    assert out["actions"]["legacy_studio"] == "detected"
    assert out["actions"]["migration"] == "declined"
    assert out["actions"]["migration_decline_action"] == "side_by_side_init"
    assert (tmp_path / ".cf-studio" / "config" / "core.toml").is_file()
    assert (tmp_path / "cypilot").is_dir()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cpt:root-agents -->" in agents_text
    assert "<!-- @cf:root-agents -->" in agents_text


def test_init_yes_does_not_imply_migration(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    _patch_minimal_constructor_cache(monkeypatch, tmp_path)

    def fail_migration(*_args, **_kwargs):
        raise AssertionError("--yes alone must not run Cyber Pilot migration")

    monkeypatch.setattr(migration, "migrate_from_cypilot", fail_migration)
    rc = main(["--json", "init", "--yes", "--project-root", str(tmp_path)])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["legacy_studio"] == "detected"
    assert out["actions"]["migration"] == "declined"
    assert out["actions"]["migration_decline_action"] == "side_by_side_init"
    assert (tmp_path / ".cf-studio" / "config" / "core.toml").is_file()
    assert (tmp_path / "cypilot").is_dir()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cpt:root-agents -->" in agents_text
    assert "<!-- @cf:root-agents -->" in agents_text


def test_existing_constructor_wins_over_legacy_migration(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    _patch_minimal_constructor_cache(monkeypatch, tmp_path)
    constructor_dir = tmp_path / ".cf-constructor"
    (constructor_dir / "config").mkdir(parents=True)
    sentinel = constructor_dir / "config" / "core.toml"
    sentinel.write_text("existing = true\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        + "\n"
        + '<!-- @cf:root-agents -->\n'
        + '```toml\n'
        + 'cf-studio-path = ".cf-constructor"\n'
        + '```\n'
        + '<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "REPAIRED"
    assert out["studio_dir"] == constructor_dir.as_posix()
    assert out["version_changed"] is False
    assert (tmp_path / "cypilot").is_dir()
    assert "existing = true" in sentinel.read_text(encoding="utf-8")


def test_implicit_migration_uses_install_dir_as_target(tmp_path, capsys, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".constructor-custom",
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["studio_dir"] == (tmp_path / ".constructor-custom").as_posix()
    assert (tmp_path / ".constructor-custom" / "config" / "core.toml").is_file()
    assert not (tmp_path / ".cf-constructor").exists()


def test_implicit_migration_allows_install_dir_matching_legacy_dir(tmp_path, capsys, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path, legacy_dir=".bootstrap")

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--install-dir",
        ".bootstrap",
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["from_dir"] == ".bootstrap"
    assert out["studio_dir"] == (tmp_path / ".bootstrap").as_posix()
    assert out["actions"]["target_dir"] == "reused"
    assert out["actions"]["update"] == "PASS"
    assert (tmp_path / ".bootstrap" / "config" / "core.toml").is_file()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert '<!-- @cf:root-agents -->' in agents_text
    assert 'cf-studio-path = ".bootstrap"' in agents_text
    assert '<!-- @cpt:root-agents -->' not in agents_text
    assert not (tmp_path / ".cf-constructor").exists()


def test_implicit_migration_does_not_use_generic_force_to_replace_target(tmp_path, capsys, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    target = tmp_path / ".cf-studio"
    target.mkdir()
    sentinel = target / "sentinel.txt"
    sentinel.write_text("keep me", encoding="utf-8")

    rc = main([
        "--json",
        "init",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
        "--force",
    ])

    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ERROR"
    assert "already exists" in out["message"]
    assert sentinel.read_text(encoding="utf-8") == "keep me"


def test_update_migrate_yes_on_legacy_project_migrates_without_prompt(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    monkeypatch.setattr("sys.stdin", _FailingInput())

    rc = main([
        "--json",
        "update",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["actions"]["update"] == "PASS"
    assert (tmp_path / ".cf-studio" / "config" / "core.toml").is_file()


def test_update_unsupported_legacy_version_can_update_baseline_then_migrate(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")

    def update_to_baseline(project_root):
        _legacy_version_file(project_root).write_text('__version__ = "3.9.0"\n', encoding="utf-8")
        return {"status": "PASS", "returncode": 0}

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", update_to_baseline)

    rc = main([
        "--json",
        "update",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert (tmp_path / ".cf-studio" / "config" / "core.toml").is_file()


def test_e2e_cpt_update_hands_off_to_cfc_init_for_cypilot_migration(tmp_path):
    if os.environ.get("CFC_E2E_SMOKE") != "1":
        pytest.skip("set CFC_E2E_SMOKE=1 to run cross-package cpt/cfc smoke")

    missing = [name for name in ("cpt", "cfc") if shutil.which(name) is None]
    if missing:
        pytest.fail(f"CFC_E2E_SMOKE=1 requires these commands on PATH: {', '.join(missing)}")

    _make_legacy_project(tmp_path, version="3.9.0")

    env = os.environ.copy()
    env.setdefault("CFC_NO_VERSION_CHECK", "1")
    env.setdefault("CFC_TELEMETRY", "0")

    proc = subprocess.run(
        [
            "cpt",
            "update",
            "--project-root",
            str(tmp_path),
            "--migrate-from-cypilot=yes",
            "--update-legacy-cypilot=yes",
        ],
        capture_output=True,
        env=env,
        text=True,
        timeout=120,
        check=False,
    )

    assert proc.returncode == 0, (
        "cpt update migration smoke failed\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()
    assert (tmp_path / ".cf-constructor" / "config" / "artifacts.toml").is_file()
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cf:root-agents -->" in agents_text
    assert 'cf-studio-path = ".cf-constructor"' in agents_text
    assert "<!-- @cpt:root-agents -->" not in agents_text


def test_update_declining_coexisting_legacy_continues_normal_update(tmp_path, capsys, monkeypatch):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration
    import studio.commands.update as update_cmd

    _make_side_by_side_project(tmp_path)
    cache_dir = tmp_path / "constructor-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(update_cmd, "CACHE_DIR", cache_dir)
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    def fail_migration(*_args, **_kwargs):
        raise AssertionError("declined coexisting migration must continue normal update")

    monkeypatch.setattr(migration, "migrate_from_cypilot", fail_migration)

    rc = main(["--json", "update", "--project-root", str(tmp_path), "--dry-run"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "Cyber Pilot (cypilot) detected alongside Constructor Studio." in captured.err
    assert "Migrate it into the current Constructor Studio install now?" in captured.err
    assert "Press N to continue regular Constructor Studio update." in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "PASS"
    assert out["dry_run"] is True
    assert out["actions"]["legacy_studio"] == "detected"
    assert out["actions"]["migration"] == "declined"
    assert out["actions"]["migration_decline_action"] == "regular_update"
    assert (tmp_path / ".cf-constructor" / "config" / "core.toml").is_file()
    assert (tmp_path / "cypilot").is_dir()


def test_update_accepting_coexisting_legacy_migrates_into_existing_constructor_dir(tmp_path, capsys, monkeypatch):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_side_by_side_project(tmp_path)
    call: dict[str, object] = {}

    def fake_migrate_from_cypilot(**kwargs):
        call.update(kwargs)
        return 0, {
            "status": "PASS",
            "project_root": kwargs["project_root"].as_posix(),
            "from_dir": kwargs["from_dir"],
            "studio_dir": (kwargs["project_root"] / kwargs["to_dir"]).as_posix(),
            "dry_run": bool(kwargs["dry_run"]),
            "actions": {"target_dir": "replaced", "update": "PASS"},
        }

    monkeypatch.setattr(migration, "migrate_from_cypilot", fake_migrate_from_cypilot)

    rc = main([
        "--json",
        "update",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert call["from_dir"] == "cypilot"
    assert call["to_dir"] == ".cf-constructor"
    assert call["force"] is True
    assert call["skip_update"] is False


def test_update_after_completed_migration_ignores_leftover_legacy_directory(
    tmp_path, capsys, monkeypatch
):
    from studio.cli import main
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration
    import studio.commands.update as update_cmd

    _make_legacy_project(tmp_path)
    rc, out = migrate_from_cypilot(project_root=tmp_path, skip_update=True, to_dir=".cf-constructor")
    assert rc == 0
    assert out["status"] == "PASS"
    agents_text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- @cf:root-agents -->" in agents_text
    assert "<!-- @cpt:root-agents -->" not in agents_text
    assert (tmp_path / "cypilot" / "config" / "core.toml").is_file()

    cache_dir = tmp_path / "constructor-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(update_cmd, "CACHE_DIR", cache_dir)

    def fail_migration(*_args, **_kwargs):
        raise AssertionError("completed migration must not re-detect leftover cypilot/")

    monkeypatch.setattr(migration, "migrate_from_cypilot", fail_migration)

    rc = main([
        "--json",
        "update",
        "--project-root",
        str(tmp_path),
        "--dry-run",
        "--migrate-from-cypilot=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "legacy_cypilot" not in out["actions"]


def test_update_declined_migration_does_not_update_legacy_skill(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    version_file = _legacy_version_file(tmp_path)
    version_before = version_file.read_text(encoding="utf-8")

    def fail_update(_project_root):
        raise AssertionError("legacy update must not run after migration is declined")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main([
        "--json",
        "update",
        "--project-root",
        str(tmp_path),
        "--migrate-from-cypilot=no",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ABORTED"
    assert "migration declined" in out["message"]
    assert out["actions"]["migration"] == "declined"
    assert not (tmp_path / ".cf-constructor").exists()
    assert version_file.read_text(encoding="utf-8") == version_before


def test_interactive_update_declined_migration_does_not_update_legacy_skill(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    version_file = _legacy_version_file(tmp_path)
    version_before = version_file.read_text(encoding="utf-8")
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    def fail_update(_project_root):
        raise AssertionError("legacy update must not run after migration is declined")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main(["--json", "update", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Existing Cyber Pilot project detected" in captured.err
    assert "Press N to abort update." in captured.err
    assert "not directly migratable" not in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "ABORTED"
    assert "migration declined" in out["message"]
    assert out["actions"]["migration"] == "declined"
    assert not (tmp_path / ".cf-constructor").exists()
    assert version_file.read_text(encoding="utf-8") == version_before


def test_interactive_update_prompts_and_declining_returns_clear_result(tmp_path, capsys, monkeypatch, followup_update_ok):
    from studio.cli import main

    _make_legacy_project(tmp_path)
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    rc = main(["--json", "update", "--project-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert rc == 1
    assert "Existing Cyber Pilot project detected" in captured.err
    assert "Press N to abort update." in captured.err
    out = json.loads(captured.out)
    assert out["status"] == "ABORTED"
    assert "migration declined" in out["message"]
    assert not (tmp_path / ".cf-constructor").exists()


def test_update_dry_run_on_legacy_project_reports_planned_migration(tmp_path, capsys, monkeypatch):
    # CR-T6-026: dry_run + ask no longer auto-approves migration; user must answer.
    # Supply _TTYInput("y") so the migration prompt is answered affirmatively.
    from studio.cli import main

    _make_legacy_project(tmp_path)
    monkeypatch.setattr("sys.stdin", _TTYInput("y"))

    rc = main(["--json", "update", "--project-root", str(tmp_path), "--dry-run"])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["dry_run"] is True
    assert out["actions"]["target_dir"] == "created"
    assert out["actions"]["root_agents"] == "dry_run"
    assert out["actions"]["update"] == "dry_run"
    assert not (tmp_path / ".cf-constructor").exists()


def test_update_dry_run_on_legacy_project_ask_uses_interactive_prompt(tmp_path, capsys, monkeypatch):
    """--dry-run keeps ask-mode interactive on TTY legacy-only projects."""
    from studio.cli import main

    _make_legacy_project(tmp_path)
    monkeypatch.setattr("sys.stdin", _TTYInput("n"))

    rc = main(["--json", "update", "--project-root", str(tmp_path), "--dry-run"])

    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert rc == 1
    assert "Existing Cyber Pilot project detected" in captured.err
    assert "Press N to abort update." in captured.err
    assert out["status"] == "ABORTED"
    assert out["actions"]["migration"] == "declined"
    assert out["dry_run"] is True
    assert not (tmp_path / ".cf-constructor").exists()


def test_update_dry_run_unsupported_legacy_reports_planned_update_without_running_it(tmp_path, capsys, monkeypatch):
    from studio.cli import main
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.8.4")
    version_file = _legacy_version_file(tmp_path)
    version_before = version_file.read_text(encoding="utf-8")

    def fail_update(_project_root):
        raise AssertionError("dry-run must not run legacy update")

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fail_update)

    rc = main([
        "--json",
        "update",
        "--project-root",
        str(tmp_path),
        "--dry-run",
        "--migrate-from-cypilot=yes",
        "--update-legacy-studio=yes",
    ])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["status"] == "PASS"
    assert out["dry_run"] is True
    assert out["legacy_version"] == "3.8.4"
    assert out["target_legacy_version"] == "3.9.0"
    assert out["actions"]["legacy_update"] == "dry_run"
    assert out["actions"]["target_dir"] == "created"
    assert out["actions"]["root_agents"] == "dry_run"
    assert out["actions"]["update"] == "dry_run"
    assert not (tmp_path / ".cf-constructor").exists()
    assert version_file.read_text(encoding="utf-8") == version_before


def test_help_does_not_list_public_migration_command(capsys):
    from studio.cli import main

    rc = main(["--json", "--help"])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "migrate-from-cypilot" not in out["commands"]


def test_public_migration_route_is_unknown(capsys):
    from studio.cli import main

    rc = main(["--json", "migrate-from-cypilot"])

    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["status"] == "ERROR"
    assert "Unknown command" in out["message"]


@pytest.mark.parametrize("command", ["init", "update"])
def test_init_and_update_help_document_migration_option(command, capsys):
    from studio.cli import main
    from studio.utils.ui import set_json_mode

    set_json_mode(False)
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])

    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--migrate-from-cypilot={ask,yes,no}" in help_text


def test_migrate_creates_root_backups_on_success(tmp_path):
    import re

    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    agents_sentinel = "sentinel-agents-pre-migration"
    claude_sentinel = "sentinel-claude-pre-migration"
    (tmp_path / "AGENTS.md").write_text(agents_sentinel, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_sentinel, encoding="utf-8")

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
    )

    assert rc == 0
    assert result["actions"]["root_agents_backup"] == "created"
    assert result["actions"]["root_claude_backup"] == "created"

    backups = result["backups"]
    agents_backup_matches = [
        b for b in backups if re.search(r"AGENTS\.md\.\d{8}-\d{6}\.backup$", b)
    ]
    claude_backup_matches = [
        b for b in backups if re.search(r"CLAUDE\.md\.\d{8}-\d{6}\.backup$", b)
    ]
    assert agents_backup_matches, f"no AGENTS.md backup in {backups}"
    assert claude_backup_matches, f"no CLAUDE.md backup in {backups}"

    assert Path(agents_backup_matches[0]).read_text(encoding="utf-8") == agents_sentinel
    assert Path(claude_backup_matches[0]).read_text(encoding="utf-8") == claude_sentinel


def test_migrate_restores_root_files_when_root_agents_rewrite_raises(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    agents_sentinel = "sentinel-agents-pre-migration"
    claude_sentinel = "sentinel-claude-pre-migration"
    (tmp_path / "AGENTS.md").write_text(agents_sentinel, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_sentinel, encoding="utf-8")

    def _raise_for_agents(target_file, _install_dir, _warnings):
        if target_file.name == "AGENTS.md":
            raise OSError("simulated")
        return f"injected-{target_file.name}"

    monkeypatch.setattr(migration, "_replace_root_block_with_warnings", _raise_for_agents)

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
    )

    assert rc == 1
    assert result["status"] == "ERROR"
    assert result["rewrite_step"] == "root_agents"
    assert result["actions"]["root_files_restore"]["root_agents"] == "restored"
    assert result["actions"]["root_files_restore"]["root_claude"] == "restored"
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_sentinel


def test_migrate_restores_root_files_when_root_claude_rewrite_raises(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    agents_sentinel = "sentinel-agents-pre-migration"
    claude_sentinel = "sentinel-claude-pre-migration"
    (tmp_path / "AGENTS.md").write_text(agents_sentinel, encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_sentinel, encoding="utf-8")

    def _raise_for_claude(target_file, _install_dir, _warnings):
        if target_file.name == "CLAUDE.md":
            raise OSError("simulated")
        return f"injected-{target_file.name}"

    monkeypatch.setattr(migration, "_replace_root_block_with_warnings", _raise_for_claude)

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
    )

    assert rc == 1
    assert result["rewrite_step"] == "root_claude"
    assert result["actions"]["root_files_restore"]["root_agents"] == "restored"
    assert result["actions"]["root_files_restore"]["root_claude"] == "restored"
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == agents_sentinel
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == claude_sentinel


_GIT_AVAILABLE = shutil.which("git") is not None


def _git_init_and_commit(project_root: Path) -> None:
    subprocess.run(
        ["git", "init", project_root.as_posix()],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=project_root.as_posix(),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-m",
            "init",
        ],
        cwd=project_root.as_posix(),
        check=True,
        capture_output=True,
    )


def test_migrate_proceeds_when_not_in_git_repo(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text("sentinel-agents-pre\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("sentinel-claude-pre\n", encoding="utf-8")

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
    )

    assert rc == 0, result


@pytest.mark.skipif(not _GIT_AVAILABLE, reason="git binary not available")
def test_migrate_proceeds_when_clean_git_state(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text("sentinel-agents-pre\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("sentinel-claude-pre\n", encoding="utf-8")
    _git_init_and_commit(tmp_path)

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
    )

    assert rc == 0, result


@pytest.mark.skipif(not _GIT_AVAILABLE, reason="git binary not available")
def test_migrate_bails_when_root_file_is_dirty(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text("sentinel-agents-pre\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("sentinel-claude-pre\n", encoding="utf-8")
    _git_init_and_commit(tmp_path)

    agents_path = tmp_path / "AGENTS.md"
    with agents_path.open("a", encoding="utf-8") as f:
        f.write("\nDIRTY-MARKER\n")

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
    )

    assert rc == 1, result
    assert result["status"] == "ERROR"
    assert "AGENTS.md" in result["root_files_dirty"]
    assert "uncommitted changes" in result["message"]
    assert "Commit or stash them first" in result["message"]
    assert "--force-overwrite-root" not in result["message"]
    assert agents_path.read_text(encoding="utf-8").endswith("DIRTY-MARKER\n")
    assert not (tmp_path / ".cf-constructor").exists()


@pytest.mark.skipif(not _GIT_AVAILABLE, reason="git binary not available")
def test_migrate_force_overwrite_root_proceeds_with_dirty_state(tmp_path):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    (tmp_path / "AGENTS.md").write_text("sentinel-agents-pre\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("sentinel-claude-pre\n", encoding="utf-8")
    _git_init_and_commit(tmp_path)

    with (tmp_path / "AGENTS.md").open("a", encoding="utf-8") as f:
        f.write("\nDIRTY-MARKER\n")

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 0, result
    assert result["actions"]["root_agents_backup"] == "created"


def test_replace_rmtree_raise_triggers_restore_to_restored(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    project_root = tmp_path
    target_dir = project_root / ".cf-constructor"
    target_dir.mkdir()
    (target_dir / "sentinel.txt").write_text("pre-migration", encoding="utf-8")

    real_rmtree = shutil.rmtree  # pyright: ignore[reportDeprecated]
    seen = {"rmtree": 0}

    def fake_rmtree(path, *args, **kwargs):
        seen["rmtree"] += 1
        if seen["rmtree"] == 1:
            raise OSError("simulated rmtree failure")
        return real_rmtree(path, *args, **kwargs)  # pyright: ignore[reportDeprecated]

    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)

    rc, result = migrate_from_cypilot(
        project_root=project_root,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=True,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 1
    assert result["status"] == "ERROR"
    assert result["actions"]["target_dir"] == "replace_failed"
    assert result["actions"]["target_dir_restore"] == "restored"
    assert "restore_error" not in result
    assert target_dir.is_dir()
    assert (target_dir / "sentinel.txt").read_text(encoding="utf-8") == "pre-migration"


def test_replace_copytree_raise_triggers_restore_to_restored(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    project_root = tmp_path
    target_dir = project_root / ".cf-constructor"
    target_dir.mkdir()
    (target_dir / "sentinel.txt").write_text("pre-migration", encoding="utf-8")

    real_copytree = shutil.copytree
    seen = {"copytree": 0}

    def fake_copytree(src, dst, *args, **kwargs):
        seen["copytree"] += 1
        if seen["copytree"] == 2:
            raise OSError("simulated copytree failure")
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copytree", fake_copytree)

    rc, result = migrate_from_cypilot(
        project_root=project_root,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=True,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 1
    assert result["actions"]["target_dir"] == "replace_failed"
    assert result["actions"]["target_dir_restore"] == "restored"
    assert (target_dir / "sentinel.txt").read_text(encoding="utf-8") == "pre-migration"


def test_replace_failure_with_restore_failure_returns_restore_failed(tmp_path, monkeypatch):
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path)
    project_root = tmp_path
    target_dir = project_root / ".cf-constructor"
    target_dir.mkdir()
    (target_dir / "sentinel.txt").write_text("pre-migration", encoding="utf-8")

    def always_fail_rmtree(_path, *_args, **_kwargs):
        raise OSError("simulated rmtree failure (persistent)")

    monkeypatch.setattr(shutil, "rmtree", always_fail_rmtree)

    rc, result = migrate_from_cypilot(
        project_root=project_root,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=True,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 1
    assert result["actions"]["target_dir"] == "replace_failed"
    assert result["actions"]["target_dir_restore"] == "restore_failed"
    assert "restore_error" in result
    assert result["restore_error"]


def test_run_legacy_update_to_baseline_emits_ctrl_c_hint(tmp_path, monkeypatch, capsys):
    import sys as _sys
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import _run_legacy_update_to_baseline

    class _FakeCompleted:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    seen = {"stderr_at_run": ""}

    def fake_run(_cmd, **_kwargs):
        # Snapshot the captured stderr buffer at the moment subprocess.run
        # would be invoked. Using the private capsys readout via the
        # capture manager preserves the buffer for the final assertion below.
        try:
            seen["stderr_at_run"] = _sys.stderr.getvalue()  # type: ignore[attr-defined]
        except AttributeError:
            seen["stderr_at_run"] = ""
        return _FakeCompleted()

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    result = _run_legacy_update_to_baseline(tmp_path)

    assert isinstance(result, dict)
    err = capsys.readouterr().err
    assert "Press Ctrl+C to cancel" in err
    # Bonus: the hint must appear BEFORE subprocess.run is invoked.
    if seen["stderr_at_run"]:
        assert "Press Ctrl+C to cancel" in seen["stderr_at_run"]


def test_run_legacy_update_to_baseline_handles_keyboard_interrupt(tmp_path, monkeypatch, capsys):
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import _run_legacy_update_to_baseline

    def fake_run(_cmd, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    result = _run_legacy_update_to_baseline(tmp_path)

    assert result["status"] == "ERROR"
    assert result["returncode"] == 130
    assert result["error"] == "Interrupted by user (Ctrl+C)"
    assert "cpt" in result["command"]
    assert "update" in result["command"]
    assert "--version" in result["command"]
    assert "3.9.0" in result["command"]
    assert "-y" in result["command"]

    err = capsys.readouterr().err
    assert "Interrupted by user (Ctrl+C)" in err


def test_run_legacy_update_to_baseline_sets_bridge_bypass_env_var(
    tmp_path, monkeypatch
):
    """SEND-side test for the CYPILOT_LEGACY_UPDATE_TO_BASELINE handshake.
    RECV-side is tested in cyber-pilot's tests/test_cpt_to_cfc_bridge.py.
    """
    import os
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import (
        _run_legacy_update_to_baseline,
    )

    class _FakeCompleted:
        def __init__(self):
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    captured = {}

    def fake_run(_cmd, **_kwargs):
        captured["env"] = _kwargs.get("env")
        captured["cwd"] = _kwargs.get("cwd")
        return _FakeCompleted()

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    result = _run_legacy_update_to_baseline(tmp_path)

    # Function returned PASS (fake subprocess succeeded)
    assert isinstance(result, dict)
    assert result.get("status") == "PASS"

    # The bridge-bypass env var IS being set
    assert captured["env"] is not None
    assert captured["env"].get("CYPILOT_LEGACY_UPDATE_TO_BASELINE") == "1"

    # The env is based on os.environ (not a sparse dict that would lose
    # PATH, HOME, etc.) — verify at least one common variable made it through
    preserved = [k for k in ("PATH", "HOME", "USER") if k in os.environ]
    if preserved:
        assert all(
            captured["env"].get(k) == os.environ[k] for k in preserved
        )

    # cwd is the project_root
    assert captured["cwd"] == tmp_path.as_posix()


def test_ensure_supported_legacy_version_returns_error_when_update_subprocess_raises(
    tmp_path, monkeypatch
):
    """RC-8: when _run_legacy_update_to_baseline returns the OSError-shape ERROR
    dict (subprocess raised, no returncode), ensure_supported_legacy_version
    surfaces it in the failed-update branch."""
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import ensure_supported_legacy_version

    _make_legacy_project(tmp_path, version="3.8.0")

    def fake_run(_project_root):
        return {
            "status": "ERROR",
            "command": ["cpt", "update", "--version", "3.9.0", "-y"],
            "error": "simulated OSError: cpt not found",
        }

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fake_run)

    supported, result = ensure_supported_legacy_version(
        project_root=tmp_path,
        legacy_rel="cypilot",
        update_choice="yes",
        interactive=False,
        dry_run=False,
    )

    assert supported is False
    assert result["status"] == "ERROR"
    assert "Failed to update Cyber Pilot skill" in result["message"]
    assert result["actions"]["legacy_update"] == "failed"
    assert result["update_result"]["error"] == "simulated OSError: cpt not found"
    assert result["legacy_version"] == "3.8.0"
    assert result["from_dir"] == "cypilot"
    assert result["project_root"] == tmp_path.as_posix()


def test_ensure_supported_legacy_version_returns_error_when_update_returncode_nonzero(
    tmp_path, monkeypatch
):
    """RC-8: when _run_legacy_update_to_baseline returns the returncode-nonzero
    ERROR shape (subprocess ran but failed), ensure_supported_legacy_version
    surfaces it in the failed-update branch."""
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import ensure_supported_legacy_version

    _make_legacy_project(tmp_path, version="3.8.0")

    def fake_run(_project_root):
        return {
            "status": "ERROR",
            "command": ["cpt", "update", "--version", "3.9.0", "-y"],
            "returncode": 1,
            "stdout": "",
            "stderr": "simulated cpt update failure",
        }

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fake_run)

    supported, result = ensure_supported_legacy_version(
        project_root=tmp_path,
        legacy_rel="cypilot",
        update_choice="yes",
        interactive=False,
        dry_run=False,
    )

    assert supported is False
    assert result["status"] == "ERROR"
    assert "Failed to update Cyber Pilot skill" in result["message"]
    assert result["actions"]["legacy_update"] == "failed"
    assert result["update_result"]["returncode"] == 1
    assert "simulated cpt update failure" in result["update_result"]["stderr"]
    assert result["legacy_version"] == "3.8.0"


def test_ensure_supported_legacy_version_returns_error_when_post_bump_version_mismatches(
    tmp_path, monkeypatch
):
    """RC-8: when _run_legacy_update_to_baseline reports PASS but the on-disk
    version file was not actually updated to a supported baseline, the
    post-bump re-read trips the version_mismatch branch."""
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import ensure_supported_legacy_version

    _make_legacy_project(tmp_path, version="3.8.0")

    def fake_run(_project_root):
        return {
            "status": "PASS",
            "command": ["cpt", "update", "--version", "3.9.0", "-y"],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fake_run)

    supported, result = ensure_supported_legacy_version(
        project_root=tmp_path,
        legacy_rel="cypilot",
        update_choice="yes",
        interactive=False,
        dry_run=False,
    )

    assert supported is False
    assert result["status"] == "ERROR"
    assert "did not reach a supported migration version" in result["message"]
    # Re-read after the no-op patched update finds the file still at 3.8.0.
    assert result["legacy_version"] == "3.8.0"
    assert result["actions"]["legacy_update"] == "version_mismatch"
    assert result["update_result"]["status"] == "PASS"
    assert "supported_legacy_versions" in result
    assert result["from_dir"] == "cypilot"


# ---------------------------------------------------------------------------
# RC-9: coverage-driven additive tests
# ---------------------------------------------------------------------------


def test_migrate_returns_error_when_legacy_install_cannot_be_detected(tmp_path):
    """Hits line 60: detect returns None and from_dir is falsy."""
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    # bare tmp_path has no AGENTS.md and no candidate dirs -> detect returns None
    rc, out = migrate_from_cypilot(project_root=tmp_path, skip_update=True, to_dir=".cf-constructor")

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "Cyber Pilot install directory" in out["message"]
    assert out["project_root"] == tmp_path.resolve().as_posix()


def test_migrate_returns_error_when_legacy_dir_missing_on_disk(tmp_path):
    """Hits line 90: legacy_dir resolves but is not a directory."""
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="not-a-real-dir",
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert "Cyber Pilot directory not found" in out["message"]


def test_migrate_create_target_copytree_failure_with_cleanup_failure_records_cleanup_error(
    tmp_path, monkeypatch
):
    """Hits lines 168-170 and 184: copytree raises, cleanup rmtree also raises."""
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    # Use a target dir that does not currently exist so we go through the
    # "create_target" branch (lines 156-186), not the "replace_target" branch.
    target_rel = "fresh-target"

    def fail_copytree(_src, dst, *_args, **_kwargs):
        # Materialize the target so the cleanup branch tries to remove it.
        Path(dst).mkdir(parents=True, exist_ok=True)
        raise shutil.Error("simulated create copy failure")

    def fail_rmtree(_path, *_args, **_kwargs):
        raise OSError("simulated cleanup rmtree failure")

    monkeypatch.setattr(migration.shutil, "copytree", fail_copytree)
    monkeypatch.setattr(migration.shutil, "rmtree", fail_rmtree)

    rc, out = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=target_rel,
        skip_update=True,
    )

    assert rc == 1
    assert out["status"] == "ERROR"
    assert out["actions"]["target_dir"] == "create_failed"
    assert out["actions"]["target_dir_cleanup"] == "cleanup_failed"
    assert "cleanup_error" in out
    assert "simulated cleanup rmtree failure" in out["cleanup_error"]
    assert "simulated create copy failure" in out["error"]


def test_resolve_cypilot_project_root_delegates_to_resolver(tmp_path):
    """Hits line 259: the public wrapper just forwards to _resolve_project_root."""
    from studio.commands.migrate_from_cypilot import resolve_cypilot_project_root

    resolved = resolve_cypilot_project_root(tmp_path.as_posix())

    assert resolved == tmp_path.resolve()


def test_read_legacy_cypilot_version_falls_back_to_second_candidate_path(tmp_path):
    """Hits the second-iteration return in read_legacy_cypilot_version's loop."""
    from studio.commands.migrate_from_cypilot import read_legacy_cypilot_version

    legacy_dir = tmp_path / "cypilot"
    second = legacy_dir / "skills" / "cypilot" / "scripts" / "cypilot" / "__init__.py"
    second.parent.mkdir(parents=True)
    second.write_text('__version__ = "3.9.0"\n', encoding="utf-8")

    assert read_legacy_cypilot_version(legacy_dir) == "3.9.0"


def test_read_legacy_cypilot_version_falls_back_to_third_candidate_path(tmp_path):
    """Hits the third-iteration return in read_legacy_cypilot_version's loop."""
    from studio.commands.migrate_from_cypilot import read_legacy_cypilot_version

    legacy_dir = tmp_path / "cypilot"
    third = legacy_dir / "scripts" / "cypilot" / "__init__.py"
    third.parent.mkdir(parents=True)
    third.write_text('__version__ = "3.10.0"\n', encoding="utf-8")

    assert read_legacy_cypilot_version(legacy_dir) == "3.10.0"


def test_read_legacy_cypilot_version_returns_none_when_no_candidate_path_exists(tmp_path):
    """Hits line 417: loop exhausts all candidates without finding a version."""
    from studio.commands.migrate_from_cypilot import read_legacy_cypilot_version

    legacy_dir = tmp_path / "cypilot"
    legacy_dir.mkdir()

    assert read_legacy_cypilot_version(legacy_dir) is None


def test_should_update_legacy_cypilot_returns_false_for_explicit_no(tmp_path):
    """Hits line 434: explicit 'no' short-circuit."""
    from studio.commands.migrate_from_cypilot import should_update_legacy_cypilot

    decision = should_update_legacy_cypilot(
        "no",
        interactive=False,
        project_root=tmp_path,
        legacy_rel="cypilot",
        version="3.8.0",
    )

    assert decision is False


def test_should_update_legacy_cypilot_returns_true_for_explicit_yes(tmp_path):
    """Companion: explicit 'yes' branch (line 432)."""
    from studio.commands.migrate_from_cypilot import should_update_legacy_cypilot

    decision = should_update_legacy_cypilot(
        "yes",
        interactive=False,
        project_root=tmp_path,
        legacy_rel="cypilot",
        version="3.8.0",
    )

    assert decision is True


def test_should_update_legacy_cypilot_returns_false_when_non_interactive_ask(tmp_path):
    """Hits line 437: ask + non-interactive falls through to False."""
    from studio.commands.migrate_from_cypilot import should_update_legacy_cypilot

    decision = should_update_legacy_cypilot(
        "ask",
        interactive=False,
        project_root=tmp_path,
        legacy_rel="cypilot",
        version="3.8.0",
    )

    assert decision is False


def test_read_version_from_init_returns_none_when_file_missing(tmp_path):
    """Hits line 470: not is_file() short-circuit."""
    from studio.commands.migrate_from_cypilot import _read_version_from_init

    assert _read_version_from_init(tmp_path / "nope.py") is None


def test_read_version_from_init_returns_none_on_os_error(tmp_path, monkeypatch):
    """Hits lines 473-474: OSError on read_text -> None."""
    from studio.commands.migrate_from_cypilot import _read_version_from_init

    init_file = tmp_path / "__init__.py"
    init_file.write_text("ignored\n", encoding="utf-8")

    real_read_text = Path.read_text

    def fail_read_text(self, *args, **kwargs):
        if self == init_file:
            raise OSError("simulated read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    assert _read_version_from_init(init_file) is None


def test_read_version_from_init_returns_none_when_no_version_line(tmp_path):
    """Hits line 479: file present but contains no __version__ assignment."""
    from studio.commands.migrate_from_cypilot import _read_version_from_init

    init_file = tmp_path / "__init__.py"
    init_file.write_text("# nothing useful here\nfoo = 1\n", encoding="utf-8")

    assert _read_version_from_init(init_file) is None


def test_normalize_legacy_version_returns_none_for_falsy_input():
    """Hits line 486: None / empty short-circuit."""
    from studio.commands.migrate_from_cypilot import _normalize_legacy_version

    assert _normalize_legacy_version(None) is None
    assert _normalize_legacy_version("") is None


def test_normalize_legacy_version_strips_v_prefix():
    """Hits lines 488-489: strip leading 'v'."""
    from studio.commands.migrate_from_cypilot import _normalize_legacy_version

    assert _normalize_legacy_version("v3.9.0") == "3.9.0"
    assert _normalize_legacy_version("  v3.10.0  ") == "3.10.0"
    assert _normalize_legacy_version("3.9.0") == "3.9.0"


def test_prompt_update_legacy_cypilot_returns_false_on_eof(tmp_path, monkeypatch, capsys):
    """Hits lines 506-507: EOFError in input() -> declined."""
    import studio.commands.migrate_from_cypilot as migration

    def fake_input(*_args, **_kwargs):
        raise EOFError

    monkeypatch.setattr(migration, "input", fake_input, raising=False)

    result = migration._prompt_update_legacy_cypilot(tmp_path, "cypilot", "3.8.0")

    assert result is False
    err = capsys.readouterr().err
    assert "not directly migratable" in err


def test_prompt_update_legacy_cypilot_returns_false_on_keyboard_interrupt(tmp_path, monkeypatch):
    """Hits lines 506-507: KeyboardInterrupt in input() -> declined."""
    import studio.commands.migrate_from_cypilot as migration

    def fake_input(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(migration, "input", fake_input, raising=False)

    assert migration._prompt_update_legacy_cypilot(tmp_path, "cypilot", None) is False


def test_run_legacy_update_to_baseline_returns_error_on_os_error(tmp_path, monkeypatch):
    """Hits line 533: subprocess raises OSError -> ERROR result."""
    import studio.commands.migrate_from_cypilot as migration

    def fake_run(_cmd, **_kwargs):
        raise OSError("cpt not on PATH")

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    result = migration._run_legacy_update_to_baseline(tmp_path)

    assert result["status"] == "ERROR"
    assert "cpt not on PATH" in result["error"]
    assert result["command"][0] == "cpt"


def test_prompt_migrate_from_cypilot_returns_false_on_eof(tmp_path, monkeypatch, capsys):
    """Hits lines 574-575: EOFError in input() -> declined."""
    import studio.commands.migrate_from_cypilot as migration

    def fake_input(*_args, **_kwargs):
        raise EOFError

    monkeypatch.setattr(migration, "input", fake_input, raising=False)

    result = migration._prompt_migrate_from_cypilot(tmp_path, "cypilot")

    assert result is False
    err = capsys.readouterr().err
    # Default heading line emitted
    assert "Cyber Pilot" in err


def test_prompt_migrate_from_cypilot_returns_false_on_keyboard_interrupt(tmp_path, monkeypatch):
    """Hits lines 574-575: KeyboardInterrupt in input() -> declined."""
    import studio.commands.migrate_from_cypilot as migration

    def fake_input(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(migration, "input", fake_input, raising=False)

    assert migration._prompt_migrate_from_cypilot(tmp_path, "cypilot") is False


def test_run_followup_update_in_json_mode_returns_parsed_payload(tmp_path, monkeypatch):
    """Hits lines 582-598: json mode branch parses cmd_update stdout."""
    import studio.commands.migrate_from_cypilot as migration
    import studio.commands.update as update_mod

    captured = {}

    def fake_cmd_update(argv):
        captured["argv"] = list(argv)
        # Emit JSON the way cmd_update does in --json mode.
        print(json.dumps({"status": "PASS", "from": "fake"}))
        return 0

    monkeypatch.setattr(update_mod, "cmd_update", fake_cmd_update)
    monkeypatch.setattr(migration, "is_json_mode", lambda: True)

    rc, parsed = migration._run_followup_update(tmp_path, yes=True)

    assert rc == 0
    assert parsed == {"status": "PASS", "from": "fake"}
    assert "--yes" in captured["argv"]
    assert "--no-interactive" not in captured["argv"]
    assert "--project-root" in captured["argv"]


def test_run_followup_update_in_json_mode_with_invalid_json_returns_raw_text(tmp_path, monkeypatch):
    """Hits lines 599-600: json.JSONDecodeError path returns raw string."""
    import studio.commands.migrate_from_cypilot as migration
    import studio.commands.update as update_mod

    def fake_cmd_update(_argv):
        print("not-json-output")
        return 0

    monkeypatch.setattr(update_mod, "cmd_update", fake_cmd_update)
    monkeypatch.setattr(migration, "is_json_mode", lambda: True)

    rc, parsed = migration._run_followup_update(tmp_path, yes=False)

    assert rc == 0
    assert parsed == "not-json-output"


def test_run_followup_update_in_json_mode_with_empty_stdout_returns_none(tmp_path, monkeypatch):
    """Hits lines 594-596: empty stdout in json mode returns (rc, None)."""
    import studio.commands.migrate_from_cypilot as migration
    import studio.commands.update as update_mod

    def fake_cmd_update(_argv):
        return 0

    monkeypatch.setattr(update_mod, "cmd_update", fake_cmd_update)
    monkeypatch.setattr(migration, "is_json_mode", lambda: True)

    rc, parsed = migration._run_followup_update(tmp_path, yes=False)

    assert rc == 0
    assert parsed is None


def test_run_followup_kit_update_passes_project_root(tmp_path, monkeypatch):
    import studio.commands.kit as kit_mod
    import studio.commands.migrate_from_cypilot as migration

    captured = {}

    def fake_cmd_kit_update(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(kit_mod, "cmd_kit_update", fake_cmd_kit_update)
    monkeypatch.setattr(migration, "is_json_mode", lambda: False)

    rc = migration._run_followup_kit_update(project_root=tmp_path, yes=True)

    assert rc == 0
    assert captured["argv"] == ["--project-root", tmp_path.as_posix(), "--yes"]


def test_post_copy_rewrite_failure_with_no_backup_records_no_backup_action(
    tmp_path, monkeypatch
):
    """Hits lines 701-702: rewrite raises but no root backup exists -> no_backup."""
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)
    # Delete CLAUDE.md so there is no claude backup, forcing the no_backup branch
    # for that label when an exception is raised during the rewrites.
    (tmp_path / "CLAUDE.md").unlink()

    def _raise_for_agents(target_file, _install_dir, _warnings):
        if target_file.name == "AGENTS.md":
            raise OSError("simulated rewrite failure")
        return f"injected-{target_file.name}"

    monkeypatch.setattr(migration, "_replace_root_block_with_warnings", _raise_for_agents)

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        skip_update=True,
    )

    assert rc == 1
    assert result["rewrite_step"] == "root_agents"
    restore = result["actions"]["root_files_restore"]
    assert restore["root_agents"] == "restored"
    assert restore["root_claude"] == "no_backup"


def test_post_copy_rewrite_failure_records_restore_failed_when_copy2_raises(
    tmp_path, monkeypatch
):
    """Hits lines 706-707: backup copy2 raises during restore -> restore_failed."""
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path)

    def _raise_for_agents(target_file, _install_dir, _warnings):
        if target_file.name == "AGENTS.md":
            raise OSError("simulated rewrite failure")
        return f"injected-{target_file.name}"

    root_paths = {tmp_path / "AGENTS.md", tmp_path / "CLAUDE.md"}
    real_copy2 = shutil.copy2

    def selective_copy2(src, dst, *args, **kwargs):
        # Allow create_backup's copy2 (dst inside project_root with .backup
        # suffix) to succeed; only fail when restoring on top of the original
        # root file path during the rewrite-failure handler.
        if Path(dst) in root_paths:
            raise OSError("simulated copy2 restore failure")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(migration, "_replace_root_block_with_warnings", _raise_for_agents)
    monkeypatch.setattr(migration.shutil, "copy2", selective_copy2)

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        skip_update=True,
    )

    assert rc == 1
    assert result["rewrite_step"] == "root_agents"
    restore = result["actions"]["root_files_restore"]
    assert restore["root_agents"].startswith("restore_failed")
    assert "simulated copy2 restore failure" in restore["root_agents"]
    assert restore["root_claude"].startswith("restore_failed")


def test_resolve_project_root_returns_arg_path_when_provided(tmp_path):
    """Hits line 717-718: explicit project_root_arg short-circuit."""
    import studio.commands.migrate_from_cypilot as migration

    sub = tmp_path / "explicit-root"
    sub.mkdir()

    assert migration._resolve_project_root(sub.as_posix()) == sub.resolve()


def test_resolve_project_root_locates_agents_with_legacy_marker(tmp_path, monkeypatch):
    """Hits lines 720-730: walk parents, find AGENTS.md with legacy marker."""
    import studio.commands.migrate_from_cypilot as migration

    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text(
        "<!-- @cpt:root-agents -->\nbody\n", encoding="utf-8"
    )

    monkeypatch.chdir(nested)

    found = migration._resolve_project_root(None)

    assert found == tmp_path.resolve()


def test_resolve_project_root_returns_none_when_no_markers_and_no_git(
    tmp_path, monkeypatch
):
    """Hits line 731: fall-through returns None when not a git repo."""
    import studio.commands.migrate_from_cypilot as migration

    sub = tmp_path / "lonely"
    sub.mkdir()
    monkeypatch.chdir(sub)

    assert migration._resolve_project_root(None) is None


def test_resolve_project_root_skips_agents_when_read_text_raises(
    tmp_path, monkeypatch
):
    """Hits lines 725-728: OSError on agents.read_text -> continue."""
    import studio.commands.migrate_from_cypilot as migration

    (tmp_path / "AGENTS.md").write_text("anything", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    real_read_text = Path.read_text

    def fail_read_text(self, *args, **kwargs):
        if self.name == "AGENTS.md":
            raise OSError("simulated agents read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    # No git dir -> final fallback returns None.
    assert migration._resolve_project_root(None) is None


def test_read_legacy_install_dir_handles_agents_read_text_error(tmp_path, monkeypatch):
    """Hits lines 757-758: OSError on agents.read_text -> content stays empty."""
    import studio.commands.migrate_from_cypilot as migration

    (tmp_path / "AGENTS.md").write_text("anything", encoding="utf-8")
    # Lay down a fallback candidate dir so the function can still return a value
    # after the read fails. This exercises the OSError -> content="" path and
    # then the candidate-scan that comes after it.
    candidate = tmp_path / ".bootstrap" / "config"
    candidate.mkdir(parents=True)
    (candidate / "core.toml").write_text("# minimal\n", encoding="utf-8")

    real_read_text = Path.read_text

    def fail_read_text(self, *args, **kwargs):
        if self.name == "AGENTS.md" and self.parent == tmp_path:
            raise OSError("simulated agents read failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    assert migration._read_legacy_install_dir(tmp_path) == ".bootstrap"


def test_read_legacy_install_dir_ignores_claude_only_cypilot_path(tmp_path):
    import studio.commands.migrate_from_cypilot as migration

    (tmp_path / "CLAUDE.md").write_text(
        '```toml\n'
        'cypilot_path = "custom-cypilot"\n'
        '```\n',
        encoding="utf-8",
    )
    custom = tmp_path / "custom-cypilot" / "config"
    custom.mkdir(parents=True)
    (custom / "core.toml").write_text("# minimal\n", encoding="utf-8")

    assert migration._read_legacy_install_dir(tmp_path) is None


def test_read_legacy_install_dir_uses_agents_cypilot_path_when_claude_disagrees(tmp_path):
    import studio.commands.migrate_from_cypilot as migration

    (tmp_path / "AGENTS.md").write_text(
        '<!-- @cpt:root-agents -->\n'
        '```toml\n'
        'cypilot_path = "agents-cypilot"\n'
        '```\n'
        '<!-- /@cpt:root-agents -->\n',
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text(
        '```toml\n'
        'cypilot_path = "claude-cypilot"\n'
        '```\n',
        encoding="utf-8",
    )

    assert migration._read_legacy_install_dir(tmp_path) == "agents-cypilot"


def test_read_legacy_install_dir_falls_back_to_candidate_dot_bootstrap(tmp_path):
    """Hits lines 770-776: no AGENTS.md/marker -> candidate-dir scan picks .bootstrap."""
    import studio.commands.migrate_from_cypilot as migration

    candidate = tmp_path / ".bootstrap"
    (candidate / "config").mkdir(parents=True)
    (candidate / "config" / "core.toml").write_text("# minimal\n", encoding="utf-8")

    assert migration._read_legacy_install_dir(tmp_path) == ".bootstrap"


def test_read_legacy_install_dir_falls_back_to_candidate_with_top_level_core_toml(tmp_path):
    """Hits the '(candidate_dir / "core.toml").is_file()' alternate condition."""
    import studio.commands.migrate_from_cypilot as migration

    candidate = tmp_path / ".cpt"
    candidate.mkdir()
    (candidate / "core.toml").write_text("# minimal\n", encoding="utf-8")

    assert migration._read_legacy_install_dir(tmp_path) == ".cpt"


def test_read_legacy_install_dir_returns_none_when_no_candidate_matches(tmp_path):
    """Hits line 777: candidate loop exhausts -> None."""
    import studio.commands.migrate_from_cypilot as migration

    # No AGENTS.md, no candidate dirs at all.
    assert migration._read_legacy_install_dir(tmp_path) is None


def test_probe_root_files_dirty_returns_empty_when_no_paths_are_files(tmp_path):
    """Hits line 791: names == [] short-circuit."""
    import studio.commands.migrate_from_cypilot as migration

    # Neither path exists, so names list is empty.
    result = migration._probe_root_files_dirty(
        tmp_path, [tmp_path / "AGENTS.md", tmp_path / "CLAUDE.md"]
    )
    assert result == []


def test_probe_root_files_dirty_returns_empty_when_git_not_found(tmp_path, monkeypatch):
    """Hits lines 801-802: FileNotFoundError -> [] (git missing)."""
    import studio.commands.migrate_from_cypilot as migration

    (tmp_path / "AGENTS.md").write_text("body\n", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("git not on PATH")

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    assert migration._probe_root_files_dirty(tmp_path, [tmp_path / "AGENTS.md"]) == []


def test_probe_root_files_dirty_returns_empty_on_timeout(tmp_path, monkeypatch):
    """Hits lines 801-802: TimeoutExpired -> []."""
    import studio.commands.migrate_from_cypilot as migration

    (tmp_path / "AGENTS.md").write_text("body\n", encoding="utf-8")

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=10)

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    assert migration._probe_root_files_dirty(tmp_path, [tmp_path / "AGENTS.md"]) == []


def test_migrate_core_toml_skips_non_dict_kit_data(tmp_path):
    """Hits line 890: kit_data not dict -> continue."""
    import studio.commands.migrate_from_cypilot as migration

    core_toml = tmp_path / "core.toml"
    # Mix a valid kit table with a scalar masquerading inside [kits]. Real
    # tomllib will reject mixing a table key and scalar at the same path, so we
    # simulate this via two kit tables, one valid dict and one (legitimate)
    # value that triggers the loop's non-dict skip via the cypilot-sdlc pop
    # being absent. The minimum trick: have a [kits] table containing one
    # entry that maps to a non-dict value via [[kits.foo]] array-of-tables,
    # which surfaces as a list (not dict) under the kits mapping.
    core_toml.write_text(
        "[kits]\n"
        "[kits.sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:cyberfabric/cyber-pilot-kit-sdlc"\n'
        "\n"
        "[[kits.extras]]\n"
        'note = "list-of-dicts not handled by the migrator"\n',
        encoding="utf-8",
    )

    result = migration._migrate_core_toml(core_toml)

    # The sdlc kit's source should still get rewritten; the non-dict kit_data
    # for `kits.extras` (a list) is skipped without raising.
    assert result == "updated"
    new_text = core_toml.read_text(encoding="utf-8")
    assert "studio-kit-sdlc" in new_text


def test_migrate_core_toml_drops_top_level_system_section(tmp_path):
    """Hits lines 900-902: top-level [system] gets deleted."""
    import studio.commands.migrate_from_cypilot as migration

    core_toml = tmp_path / "core.toml"
    core_toml.write_text(
        "[system]\n"
        'name = "legacy"\n',
        encoding="utf-8",
    )

    result = migration._migrate_core_toml(core_toml)

    assert result == "updated"
    new_text = core_toml.read_text(encoding="utf-8")
    assert "[system]" not in new_text


def test_migrate_core_toml_returns_unchanged_when_no_legacy_keys(tmp_path):
    """Hits line 907: nothing to rewrite -> 'unchanged'."""
    import studio.commands.migrate_from_cypilot as migration

    core_toml = tmp_path / "core.toml"
    core_toml.write_text(
        "[kits]\n"
        "[kits.sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:constructorfabric/studio-kit-sdlc"\n',
        encoding="utf-8",
    )
    snapshot = core_toml.read_text(encoding="utf-8")

    result = migration._migrate_core_toml(core_toml)

    assert result == "unchanged"
    # File untouched.
    assert core_toml.read_text(encoding="utf-8") == snapshot


def test_human_migrate_ok_emits_header_details_actions_and_warnings(capsys):
    """Hits lines 958-967: _human_migrate_ok formats a successful result."""
    import studio.commands.migrate_from_cypilot as migration
    import studio.utils.ui as ui_mod

    # The ui module's _json_mode flag is a process-wide global; force it off
    # so the human-mode branch actually emits content this test can observe.
    ui_mod.set_json_mode(False)

    data = {
        "dry_run": True,
        "project_root": "/tmp/proj",
        "from_dir": "cypilot",
        "studio_dir": "/tmp/proj/.cf-constructor",
        "actions": {"target_dir": "created", "update": "skipped"},
        "warnings": ["something to look at", "another"],
    }

    migration._human_migrate_ok(data)

    out_err = capsys.readouterr()
    combined = out_err.out + out_err.err
    assert "Migration" in combined
    assert "/tmp/proj" in combined
    assert "cypilot" in combined
    assert "created" in combined
    assert "something to look at" in combined
    assert "another" in combined


def test_human_migrate_ok_omits_warnings_when_none(capsys):
    """Companion: covers the falsy-warnings branch of _human_migrate_ok."""
    import studio.commands.migrate_from_cypilot as migration
    import studio.utils.ui as ui_mod

    ui_mod.set_json_mode(False)

    data = {
        "dry_run": False,
        "project_root": "/tmp/proj",
        "from_dir": "cypilot",
        "studio_dir": "/tmp/proj/.cf-constructor",
        "actions": {"target_dir": "created"},
    }

    migration._human_migrate_ok(data)

    out_err = capsys.readouterr()
    combined = out_err.out + out_err.err
    # Header is printed without the [dry-run] prefix.
    assert "[dry-run]" not in combined
    assert "Migration" in combined


def test_migrate_core_toml_appends_warning_when_system_section_removed(tmp_path):
    """RC-10: deleting [system] surfaces a warning so users notice."""
    import studio.commands.migrate_from_cypilot as migration

    core_toml = tmp_path / "core.toml"
    core_toml.write_text(
        "[system]\n"
        'name = "test"\n'
        "\n"
        "[kits.sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:constructorfabric/studio-kit-sdlc"\n',
        encoding="utf-8",
    )

    warnings = []
    result = migration._migrate_core_toml(core_toml, warnings=warnings)

    assert result == "updated"
    assert len(warnings) >= 1
    assert "system" in warnings[0].lower()
    new_text = core_toml.read_text(encoding="utf-8")
    assert "[system]" not in new_text


def test_migrate_core_toml_does_not_warn_when_no_system_section(tmp_path):
    """RC-10: kit-rename-only path must not append a [system] warning."""
    import studio.commands.migrate_from_cypilot as migration

    core_toml = tmp_path / "core.toml"
    core_toml.write_text(
        "[kits.cypilot-sdlc]\n"
        'format = "CFS"\n'
        'path = "config/kits/cypilot-sdlc"\n'
        'version = "1.0.0"\n'
        'source = "github:cyberfabric/cyber-pilot-kit-sdlc"\n',
        encoding="utf-8",
    )

    warnings = []
    result = migration._migrate_core_toml(core_toml, warnings=warnings)

    assert result == "updated"
    assert warnings == []
    new_text = core_toml.read_text(encoding="utf-8")
    assert "[kits.sdlc]" in new_text


def test_migrate_creates_config_md_backups_on_success(tmp_path):
    """RC-11: backup target/config/{AGENTS,SKILL,README}.md before rewrite."""
    import re

    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path, version="3.9.0")

    # Ensure all three config md files exist in the legacy install so they
    # survive stage 2's copytree into target/config and trigger pre-rewrite
    # backups during _run_post_copy_rewrites.
    legacy_config = tmp_path / "cypilot" / "config"
    agents_sentinel = "Cypilot agents config uses {cypilot_path}\n"
    skill_sentinel = "Cypilot skill uses {cypilot_path}\n"
    readme_sentinel = "Cypilot readme references {cypilot_path}\n"
    (legacy_config / "AGENTS.md").write_text(agents_sentinel, encoding="utf-8")
    (legacy_config / "SKILL.md").write_text(skill_sentinel, encoding="utf-8")
    (legacy_config / "README.md").write_text(readme_sentinel, encoding="utf-8")

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 0, result
    config_md_backup = result["actions"]["config_md_backup"]
    assert config_md_backup["AGENTS.md"] == "created"
    assert config_md_backup["SKILL.md"] == "created"
    assert config_md_backup["README.md"] == "created"

    backups = result["backups"]
    agents_backup_matches = [
        b for b in backups if re.search(r"AGENTS\.md\.\d{8}-\d{6}\.backup$", b)
    ]
    skill_backup_matches = [
        b for b in backups if re.search(r"SKILL\.md\.\d{8}-\d{6}\.backup$", b)
    ]
    readme_backup_matches = [
        b for b in backups if re.search(r"README\.md\.\d{8}-\d{6}\.backup$", b)
    ]
    assert agents_backup_matches, f"no AGENTS.md backup in {backups}"
    assert skill_backup_matches, f"no SKILL.md backup in {backups}"
    assert readme_backup_matches, f"no README.md backup in {backups}"

    # Locate the config-dir backups specifically (root AGENTS.md backups also
    # match the AGENTS.md regex, so filter by the config dir path).
    config_dir_posix = (tmp_path / ".cf-constructor" / "config").as_posix()
    agents_cfg_backup = next(
        b for b in agents_backup_matches if b.startswith(config_dir_posix)
    )
    skill_cfg_backup = next(
        b for b in skill_backup_matches if b.startswith(config_dir_posix)
    )
    readme_cfg_backup = next(
        b for b in readme_backup_matches if b.startswith(config_dir_posix)
    )

    assert Path(agents_cfg_backup).read_text(encoding="utf-8") == agents_sentinel
    assert Path(skill_cfg_backup).read_text(encoding="utf-8") == skill_sentinel
    assert Path(readme_cfg_backup).read_text(encoding="utf-8") == readme_sentinel


def test_migrate_restores_config_md_files_when_config_markdown_rewrite_raises(
    tmp_path, monkeypatch
):
    """RC-11: when _migrate_config_markdown raises, restore from backups."""
    from studio.commands.migrate_from_cypilot import migrate_from_cypilot
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, version="3.9.0")

    legacy_config = tmp_path / "cypilot" / "config"
    agents_sentinel = "AGENTS sentinel uses {cypilot_path}\n"
    skill_sentinel = "SKILL sentinel uses {cypilot_path}\n"
    readme_sentinel = "README sentinel uses {cypilot_path}\n"
    (legacy_config / "AGENTS.md").write_text(agents_sentinel, encoding="utf-8")
    (legacy_config / "SKILL.md").write_text(skill_sentinel, encoding="utf-8")
    (legacy_config / "README.md").write_text(readme_sentinel, encoding="utf-8")

    def _raise_config_markdown(_config_dir):
        raise OSError("simulated")

    monkeypatch.setattr(migration, "_migrate_config_markdown", _raise_config_markdown)

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 1
    assert result["status"] == "ERROR"
    assert result["rewrite_step"] == "config_markdown"
    config_md_restore = result["actions"]["config_md_restore"]
    assert config_md_restore["AGENTS.md"] == "restored"
    assert config_md_restore["SKILL.md"] == "restored"
    assert config_md_restore["README.md"] == "restored"

    target_config = tmp_path / ".cf-constructor" / "config"
    assert (target_config / "AGENTS.md").read_text(encoding="utf-8") == agents_sentinel
    assert (target_config / "SKILL.md").read_text(encoding="utf-8") == skill_sentinel
    assert (target_config / "README.md").read_text(encoding="utf-8") == readme_sentinel


def test_migrate_no_config_md_backup_when_files_absent(tmp_path):
    """RC-11: absent config md files leave no entry in config_md_backup."""
    import re

    from studio.commands.migrate_from_cypilot import migrate_from_cypilot

    _make_legacy_project(tmp_path, version="3.9.0")

    # _make_legacy_project creates only config/AGENTS.md, so SKILL.md and
    # README.md never reach target/config — their backup setup must be a
    # no-op (no entry under config_md_backup, no backups appended).
    legacy_config = tmp_path / "cypilot" / "config"
    assert (legacy_config / "AGENTS.md").is_file()
    assert not (legacy_config / "SKILL.md").exists()
    assert not (legacy_config / "README.md").exists()

    rc, result = migrate_from_cypilot(
        project_root=tmp_path,
        from_dir="cypilot",
        to_dir=".cf-constructor",
        dry_run=False,
        force=False,
        yes=False,
        skip_update=True,
        force_overwrite_root=True,
    )

    assert rc == 0, result
    config_md_backup = result["actions"]["config_md_backup"]
    assert config_md_backup["AGENTS.md"] == "created"
    assert "SKILL.md" not in config_md_backup
    assert "README.md" not in config_md_backup

    backups = result.get("backups", [])
    config_dir_posix = (tmp_path / ".cf-constructor" / "config").as_posix()
    skill_backups = [b for b in backups if re.search(r"SKILL\.md\.\d{8}-\d{6}\.backup$", b)]
    readme_cfg_backups = [
        b
        for b in backups
        if re.search(r"README\.md\.\d{8}-\d{6}\.backup$", b) and b.startswith(config_dir_posix)
    ]
    assert skill_backups == []
    assert readme_cfg_backups == []


def test_migrate_config_markdown_touches_all_markdown_files_recursively(tmp_path):
    """Pin the recursive `config/**/*.md` walk contract.

    The rewriter now walks every markdown file under config_dir (including
    subdirectories like rules/). The 4 conservative substitutions apply
    uniformly. Non-markdown files are still ignored.
    """
    from studio.commands.migrate_from_cypilot import _migrate_config_markdown

    config_dir = tmp_path / "config"
    rules_dir = config_dir / "rules"
    rules_dir.mkdir(parents=True)
    payload = "Cypilot uses {cypilot_path} via `cpt ` calls.\n"
    md_files = [
        config_dir / "AGENTS.md",
        config_dir / "SKILL.md",
        config_dir / "README.md",
        config_dir / "CONTRIBUTING.md",
        rules_dir / "foo.md",
    ]
    for path in md_files:
        path.write_text(payload, encoding="utf-8")
    # A non-markdown file must NOT be rewritten.
    (config_dir / "ignored.txt").write_text(payload, encoding="utf-8")

    result = _migrate_config_markdown(config_dir)

    # Result contains relative-to-config_dir posix paths for every rewritten file.
    expected = sorted([
        "AGENTS.md", "SKILL.md", "README.md", "CONTRIBUTING.md", "rules/foo.md",
    ])
    assert sorted(result) == expected

    # Each markdown file received all four substitutions.
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        assert "Constructor Studio" in text
        assert "{cf-studio-path}" in text
        assert "Cypilot" not in text
        assert "{cypilot_path}" not in text

    # Non-markdown file untouched.
    assert (config_dir / "ignored.txt").read_text(encoding="utf-8") == payload


def test_migrate_core_toml_appends_warning_when_file_is_invalid(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_core_toml

    path = tmp_path / "core.toml"
    path.write_text("[broken section\n", encoding="utf-8")  # malformed TOML
    warnings = []

    result = _migrate_core_toml(path, warnings=warnings)

    assert result == "invalid"
    assert len(warnings) >= 1
    assert "core.toml" in warnings[0].lower()
    # Either "parse" or "parsed" should appear since the message uses
    # "could not be parsed"
    assert "parse" in warnings[0].lower()


def test_migrate_artifacts_toml_appends_warning_when_file_is_invalid(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_artifacts_toml

    path = tmp_path / "artifacts.toml"
    path.write_text("[broken section\n", encoding="utf-8")
    warnings = []

    result = _migrate_artifacts_toml(path, warnings=warnings)

    assert result == "invalid"
    assert len(warnings) >= 1
    assert "artifacts.toml" in warnings[0].lower()
    assert "parse" in warnings[0].lower()


def test_migrate_artifacts_toml_does_not_warn_when_valid(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_artifacts_toml

    path = tmp_path / "artifacts.toml"
    path.write_text(
        '[[systems]]\nname = "x"\nkit = "cypilot-sdlc"\n',
        encoding="utf-8",
    )
    warnings = []

    result = _migrate_artifacts_toml(path, warnings=warnings)

    assert result == "updated"
    assert warnings == []

    # Verify the kit got renamed
    import tomllib
    with open(path, "rb") as f:
        data = tomllib.load(f)
    assert data["systems"][0]["kit"] == "sdlc"


def test_migrate_core_toml_appends_warning_when_file_is_missing(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_core_toml

    path = tmp_path / "core.toml"   # deliberately not created
    warnings = []

    result = _migrate_core_toml(path, warnings=warnings)

    assert result == "missing"
    assert len(warnings) >= 1
    msg = warnings[0].lower()
    assert "core.toml" in msg
    assert "not found" in msg or "missing" in msg
    assert "skipped" in msg


def test_migrate_artifacts_toml_appends_warning_when_file_is_missing(tmp_path):
    from studio.commands.migrate_from_cypilot import _migrate_artifacts_toml

    path = tmp_path / "artifacts.toml"   # deliberately not created
    warnings = []

    result = _migrate_artifacts_toml(path, warnings=warnings)

    assert result == "missing"
    assert len(warnings) >= 1
    msg = warnings[0].lower()
    assert "artifacts.toml" in msg
    assert "not found" in msg or "missing" in msg
    assert "skipped" in msg


def test_migrate_config_markdown_returns_empty_when_all_files_missing(tmp_path):
    """No supported markdown files in config_dir → silent skip, empty list."""
    from studio.commands.migrate_from_cypilot import _migrate_config_markdown

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Deliberately do NOT create AGENTS.md, SKILL.md, or README.md.

    result = _migrate_config_markdown(config_dir)

    assert result == []
    # config_dir still exists and is empty (function did not create
    # placeholders).
    assert list(config_dir.iterdir()) == []


def test_migrate_config_markdown_skips_missing_processes_present_silently(tmp_path):
    """Mix of present/absent supported files: only present-with-changes appears in result."""
    from studio.commands.migrate_from_cypilot import _migrate_config_markdown

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    payload = "Cypilot uses {cypilot_path}\n"
    # Create AGENTS.md only. SKILL.md / README.md deliberately absent.
    (config_dir / "AGENTS.md").write_text(payload, encoding="utf-8")

    result = _migrate_config_markdown(config_dir)

    # Only the present, mutated file appears.
    assert result == ["AGENTS.md"]
    # AGENTS.md was rewritten.
    text = (config_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "Constructor Studio" in text
    assert "{cf-studio-path}" in text
    # SKILL.md and README.md were NOT created as side effects.
    assert not (config_dir / "SKILL.md").exists()
    assert not (config_dir / "README.md").exists()


def test_migrate_config_markdown_returns_empty_when_config_dir_missing(tmp_path):
    """Non-existent config_dir → returns [] silently, no auto-create."""
    from studio.commands.migrate_from_cypilot import _migrate_config_markdown

    config_dir = tmp_path / "does_not_exist"
    # Deliberately do NOT create config_dir.

    result = _migrate_config_markdown(config_dir)

    assert result == []
    # Function did NOT auto-create the directory as a side effect.
    assert not config_dir.exists()


def test_human_migrate_ok_surfaces_backup_paths_when_present(capsys):
    """The human output prints data['backups'] as a labeled list."""
    import studio.commands.migrate_from_cypilot as migration
    import studio.utils.ui as ui_mod

    # The ui module's _json_mode is True by default per the autouse fixture;
    # force it off so human-mode output is what we observe.
    ui_mod.set_json_mode(False)

    data = {
        "dry_run": False,
        "project_root": "/tmp/proj",
        "from_dir": "cypilot",
        "studio_dir": "/tmp/proj/.cf-constructor",
        "actions": {"target_dir": "created", "update": "PASS"},
        "warnings": [],
        "backups": [
            "/tmp/proj/.cf-constructor.20260101-120000.backup",
            "/tmp/proj/AGENTS.md.20260101-120000.backup",
        ],
    }

    migration._human_migrate_ok(data)

    out_err = capsys.readouterr()
    combined = out_err.out + out_err.err
    # Both backup paths appear in the output
    assert "/tmp/proj/.cf-constructor.20260101-120000.backup" in combined
    assert "/tmp/proj/AGENTS.md.20260101-120000.backup" in combined
    # A "Backups" label appears somewhere (case-insensitive)
    assert "backup" in combined.lower()


def test_ensure_supported_legacy_version_dry_run_bypass_does_not_trigger_bump(tmp_path, monkeypatch):
    """Pin the dry-run bypass contract: no subprocess, no bump call.

    When dry_run=True AND update_choice != "no" AND the legacy version is
    NOT in SUPPORTED_LEGACY_MIGRATION_VERSIONS, the function MUST return
    PASS without invoking _run_legacy_update_to_baseline. This test
    enforces that contract via a monkeypatched bump that raises if called.
    """
    import studio.commands.migrate_from_cypilot as migration
    from studio.commands.migrate_from_cypilot import (
        ensure_supported_legacy_version,
    )

    _make_legacy_project(tmp_path, version="3.8.0")   # unsupported version

    calls = {"bump": 0}

    def fake_bump(_project_root):
        calls["bump"] += 1
        raise AssertionError(
            "dry-run path must not invoke _run_legacy_update_to_baseline"
        )

    monkeypatch.setattr(migration, "_run_legacy_update_to_baseline", fake_bump)

    supported, result = ensure_supported_legacy_version(
        project_root=tmp_path,
        legacy_rel="cypilot",
        update_choice="yes",
        interactive=False,
        dry_run=True,
    )

    assert supported is True
    assert result["status"] == "PASS"
    assert result["dry_run"] is True
    assert result["actions"]["legacy_update"] == "dry_run"
    assert calls["bump"] == 0


# ---------------------------------------------------------------------------
# RC-24: cmd_init migration branch must prompt for target install dir
# ---------------------------------------------------------------------------


def test_cmd_init_migration_shows_install_options_before_migration(tmp_path, monkeypatch, capsys):
    """Interactive migration shows the standard init options menu first,
    defaulting to in-place migration (target = legacy dir name)."""
    import studio.commands.init as init_module
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, legacy_dir=".bootstrap", version="3.9.0")

    monkeypatch.chdir(tmp_path)

    # Force the prompt gate to consider stdin interactive (TTY).
    monkeypatch.setattr(init_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "n")

    # Capture _prompt_path calls; the options menu is declined, so no target-dir
    # specific prompt should be needed after the standard menu is shown.
    prompt_calls: list[tuple[str, str]] = []

    def fake_prompt_path(prompt, default):
        prompt_calls.append((prompt, default))
        return default

    monkeypatch.setattr(init_module, "_prompt_path", fake_prompt_path)

    # Stub should_migrate_from_cypilot via the source module: cmd_init imports
    # it via a function-local from-import inside the migration branch, so the
    # binding is re-resolved each call from the source module — see RC-24.
    monkeypatch.setattr(
        migration,
        "should_migrate_from_cypilot",
        lambda *args, **kwargs: True,
    )

    # Force the legacy preflight to pass without touching the filesystem.
    monkeypatch.setattr(
        migration,
        "ensure_supported_legacy_version",
        lambda **kwargs: (True, {"status": "PASS"}),
    )

    # Capture the migrate_from_cypilot call made by cmd_init.
    migrate_calls: list[dict] = []

    def fake_migrate(**kwargs):
        migrate_calls.append(kwargs)
        return (0, {"status": "PASS"})

    monkeypatch.setattr(migration, "migrate_from_cypilot", fake_migrate)

    # Default --migrate-from-cypilot=ask, so the migration approval is
    # treated as having come from the interactive prompt.
    rc = init_module.cmd_init([
        "--project-root", str(tmp_path),
    ])

    assert rc == 0
    err = capsys.readouterr().err
    assert "Installation options" in err
    assert "Constructor Studio directory: .bootstrap/" in err
    assert "Review or change installation options?" in err
    assert prompt_calls == []
    # migrate_from_cypilot was invoked with that default as to_dir.
    assert len(migrate_calls) == 1
    assert migrate_calls[0]["to_dir"] == ".bootstrap"
    assert migrate_calls[0]["from_dir"] == ".bootstrap"


def test_cmd_init_migration_install_options_can_change_target_dir(tmp_path, monkeypatch):
    """The standard init options menu controls migrate_from_cypilot to_dir."""
    import studio.commands.init as init_module
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, legacy_dir=".bootstrap", version="3.9.0")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_module.sys.stdin, "isatty", lambda: True)

    answers = iter(["y", "1", "7"])
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    def fake_prompt_path(prompt, default):
        assert "Constructor Studio directory" in prompt
        assert default == ".bootstrap"
        return ".custom-target"

    monkeypatch.setattr(init_module, "_prompt_path", fake_prompt_path)
    monkeypatch.setattr(
        migration,
        "should_migrate_from_cypilot",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        migration,
        "ensure_supported_legacy_version",
        lambda **kwargs: (True, {"status": "PASS"}),
    )

    migrate_calls: list[dict] = []

    def fake_migrate(**kwargs):
        migrate_calls.append(kwargs)
        return (0, {"status": "PASS"})

    monkeypatch.setattr(migration, "migrate_from_cypilot", fake_migrate)

    rc = init_module.cmd_init([
        "--project-root", str(tmp_path),
    ])

    assert rc == 0
    assert len(migrate_calls) == 1
    assert migrate_calls[0]["to_dir"] == ".custom-target"
    assert migrate_calls[0]["from_dir"] == ".bootstrap"


def test_cmd_init_migration_uses_install_dir_flag_when_provided(tmp_path, monkeypatch):
    """When --install-dir is given, cmd_init MUST NOT prompt for the
    target install dir and must pass the flag value through to
    migrate_from_cypilot as to_dir."""
    import studio.commands.init as init_module
    import studio.commands.migrate_from_cypilot as migration

    _make_legacy_project(tmp_path, legacy_dir=".bootstrap", version="3.9.0")

    monkeypatch.chdir(tmp_path)

    # _prompt_path must NOT be called when both --project-root and
    # --install-dir are given.
    def fake_prompt_path_raising(prompt, default):
        raise AssertionError(
            f"_prompt_path should not be called; got prompt={prompt!r}"
        )

    monkeypatch.setattr(init_module, "_prompt_path", fake_prompt_path_raising)

    monkeypatch.setattr(
        migration,
        "ensure_supported_legacy_version",
        lambda **kwargs: (True, {"status": "PASS"}),
    )

    migrate_calls: list[dict] = []

    def fake_migrate(**kwargs):
        migrate_calls.append(kwargs)
        return (0, {"status": "PASS"})

    monkeypatch.setattr(migration, "migrate_from_cypilot", fake_migrate)

    rc = init_module.cmd_init([
        "--project-root", str(tmp_path),
        "--migrate-from-cypilot=yes",
        "--install-dir=.custom-target",
    ])

    assert rc == 0
    assert len(migrate_calls) == 1
    assert migrate_calls[0]["to_dir"] == ".custom-target"
    assert migrate_calls[0]["from_dir"] == ".bootstrap"


def test_migration_cleanup_preserves_github_workflows(tmp_path, monkeypatch):
    """Regression guard: _cleanup_legacy_host_integrations MUST NOT touch
    .github/workflows/*.yml.

    ci.yml was deleted externally in commit 4999fb5 (not by migration code),
    but without an invariant test a future change to cleanup globs or helper
    logic could accidentally widen the cleanup surface to include workflow
    files.  This test pins the contract.
    """
    import studio.commands.agents as agents_mod
    from studio.commands.migrate_from_cypilot import _cleanup_legacy_host_integrations

    # --- sentinel workflow files -------------------------------------------------
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)

    ci_content = "# sentinel: ci workflow\nname: CI\non: [push]\n"
    ci_extra_content = "# sentinel: extra workflow\nname: Extra\non: [pull_request]\n"
    ci_yml = workflows_dir / "ci.yml"
    ci_extra_yml = workflows_dir / "ci-extra.yml"
    ci_yml.write_text(ci_content, encoding="utf-8")
    ci_extra_yml.write_text(ci_extra_content, encoding="utf-8")

    # --- fake copilot legacy artifacts (so the migrator has something to clean) --
    # These must look like generator stubs so _is_legacy_generator_stub returns True.
    _STUB = (
        "<!-- Generated by cypilot agents -- do not edit -->\n"
        "ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/SKILL.md`\n"
    )
    agents_dir = tmp_path / ".github" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "cf-constructor-analyze.agent.md").write_text(_STUB, encoding="utf-8")

    prompts_dir = tmp_path / ".github" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "cypilot-generate.prompt.md").write_text(_STUB, encoding="utf-8")

    # --- stub out regeneration so the test does not need a real studio_dir tree --
    monkeypatch.setattr(agents_mod, "_process_single_agent", lambda *args, **kwargs: None)

    # --- run the cleanup ---------------------------------------------------------
    studio_dir = tmp_path / "cypilot"
    studio_dir.mkdir()
    warnings: list[str] = []
    result = _cleanup_legacy_host_integrations(
        project_root=tmp_path,
        warnings=warnings,
        studio_dir=studio_dir,
    )

    # --- invariant assertions ----------------------------------------------------
    # Both workflow files must survive byte-identical.
    assert ci_yml.exists(), ".github/workflows/ci.yml was deleted by migration cleanup"
    assert ci_yml.read_text(encoding="utf-8") == ci_content

    assert ci_extra_yml.exists(), ".github/workflows/ci-extra.yml was deleted by migration cleanup"
    assert ci_extra_yml.read_text(encoding="utf-8") == ci_extra_content

    # The cleanup must have removed the copilot legacy stubs (verifies the
    # test exercises the real cleanup path, not a vacuous no-op).
    removed_copilot = result.get("removed", {}).get("copilot", [])
    assert len(removed_copilot) > 0, (
        "expected at least one copilot legacy artifact to be removed; "
        "the test fixture may need updating if the glob patterns changed"
    )


def test_generate_agents_preserves_github_workflows(tmp_path, monkeypatch):
    """Regression guard: `cfs generate-agents` (i.e. _process_single_agent for the
    copilot host) MUST NOT touch .github/workflows/*.yml.

    Companion to test_migration_cleanup_preserves_github_workflows: pins the
    SAME invariant for the second entry point that operates on the .github/
    tree (the generate-agents code path, not just the migration cleanup path).
    """
    import studio.commands.agents as agents_mod

    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True)
    ci_content = "# sentinel: ci workflow\nname: CI\non: [push]\n"
    ci_yml = workflows_dir / "ci.yml"
    ci_yml.write_text(ci_content, encoding="utf-8")

    # _process_single_agent reads its config from a Studio install layout; build
    # a minimal one so the helper has something to walk. Then exercise the
    # cleanup helpers directly — those are the only code paths under
    # _process_single_agent that could theoretically reach into .github/.
    studio_dir = tmp_path / ".cf-studio"
    (studio_dir / "config").mkdir(parents=True)

    # Drop legacy stubs in the locations the cleanup helpers actually scan.
    _STUB = (
        "<!-- Generated by cypilot agents -- do not edit -->\n"
        "ALWAYS open and follow `{cypilot_path}/.core/skills/cypilot/SKILL.md`\n"
    )
    agents_dir = tmp_path / ".github" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "cypilot-analyze.agent.md").write_text(_STUB, encoding="utf-8")

    # Exercise the three cleanup helpers `_process_single_agent` calls
    # transitively for the copilot host.
    agents_mod._cleanup_studio_legacy_subagents("copilot", tmp_path, dry_run=False)
    agents_mod._cleanup_studio_legacy_markers("copilot", tmp_path, dry_run=False)
    agents_mod._cleanup_legacy_skill_dirs("copilot", tmp_path, dry_run=False)

    # Invariant: ci.yml is byte-identical after all cleanup helpers ran.
    assert ci_yml.exists(), (
        ".github/workflows/ci.yml was deleted by a generate-agents cleanup helper"
    )
    assert ci_yml.read_text(encoding="utf-8") == ci_content
