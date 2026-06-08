import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.init import cmd_init, _copy_from_cache, _prompt_install_options
from studio.commands.update import cmd_update
from studio.utils.ui import set_json_mode


def _make_cache(root: Path) -> Path:
    cache = root / "cache"
    for name in ("requirements", "schemas", "workflows", "skills"):
        (cache / name).mkdir(parents=True, exist_ok=True)
        (cache / name / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    arch = cache / "architecture" / "specs" / "kit"
    arch.mkdir(parents=True, exist_ok=True)
    for rel in (
        "specs/traceability.md",
        "specs/CDSL.md",
        "specs/PDSL.md",
        "specs/cli.md",
        "specs/CLISPEC.md",
        "specs/artifacts-registry.md",
        "specs/kit/constraints.md",
        "specs/kit/kit.md",
    ):
        target = cache / "architecture" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {rel}\n", encoding="utf-8")
    (cache / "whatsnew.toml").write_text(
        '[whatsnew."v1.0.0"]\nsummary = "Initial"\ndetails = ""\n',
        encoding="utf-8",
    )
    (cache / "version.toml").write_text(
        '[cfs]\nversion = "v1.0.0"\n',
        encoding="utf-8",
    )
    return cache


def _write_initialized_project(root: Path, install_rel: str = ".bootstrap") -> Path:
    (root / ".git").mkdir()
    (root / "AGENTS.md").write_text(
        f'<!-- @cf:root-agents -->\n```toml\ncf-studio-path = "{install_rel}"\n```\n<!-- /@cf:root-agents -->\n',
        encoding="utf-8",
    )
    studio_dir = root / install_rel
    (studio_dir / "config").mkdir(parents=True)
    (studio_dir / "config" / "core.toml").write_text(
        'version = "1.0"\nproject_root = ".."\n\n[install]\nkit_tracking = "tracked"\n\n[kits.sdlc]\nsource = ""\npath = "config/kits/sdlc"\ntracking = "tracked"\n',
        encoding="utf-8",
    )
    return studio_dir


def _run_json(fn, argv):
    set_json_mode(True)
    try:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(argv)
        return rc, json.loads(out.getvalue())
    finally:
        set_json_mode(False)


def test_prompt_install_options_can_edit_all_install_choices():
    with TemporaryDirectory() as td, patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = True
        stderr = io.StringIO()
        answers = [
            "y", "2", "Renamed Project",
            "y", "3", "t",
            "y", "4", "t",
            "y", "5", "i",
            "y", "6", "t",
            "y", "7",
        ]
        with patch("builtins.input", side_effect=answers), redirect_stderr(stderr):
            (
                install_rel,
                project_name,
                runtime_tracking,
                agent_tracking,
                default_tracking,
                overrides,
            ) = _prompt_install_options(
                Path(td),
                ".cf-studio",
                "Original",
                "ignored",
                "ignored",
                "tracked",
                {},
                True,
            )

    assert install_rel == ".cf-studio"
    assert project_name == "Renamed Project"
    assert runtime_tracking == "tracked"
    assert agent_tracking == "tracked"
    assert default_tracking == "ignored"
    assert overrides == {"sdlc": "tracked"}
    prompt = stderr.getvalue()
    assert "Project name?" in prompt
    assert "Runtime files (.core/.gen) git tracking" in prompt
    assert "Git tracking for runtime files (.core/.gen)?" in prompt
    assert "Agent integration files git tracking" in prompt
    assert "Git tracking for agent integration files?" in prompt
    assert "Default git tracking for kits?" in prompt
    assert "Kit sdlc git tracking: tracked" in prompt


def test_prompt_install_options_non_interactive_returns_defaults():
    install_rel, project_name, runtime_tracking, agent_tracking, default_tracking, overrides = _prompt_install_options(
        Path("/tmp/project"),
        ".cf-studio",
        "Project",
        "ignored",
        "ignored",
        "tracked",
        {"sdlc": "ignored"},
        False,
    )

    assert install_rel == ".cf-studio"
    assert project_name == "Project"
    assert runtime_tracking == "ignored"
    assert agent_tracking == "ignored"
    assert default_tracking == "tracked"
    assert overrides == {"sdlc": "ignored"}


def test_init_writes_minimal_gitignore_and_per_kit_ignored_policy():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        (root / ".git").mkdir()
        cache = _make_cache(Path(td))

        def fake_install_default_kit(studio_dir, _interactive, _actions, _errors):
            kit_dir = studio_dir / "config" / "kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# SDLC\n", encoding="utf-8")
            core_path = studio_dir / "config" / "core.toml"
            core_path.write_text(
                core_path.read_text(encoding="utf-8")
                + '\n[kits.sdlc]\npath = "config/kits/sdlc"\n',
                encoding="utf-8",
            )
            return {"sdlc": {"path": "config/kits/sdlc"}}

        with patch("studio.commands.init.CACHE_DIR", cache), patch(
            "studio.commands.init._install_default_kit",
            side_effect=fake_install_default_kit,
        ):
            rc, result = _run_json(
                cmd_init,
                [
                    "--project-root",
                    str(root),
                    "--install-dir",
                    ".bootstrap",
                    "--kit-tracking",
                    "tracked",
                    "--kit-tracking",
                    "sdlc=untracked",
                    "--yes",
                ],
            )

        assert rc == 0
        assert result["status"] == "PASS"
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        assert ".bootstrap/.core/" in gitignore
        assert ".bootstrap/.gen/" in gitignore
        assert ".bootstrap/whatsnew.toml" not in gitignore
        assert ".bootstrap/version.toml" not in gitignore
        assert ".bootstrap/config/kits/sdlc/" in gitignore
        assert ".bootstrap/config/kits/\n" not in gitignore
        assert ".github/\n" not in gitignore
        assert ".github/prompts/cf*.prompt.md" in gitignore
        core = (root / ".bootstrap" / "config" / "core.toml").read_text(encoding="utf-8")
        assert 'tracking = "ignored"' in core
        assert (root / ".bootstrap" / "whatsnew.toml").is_file()
        assert (root / ".bootstrap" / "version.toml").is_file()


def test_init_tracked_runtime_and_agents_are_not_gitignored():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        (root / ".git").mkdir()
        cache = _make_cache(Path(td))

        with patch("studio.commands.init.CACHE_DIR", cache), patch(
            "studio.commands.init._install_default_kit",
            return_value={},
        ):
            rc, result = _run_json(
                cmd_init,
                [
                    "--project-root",
                    str(root),
                    "--install-dir",
                    ".bootstrap",
                    "--runtime-tracking",
                    "tracked",
                    "--agent-tracking",
                    "tracked",
                    "--yes",
                ],
            )

        assert rc == 0
        assert result["status"] == "PASS"
        assert result["runtime_tracking"] == "tracked"
        assert result["agent_tracking"] == "tracked"
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        assert ".bootstrap/.core/" not in gitignore
        assert ".bootstrap/.gen/" not in gitignore
        assert ".codex/agents/cf*.toml" not in gitignore
        assert ".github/prompts/cf*.prompt.md" not in gitignore
        core = (root / ".bootstrap" / "config" / "core.toml").read_text(encoding="utf-8")
        assert 'runtime_tracking = "tracked"' in core
        assert 'agent_tracking = "tracked"' in core


def test_init_interactive_prompts_for_installed_kit_tracking():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        (root / ".git").mkdir()
        cache = _make_cache(Path(td))

        def fake_install_default_kit(studio_dir, _interactive, _actions, _errors):
            kit_dir = studio_dir / "config" / "kits" / "sdlc"
            kit_dir.mkdir(parents=True)
            (kit_dir / "SKILL.md").write_text("# SDLC\n", encoding="utf-8")
            core_path = studio_dir / "config" / "core.toml"
            core_path.write_text(
                core_path.read_text(encoding="utf-8")
                + '\n[kits.sdlc]\npath = "config/kits/sdlc"\n',
                encoding="utf-8",
            )
            return {"sdlc": {"path": "config/kits/sdlc"}}

        with patch("studio.commands.init.CACHE_DIR", cache), patch(
            "studio.commands.init._install_default_kit",
            side_effect=fake_install_default_kit,
        ), patch("builtins.input", side_effect=[str(root), "y", "1", ".bootstrap", "n", "a", "i"]), patch(
            "sys.stdin"
        ) as mock_stdin:
            mock_stdin.isatty.return_value = True
            stderr = io.StringIO()
            stdout = io.StringIO()
            set_json_mode(True)
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    rc = cmd_init([])
                result = json.loads(stdout.getvalue())
            finally:
                set_json_mode(False)

        assert rc == 0
        assert result["status"] == "PASS"
        assert "Installation options" in stderr.getvalue()
        assert "Review or change installation options?" in stderr.getvalue()
        assert "Select installation option" in stderr.getvalue()
        assert "Git tracking for kit 'sdlc'?" in stderr.getvalue()
        core = (root / ".bootstrap" / "config" / "core.toml").read_text(encoding="utf-8")
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        assert 'tracking = "ignored"' in core
        assert ".bootstrap/config/kits/sdlc/" in gitignore


def test_init_existing_project_repairs_instead_of_failing():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        _write_initialized_project(root)
        cache = _make_cache(Path(td))

        with patch("studio.commands.init.CACHE_DIR", cache):
            rc, result = _run_json(
                cmd_init,
                ["--project-root", str(root), "--yes"],
            )

        assert rc == 0
        assert result["status"] == "REPAIRED"
        assert result["version_changed"] is False
        assert result["version_source"] == "project_config"
        assert (root / ".bootstrap" / ".core" / "README.md").is_file()
        assert (root / ".bootstrap" / "whatsnew.toml").is_file()
        assert (root / ".bootstrap" / "version.toml").is_file()
        assert ".bootstrap/.core/" in (root / ".gitignore").read_text(encoding="utf-8")


def test_init_dry_run_reports_install_root_metadata_files():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        cache = _make_cache(Path(td))

        with patch("studio.commands.init.CACHE_DIR", cache):
            rc, result = _run_json(
                cmd_init,
                ["--project-root", str(root), "--install-dir", ".bootstrap", "--dry-run", "--yes"],
            )

        assert rc == 0
        copy_actions = json.loads(result["actions"]["copy"])
        assert copy_actions["whatsnew.toml"] == "dry_run"
        assert copy_actions["version.toml"] == "dry_run"


def test_init_repair_dry_run_reports_install_root_metadata_files():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        _write_initialized_project(root)
        cache = _make_cache(Path(td))

        with patch("studio.commands.init.CACHE_DIR", cache):
            rc, result = _run_json(cmd_init, ["--project-root", str(root), "--dry-run", "--yes"])

        assert rc == 0
        assert result["actions"]["copy"]["whatsnew.toml"] == "dry_run"
        assert result["actions"]["copy"]["version.toml"] == "dry_run"


def test_force_copy_root_file_unlinks_symlink_destination():
    with TemporaryDirectory() as td:
        workspace = Path(td)
        cache = _make_cache(workspace)
        target_dir = workspace / "proj" / ".bootstrap"
        target_dir.mkdir(parents=True)
        outside = workspace / "outside-version.toml"
        outside.write_text("outside", encoding="utf-8")
        link = target_dir / "version.toml"
        try:
            link.symlink_to(outside)
        except OSError:
            return

        result = _copy_from_cache(cache, target_dir, force=True)

        assert result["version.toml"] == "updated"
        assert not link.is_symlink()
        assert '[cfs]' in link.read_text(encoding="utf-8")
        assert outside.read_text(encoding="utf-8") == "outside"


def test_force_copy_root_file_removes_stale_destination_when_missing_in_cache():
    with TemporaryDirectory() as td:
        workspace = Path(td)
        cache = _make_cache(workspace)
        (cache / "whatsnew.toml").unlink()
        target_dir = workspace / "proj" / ".bootstrap"
        target_dir.mkdir(parents=True)
        stale = target_dir / "whatsnew.toml"
        stale.write_text("stale", encoding="utf-8")

        result = _copy_from_cache(cache, target_dir, force=True)

        assert result["whatsnew.toml"] == "missing_in_cache"
        assert not stale.exists()


def test_force_copy_root_file_replaces_directory_collision():
    with TemporaryDirectory() as td:
        workspace = Path(td)
        cache = _make_cache(workspace)
        target_dir = workspace / "proj" / ".bootstrap"
        collision = target_dir / "version.toml"
        collision.mkdir(parents=True)
        (collision / "nested").write_text("stale", encoding="utf-8")

        result = _copy_from_cache(cache, target_dir, force=True)

        assert result["version.toml"] == "updated"
        assert collision.is_file()
        assert '[cfs]' in collision.read_text(encoding="utf-8")


def test_dry_run_reports_stale_root_file_removal_when_cache_source_missing():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        studio_dir = _write_initialized_project(root)
        cache = _make_cache(Path(td))
        (cache / "whatsnew.toml").unlink()
        (studio_dir / "whatsnew.toml").write_text("stale", encoding="utf-8")

        with patch("studio.commands.update.CACHE_DIR", cache):
            rc, result = _run_json(cmd_update, ["--project-root", str(root), "--dry-run"])

        assert rc == 0
        assert result["actions"]["core_update"]["whatsnew.toml"] == "would_remove"


def test_update_skips_kit_updates_by_default():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        _write_initialized_project(root)
        cache = _make_cache(Path(td))

        with patch("studio.commands.update.CACHE_DIR", cache), patch(
            "studio.commands.kit.update_kit",
        ) as update_kit, patch(
            "studio.commands.validate_kits.run_validate_kits",
            return_value=(0, {"status": "PASS"}),
        ):
            rc, result = _run_json(cmd_update, ["--project-root", str(root), "-y"])

        assert rc == 0
        update_kit.assert_not_called()
        assert result["actions"]["kits"]["status"] == "skipped"


def test_update_with_kits_yes_runs_kit_update_pipeline():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        _write_initialized_project(root)
        cache = _make_cache(Path(td))
        (cache / "kits" / "sdlc").mkdir(parents=True)

        with patch("studio.commands.update.CACHE_DIR", cache), patch(
            "studio.commands.kit.update_kit",
            return_value={"kit": "sdlc", "version": {"status": "current"}, "gen": {"files_written": 0}},
        ) as update_kit, patch(
            "studio.commands.validate_kits.run_validate_kits",
            return_value=(0, {"status": "PASS"}),
        ):
            rc, result = _run_json(
                cmd_update,
                ["--project-root", str(root), "-y", "--with-kits", "yes"],
            )

        assert rc == 0
        update_kit.assert_called_once()
        assert "sdlc" in result["actions"]["kits"]


def test_update_with_kits_dry_run_plans_github_kit_without_download():
    with TemporaryDirectory() as td:
        root = Path(td) / "proj"
        root.mkdir()
        studio_dir = _write_initialized_project(root)
        cache = _make_cache(Path(td))
        core_toml = studio_dir / "config" / "core.toml"
        core_toml.write_text(
            core_toml.read_text(encoding="utf-8").replace(
                'source = ""',
                'source = "github:constructorfabric/sdlc"',
            ),
            encoding="utf-8",
        )

        with patch("studio.commands.update.CACHE_DIR", cache), patch(
            "studio.commands.kit._download_kit_from_github_with_authority",
        ) as download_kit:
            rc, result = _run_json(
                cmd_update,
                [
                    "--project-root",
                    str(root),
                    "--dry-run",
                    "--with-kits",
                    "yes",
                ],
            )

        assert rc == 0
        download_kit.assert_not_called()
        assert result["actions"]["kits"]["sdlc"]["version"]["status"] == "dry_run"
