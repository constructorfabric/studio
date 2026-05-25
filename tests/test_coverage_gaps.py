"""
Tests to close per-file coverage gaps for CI test-coverage gate.

Covers uncovered branches in:
- _core_config.py: OSError/ValueError exception path in load_core_config
- doctor.py: PASS, WARN (has_warn), FAIL branches, incompatible ralphex
- delegate.py: relative plan_dir resolution, _print_human delegated branch
- ralphex_export.py: error paths in compile, run_delegation, _parse_toml_frontmatter, etc.
"""

import io
import os
import subprocess
import sys
import textwrap
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.commands._core_config import load_core_config, find_core_toml
from studio.commands.doctor import cmd_doctor, _check_ralphex
from studio.commands.delegate import cmd_delegate, _result_to_exit_code, _print_human
from studio.utils.ui import is_json_mode
from studio.ralphex_export import (
    compile_delegation_plan,
    run_delegation,
    run_validation_commands,
    check_review_precondition,
    _parse_toml_frontmatter,
    _extract_section_items,
    _extract_section_body,
    _resolve_plan_manifest_path,
    _format_phase_reference_path,
    _read_plans_dir_from_config,
    DelegationLifecycle,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PLAN_TOML = textwrap.dedent("""\
    [plan]
    task = "Implement widget-feature"
    type = "implement"
    target = "FEATURE"

    [[phases]]
    number = 1
    title = "Widget Factory"
    slug = "widget-factory"
    file = "phase-01.md"
    status = "pending"
    kind = "delivery"
    depends_on = []
    input_files = ["architecture/features/widget.md"]
    output_files = ["src/widget.py", "tests/test_widget.py"]
""")

PHASE_01_CONTENT = textwrap.dedent("""\
    ```toml
    [phase]
    plan = "widget-feature"
    number = 1
    total = 1
    type = "implement"
    title = "Widget Factory"
    depends_on = []
    input_files = ["architecture/features/widget.md"]
    output_files = ["src/widget.py", "tests/test_widget.py"]
    outputs = []
    inputs = []
    ```

    ## What

    Build the widget factory module.

    ## Task

    1. Read design spec.
    2. Implement WidgetFactory class.

    ## Acceptance Criteria

    - [ ] WidgetFactory class exists
    - [ ] Unit tests pass
""")


def _make_plan_dir(tmp: str) -> str:
    plan_dir = Path(tmp) / "test-plan"
    plan_dir.mkdir()
    (plan_dir / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
    (plan_dir / "phase-01.md").write_text(PHASE_01_CONTENT, encoding="utf-8")
    return str(plan_dir)


def _make_repo_with_ralphex_config(tmp: str) -> str:
    repo = Path(tmp) / "repo"
    repo.mkdir()
    ralphex_dir = repo / ".ralphex"
    ralphex_dir.mkdir()
    (ralphex_dir / "config").write_text('plans_dir = "docs/plans"\n', encoding="utf-8")
    return str(repo)


# ---------------------------------------------------------------------------
# _core_config.py — OSError/ValueError exception branch (lines 27-28)
# ---------------------------------------------------------------------------

class TestCoreConfigExceptionBranch:
    def test_load_core_config_returns_empty_on_invalid_toml(self):
        """load_core_config returns {} when core.toml contains invalid TOML."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".cf-constructor" / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "core.toml").write_text("this is not valid toml [[[", encoding="utf-8")
            result = load_core_config(root)
        assert result == {}

    def test_load_core_config_returns_empty_on_os_error(self):
        """load_core_config returns {} when the file cannot be opened."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".cf-constructor" / "config"
            config_dir.mkdir(parents=True)
            core_path = config_dir / "core.toml"
            core_path.write_text("[integrations]\n", encoding="utf-8")
            with patch("builtins.open", side_effect=OSError("permission denied")):
                result = load_core_config(root)
        assert result == {}


# ---------------------------------------------------------------------------
# doctor.py — PASS, WARN, FAIL branches + incompatible ralphex
# ---------------------------------------------------------------------------

class TestDoctorPassBranch:
    def test_doctor_pass_returns_zero(self):
        """cmd_doctor returns 0 when all checks pass (covers line 49, 67-69)."""
        with TemporaryDirectory() as tmp:
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                rc = cmd_doctor(["--root", tmp])
        assert rc == 0


class TestDoctorWarnBranch:
    def test_doctor_warn_returns_zero(self):
        """cmd_doctor returns 0 with has_warn when ralphex missing (covers lines 51-52)."""
        with TemporaryDirectory() as tmp:
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                rc = cmd_doctor(["--root", tmp])
        assert rc == 0


class TestDoctorFailBranch:
    def test_doctor_fail_returns_two(self):
        """cmd_doctor returns 2 when a check is FAIL (covers lines 53-55, 59-61)."""
        fail_check = {"name": "test-fail", "level": "FAIL", "message": "broken"}
        with TemporaryDirectory() as tmp:
            with patch("studio.commands.doctor._check_ralphex", return_value=fail_check):
                rc = cmd_doctor(["--root", tmp])
        assert rc == 2


class TestDoctorIncompatibleRalphex:
    def test_incompatible_ralphex_returns_warn(self):
        """_check_ralphex returns WARN for incompatible version (covers lines 123-124)."""
        mock_proc = MagicMock(returncode=1, stdout="", stderr="error")
        with TemporaryDirectory() as tmp:
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = _check_ralphex(Path(tmp))
        assert result["level"] == "WARN"


# ---------------------------------------------------------------------------
# delegate.py — relative plan path + _print_human branches
# ---------------------------------------------------------------------------

class TestDelegateRelativePlanDir:
    def test_relative_plan_dir_resolved_against_root(self):
        """cmd_delegate resolves relative plan_dir against --root (covers line 99)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir_path = Path(repo) / "plans" / "my-plan"
            plan_dir_path.mkdir(parents=True)
            (plan_dir_path / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
            (plan_dir_path / "phase-01.md").write_text(PHASE_01_CONTENT, encoding="utf-8")
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                rc = cmd_delegate(["plans/my-plan", "--dry-run", "--root", repo])
        assert rc == 0


class TestPrintHumanDelegatedBranch:
    def test_print_human_delegated_status(self):
        """_print_human prints delegated info (covers lines 186-194)."""
        from studio.utils.ui import set_json_mode
        result = {
            "status": "delegated",
            "command": ["/usr/bin/ralphex", "plan.md"],
            "mode": "execute",
            "dashboard_url": "http://localhost:8080",
            "lifecycle_state": "completed",
        }
        saved = is_json_mode()
        set_json_mode(False)
        stderr = io.StringIO()
        try:
            with redirect_stderr(stderr):
                _print_human(result)
        finally:
            set_json_mode(saved)
        output = stderr.getvalue()
        assert "Delegation completed" in output
        assert "Dashboard" in output

    def test_print_human_delegated_no_dashboard(self):
        """_print_human omits dashboard when not present."""
        from studio.utils.ui import set_json_mode
        result = {
            "status": "delegated",
            "command": ["/usr/bin/ralphex", "plan.md"],
            "mode": "execute",
            "lifecycle_state": "completed",
        }
        saved = is_json_mode()
        set_json_mode(False)
        stderr = io.StringIO()
        try:
            with redirect_stderr(stderr):
                _print_human(result)
        finally:
            set_json_mode(saved)
        output = stderr.getvalue()
        assert "Delegation completed" in output
        assert "Dashboard" not in output


# ---------------------------------------------------------------------------
# ralphex_export.py — error paths and edge cases
# ---------------------------------------------------------------------------

class TestCompileDelegationPlanMissingSection:
    def test_missing_plan_section_raises(self):
        """compile_delegation_plan raises when [plan] section is empty (covers line 52)."""
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "bad-plan"
            plan_dir.mkdir()
            (plan_dir / "plan.toml").write_text("[plan]\n", encoding="utf-8")
            try:
                compile_delegation_plan(str(plan_dir))
                assert False, "Should have raised ValueError"
            except ValueError as exc:
                assert "missing required [plan] section" in str(exc)


class TestCompileDelegationPlanMissingPhaseFile:
    def test_missing_phase_file_raises(self):
        """compile_delegation_plan raises when phase file is missing (covers line 71)."""
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "bad-plan"
            plan_dir.mkdir()
            plan_toml = MINIMAL_PLAN_TOML
            (plan_dir / "plan.toml").write_text(plan_toml, encoding="utf-8")
            # Don't create phase-01.md
            try:
                compile_delegation_plan(str(plan_dir))
                assert False, "Should have raised FileNotFoundError"
            except FileNotFoundError as exc:
                assert "phase-01.md" in str(exc)


class TestParseFrontmatter:
    def test_no_toml_fence_returns_empty(self):
        """_parse_toml_frontmatter returns {} when no toml fence found (covers line 1352)."""
        result = _parse_toml_frontmatter("Just some markdown content\n")
        assert result == {}

    def test_invalid_toml_returns_empty(self):
        """_parse_toml_frontmatter returns {} on invalid TOML (covers lines 1355-1357)."""
        content = "```toml\nthis is [[[invalid\n```\n"
        result = _parse_toml_frontmatter(content)
        assert result == {}


class TestExtractSectionItems:
    def test_missing_section_returns_empty(self):
        """_extract_section_items returns [] when section not found (covers line 1371)."""
        result = _extract_section_items("## Other\nSome content\n", "NonExistent")
        assert result == []


class TestExtractSectionBody:
    def test_missing_section_returns_empty(self):
        """_extract_section_body returns '' when section not found (covers line 1404)."""
        result = _extract_section_body("## Other\nSome content\n", "NonExistent")
        assert result == ""


class TestRunValidationCommandsErrors:
    def test_os_error_captured(self):
        """run_validation_commands captures OSError (covers lines 682-684)."""
        with patch("studio.ralphex_export.subprocess.run", side_effect=OSError("no such file")):
            result = run_validation_commands(["some-command"])
        assert result["passed"] is False
        assert "OS error" in result["results"][0]["error"]


class TestCheckReviewPreconditionErrors:
    def test_os_error_captured(self):
        """check_review_precondition captures OSError (covers lines 520-522)."""
        with patch("studio.ralphex_export.subprocess.run", side_effect=OSError("fail")):
            result = check_review_precondition("main", repo_root="/tmp")
        assert result["ok"] is False
        assert "Failed to check" in result["message"]


class TestResolvePlanManifestPath:
    def test_absolute_path_returned_directly(self):
        """_resolve_plan_manifest_path returns absolute path as-is (covers line 248)."""
        result = _resolve_plan_manifest_path("/absolute/path", "/some/plan")
        assert result == Path("/absolute/path")

    def test_rooted_path_with_bootstrap_prefix(self):
        """_resolve_plan_manifest_path resolves .bootstrap/ prefix to project root (covers lines 250-253)."""
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "plans" / "my-plan"
            plan_dir.mkdir(parents=True)
            (Path(tmp) / ".git").mkdir()
            result = _resolve_plan_manifest_path(".bootstrap/foo", str(plan_dir))
            assert ".bootstrap/foo" in str(result)


class TestFormatPhaseReferencePath:
    def test_fallback_to_filename(self):
        """_format_phase_reference_path falls back to filename (covers lines 238-241)."""
        # Use a path that can't be made relative to any root
        result = _format_phase_reference_path(Path("/unrelated/phase.md"), "/completely/different")
        assert result == "phase.md"


class TestRunDelegationCompileError:
    def test_compile_error_returns_error_status(self):
        """run_delegation returns error when compile fails (covers lines 958-960)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = Path(tmp) / "bad-plan"
            plan_dir.mkdir()
            (plan_dir / "plan.toml").write_text("[plan]\n", encoding="utf-8")
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config={}, plan_dir=str(plan_dir), repo_root=repo, dry_run=True,
                )
        assert result["status"] == "error"
        assert "missing required [plan] section" in result["error"]


class TestRunDelegationPersistPath:
    def test_persist_path_called_when_config_path_provided(self):
        """run_delegation persists discovered path when config_path given (covers line 940)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            config_path = Path(repo) / ".bootstrap" / "config" / "core.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text('[integrations.ralphex]\nexecutable_path = ""\n', encoding="utf-8")
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_discover.persist_path") as mock_persist:
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo,
                    config_path=config_path, dry_run=True,
                )
            assert result["status"] == "ready"
            mock_persist.assert_called_once()


class TestRunDelegationReviewArtifactError:
    def test_review_artifact_os_error(self):
        """run_delegation returns error when review artifact generation fails (covers lines 993-996)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={"ok": True, "commit_count": 1}), \
                 patch("studio.ralphex_export.generate_review_artifacts", side_effect=OSError("disk full")):
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo,
                    mode="review", dry_run=True,
                )
        assert result["status"] == "error"
        assert "Failed to generate review artifacts" in result["error"]


class TestRunDelegationFileNotFound:
    def test_ralphex_executable_not_found(self):
        """run_delegation handles FileNotFoundError from subprocess (covers lines 1112-1116)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", side_effect=FileNotFoundError("not found")):
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo, dry_run=False,
                )
        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_ralphex_os_error(self):
        """run_delegation handles OSError from subprocess (covers lines 1117-1121)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", side_effect=OSError("permission denied")):
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo, dry_run=False,
                )
        assert result["status"] == "error"
        assert "Failed to invoke ralphex" in result["error"]


class TestRunDelegationStreamOutputError:
    def test_stream_output_error_message(self):
        """run_delegation error msg for stream_output on non-zero exit (covers line 1106)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=42)
            invoke_proc.communicate.return_value = ("", "")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc):
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo,
                    dry_run=False, stream_output=True,
                )
        assert result["status"] == "error"
        assert "exited with code 42" in result["error"]


class TestRunDelegationNonInteractiveTimeout:
    def test_non_interactive_timeout_gives_up(self):
        """run_delegation gives up after max retries in non-interactive mode (covers lines 1023-1032)."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")

            # Simulate a process that times out on communicate, then returns after terminate
            invoke_proc = MagicMock()
            invoke_proc.returncode = -15
            # First 3 calls timeout (initial + 2 retries), then terminate+communicate returns
            invoke_proc.communicate.side_effect = [
                subprocess.TimeoutExpired(cmd="ralphex", timeout=3600),
                subprocess.TimeoutExpired(cmd="ralphex", timeout=3600),
                subprocess.TimeoutExpired(cmd="ralphex", timeout=3600),
                ("", "timed out"),  # after terminate
            ]

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc), \
                 patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo,
                    dry_run=False, stream_output=False,
                )
        assert result["status"] == "error"
        assert "timed out" in result["error"]


class TestReadRalphexConfigOSError:
    def test_read_plans_dir_os_error(self):
        """_read_plans_dir_from_config returns None on OSError (covers lines 1329-1330)."""
        from studio.ralphex_export import _read_plans_dir_from_config
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config"
            config_path.write_text('plans_dir = "foo"\n', encoding="utf-8")
            with patch.object(Path, "read_text", side_effect=OSError("fail")):
                result = _read_plans_dir_from_config(config_path)
        assert result is None


class TestReadPlansDirInlineCommentStripping:
    """Regression: _read_plans_dir_from_config must strip inline comments on unquoted values."""

    def test_unquoted_value_with_inline_comment(self):
        """Unquoted value with inline # comment returns only the value."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config"
            config_path.write_text("plans_dir = docs/plans # comment\n", encoding="utf-8")
            result = _read_plans_dir_from_config(config_path)
        assert result == "docs/plans"

    def test_quoted_value_with_inline_comment(self):
        """Double-quoted value with inline comment returns only the value."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config"
            config_path.write_text('plans_dir = "docs/plans" # comment\n', encoding="utf-8")
            result = _read_plans_dir_from_config(config_path)
        assert result == "docs/plans"

    def test_single_quoted_value(self):
        """Single-quoted value is parsed correctly."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config"
            config_path.write_text("plans_dir = 'my/plans'\n", encoding="utf-8")
            result = _read_plans_dir_from_config(config_path)
        assert result == "my/plans"

    def test_unquoted_value_without_comment(self):
        """Unquoted value without comment still works."""
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config"
            config_path.write_text("plans_dir = docs/plans\n", encoding="utf-8")
            result = _read_plans_dir_from_config(config_path)
        assert result == "docs/plans"


class TestReviewArtifactFailureLifecycleConsistency:
    """Regression: review artifact failure must clean up exported plan file and set plan_file=None."""

    def test_review_artifact_failure_cleans_up_plan_file(self):
        """Plan file is removed from disk when review artifact generation fails."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={"ok": True, "commit_count": 1}), \
                 patch("studio.ralphex_export.generate_review_artifacts", side_effect=OSError("disk full")):
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo,
                    mode="review", dry_run=True,
                )
            # Verify no exported plan files were written (review mode skips
            # compile_delegation_plan so the output plans dir should not exist).
            export_dir = Path(repo) / "docs" / "plans"
            if export_dir.exists():
                exported = list(export_dir.rglob("*.md"))
                assert exported == [], f"Unexpected plan files in export dir: {exported}"
        assert result["status"] == "error"
        assert result["plan_file"] is None
        assert result["lifecycle_state"] == "failed"

    def test_review_artifact_failure_lifecycle_state_is_failed(self):
        """lifecycle_state is 'failed' (not 'exported') on review artifact error."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={"ok": True, "commit_count": 1}), \
                 patch("studio.ralphex_export.generate_review_artifacts", side_effect=OSError("io error")):
                result = run_delegation(
                    config={}, plan_dir=plan_dir, repo_root=repo,
                    mode="review", dry_run=True,
                )
        assert result["lifecycle_state"] == "failed"
        assert "Failed to generate review artifacts" in result["error"]
