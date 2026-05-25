"""
Tests for ralphex post-run handoff, lifecycle state tracking, and bootstrap gate.

Covers:
- read_handoff_status(): exit status and output ref extraction
- check_completed_plans(): completed/ subdirectory inspection
- run_validation_commands(): re-execution of Cypilot validation commands
- report_handoff(): delegation summary assembly
- DelegationLifecycle: state transitions (not_exported → exported → delegated → completed/failed)
- check_bootstrap_needed(): missing .ralphex/config detection and approval gate
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from studio.ralphex_export import (
    read_handoff_status,
    check_completed_plans,
    run_validation_commands,
    report_handoff,
    extract_validation_commands,
    DelegationLifecycle,
    check_bootstrap_needed,
)


# -- Fixtures ----------------------------------------------------------------

MINIMAL_PLAN_TOML = textwrap.dedent("""\
    [plan]
    task = "Implement test-plan"
    type = "implement"

    [[phases]]
    number = 1
    title = "Widget Factory"
    slug = "widget-factory"
    file = "phase-01.md"
    status = "pending"
    kind = "delivery"
    depends_on = []
    input_files = []
    output_files = ["src/widget.py", "tests/test_widget.py"]
""")


class TestReadHandoffStatus:
    """Tests for read_handoff_status() — ralphex exit code and output refs."""

    def test_success_exit_code_zero(self):
        """Returns success status when exit code is 0."""
        result = read_handoff_status(exit_code=0, output_refs=["out/report.md"])
        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert result["output_refs"] == ["out/report.md"]

    def test_failure_exit_code_nonzero(self):
        """Returns failed status when exit code is non-zero."""
        result = read_handoff_status(exit_code=1, output_refs=[])
        assert result["status"] == "failed"
        assert result["exit_code"] == 1

    def test_partial_status_with_partial_flag(self):
        """Returns partial status when partial=True and exit code is non-zero."""
        result = read_handoff_status(exit_code=1, output_refs=["a.md"], partial=True)
        assert result["status"] == "partial"

    def test_empty_output_refs(self):
        """Handles empty output refs list."""
        result = read_handoff_status(exit_code=0, output_refs=[])
        assert result["output_refs"] == []

    def test_multiple_output_refs(self):
        """Handles multiple output refs."""
        refs = ["out/a.md", "out/b.md", "out/c.md"]
        result = read_handoff_status(exit_code=0, output_refs=refs)
        assert result["output_refs"] == refs


class TestCheckCompletedPlans:
    """Tests for check_completed_plans() — completed/ subdirectory inspection."""

    def test_finds_completed_plan(self):
        """Detects plan file in completed/ subdirectory."""
        with TemporaryDirectory() as tmp:
            completed = Path(tmp) / "completed"
            completed.mkdir()
            (completed / "test-plan.md").write_text("# Done\n", encoding="utf-8")
            result = check_completed_plans(tmp, "test-plan")
        assert result["found"] is True
        assert "test-plan.md" in result["completed_path"]

    def test_no_completed_directory(self):
        """Returns not found when completed/ does not exist."""
        with TemporaryDirectory() as tmp:
            result = check_completed_plans(tmp, "test-plan")
        assert result["found"] is False

    def test_completed_dir_exists_but_no_matching_plan(self):
        """Returns not found when completed/ exists but has no matching plan."""
        with TemporaryDirectory() as tmp:
            completed = Path(tmp) / "completed"
            completed.mkdir()
            (completed / "other-plan.md").write_text("# Other\n", encoding="utf-8")
            result = check_completed_plans(tmp, "test-plan")
        assert result["found"] is False

    def test_lists_all_completed_artifacts(self):
        """Lists all files in completed/ directory."""
        with TemporaryDirectory() as tmp:
            completed = Path(tmp) / "completed"
            completed.mkdir()
            (completed / "plan-a.md").write_text("# A\n", encoding="utf-8")
            (completed / "plan-b.md").write_text("# B\n", encoding="utf-8")
            result = check_completed_plans(tmp, "plan-a")
        assert result["found"] is True
        assert len(result["artifacts"]) == 2


class TestRunValidationCommands:
    """Tests for run_validation_commands() — re-run Cypilot validation."""

    def test_runs_pytest_command(self):
        """Executes pytest command and captures result."""
        proc = MagicMock(returncode=0, stdout="all passed\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc) as mock_run:
            result = run_validation_commands(
                ["python -m pytest tests/test_widget.py"]
            )
        assert result["passed"] is True
        assert result["results"][0]["returncode"] == 0
        mock_run.assert_called_once()

    def test_captures_failure(self):
        """Reports failure when validation command fails."""
        proc = MagicMock(returncode=1, stdout="FAILED\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = run_validation_commands(
                ["python -m pytest tests/test_widget.py"]
            )
        assert result["passed"] is False
        assert result["results"][0]["returncode"] == 1

    def test_multiple_commands(self):
        """Runs multiple validation commands and aggregates results."""
        proc_ok = MagicMock(returncode=0, stdout="ok\n", stderr="")
        proc_fail = MagicMock(returncode=1, stdout="fail\n", stderr="")
        with patch(
            "studio.ralphex_export.subprocess.run",
            side_effect=[proc_ok, proc_fail],
        ):
            result = run_validation_commands([
                "python -m pytest tests/a.py",
                "python -m pytest tests/b.py",
            ])
        assert result["passed"] is False
        assert len(result["results"]) == 2

    def test_empty_commands_passes(self):
        """No commands means validation passes vacuously."""
        result = run_validation_commands([])
        assert result["passed"] is True
        assert result["results"] == []

    def test_timeout_handled_gracefully(self):
        """Timeout during validation is captured as failure."""
        with patch(
            "studio.ralphex_export.subprocess.run",
            side_effect=subprocess.TimeoutExpired("cmd", 30),
        ):
            result = run_validation_commands(["python -m pytest tests/"])
        assert result["passed"] is False
        assert "timeout" in result["results"][0]["error"].lower()

    def test_empty_string_command_skipped(self):
        """Empty string commands are skipped with error."""
        result = run_validation_commands([""])
        assert result["passed"] is False
        assert result["results"][0]["returncode"] == -1
        assert "empty" in result["results"][0]["error"].lower()

    def test_whitespace_only_command_skipped(self):
        """Whitespace-only commands are skipped with error."""
        result = run_validation_commands(["   "])
        assert result["passed"] is False
        assert "empty" in result["results"][0]["error"].lower()

    def test_non_string_command_skipped(self):
        """Non-string commands are skipped with error."""
        result = run_validation_commands([None])
        assert result["passed"] is False
        assert "non-string" in result["results"][0]["error"].lower()

    def test_mixed_valid_and_invalid_commands(self):
        """Valid commands still run when invalid commands are present."""
        proc = MagicMock(returncode=0, stdout="ok\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc) as mock_run:
            result = run_validation_commands(["", "echo ok"])
        assert result["passed"] is False  # empty command taints overall result
        assert len(result["results"]) == 2
        assert result["results"][1]["returncode"] == 0
        mock_run.assert_called_once()


class TestReportHandoff:
    """Tests for report_handoff() — delegation summary assembly."""

    def test_success_report(self):
        """Assembles success summary with all fields."""
        report = report_handoff(
            plan_file="docs/plans/task.md",
            mode="execute",
            exit_code=0,
            output_refs=["out/report.md"],
            completed_plan_path="docs/plans/completed/task.md",
            validation_passed=True,
        )
        assert report["status"] == "success"
        assert report["plan_file"] == "docs/plans/task.md"
        assert report["mode"] == "execute"
        assert report["validation_passed"] is True
        assert report["completed_plan_path"] == "docs/plans/completed/task.md"

    def test_failed_report(self):
        """Assembles failed summary."""
        report = report_handoff(
            plan_file="docs/plans/task.md",
            mode="execute",
            exit_code=1,
            output_refs=[],
            completed_plan_path=None,
            validation_passed=False,
        )
        assert report["status"] == "failed"
        assert report["validation_passed"] is False

    def test_partial_report(self):
        """Assembles partial summary when flagged."""
        report = report_handoff(
            plan_file="docs/plans/task.md",
            mode="tasks-only",
            exit_code=1,
            output_refs=["out/partial.md"],
            completed_plan_path=None,
            validation_passed=False,
            partial=True,
        )
        assert report["status"] == "partial"

    def test_report_includes_output_refs(self):
        """Report includes output references list."""
        refs = ["a.md", "b.md"]
        report = report_handoff(
            plan_file="p.md",
            mode="execute",
            exit_code=0,
            output_refs=refs,
            completed_plan_path=None,
            validation_passed=True,
        )
        assert report["output_refs"] == refs


class TestDelegationLifecycle:
    """Tests for DelegationLifecycle — state machine transitions."""

    def test_initial_state_is_not_exported(self):
        """Lifecycle starts in not_exported state."""
        lc = DelegationLifecycle()
        assert lc.state == "not_exported"

    def test_export_transitions_to_exported(self):
        """not_exported → exported on export."""
        lc = DelegationLifecycle()
        lc.export()
        assert lc.state == "exported"

    def test_delegate_transitions_to_delegated(self):
        """exported → delegated on delegate."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        assert lc.state == "delegated"

    def test_complete_transitions_to_completed(self):
        """delegated → completed on complete."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        lc.complete()
        assert lc.state == "completed"

    def test_fail_transitions_to_failed(self):
        """delegated → failed on fail."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        lc.fail()
        assert lc.state == "failed"

    def test_re_export_from_failed(self):
        """failed → exported on re-export."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        lc.fail()
        lc.export()
        assert lc.state == "exported"

    def test_invalid_transition_raises(self):
        """Invalid transitions raise ValueError."""
        lc = DelegationLifecycle()
        # Cannot delegate from not_exported
        with pytest.raises(ValueError):
            lc.delegate()

    def test_cannot_complete_from_exported(self):
        """Cannot complete directly from exported."""
        lc = DelegationLifecycle()
        lc.export()
        with pytest.raises(ValueError):
            lc.complete()

    def test_cannot_export_from_delegated(self):
        """Cannot re-export from delegated (must fail first)."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        with pytest.raises(ValueError):
            lc.export()

    def test_history_tracks_transitions(self):
        """History records all state transitions."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        lc.complete()
        assert lc.history == [
            ("not_exported", "exported"),
            ("exported", "delegated"),
            ("delegated", "completed"),
        ]


class TestCheckBootstrapNeeded:
    """Tests for check_bootstrap_needed() — .ralphex/config detection."""

    def test_not_needed_when_config_exists(self):
        """Returns not needed when .ralphex/config exists."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text(
                'plans_dir = "docs/plans"\n', encoding="utf-8"
            )
            result = check_bootstrap_needed(tmp)
        assert result["needed"] is False

    def test_needed_when_no_ralphex_dir(self):
        """Returns needed when .ralphex/ directory does not exist."""
        with TemporaryDirectory() as tmp:
            result = check_bootstrap_needed(tmp)
        assert result["needed"] is True
        assert "missing" in result["message"].lower()

    def test_needed_when_no_config_file(self):
        """Returns needed when .ralphex/ exists but config file is missing."""
        with TemporaryDirectory() as tmp:
            (Path(tmp) / ".ralphex").mkdir()
            result = check_bootstrap_needed(tmp)
        assert result["needed"] is True

    def test_never_runs_init_automatically(self):
        """check_bootstrap_needed never executes ralphex --init itself."""
        with TemporaryDirectory() as tmp:
            with patch("studio.ralphex_export.subprocess.run") as mock_run:
                check_bootstrap_needed(tmp)
            mock_run.assert_not_called()

    def test_message_requests_user_approval(self):
        """Message explicitly requests user approval for bootstrap."""
        with TemporaryDirectory() as tmp:
            result = check_bootstrap_needed(tmp)
        assert "approval" in result["message"].lower() or "approve" in result["message"].lower()


class TestValidationRoundTrip:
    """Tests for round-trip validation contract — extract → handoff reuse."""

    def test_extract_commands_reusable_by_run_validation(self):
        """Commands from extract_validation_commands can be passed to run_validation_commands."""
        manifest = {
            "plan": {"validation_commands": ["echo ok"]},
            "phases": [],
        }
        commands = extract_validation_commands(manifest)
        assert len(commands) == 1
        # run_validation_commands accepts the same list — mock subprocess for hermeticity
        mock_result = MagicMock(returncode=0, stdout="ok\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=mock_result):
            result = run_validation_commands(commands)
        assert result["passed"] is True
        assert result["results"][0]["command"] == "echo ok"

    def test_extract_and_validate_from_same_manifest(self):
        """Same manifest produces consistent commands for export and handoff."""
        manifest = {
            "plan": {"task": "Test plan"},
            "phases": [
                {"output_files": ["tests/test_widget.py"]},
                {"output_files": ["tests/test_validator.py"]},
            ],
        }
        commands = extract_validation_commands(manifest)
        assert len(commands) == 1
        assert "tests/test_validator.py" in commands[0]
        assert "tests/test_widget.py" in commands[0]

    def test_explicit_commands_survive_round_trip(self):
        """Explicit validation_commands are identical at extract and handoff time."""
        explicit = ["python -m pytest tests/ -x", "ruff check src/"]
        manifest = {"plan": {"validation_commands": explicit}, "phases": []}
        commands = extract_validation_commands(manifest)
        assert commands == explicit
