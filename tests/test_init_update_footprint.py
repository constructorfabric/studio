import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.commands.init import cmd_init
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
        'version = "1.0"\nproject_root = ".."\n\n[install]\nkit_tracking = "tracked"\n\n[kits.sdlc]\nsource = ""\n',
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


def test_init_writes_minimal_gitignore_and_ignored_kits_policy():
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
                    "--kit-tracking",
                    "ignored",
                    "--yes",
                ],
            )

        assert rc == 0
        assert result["status"] == "PASS"
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        assert ".bootstrap/.core/" in gitignore
        assert ".bootstrap/.gen/" in gitignore
        assert ".bootstrap/config/kits/" in gitignore
        assert ".github/\n" not in gitignore
        assert ".github/prompts/cf*.prompt.md" in gitignore


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
        assert ".bootstrap/.core/" in (root / ".gitignore").read_text(encoding="utf-8")


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
