"""
Tests for the CLI delegate command and non-blocking bootstrap flow.

Covers:
- CLI entrypoint wiring (delegate command reachable from cli.main)
- cmd_delegate argument parsing and validation
- Non-blocking bootstrap gate (delegation proceeds when .ralphex/config missing)
- End-to-end dry-run delegation via CLI
- Error cases: missing plan_dir, missing plan.toml, ralphex not found
- Regression tests covering delegate dashboard_url propagation and human-readable dashboard output
"""

import io
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.commands.delegate import cmd_delegate
from studio.ralphex_export import run_delegation
from studio.utils.ui import is_json_mode, set_json_mode

# -- Fixtures ----------------------------------------------------------------

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
    """Create a minimal plan directory for tests."""
    plan_dir = Path(tmp) / "test-plan"
    plan_dir.mkdir()
    (plan_dir / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
    (plan_dir / "phase-01.md").write_text(PHASE_01_CONTENT, encoding="utf-8")
    return str(plan_dir)


def _make_repo_with_ralphex_config(tmp: str) -> str:
    """Create a repo directory with .ralphex/config."""
    repo = Path(tmp) / "repo"
    repo.mkdir()
    ralphex_dir = repo / ".ralphex"
    ralphex_dir.mkdir()
    (ralphex_dir / "config").write_text('plans_dir = "docs/plans"\n', encoding="utf-8")
    return str(repo)


# -- CLI entrypoint tests ---------------------------------------------------

class TestCLIDelegateCommand:
    """Tests for cmd_delegate CLI handler."""

    def test_missing_plan_dir_returns_error(self):
        """cmd_delegate returns 1 when plan directory does not exist."""
        with TemporaryDirectory() as tmp:
            rc = cmd_delegate(["/nonexistent/plan/dir", "--root", tmp])
        assert rc == 1

    def test_missing_plan_toml_returns_error(self):
        """cmd_delegate returns 1 when plan.toml is missing from plan_dir."""
        with TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / "empty-plan"
            plan_dir.mkdir()
            rc = cmd_delegate([str(plan_dir), "--root", tmp])
        assert rc == 1

    def test_dry_run_succeeds_with_valid_plan(self):
        """cmd_delegate --dry-run returns 0 when plan and ralphex are valid."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                rc = cmd_delegate([plan_dir, "--dry-run", "--root", repo])
        assert rc == 0

    def test_returns_error_when_ralphex_not_found(self):
        """cmd_delegate returns 2 when ralphex is not discoverable."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                rc = cmd_delegate([plan_dir, "--dry-run", "--root", repo])
        assert rc == 2

    def test_nonexistent_root_returns_error(self):
        """cmd_delegate returns 1 when --root points to nonexistent directory."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            nonexistent = Path(tmp) / "does_not_exist"
            rc = cmd_delegate([plan_dir, "--root", str(nonexistent)])
        assert rc == 1

    def test_nonexistent_root_does_not_create_files(self):
        """cmd_delegate with nonexistent --root must not create directories or files."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            nonexistent = Path(tmp) / "does_not_exist"
            rc = cmd_delegate([plan_dir, "--root", str(nonexistent)])
            assert rc == 1
            assert not nonexistent.exists()

    def test_json_mode_on_invalid_root_emits_json(self):
        """cmd_delegate emits JSON error when --root is invalid under JSON mode."""
        import json as _json
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            nonexistent = Path(tmp) / "does_not_exist"
            saved = is_json_mode()
            set_json_mode(True)
            stdout = io.StringIO()
            try:
                with redirect_stdout(stdout):
                    rc = cmd_delegate([plan_dir, "--root", str(nonexistent)])
            finally:
                set_json_mode(saved)
            assert rc == 1
            parsed = _json.loads(stdout.getvalue())
            assert parsed["status"] == "error"
            assert "error" in parsed

    def test_json_mode_on_missing_plan_toml_emits_json(self):
        """cmd_delegate emits JSON error when plan.toml missing under JSON mode."""
        import json as _json
        with TemporaryDirectory() as tmp:
            empty_plan = Path(tmp) / "empty-plan"
            empty_plan.mkdir()
            saved = is_json_mode()
            set_json_mode(True)
            stdout = io.StringIO()
            try:
                with redirect_stdout(stdout):
                    rc = cmd_delegate([str(empty_plan), "--root", tmp])
            finally:
                set_json_mode(saved)
            assert rc == 1
            parsed = _json.loads(stdout.getvalue())
            assert parsed["status"] == "error"
            assert "error" in parsed

    def test_mode_flag_accepted(self):
        """cmd_delegate accepts --mode tasks-only."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                rc = cmd_delegate([plan_dir, "--mode", "tasks-only", "--dry-run", "--root", repo])
        assert rc == 0

    def test_dashboard_served_by_default(self):
        """cmd_delegate enables dashboard serving by default."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            result = {
                "status": "ready",
                "bootstrap": {"needed": False},
                "command": ["/usr/bin/ralphex", "plan.md", "--serve"],
                "plan_file": "/tmp/plan.md",
                "lifecycle_state": "exported",
            }
            with patch("studio.ralphex_export.run_delegation", return_value=result) as mock_run:
                rc = cmd_delegate([plan_dir, "--dry-run", "--root", repo])
            assert rc == 0
            assert mock_run.call_args.kwargs["serve"] is True

    def test_no_serve_flag_disables_dashboard(self):
        """cmd_delegate forwards --no-serve as serve=False."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            result = {
                "status": "ready",
                "bootstrap": {"needed": False},
                "command": ["/usr/bin/ralphex", "plan.md"],
                "plan_file": "/tmp/plan.md",
                "lifecycle_state": "exported",
            }
            with patch("studio.ralphex_export.run_delegation", return_value=result) as mock_run:
                rc = cmd_delegate([plan_dir, "--dry-run", "--no-serve", "--root", repo])
            assert rc == 0
            assert mock_run.call_args.kwargs["serve"] is False

    def test_human_mode_enables_stream_output(self):
        """cmd_delegate enables live stdio passthrough outside JSON mode."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            result = {
                "status": "ready",
                "bootstrap": {"needed": False},
                "command": ["/usr/bin/ralphex", "plan.md"],
                "plan_file": "/tmp/plan.md",
                "lifecycle_state": "exported",
            }
            saved_json_mode = is_json_mode()
            set_json_mode(False)
            try:
                with patch("studio.ralphex_export.run_delegation", return_value=result) as mock_run:
                    rc = cmd_delegate([plan_dir, "--dry-run", "--root", repo])
            finally:
                set_json_mode(saved_json_mode)
            assert rc == 0
            assert mock_run.call_args.kwargs["serve"] is True
            assert mock_run.call_args.kwargs["stream_output"] is True

    def test_json_mode_emits_json_output(self):
        """cmd_delegate respects JSON mode and emits parsable JSON to stdout."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            result = {
                "status": "ready",
                "bootstrap": {"needed": False},
                "command": ["/usr/bin/ralphex", "plan.md", "--serve"],
                "plan_file": "/tmp/plan.md",
                "dashboard_url": "http://localhost:8080",
                "lifecycle_state": "exported",
            }
            saved_json_mode = is_json_mode()
            set_json_mode(True)
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with redirect_stdout(stdout), redirect_stderr(stderr), \
                     patch("studio.ralphex_export.run_delegation", return_value=result) as mock_run:
                    rc = cmd_delegate([plan_dir, "--dry-run", "--root", repo])
            finally:
                set_json_mode(saved_json_mode)
            assert rc == 0
            assert mock_run.call_args.kwargs["serve"] is True
            assert mock_run.call_args.kwargs["stream_output"] is False
            import json
            parsed = json.loads(stdout.getvalue())
            assert parsed["status"] == "ready"
            assert parsed["dashboard_url"] == "http://localhost:8080"

    def test_json_mode_disables_stream_output(self):
        """cmd_delegate passes stream_output=False in JSON mode to prevent stdout corruption."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            result = {
                "status": "delegated",
                "bootstrap": {"needed": False},
                "command": ["/usr/bin/ralphex", "plan.md"],
                "plan_file": "/tmp/plan.md",
                "mode": "execute",
                "lifecycle_state": "completed",
                "returncode": 0,
            }
            saved_json_mode = is_json_mode()
            set_json_mode(True)
            stdout = io.StringIO()
            try:
                with redirect_stdout(stdout), \
                     patch("studio.ralphex_export.run_delegation", return_value=result) as mock_run:
                    rc = cmd_delegate([plan_dir, "--root", repo])
            finally:
                set_json_mode(saved_json_mode)
            assert rc == 0
            assert mock_run.call_args.kwargs["stream_output"] is False
            import json
            raw = stdout.getvalue()
            parsed = json.loads(raw)
            assert parsed["status"] == "delegated"

    def test_human_output_shows_dashboard_url(self):
        """cmd_delegate prints dashboard URL in human mode when available."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            result = {
                "status": "ready",
                "bootstrap": {"needed": False},
                "command": ["/usr/bin/ralphex", "plan.md", "--serve"],
                "plan_file": "/tmp/plan.md",
                "dashboard_url": "http://localhost:8080",
                "lifecycle_state": "exported",
            }
            saved_json_mode = is_json_mode()
            set_json_mode(False)
            stderr = io.StringIO()
            try:
                with redirect_stderr(stderr), \
                     patch("studio.ralphex_export.run_delegation", return_value=result):
                    rc = cmd_delegate([plan_dir, "--dry-run", "--root", repo])
            finally:
                set_json_mode(saved_json_mode)
            assert rc == 0
            assert "Dashboard: http://localhost:8080" in stderr.getvalue()


# -- CLI wiring tests -------------------------------------------------------

class TestCLIWiring:
    """Tests that delegate command is reachable from cli.main."""

    def test_delegate_in_all_commands_list(self):
        """delegate appears in the all_commands list used by cli.main."""
        from cypilot import cli as cli_mod
        # Verify delegate is routable by checking the dispatch succeeds
        assert hasattr(cli_mod, "_cmd_delegate"), "cli module must expose _cmd_delegate"

    def test_delegate_dispatches_to_handler(self):
        """cli.main routes 'delegate' to _cmd_delegate."""
        from cypilot import cli as cli_mod
        with patch.object(cli_mod, "_cmd_delegate", return_value=0) as mock_handler, \
             patch("studio.utils.context.CypilotContext.load", return_value=None):
            rc = cli_mod.main(["delegate", "/some/plan"])
        mock_handler.assert_called_once_with(["/some/plan"])


# -- Bootstrap gate tests ---------------------------------------------------

class TestBootstrapGate:
    """Tests that bootstrap gate blocks delegation when .ralphex/config is missing."""

    def test_delegation_blocked_without_ralphex_config(self):
        """run_delegation returns error when .ralphex/config is missing."""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            # No .ralphex/config
            plan_dir = _make_plan_dir(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=str(repo),
                    dry_run=True,
                )
            assert result["status"] == "error"
            assert "ralphex --init" in result["error"]
            assert result["bootstrap"]["needed"] is True
            assert result["plan_file"] is None

    def test_bootstrap_error_included_in_result(self):
        """run_delegation includes bootstrap error message when config is missing."""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            plan_dir = _make_plan_dir(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=str(repo),
                    dry_run=True,
                )
            bootstrap = result["bootstrap"]
            assert bootstrap["needed"] is True
            assert "ralphex --init" in bootstrap["message"]
            assert result["error"] == bootstrap["message"]

    def test_bootstrap_blocks_before_plans_dir_resolution(self):
        """Bootstrap gate blocks before plans directory is resolved."""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            plan_dir = _make_plan_dir(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch.dict("os.environ", {"XDG_CONFIG_HOME": str(Path(tmp) / "no_xdg")}):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=str(repo),
                    dry_run=True,
                )
            assert result["status"] == "error"
            assert result["plan_file"] is None

    def test_bootstrap_not_needed_skips_warning(self):
        """When .ralphex/config exists, bootstrap.needed is False."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo,
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert result["bootstrap"]["needed"] is False

    def test_delegation_result_includes_dashboard_url(self):
        """run_delegation exposes dashboard URL when serving is enabled."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch.dict("os.environ", {"RALPHEX_PORT": "9090"}, clear=False):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo,
                    serve=True,
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert result["dashboard_url"] == "http://localhost:9090"

    def test_cli_delegate_succeeds_without_ralphex_config(self):
        """cmd_delegate returns 0 even without .ralphex/config (non-blocking)."""
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                rc = cmd_delegate([plan_dir, "--dry-run", "--root", str(repo)])
        assert rc == 2


# -- End-to-end delegation flow tests ---------------------------------------

class TestEndToEndDelegation:
    """End-to-end tests for the full CLI → run_delegation → export flow."""

    def test_full_dry_run_produces_exported_plan(self):
        """Full dry-run flow: CLI → run_delegation → exported plan file."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config={},
                    plan_dir=plan_dir,
                    repo_root=repo,
                    dry_run=True,
                )
            assert result["status"] == "ready"
            plan_content = Path(result["plan_file"]).read_text(encoding="utf-8")
            assert "## Validation Commands" in plan_content
            assert "### Task 1:" in plan_content
            assert result["command"][0] == "/usr/bin/ralphex"

    def test_non_dry_run_returns_delegated(self):
        """Non-dry-run returns delegated status and invokes subprocess."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=0)
            invoke_proc.communicate.return_value = ("Done\n", "")

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc) as mock_validate, \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc) as mock_popen:
                result = run_delegation(
                    config={},
                    plan_dir=plan_dir,
                    repo_root=repo,
                    dry_run=False,
                )
            assert result["status"] == "delegated"
            assert result["lifecycle_state"] == "completed"
            mock_validate.assert_called_once()
            assert mock_popen.call_args.args[0][0] == "/usr/bin/ralphex"
            assert result["returncode"] == 0

    def test_non_dry_run_reports_error_on_nonzero_exit(self):
        """Non-dry-run reports error when ralphex exits non-zero."""
        with TemporaryDirectory() as tmp:
            repo = _make_repo_with_ralphex_config(tmp)
            plan_dir = _make_plan_dir(tmp)
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=1)
            invoke_proc.communicate.return_value = ("", "task failed")

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc):
                result = run_delegation(
                    config={},
                    plan_dir=plan_dir,
                    repo_root=repo,
                    dry_run=False,
                )
            assert result["status"] == "error"
            assert "task failed" in result["error"]
            assert result["returncode"] == 1
