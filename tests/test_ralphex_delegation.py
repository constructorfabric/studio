"""
Integration tests for the ralphex delegation feature.

Covers all 14 acceptance criteria from the feature spec (section 7):

AC-01: cypilot-ralphex skill discovers ralphex on PATH and persists resolved path
AC-02: Previously persisted path is reused without re-discovery
AC-03: Missing ralphex produces diagnostic output with install guidance, not hard error
AC-04: ralphex --init can be invoked for project-local bootstrap on user request
AC-05: Plan outputs exported into ralphex-compatible Markdown with Validation Commands and Task sections
AC-06: Export target directory resolved from ralphex config precedence
AC-07: Exported plans contain only bounded SDLC slices, not the entire kit
AC-08: One Cypilot phase maps to one Task block
AC-09: Delegation invokes ralphex with correct mode flags
AC-10: --worktree only appended for full mode and tasks-only, not review-only
AC-11: Review-only delegation verifies committed changes before invoking ralphex --review
AC-12: Post-run handoff reports status, output refs, and re-runs validation commands
AC-13: Integration is fully optional — projects without ralphex have zero behavioral change
AC-14: No Cypilot SDLC assets duplicated into .ralphex/
"""

import builtins
import os
import subprocess
import sys
import textwrap

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.ralphex_discover import discover, validate, persist_path, INSTALL_GUIDANCE
from studio.ralphex_export import (
    _validate_delegation_command,
    compile_delegation_plan,
    generate_review_artifacts,
    map_phase_to_task,
    resolve_plans_dir,
    build_delegation_command,
    check_review_precondition,
    read_handoff_status,
    check_completed_plans,
    run_validation_commands,
    report_handoff,
    DelegationLifecycle,
    check_bootstrap_needed,
    run_delegation,
    REVIEW_PROMPT_RELATIVES,
)


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

    [[phases]]
    number = 2
    title = "Widget Validator"
    slug = "widget-validator"
    file = "phase-02.md"
    status = "pending"
    kind = "delivery"
    depends_on = [1]
    input_files = []
    output_files = ["src/validator.py"]
""")

PHASE_01_CONTENT = textwrap.dedent("""\
    ```toml
    [phase]
    plan = "widget-feature"
    number = 1
    total = 2
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

PHASE_02_CONTENT = textwrap.dedent("""\
    ```toml
    [phase]
    plan = "widget-feature"
    number = 2
    total = 2
    type = "implement"
    title = "Widget Validator"
    depends_on = [1]
    input_files = []
    output_files = ["src/validator.py"]
    outputs = []
    inputs = []
    ```

    ## What

    Add validation to widgets.

    ## Rules

    ### Engineering
    - **TDD**: Write failing test first

    ### Quality
    - **Readability**: Clear naming

    ### MUST NOT
    - No hardcoded secrets

    ## Task

    1. Write failing tests.
    2. Implement validate() method.

    ## Acceptance Criteria

    - [ ] validate() rejects invalid widgets
""")


def _make_plan_dir(tmp: str) -> str:
    """Create a minimal plan directory for integration tests."""
    plan_dir = Path(tmp) / "test-plan"
    plan_dir.mkdir()
    (plan_dir / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
    (plan_dir / "phase-01.md").write_text(PHASE_01_CONTENT, encoding="utf-8")
    (plan_dir / "phase-02.md").write_text(PHASE_02_CONTENT, encoding="utf-8")
    return str(plan_dir)


def _make_plan_dir_with_lifecycle_action(
    tmp: str,
    lifecycle: str,
    *,
    lifecycle_action: str | None = None,
    phase_numbers: tuple[int, int] = (1, 2),
) -> str:
    """Create a minimal plan directory with lifecycle metadata and optional action."""
    plan_dir = Path(tmp) / f"test-plan-{lifecycle}-{lifecycle_action or 'none'}"
    plan_dir.mkdir()
    plan_toml = MINIMAL_PLAN_TOML.replace(
        'type = "implement"\n',
        (
            'type = "implement"\n'
            f'lifecycle = "{lifecycle}"\n'
            'lifecycle_status = "pending"\n'
            f'plan_dir = "{plan_dir.as_posix()}"\n'
            f'active_plan_dir = "{plan_dir.as_posix()}"\n'
        ),
        1,
    )
    # Replace higher number first to avoid collision when phase_numbers[0]
    # equals the original value of the second phase (e.g. (2, 4) would turn
    # the first 'number = 1' into 'number = 2', shadowing the real second phase).
    plan_toml = plan_toml.replace('number = 2\n', f'number = {phase_numbers[1]}\n', 1)
    plan_toml = plan_toml.replace('number = 1\n', f'number = {phase_numbers[0]}\n', 1)
    if lifecycle_action is not None:
        plan_toml += f'\n[decisions]\nlifecycle_action = "{lifecycle_action}"\n'
    (plan_dir / "plan.toml").write_text(plan_toml, encoding="utf-8")
    (plan_dir / "phase-01.md").write_text(PHASE_01_CONTENT, encoding="utf-8")
    (plan_dir / "phase-02.md").write_text(PHASE_02_CONTENT, encoding="utf-8")
    return str(plan_dir)


def _make_plan_dir_with_lifecycle(tmp: str, lifecycle: str) -> str:
    """Create a minimal plan directory with lifecycle metadata for export tests."""
    plan_dir = Path(tmp) / f"test-plan-{lifecycle}"
    plan_dir.mkdir()
    plan_toml = MINIMAL_PLAN_TOML.replace(
        'type = "implement"\n',
        (
            'type = "implement"\n'
            f'lifecycle = "{lifecycle}"\n'
            'lifecycle_status = "pending"\n'
            f'plan_dir = "{plan_dir.as_posix()}"\n'
            f'active_plan_dir = "{plan_dir.as_posix()}"\n'
        ),
        1,
    )
    (plan_dir / "plan.toml").write_text(plan_toml, encoding="utf-8")
    (plan_dir / "phase-01.md").write_text(PHASE_01_CONTENT, encoding="utf-8")
    (plan_dir / "phase-02.md").write_text(PHASE_02_CONTENT, encoding="utf-8")
    return str(plan_dir)


# -- AC-01: Discovery persists resolved path ----------------------------------

class TestAC01DiscoveryAndPersistence:
    """AC-01: cypilot-ralphex discovers ralphex on PATH and persists resolved path."""

    def test_discover_finds_and_persist_writes(self):
        """Full flow: discover on PATH, then persist to core.toml."""
        config = {"integrations": {"ralphex": {"executable_path": ""}}}
        with patch("studio.ralphex_discover.shutil.which", return_value="/usr/local/bin/ralphex"):
            path = discover(config)
        assert path == "/usr/local/bin/ralphex"

        # Persist the discovered path
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "core.toml"
            config_path.write_text(
                '[integrations.ralphex]\nexecutable_path = ""\n',
                encoding="utf-8",
            )
            persist_path(config_path, path)

            import tomllib
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            assert data["integrations"]["ralphex"]["executable_path"] == "/usr/local/bin/ralphex"


# -- AC-02: Persisted path reused without re-discovery -------------------------

class TestAC02PersistedPathReuse:
    """AC-02: Previously persisted path is reused on subsequent invocations."""

    def test_reuses_persisted_path_when_path_lookup_misses(self):
        """discover() returns persisted path without re-scanning PATH."""
        with TemporaryDirectory() as tmp:
            fake_bin = Path(tmp) / "ralphex"
            fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_bin.chmod(0o755)

            config = {"integrations": {"ralphex": {"executable_path": str(fake_bin)}}}
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                result = discover(config)
            assert result == str(fake_bin)


# -- AC-03: Missing ralphex → diagnostic, not hard error ----------------------

class TestAC03MissingRalphexDiagnostic:
    """AC-03: Missing ralphex produces diagnostic with install guidance, not hard error."""

    def test_missing_returns_none_not_exception(self):
        """discover() returns None, does not raise."""
        config = {}
        with patch("studio.ralphex_discover.shutil.which", return_value=None):
            result = discover(config)
        assert result is None

    def test_validate_none_gives_install_guidance(self):
        """validate(None) returns unavailable with install instructions."""
        result = validate(None)
        assert result["status"] == "unavailable"
        assert "brew" in result["message"].lower() or "homebrew" in result["message"].lower()
        assert "go install" in result["message"].lower()

    def test_doctor_check_warns_not_fails(self):
        """Doctor inst-check-ralphex returns WARN, not FAIL, when missing."""
        from studio.commands.doctor import _check_ralphex

        with TemporaryDirectory() as tmp:
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                result = _check_ralphex(Path(tmp))
        assert result["level"] == "WARN"
        assert result["name"] == "inst-check-ralphex"

    def test_doctor_reads_install_config(self):
        """Doctor discovers ralphex via .cf/config/core.toml."""
        from studio.commands._core_config import load_core_config as _load_core_config

        with TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_dir = project_root / ".cf" / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "core.toml").write_text(
                '[ralphex]\npath = "/usr/local/bin/ralphex"\n',
                encoding="utf-8",
            )
            config = _load_core_config(project_root)
        assert config.get("ralphex", {}).get("path") == "/usr/local/bin/ralphex"

    def test_doctor_check_finds_ralphex_from_install_config(self):
        """Doctor _check_ralphex finds ralphex when path is only in .cf/config/core.toml."""
        from studio.commands.doctor import _check_ralphex

        with TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_dir = project_root / ".cf" / "config"
            config_dir.mkdir(parents=True)
            # Write a config with the correct key structure for discover()
            fake_bin = project_root / "fake-ralphex"
            fake_bin.write_text("#!/bin/sh\necho ralphex", encoding="utf-8")
            fake_bin.chmod(0o755)
            (config_dir / "core.toml").write_text(
                f'[integrations.ralphex]\nexecutable_path = "{fake_bin}"\n',
                encoding="utf-8",
            )
            # Patch shutil.which to return None (not on PATH) so discover
            # falls through to the persisted config path
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                with patch("studio.ralphex_discover.validate", return_value={"status": "available", "version": "0.1.0"}):
                    result = _check_ralphex(project_root)
        assert result["level"] == "PASS"


# -- AC-04: ralphex --init bootstrap on user request ---------------------------

class TestAC04BootstrapInit:
    """AC-04: ralphex --init can be invoked for project-local bootstrap on user request."""

    def test_bootstrap_needed_when_no_config(self):
        """check_bootstrap_needed detects missing .ralphex/config."""
        with TemporaryDirectory() as tmp:
            result = check_bootstrap_needed(tmp)
        assert result["needed"] is True

    def test_bootstrap_not_needed_when_config_exists(self):
        """check_bootstrap_needed returns not needed when config present."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text('plans_dir = "docs/plans"\n', encoding="utf-8")
            result = check_bootstrap_needed(tmp)
        assert result["needed"] is False

    def test_never_runs_init_automatically(self):
        """check_bootstrap_needed never executes ralphex --init itself."""
        with TemporaryDirectory() as tmp:
            with patch("studio.ralphex_export.subprocess.run") as mock_run:
                check_bootstrap_needed(tmp)
            mock_run.assert_not_called()

    def test_message_mentions_user_approval(self):
        """Bootstrap message explicitly requires user approval."""
        with TemporaryDirectory() as tmp:
            result = check_bootstrap_needed(tmp)
        msg = result["message"].lower()
        assert "approval" in msg or "approve" in msg or "explicit" in msg


# -- AC-05: Export produces ralphex-compatible Markdown ------------------------

class TestAC05ExportFormat:
    """AC-05: Exported plans have ## Validation Commands and ### Task N: sections."""

    def test_exported_plan_has_validation_commands(self):
        """Compiled plan contains ## Validation Commands section."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert "## Validation Commands" in result

    def test_exported_plan_has_task_sections(self):
        """Compiled plan contains ### Task N: blocks."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert "### Task 1:" in result
        assert "### Task 2:" in result
        assert "**Original Phase File:**" in result
        assert "**Execution Prompt:**" in result
        assert "`test-plan/phase-01.md`" in result
        assert "`test-plan/phase-02.md`" in result

    def test_sections_in_ralphex_grammar_order(self):
        """Title, Validation Commands, Tasks appear in correct order."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        title_pos = result.index("# ")
        validation_pos = result.index("## Validation Commands")
        task1_pos = result.index("### Task 1:")
        assert title_pos < validation_pos < task1_pos

    def test_archive_lifecycle_adds_final_task(self):
        """Archive lifecycle exports an additional final lifecycle task."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir_with_lifecycle(tmp, "archive")
            result = compile_delegation_plan(plan_dir)
        assert "### Task 3: Plan lifecycle — archive plan files" in result
        assert "Move the active plan directory" in result
        assert "`.plans/.archive/`" not in result
        assert "lifecycle_status = `done`" not in result
        assert "`lifecycle_status` is `done`." in result
        assert 'Set `lifecycle_status = "ready"` before moving the completed plan directory.' in result

    def test_manual_delete_lifecycle_action_adds_final_task(self):
        """Manual lifecycle with chosen delete action exports a final delete task."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir_with_lifecycle_action(
                tmp,
                "manual",
                lifecycle_action="delete",
            )
            result = compile_delegation_plan(plan_dir)
        assert "### Task 3: Plan lifecycle — delete plan files" in result
        assert "Delete the active plan directory" in result
        assert "Do not delete project files outside the plan directory." in result

    def test_manual_without_lifecycle_action_adds_no_final_task(self):
        """Manual lifecycle without a resolved action does not export a synthetic lifecycle task."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir_with_lifecycle_action(tmp, "manual")
            result = compile_delegation_plan(plan_dir)
        assert "Plan lifecycle —" not in result

    def test_unrecognized_lifecycle_raises_error(self):
        """Unrecognized lifecycle value (e.g. legacy 'delete') raises ValueError."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir_with_lifecycle(tmp, "delete")
            with pytest.raises(ValueError, match="Unrecognized plan.lifecycle value 'delete'"):
                compile_delegation_plan(plan_dir)

    def test_lifecycle_task_uses_next_phase_number(self):
        """Synthetic lifecycle task uses max phase number plus one."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir_with_lifecycle_action(
                tmp,
                "archive",
                phase_numbers=(2, 4),
            )
            result = compile_delegation_plan(plan_dir)
        assert "### Task 2: Widget Factory" in result
        assert "### Task 4: Widget Validator" in result
        assert "### Task 5: Plan lifecycle — archive plan files" in result
        assert "Run after Tasks 2, 4 complete successfully." in result


# -- AC-06: Export target from ralphex config precedence -----------------------

class TestAC06ExportTargetPrecedence:
    """AC-06: Export target directory resolved from ralphex config precedence."""

    def test_local_config_overrides_default(self):
        """Local .ralphex/config plans_dir takes precedence."""
        with TemporaryDirectory() as tmp:
            ralphex_dir = Path(tmp) / ".ralphex"
            ralphex_dir.mkdir()
            (ralphex_dir / "config").write_text(
                'plans_dir = "custom/plans"\n', encoding="utf-8"
            )
            result = resolve_plans_dir(tmp)
        assert result == os.path.join(tmp, "custom/plans")

    def test_default_is_docs_plans(self):
        """Without any config, falls back to docs/plans/."""
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "no_config")}):
                result = resolve_plans_dir(tmp)
        assert result == os.path.join(tmp, "docs/plans")

    def test_not_hardcoded_or_cypilot_owned(self):
        """Resolved path does not contain .bootstrap or cypilot-specific directories."""
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(Path(tmp) / "no_config")}):
                result = resolve_plans_dir(tmp)
        assert ".bootstrap" not in result
        assert "cypilot" not in result.lower() or "cypilot" in tmp.lower()


# -- AC-07: Exported plans contain only bounded SDLC slices -------------------

class TestAC07BoundedSlices:
    """AC-07: Exported plans contain only bounded SDLC slices, not entire kit."""

    def test_guidance_only_from_engineering_and_quality(self):
        """Only Engineering and Quality rules subsections appear in guidance."""
        result = map_phase_to_task(PHASE_02_CONTENT, 2)
        # Should include Engineering/Quality guidance
        assert "TDD" in result or "test first" in result.lower()
        assert "Readability" in result or "naming" in result.lower()
        # Should NOT include MUST NOT section items
        assert "hardcoded secrets" not in result.lower()

    def test_excluded_sections_not_in_output(self):
        """Output Format, Preamble, etc. are excluded from task blocks."""
        phase_with_excluded = PHASE_01_CONTENT + "\n## Output Format\n\nThis should not appear.\n"
        result = map_phase_to_task(phase_with_excluded, 1)
        assert "This should not appear" not in result
        assert "Prioritize the phase frontmatter plus `What`, `Rules`, `Input`, `Task`, `Acceptance Criteria`, and `Output Format`." in result
        assert "**Ignore:**" in result


# -- AC-08: One phase maps to one Task block -----------------------------------

class TestAC08PhaseToTaskMapping:
    """AC-08: One Cypilot phase maps to one ### Task N: block."""

    def test_each_phase_is_one_task_block(self):
        """compile_delegation_plan produces exactly one Task block per phase."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        # Count ### Task N: blocks
        import re
        task_blocks = re.findall(r"### Task \d+:", result)
        assert len(task_blocks) == 2  # matches 2 phases in fixture

    def test_phase_number_matches_task_number(self):
        """Phase 1 → Task 1, Phase 2 → Task 2."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert "### Task 1: Widget Factory" in result
        assert "### Task 2: Widget Validator" in result
        assert "test-plan/phase-01.md" in result
        assert "test-plan/phase-02.md" in result


# -- AC-09: Delegation uses correct mode flags ---------------------------------

class TestAC09DelegationModeFlags:
    """AC-09: Delegation invokes ralphex with correct mode flags."""

    def test_execute_mode(self):
        """Execute mode: ralphex <plan.md>."""
        cmd = build_delegation_command("/bin/ralphex", "plan.md", "execute")
        assert cmd == ["/bin/ralphex", "plan.md"]

    def test_tasks_only_mode(self):
        """Tasks-only mode: --tasks-only flag appended."""
        cmd = build_delegation_command("/bin/ralphex", "plan.md", "tasks-only")
        assert "--tasks-only" in cmd

    def test_review_mode(self):
        """Review mode: --review flag."""
        cmd = build_delegation_command("/bin/ralphex", None, "review")
        assert "--review" in cmd

    def test_serve_flag(self):
        """Dashboard mode: --serve flag appended."""
        cmd = build_delegation_command("/bin/ralphex", "plan.md", "execute", serve=True)
        assert "--serve" in cmd

    def test_worktree_flag(self):
        """Worktree mode: --worktree flag appended."""
        cmd = build_delegation_command("/bin/ralphex", "plan.md", "execute", worktree=True)
        assert "--worktree" in cmd


# -- AC-10: --worktree constraint enforcement ----------------------------------

class TestAC10WorktreeConstraint:
    """AC-10: --worktree only for full mode and tasks-only, not review-only."""

    def test_worktree_allowed_for_execute(self):
        cmd = build_delegation_command("/bin/ralphex", "p.md", "execute", worktree=True)
        assert "--worktree" in cmd

    def test_worktree_allowed_for_tasks_only(self):
        cmd = build_delegation_command("/bin/ralphex", "p.md", "tasks-only", worktree=True)
        assert "--worktree" in cmd

    def test_worktree_not_appended_for_review(self):
        """--worktree is silently dropped for review mode."""
        cmd = build_delegation_command("/bin/ralphex", None, "review", worktree=True)
        assert "--worktree" not in cmd


# -- AC-11: Review-only verifies committed changes -----------------------------

class TestAC11ReviewPrecondition:
    """AC-11: Review-only verifies committed changes before invoking ralphex --review."""

    def test_passes_when_commits_ahead(self):
        """Precondition passes with commits ahead of default branch."""
        proc = MagicMock(returncode=0, stdout="abc123\ndef456\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition("main")
        assert result["ok"] is True
        assert result["commit_count"] == 2

    def test_fails_when_no_commits_ahead(self):
        """Precondition fails when no commits ahead."""
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition("main")
        assert result["ok"] is False
        assert "no committed changes" in result["message"].lower()

    def test_fails_on_git_error(self):
        """Precondition fails gracefully on git error."""
        proc = MagicMock(returncode=128, stdout="", stderr="fatal: bad revision")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            result = check_review_precondition("main")
        assert result["ok"] is False


# -- AC-12: Post-run handoff reports status and re-runs validation -------------

class TestAC12PostRunHandoff:
    """AC-12: Post-run handoff reports status, output refs, and re-runs validation."""

    def test_handoff_success_flow(self):
        """Full handoff: read status → check completed → run validation → report."""
        # Step 1: Read status
        status = read_handoff_status(exit_code=0, output_refs=["out/report.md"])
        assert status["status"] == "success"

        # Step 2: Check completed plans
        with TemporaryDirectory() as tmp:
            completed = Path(tmp) / "completed"
            completed.mkdir()
            (completed / "task.md").write_text("# Done\n", encoding="utf-8")
            plans = check_completed_plans(tmp, "task")
        assert plans["found"] is True

        # Step 3: Run validation commands
        proc = MagicMock(returncode=0, stdout="ok\n", stderr="")
        with patch("studio.ralphex_export.subprocess.run", return_value=proc):
            validation = run_validation_commands(["python -m pytest tests/"])
        assert validation["passed"] is True

        # Step 4: Report handoff
        report = report_handoff(
            plan_file="docs/plans/task.md",
            mode="execute",
            exit_code=0,
            output_refs=["out/report.md"],
            completed_plan_path=str(completed / "task.md"),
            validation_passed=True,
        )
        assert report["status"] == "success"
        assert report["validation_passed"] is True
        assert report["output_refs"] == ["out/report.md"]

    def test_handoff_failure_flow(self):
        """Handoff reports failure when ralphex exits non-zero."""
        status = read_handoff_status(exit_code=1, output_refs=[])
        assert status["status"] == "failed"

        report = report_handoff(
            plan_file="p.md",
            mode="execute",
            exit_code=1,
            output_refs=[],
            completed_plan_path=None,
            validation_passed=False,
        )
        assert report["status"] == "failed"

    def test_lifecycle_tracks_full_flow(self):
        """DelegationLifecycle tracks export → delegate → complete."""
        lc = DelegationLifecycle()
        lc.export()
        lc.delegate()
        lc.complete()
        assert lc.state == "completed"
        assert len(lc.history) == 3


# -- AC-13: Fully optional integration ----------------------------------------

class TestAC13OptionalIntegration:
    """AC-13: Projects without ralphex use normal Cypilot workflows with zero change."""

    def test_discover_returns_none_no_side_effects(self):
        """When ralphex is absent, discover returns None without modifying anything."""
        config = {}
        with patch("studio.ralphex_discover.shutil.which", return_value=None):
            result = discover(config)
        assert result is None
        # Config unchanged
        assert config == {}

    def test_validate_none_is_informational_only(self):
        """validate(None) provides guidance without raising or failing."""
        result = validate(None)
        assert result["status"] == "unavailable"
        # Not a hard error — caller decides how to handle

    def test_doctor_check_does_not_block_on_missing(self):
        """Doctor returns WARN (not FAIL) when ralphex is missing."""
        from studio.commands.doctor import _check_ralphex

        with TemporaryDirectory() as tmp:
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                result = _check_ralphex(Path(tmp))
        assert result["level"] == "WARN"

    def test_doctor_exit_code_zero_when_only_warns(self):
        """Doctor returns exit 0 even with WARN-level checks."""
        from studio.commands.doctor import cmd_doctor

        with patch("studio.ralphex_discover.shutil.which", return_value=None):
            exit_code = cmd_doctor(["--root", "/tmp"])
        assert exit_code == 0


# -- AC-14: No SDLC asset duplication into .ralphex/ ---------------------------

class TestAC14NoSDLCDuplication:
    """AC-14: No Cypilot SDLC assets duplicated into .ralphex/."""

    def test_export_does_not_write_to_ralphex_dir(self):
        """compile_delegation_plan output contains no .ralphex/ file writes."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        # Output is a string, not written to disk by compile_delegation_plan
        assert ".ralphex/" not in result

    def test_no_kit_content_in_exported_plan(self):
        """Exported plan does not contain kit file references (rules.md, checklist.md)."""
        with TemporaryDirectory() as tmp:
            plan_dir = _make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        # Should not contain references to kit workflow files
        assert "rules.md" not in result.lower()
        assert "checklist.md" not in result.lower()
        assert "kit workflows" not in result.lower()

    def test_bootstrap_check_does_not_copy_sdlc(self):
        """check_bootstrap_needed only reports — never copies SDLC assets."""
        with TemporaryDirectory() as tmp:
            result = check_bootstrap_needed(tmp)
            # The .ralphex directory should not have been created
            assert not (Path(tmp) / ".ralphex").exists()


# -- Review artifact generation integration -----------------------------------

class TestReviewArtifactGeneration:
    """Review artifact generation produces deterministic .ralphex/ overrides."""

    def _make_project_with_sources(self, tmp):
        """Create a project with canonical Cypilot sources for review artifact generation."""
        repo_root = Path(tmp) / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()
        (repo_root / ".ralphex" / "config").parent.mkdir(parents=True, exist_ok=True)
        (repo_root / ".ralphex" / "config").write_text(
            'plans_dir = "docs/plans"\n', encoding="utf-8"
        )

        prompts = repo_root / ".ralphex" / "prompts"
        prompts.mkdir(parents=True)
        (prompts / "review_first.txt").write_text(
            "# first review prompt\n\nOriginal first review body.\n",
            encoding="utf-8",
        )
        (prompts / "review_second.txt").write_text(
            "# second review prompt\n\nOriginal second review body.\n",
            encoding="utf-8",
        )

        core = repo_root / ".bootstrap" / ".core"
        workflows = core / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "analyze.md").write_text("# Analyze\n", encoding="utf-8")
        reqs = core / "requirements"
        reqs.mkdir(parents=True)
        for name in ("bug-finding.md", "prompt-engineering.md",
                      "prompt-bug-finding.md", "code-checklist.md"):
            (reqs / name).write_text(f"# {name}\n", encoding="utf-8")

        plan_dir = _make_plan_dir(tmp)
        return str(repo_root), plan_dir

    def test_review_artifacts_generated_at_deterministic_path(self):
        """generate_review_artifacts creates override at .ralphex/prompts/."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project_with_sources(tmp)
            result = generate_review_artifacts(plan_dir, repo_root)
            assert len(result["artifacts"]) == 2
            assert Path(result["artifacts"][0]).exists()
            assert result["relative_paths"] == list(REVIEW_PROMPT_RELATIVES)

    def test_review_artifacts_do_not_alter_compiled_plan(self):
        """Generating review artifacts does not change compile_delegation_plan output."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project_with_sources(tmp)
            plan_before = compile_delegation_plan(plan_dir)
            generate_review_artifacts(plan_dir, repo_root)
            plan_after = compile_delegation_plan(plan_dir)
            assert plan_before == plan_after

    def test_review_override_not_in_compiled_plan(self):
        """The .ralphex/ review override is not referenced in the compiled plan."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project_with_sources(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            plan = compile_delegation_plan(plan_dir)
            assert ".ralphex/prompts" not in plan

    def test_non_review_delegation_unaffected(self):
        """Non-review delegation (execute mode) continues to work identically."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project_with_sources(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert "### Task 1:" in Path(result["plan_file"]).read_text(encoding="utf-8")


# -- Orchestration entrypoint tests ------------------------------------------

class TestRunDelegation:
    """Tests for the canonical run_delegation() orchestration entrypoint."""

    def _make_delegatable_project(self, tmp):
        """Create a project directory with plan, ralphex config, and mock ralphex."""
        repo_root = Path(tmp) / "repo"
        repo_root.mkdir()
        # ralphex config so bootstrap gate passes
        ralphex_dir = repo_root / ".ralphex"
        ralphex_dir.mkdir()
        (ralphex_dir / "config").write_text(
            'plans_dir = "docs/plans"\n', encoding="utf-8"
        )
        # Plan directory
        plan_dir = _make_plan_dir(tmp)
        return str(repo_root), plan_dir

    def test_dry_run_returns_ready_with_command(self):
        """dry_run=True assembles command without invoking, returns 'ready'."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert result["ralphex_path"] == "/usr/bin/ralphex"
            assert result["plan_file"] is not None
            assert Path(result["plan_file"]).exists()
            assert len(result["command"]) > 0
            assert result["command"][0] == "/usr/bin/ralphex"
            assert result["lifecycle_state"] == "exported"
            assert result["error"] is None

    def test_full_delegation_returns_delegated(self):
        """Non-dry-run returns 'delegated' with lifecycle in completed state."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=0)
            invoke_proc.communicate.return_value = ("Done\n", "")

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=False,
                )
            assert result["status"] == "delegated"
            assert result["lifecycle_state"] == "completed"
            assert result["returncode"] == 0

    def test_full_delegation_streams_output_when_requested(self):
        """stream_output=True invokes ralphex with inherited stdio."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=0)
            invoke_kwargs = {}

            def _capture_popen(*args, **kwargs):
                invoke_kwargs.update(kwargs)
                return invoke_proc

            invoke_proc.communicate.return_value = (None, None)

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", side_effect=_capture_popen):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=False,
                    stream_output=True,
                )
            assert result["status"] == "delegated"
            assert result["lifecycle_state"] == "completed"
            assert result["stdout"] is None
            assert result["stderr"] is None
            assert result["returncode"] == 0
            assert "capture_output" not in invoke_kwargs
            assert "text" not in invoke_kwargs

    def test_validate_delegation_command_rejects_unknown_flag(self, tmp_path):
        """Command validation rejects unexpected ralphex flags before launch."""
        executable = tmp_path / "ralphex"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)

        error = _validate_delegation_command([str(executable), "--bad-flag"])

        assert "unsupported flag" in error

    def test_delegation_rejects_non_absolute_executable_path(self):
        """Delegation refuses a non-absolute ralphex executable path before subprocess launch."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {
                "integrations": {
                    "ralphex": {
                        "executable_path": "ralphex",
                    }
                }
            }
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=True,
                )
            assert result["status"] == "error"
            assert "not installed" in result["validation"]["message"]

    def test_nonzero_exit_sets_failed_lifecycle(self):
        """Regression: non-zero subprocess return code transitions lifecycle to failed."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=1)
            invoke_proc.communicate.return_value = ("", "task failed")

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=False,
                )
            assert result["status"] == "error"
            assert result["lifecycle_state"] == "failed"
            assert result["returncode"] == 1

    def _mock_tty_open(self, answer):
        """Return a context manager that mocks /dev/tty open to return *answer*.

        Falls through to the real ``open`` for any other path so file I/O in
        the test helpers is unaffected.
        """
        real_open = builtins.open
        mock_tty = MagicMock()
        mock_tty.__enter__.return_value.readline.return_value = answer + "\n"

        def _side_effect(path, *args, **kwargs):
            if str(path) == "/dev/tty":
                return mock_tty
            return real_open(path, *args, **kwargs)

        return patch("builtins.open", side_effect=_side_effect)

    def _mock_tty_open_error(self, exc):
        """Return a context manager that raises *exc* only for /dev/tty open."""
        real_open = builtins.open

        def _side_effect(path, *args, **kwargs):
            if str(path) == "/dev/tty":
                raise exc
            return real_open(path, *args, **kwargs)

        return patch("builtins.open", side_effect=_side_effect)

    def test_timeout_prompt_enter_continues_waiting(self):
        """Timeout prompt continues waiting on Enter and preserves successful completion."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=0)
            invoke_proc.communicate.side_effect = [
                subprocess.TimeoutExpired(["/usr/bin/ralphex"], 3600),
                ("Done\n", ""),
            ]

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc), \
                 patch("sys.stdin.isatty", return_value=True), \
                 self._mock_tty_open(""):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=False,
                )
            assert result["status"] == "delegated"
            assert result["lifecycle_state"] == "completed"
            assert invoke_proc.communicate.call_count == 2

    def test_timeout_prompt_no_stops_process(self):
        """Timeout prompt stops the process when user answers no."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=143)
            invoke_proc.communicate.side_effect = [
                subprocess.TimeoutExpired(["/usr/bin/ralphex"], 3600),
                ("", ""),
            ]

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc), \
                 patch("sys.stdin.isatty", return_value=True), \
                 self._mock_tty_open("n"):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=False,
                )
            invoke_proc.terminate.assert_called_once_with()
            assert result["status"] == "error"
            assert result["lifecycle_state"] == "failed"
            assert "was stopped" in result["error"].lower()

    def test_timeout_prompt_eof_stops_process(self):
        """Timeout prompt stops the process when no answer can be read."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=143)
            invoke_proc.communicate.side_effect = [
                subprocess.TimeoutExpired(["/usr/bin/ralphex"], 3600),
                ("", ""),
            ]

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc), \
                 patch("sys.stdin.isatty", return_value=True), \
                 self._mock_tty_open_error(OSError()), \
                 patch("builtins.input", side_effect=EOFError):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=False,
                )
            invoke_proc.terminate.assert_called_once_with()
            assert result["status"] == "error"
            assert result["lifecycle_state"] == "failed"
            assert "was stopped" in result["error"].lower()

    def test_error_when_ralphex_not_found(self):
        """Returns error when ralphex is not discoverable."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            with patch("studio.ralphex_discover.shutil.which", return_value=None):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    dry_run=True,
                )
            assert result["status"] == "error"
            assert result["error"] is not None
            assert result["validation"]["status"] == "unavailable"

    def test_bootstrap_needed_is_non_blocking(self):
        """Delegation proceeds with warning when .ralphex/config is missing."""
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            # No .ralphex/config
            plan_dir = _make_plan_dir(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=str(repo_root),
                    dry_run=True,
                )
            assert result["status"] == "error"
            assert result["bootstrap"]["needed"] is True
            assert result["error"] == result["bootstrap"]["message"]
            assert result["plan_file"] is None

    def test_error_when_review_no_commits(self):
        """Returns error when review mode but no commits ahead."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_version = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            mock_revlist = MagicMock(returncode=0, stdout="", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_version), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={
                     "ok": False, "commit_count": 0,
                     "message": "No committed changes ahead of main.",
                 }):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="review",
                    dry_run=True,
                )
            assert result["status"] == "error"
            assert "committed changes" in result["error"].lower() or "no committed" in result["error"].lower()

    def test_exported_plan_file_contains_valid_content(self):
        """The exported plan file contains ralphex grammar sections."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    dry_run=True,
                )
            plan_content = Path(result["plan_file"]).read_text(encoding="utf-8")
            assert "## Validation Commands" in plan_content
            assert "### Task 1:" in plan_content

    def test_composes_existing_helpers(self):
        """run_delegation uses discover, validate, compile_delegation_plan, etc."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex") as mock_which, \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    dry_run=True,
                )
            # Verify discover was called (via shutil.which)
            mock_which.assert_called_once_with("ralphex")
            # Verify the result schema matches the documented contract
            expected_keys = {
                "status", "ralphex_path", "validation", "bootstrap",
                "plan_file", "command", "mode", "lifecycle_state", "error",
                "dashboard_url",
            }
            assert set(result.keys()) == expected_keys

    def test_mode_passed_through_to_command(self):
        """Delegation mode is reflected in the assembled command."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="tasks-only",
                    dry_run=True,
                )
            assert "--tasks-only" in result["command"]
            assert result["mode"] == "tasks-only"


# -- Review-mode orchestration tests -----------------------------------------

class TestReviewModeOrchestration:
    """Tests for review-mode delegation wiring via run_delegation()."""

    def _make_review_project(self, tmp):
        """Create a project with canonical Cypilot sources for review delegation."""
        repo_root = Path(tmp) / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

        # .ralphex/config so bootstrap gate passes
        ralphex_dir = repo_root / ".ralphex"
        ralphex_dir.mkdir()
        (ralphex_dir / "config").write_text(
            'plans_dir = "docs/plans"\n', encoding="utf-8"
        )
        prompts = ralphex_dir / "prompts"
        prompts.mkdir()
        (prompts / "review_first.txt").write_text(
            "# first review prompt\n\nOriginal first review body.\n",
            encoding="utf-8",
        )
        (prompts / "review_second.txt").write_text(
            "# second review prompt\n\nOriginal second review body.\n",
            encoding="utf-8",
        )

        # Canonical Cypilot sources for review artifact generation
        core = repo_root / ".bootstrap" / ".core"
        workflows = core / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "analyze.md").write_text("# Analyze\n", encoding="utf-8")
        reqs = core / "requirements"
        reqs.mkdir(parents=True)
        for name in ("bug-finding.md", "prompt-engineering.md",
                      "prompt-bug-finding.md", "code-checklist.md"):
            (reqs / name).write_text(f"# {name}\n", encoding="utf-8")

        plan_dir = _make_plan_dir(tmp)
        return str(repo_root), plan_dir

    def test_review_mode_generates_review_artifacts(self):
        """run_delegation in review mode generates .ralphex/prompts/ override."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_review_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={
                     "ok": True, "commit_count": 3,
                     "message": "3 commit(s) ahead of main, ready for review.",
                 }):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="review",
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert "review_artifacts" in result
            assert len(result["review_artifacts"]["artifacts"]) == 2
            assert result["review_artifacts"]["relative_paths"] == list(REVIEW_PROMPT_RELATIVES)
            for relative_path in REVIEW_PROMPT_RELATIVES:
                prompt_content = (Path(repo_root) / relative_path).read_text(encoding="utf-8")
                assert "<!-- @cpt-begin:studio-review-override -->" in prompt_content
                assert "Final review step: load and follow" in prompt_content

    def test_review_mode_override_contains_methodology_routing(self):
        """Generated review override contains code and prompt review routing."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_review_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={
                     "ok": True, "commit_count": 1,
                     "message": "1 commit(s) ahead of main, ready for review.",
                 }):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="review",
                    dry_run=True,
                )
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "standard ralphex review flow" in content
            assert "final analyze step" in content
            assert "STUDIO_ANALYZE_START:" in content
            assert "STUDIO_ANALYZE_DONE: no_findings" in content
            assert "REVIEW_DONE" in content

    def test_execute_mode_does_not_generate_review_artifacts(self):
        """run_delegation in execute mode skips review artifact generation."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_review_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert "review_artifacts" not in result
            for relative_path in REVIEW_PROMPT_RELATIVES:
                prompt_content = (Path(repo_root) / relative_path).read_text(encoding="utf-8")
                assert "<!-- @cpt-begin:studio-review-override -->" not in prompt_content

    def test_review_mode_command_includes_review_flag(self):
        """Review-mode delegation command has --review flag."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_review_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc), \
                 patch("studio.ralphex_export.check_review_precondition", return_value={
                     "ok": True, "commit_count": 2,
                     "message": "2 commit(s) ahead of main, ready for review.",
                 }):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="review",
                    dry_run=True,
                )
            assert "--review" in result["command"]

    def test_review_mode_preserves_non_review_behavior(self):
        """Execute-mode delegation is unchanged by review-mode wiring."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_review_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert "--review" not in result["command"]
            plan_content = Path(result["plan_file"]).read_text(encoding="utf-8")
            assert "### Task 1:" in plan_content
            for relative_path in REVIEW_PROMPT_RELATIVES:
                prompt_content = (Path(repo_root) / relative_path).read_text(encoding="utf-8")
                assert "<!-- @cpt-begin:studio-review-override -->" not in prompt_content
            assert "review_artifacts" not in result


# -- End-to-end capability surface verification --------------------------------

class TestEndToEndCapabilitySurface:
    """Prove routing, orchestration, export contract, handoff, and agent delivery
    work together as one coherent capability surface."""

    def _make_delegatable_project(self, tmp):
        """Create a project with plan, ralphex config, and mock ralphex."""
        repo_root = Path(tmp) / "repo"
        repo_root.mkdir()
        ralphex_dir = repo_root / ".ralphex"
        ralphex_dir.mkdir()
        (ralphex_dir / "config").write_text(
            'plans_dir = "docs/plans"\n', encoding="utf-8"
        )
        plan_dir = _make_plan_dir(tmp)
        return str(repo_root), plan_dir

    def test_orchestration_produces_valid_export_contract(self):
        """run_delegation output satisfies the full export contract:
        title, ## Validation Commands, ### Task blocks, phase references,
        bounded guidance, ignore rules, and no absolute paths."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    dry_run=True,
                )
            assert result["status"] == "ready"
            plan_content = Path(result["plan_file"]).read_text(encoding="utf-8")
            # Export contract: title
            assert plan_content.startswith("# ")
            # Export contract: validation commands
            assert "## Validation Commands" in plan_content
            # Export contract: task blocks per phase
            assert "### Task 1:" in plan_content
            assert "### Task 2:" in plan_content
            assert "**Original Phase File:**" in plan_content
            assert "**Execution Prompt:**" in plan_content
            assert "**Ignore:**" in plan_content
            assert "**Declared Scope:**" in plan_content
            assert "test-plan/phase-01.md" in plan_content
            assert "test-plan/phase-02.md" in plan_content
            # Export contract: no absolute paths
            assert tmp not in plan_content
            # Export contract: bounded guidance (only Engineering/Quality)
            assert "hardcoded secrets" not in plan_content.lower()

    def test_orchestration_to_handoff_continuity(self):
        """run_delegation result feeds correctly into the handoff pipeline:
        read_handoff_status → check_completed_plans → run_validation → report_handoff."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            discover_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            invoke_proc = MagicMock(returncode=0)
            invoke_proc.communicate.return_value = ("Done\n", "")

            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=discover_proc), \
                 patch("studio.ralphex_export.subprocess.Popen", return_value=invoke_proc):
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    dry_run=False,
                )
            assert result["status"] == "delegated"
            # Simulate ralphex completing successfully
            handoff_status = read_handoff_status(
                exit_code=0,
                output_refs=[result["plan_file"]],
            )
            assert handoff_status["status"] == "success"
            # Check completed plans in the resolved plans dir
            plans_dir = os.path.dirname(result["plan_file"])
            completed = Path(plans_dir) / "completed"
            completed.mkdir(parents=True, exist_ok=True)
            slug = Path(result["plan_file"]).stem
            (completed / f"{slug}.md").write_text("# Done\n", encoding="utf-8")
            completed_check = check_completed_plans(plans_dir, slug)
            assert completed_check["found"] is True
            # Report handoff using orchestration result
            report = report_handoff(
                plan_file=result["plan_file"],
                mode=result["mode"],
                exit_code=0,
                output_refs=[result["plan_file"]],
                completed_plan_path=completed_check["completed_path"],
                validation_passed=True,
            )
            assert report["status"] == "success"
            assert report["mode"] == result["mode"]
            assert report["plan_file"] == result["plan_file"]

    def test_routing_to_orchestration_to_command(self):
        """Agent registration → discovery → run_delegation produces valid command
        with correct executable and mode flags."""
        from studio.ralphex_discover import discover, validate
        import tomllib

        # Verify routing: agents.toml registers cf-ralphex
        agents_toml = Path(__file__).parent.parent / "skills" / "studio" / "agents.toml"
        with open(agents_toml, "rb") as f:
            agents_data = tomllib.load(f)
        assert "cf-ralphex" in agents_data["agents"]

        # Verify orchestration: discover → validate → run_delegation
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_delegatable_project(tmp)
            config = {}
            mock_proc = MagicMock(returncode=0, stdout="ralphex v1.0.0\n", stderr="")
            with patch("studio.ralphex_discover.shutil.which", return_value="/usr/bin/ralphex"), \
                 patch("studio.ralphex_discover.subprocess.run", return_value=mock_proc):
                # Discovery works
                path = discover(config)
                assert path == "/usr/bin/ralphex"
                # Validation passes
                val = validate(path)
                assert val["status"] == "available"
                # Orchestration assembles valid command
                result = run_delegation(
                    config=config,
                    plan_dir=plan_dir,
                    repo_root=repo_root,
                    mode="execute",
                    worktree=True,
                    dry_run=True,
                )
            assert result["status"] == "ready"
            assert result["command"][0] == "/usr/bin/ralphex"
            assert "--worktree" in result["command"]
            assert result["lifecycle_state"] == "exported"

    def test_windsurf_delegation_reachable_via_skill_routing(self):
        """Windsurf accesses delegation through SKILL.md routing, not a subagent proxy.
        Verify the skill output references the canonical SKILL.md and subagents are skipped."""
        from studio.commands.agents import _process_single_agent, _default_agents_config, _discover_kit_agents
        import shutil

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            (root / ".git").mkdir()
            cpt = root / "studio"
            cpt.mkdir()
            core_skill = cpt / ".core" / "skills" / "studio"
            core_skill.mkdir(parents=True)
            core_skill_md = core_skill / "SKILL.md"
            core_skill_md.write_text(
                "---\nname: studio\ndescription: Test skill\n---\nContent\n",
                encoding="utf-8",
            )
            # Copy real agents.toml
            src_agents_toml = Path(__file__).parent.parent / "skills" / "studio" / "agents.toml"
            shutil.copy2(src_agents_toml, core_skill / "agents.toml")
            # Create prompt files
            agents_dir = core_skill / "agents"
            agents_dir.mkdir(parents=True)
            for name in ("cf-ralphex", "cf-codegen", "cf-pr-review"):
                (agents_dir / f"{name}.md").write_text(
                    f"You are {name}.\n", encoding="utf-8"
                )
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)

            # Verify ralphex is discoverable
            agents = _discover_kit_agents(cpt, root)
            ralphex_agents = [a for a in agents if a["name"] == "cf-ralphex"]
            assert len(ralphex_agents) == 1

            # Generate windsurf output
            cfg = _default_agents_config()
            result = _process_single_agent("windsurf", root, cpt, cfg, None, dry_run=False)

            # Windsurf skill output exists and references canonical SKILL.md
            skills = result.get("skills", {})
            skill_files = skills.get("created", []) + skills.get("updated", [])
            assert len(skill_files) > 0, "Windsurf must produce skill output"
            found = any(
                "ALWAYS open and follow" in Path(f).read_text(encoding="utf-8")
                and "SKILL.md" in Path(f).read_text(encoding="utf-8")
                for f in skill_files
            )
            assert found, "Windsurf skill must reference canonical SKILL.md"

            # Windsurf does not produce subagent proxies (consistent with its design)
            subagents = result.get("subagents", {})
            assert subagents.get("skipped", False), "Windsurf subagents must be skipped"

    def test_all_integrations_produce_ralphex_proxy(self):
        """All supported integrations (claude, cursor, copilot, openai) produce
        a cypilot-ralphex proxy pointing to the same canonical prompt path."""
        from studio.commands.agents import _process_single_agent, _default_agents_config
        import shutil

        with TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            (root / ".git").mkdir()
            cpt = root / "studio"
            cpt.mkdir()
            core_skill = cpt / ".core" / "skills" / "studio"
            core_skill.mkdir(parents=True)
            core_skill_md = core_skill / "SKILL.md"
            core_skill_md.write_text(
                "---\nname: studio\ndescription: Test skill\n---\nContent\n",
                encoding="utf-8",
            )
            src_agents_toml = Path(__file__).parent.parent / "skills" / "studio" / "agents.toml"
            shutil.copy2(src_agents_toml, core_skill / "agents.toml")
            agents_dir = core_skill / "agents"
            agents_dir.mkdir(parents=True)
            for name in ("cf-ralphex", "cf-codegen", "cf-pr-review"):
                (agents_dir / f"{name}.md").write_text(
                    f"You are {name}.\n", encoding="utf-8"
                )
            (cpt / ".core" / "workflows").mkdir(parents=True, exist_ok=True)

            canonical_fragment = "skills/studio/agents/cf-ralphex.md"
            for agent in ("claude", "cursor", "copilot", "openai"):
                cfg = _default_agents_config()
                result = _process_single_agent(agent, root, cpt, cfg, None, dry_run=False)
                subagents = result.get("subagents", {})
                all_files = subagents.get("created", []) + subagents.get("updated", [])
                ralphex_found = False
                for fpath in all_files:
                    content = Path(fpath).read_text(encoding="utf-8")
                    if "cf-ralphex" in fpath or "cf_ralphex" in content:
                        assert canonical_fragment in content, (
                            f"{agent} proxy must point to canonical prompt"
                        )
                        ralphex_found = True
                assert ralphex_found, f"{agent} must generate a cf-ralphex proxy"
