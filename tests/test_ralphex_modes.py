"""
Tests for ralphex delegation mode selection and orchestration.

Covers:
- resolve_plans_dir(): config precedence for plans directory resolution
- build_delegation_command(): CLI command assembly with mode flags
- check_review_precondition(): committed changes verification on feature branch
- Worktree constraint enforcement: --worktree only valid for full/tasks-only
"""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.ralphex_export import (
    resolve_plans_dir,
    build_delegation_command,
    check_review_precondition,
)


class TestResolvePlansDir:
    """Tests for resolve_plans_dir() — config precedence for plans directory."""

    def test_local_ralphex_config_takes_priority(self):
        """plans_dir from .ralphex/config overrides default."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text(
                'plans_dir = "custom/plans"\n', encoding="utf-8"
            )
            result = resolve_plans_dir(tmp)
            assert result == os.path.join(tmp, "custom/plans")

    def test_global_config_used_when_no_local(self):
        """plans_dir from ~/.config/ralphex/config used when no .ralphex/ exists."""
        with TemporaryDirectory() as tmp:
            global_dir = Path(tmp) / "global_config" / "ralphex"
            global_dir.mkdir(parents=True)
            (global_dir / "config").write_text(
                'plans_dir = "global/plans"\n', encoding="utf-8"
            )
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "global_config")}):
                result = resolve_plans_dir(tmp)
            assert result == os.path.join(tmp, "global/plans")

    def test_default_docs_plans_when_no_config(self):
        """Falls back to docs/plans/ when no ralphex config exists."""
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "no_config")}):
                result = resolve_plans_dir(tmp)
            assert result == os.path.join(tmp, "docs/plans")

    def test_default_dir_used_when_no_config(self):
        """Caller-provided default_dir is used when no ralphex config exists."""
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "no_config")}):
                result = resolve_plans_dir(tmp, default_dir=".bootstrap/.plans/my-plan")
            assert result == os.path.join(tmp, ".bootstrap/.plans/my-plan")

    def test_local_config_overrides_global(self):
        """Local .ralphex/config takes precedence over global config."""
        with TemporaryDirectory() as tmp:
            # Local config
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text(
                'plans_dir = "local/plans"\n', encoding="utf-8"
            )
            # Global config
            global_dir = Path(tmp) / "global_config" / "ralphex"
            global_dir.mkdir(parents=True)
            (global_dir / "config").write_text(
                'plans_dir = "global/plans"\n', encoding="utf-8"
            )
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "global_config")}):
                result = resolve_plans_dir(tmp)
            assert result == os.path.join(tmp, "local/plans")

    def test_absolute_plans_dir_in_config(self):
        """Absolute plans_dir in config is returned as-is."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text(
                f'plans_dir = "{tmp}/absolute/plans"\n', encoding="utf-8"
            )
            result = resolve_plans_dir(tmp)
            assert result == os.path.join(tmp, "absolute/plans")

    def test_empty_config_falls_back_to_default(self):
        """Empty .ralphex/config falls back to docs/plans/."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text("", encoding="utf-8")
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "no_config")}):
                result = resolve_plans_dir(tmp)
            assert result == os.path.join(tmp, "docs/plans")

    def test_explicit_override_takes_highest_priority(self):
        """Explicit override beats local .ralphex/config."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text(
                'plans_dir = "local/plans"\n', encoding="utf-8"
            )
            result = resolve_plans_dir(tmp, override="explicit/plans")
            assert result == os.path.join(tmp, "explicit/plans")

    def test_explicit_override_absolute_path(self):
        """Absolute explicit override returned as-is."""
        with TemporaryDirectory() as tmp:
            result = resolve_plans_dir(tmp, override="/absolute/plans")
            assert result == "/absolute/plans"

    def test_explicit_override_relative_path(self):
        """Relative explicit override resolved against repo_root."""
        with TemporaryDirectory() as tmp:
            result = resolve_plans_dir(tmp, override="my/plans")
            assert result == os.path.join(tmp, "my/plans")


class TestBuildDelegationCommand:
    """Tests for build_delegation_command() — CLI command assembly."""

    def test_full_execute_mode(self):
        """Full execute mode: ralphex <plan.md>."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="execute",
        )
        assert cmd == ["/usr/local/bin/ralphex", "/repo/docs/plans/task.md"]

    def test_tasks_only_mode(self):
        """Tasks-only mode appends --tasks-only flag."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="tasks-only",
        )
        assert cmd == [
            "/usr/local/bin/ralphex",
            "/repo/docs/plans/task.md",
            "--tasks-only",
        ]

    def test_review_mode_without_plan(self):
        """Review mode: ralphex --review (no plan file required)."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file=None,
            mode="review",
        )
        assert cmd == ["/usr/local/bin/ralphex", "--review"]

    def test_review_mode_with_plan_as_context(self):
        """Review mode with optional plan file for context."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="review",
        )
        assert cmd == [
            "/usr/local/bin/ralphex",
            "--review",
            "/repo/docs/plans/task.md",
        ]

    def test_worktree_flag_for_execute_mode(self):
        """--worktree is appended for full execute mode."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="execute",
            worktree=True,
        )
        assert "--worktree" in cmd

    def test_worktree_flag_for_tasks_only_mode(self):
        """--worktree is appended for tasks-only mode."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="tasks-only",
            worktree=True,
        )
        assert "--worktree" in cmd
        assert "--tasks-only" in cmd

    def test_worktree_flag_not_appended_for_review(self):
        """--worktree is NOT appended for review mode (constraint enforced)."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file=None,
            mode="review",
            worktree=True,
        )
        assert "--worktree" not in cmd

    def test_serve_flag_appended(self):
        """--serve flag is appended when requested."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="execute",
            serve=True,
        )
        assert "--serve" in cmd

    def test_all_flags_combined(self):
        """All flags combine correctly for full execute + worktree + serve."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="execute",
            worktree=True,
            serve=True,
        )
        assert cmd == [
            "/usr/local/bin/ralphex",
            "/repo/docs/plans/task.md",
            "--worktree",
            "--serve",
        ]

    def test_serve_flag_not_appended_when_false(self):
        """--serve is not in command when serve=False."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file="/repo/docs/plans/task.md",
            mode="execute",
            serve=False,
        )
        assert "--serve" not in cmd

    def test_serve_flag_not_appended_for_review(self):
        """--serve is NOT appended for review mode even when requested."""
        cmd = build_delegation_command(
            ralphex_path="/usr/local/bin/ralphex",
            plan_file=None,
            mode="review",
            serve=True,
        )
        assert "--serve" not in cmd


class TestCheckReviewPrecondition:
    """Tests for check_review_precondition() — committed changes verification."""

    def test_passes_when_branch_has_commits_ahead(self):
        """Precondition passes when feature branch has commits ahead of default."""
        proc = MagicMock(returncode=0, stdout="abc1234\ndef5678\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition(default_branch="main")
        assert result["ok"] is True
        assert result["commit_count"] == 2

    def test_fails_when_no_commits_ahead(self):
        """Precondition fails when feature branch has no commits ahead."""
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition(default_branch="main")
        assert result["ok"] is False
        assert "no committed changes" in result["message"].lower()

    def test_fails_when_on_default_branch(self):
        """Precondition fails when HEAD is on the default branch itself."""
        # git rev-list returns empty (no commits ahead of self)
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition(default_branch="main")
        assert result["ok"] is False

    def test_fails_when_git_command_errors(self):
        """Precondition fails gracefully when git command errors."""
        proc = MagicMock(returncode=128, stdout="", stderr="fatal: bad revision")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition(default_branch="main")
        assert result["ok"] is False
        assert "error" in result["message"].lower() or "failed" in result["message"].lower()

    def test_uses_default_branch_parameter(self):
        """Git command references the specified default branch."""
        proc = MagicMock(returncode=0, stdout="abc1234\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc) as mock_run:
            check_review_precondition(default_branch="master")
        call_args = mock_run.call_args[0][0]
        assert any("master" in str(arg) for arg in call_args)


class TestWorktreeConstraintEnforcement:
    """Integration-level tests confirming worktree is only valid for execute/tasks-only."""

    def test_worktree_valid_modes(self):
        """--worktree appears only in commands for valid modes."""
        for mode in ("execute", "tasks-only"):
            cmd = build_delegation_command(
                ralphex_path="ralphex",
                plan_file="plan.md",
                mode=mode,
                worktree=True,
            )
            assert "--worktree" in cmd, f"--worktree should be in {mode} mode"

    def test_worktree_invalid_mode(self):
        """--worktree does NOT appear for review mode even when requested."""
        cmd = build_delegation_command(
            ralphex_path="ralphex",
            plan_file=None,
            mode="review",
            worktree=True,
        )
        assert "--worktree" not in cmd
