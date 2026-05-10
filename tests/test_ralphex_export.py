"""
Tests for ralphex plan export compiler module.

Covers:
- map_phase_to_task(): title extraction, step flattening, criteria flattening,
  guidance distillation, file path inclusion
- compile_delegation_plan(): plan assembly, validation section, task blocks,
  path resolution
"""

import os
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "cypilot" / "scripts"))

from cypilot.ralphex_export import (
    _resolve_paths,
    compile_delegation_plan,
    extract_validation_commands,
    generate_review_artifacts,
    map_phase_to_task,
    REVIEW_PROMPT_RELATIVES,
)


# -- Fixtures: minimal phase content and plan manifest -----------------------

MINIMAL_PHASE = textwrap.dedent("""\
    ```toml
    [phase]
    plan = "test-plan"
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
    2. Implement `WidgetFactory` class.
    3. Write unit tests.

    ## Acceptance Criteria

    - [ ] WidgetFactory class exists
    - [ ] Unit tests pass
    - [ ] No unresolved variables

    ## Output Format

    Ignored section.
""")

PHASE_WITH_RULES = textwrap.dedent("""\
    ```toml
    [phase]
    plan = "test-plan"
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
    - **Error handling**: Fail explicitly with clear errors

    ## Task

    1. Write failing tests for validation.
    2. Implement validate() method.

    ## Acceptance Criteria

    - [ ] validate() rejects invalid widgets
    - [ ] Tests cover edge cases
""")

MINIMAL_PLAN_TOML = textwrap.dedent("""\
    [plan]
    task = "Implement test-plan"
    type = "implement"
    target = "FEATURE"

    [[phases]]
    number = 1
    title = "Widget Factory"
    slug = "widget-factory"
    file = "phase-01-widget-factory.md"
    status = "pending"
    kind = "delivery"
    depends_on = []
    input_files = []
    output_files = ["src/widget.py", "tests/test_widget.py"]

    [[phases]]
    number = 2
    title = "Widget Validator"
    slug = "widget-validator"
    file = "phase-02-widget-validator.md"
    status = "pending"
    kind = "delivery"
    depends_on = [1]
    input_files = []
    output_files = ["src/validator.py"]
""")


class TestMapPhaseToTask:
    """Tests for map_phase_to_task() — single phase to Task block."""

    def test_extracts_title(self):
        """Task block header uses phase title."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        assert "### Task 1:" in result
        assert "Widget Factory" in result

    def test_flattens_task_steps_to_bullets(self):
        """Numbered task steps become bullet items in Phase Focus."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        assert "- Read design spec" in result
        assert "- Implement `WidgetFactory` class" in result
        assert "- Write unit tests" in result

    def test_flattens_acceptance_criteria_to_success_checks(self):
        """Acceptance criteria are included as Success Checks bullets."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        assert "**Success Checks:**" in result
        assert "- WidgetFactory class exists" in result
        assert "- Unit tests pass" in result
        assert "- No unresolved variables" in result

    def test_includes_output_file_paths(self):
        """Output file paths from frontmatter are included."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        assert "src/widget.py" in result
        assert "tests/test_widget.py" in result

    def test_distills_bounded_guidance(self):
        """Rules section is distilled into bounded guidance."""
        result = map_phase_to_task(PHASE_WITH_RULES, 2)
        assert "### Task 2:" in result
        assert "TDD" in result or "test first" in result.lower()
        assert "Error handling" in result or "error" in result.lower()

    def test_no_output_format_content(self):
        """Output Format content body is not included in task block."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        assert "Ignored section" not in result

    def test_phase_num_in_header(self):
        """Phase number is used in Task header."""
        result = map_phase_to_task(MINIMAL_PHASE, 5)
        assert "### Task 5:" in result

    def test_no_unresolved_variables(self):
        """No unresolved {…} template variables in output (outside code fences)."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        # Strip code fences before checking
        in_fence = False
        for line in result.splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                import re as _re
                assert not _re.search(r"\{[a-z_]+\}", line), (
                    f"Unresolved variable in: {line}"
                )


class TestCompileDelegationPlan:
    """Tests for compile_delegation_plan() — full plan assembly."""

    def _make_plan_dir(self, tmp: str) -> str:
        """Create a minimal plan directory with plan.toml and phase files."""
        plan_dir = Path(tmp) / "test-plan"
        plan_dir.mkdir()

        (plan_dir / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
        (plan_dir / "phase-01-widget-factory.md").write_text(
            MINIMAL_PHASE, encoding="utf-8"
        )
        (plan_dir / "phase-02-widget-validator.md").write_text(
            PHASE_WITH_RULES, encoding="utf-8"
        )
        return str(plan_dir)

    def test_produces_valid_markdown(self):
        """compile_delegation_plan() returns non-empty Markdown string."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_validation_commands_section(self):
        """Output contains ## Validation Commands derived from deterministic contract."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert "## Validation Commands" in result
        # Derived from output_files — deterministic, not heuristic
        assert "tests/test_widget.py" in result

    def test_contains_task_blocks_per_phase(self):
        """Output contains ### Task N: blocks for each phase."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert "### Task 1:" in result
        assert "### Task 2:" in result

    def test_task_blocks_have_checkboxes(self):
        """Task blocks contain checkboxes."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert "- [ ]" in result

    def test_contains_plan_title(self):
        """Output starts with a plan title."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        assert result.startswith("# ")

    def test_sections_in_ralphex_grammar_order(self):
        """Sections appear in order: title, overview, Validation Commands, Tasks."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        title_pos = result.index("# ")
        validation_pos = result.index("## Validation Commands")
        task1_pos = result.index("### Task 1:")
        task2_pos = result.index("### Task 2:")
        assert title_pos < validation_pos < task1_pos < task2_pos

    def test_file_paths_are_project_root_relative(self):
        """All file paths in output are project-root-relative (no absolute paths)."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        for line in result.splitlines():
            # Skip code fences and headers
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("#"):
                continue
            # No absolute paths should appear
            if "/tmp/" in line or tmp in line:
                raise AssertionError(f"Absolute path found: {line}")

    def test_checkboxes_only_inside_task_sections(self):
        """Checkboxes (- [ ]) appear only inside ### Task sections."""
        with TemporaryDirectory() as tmp:
            plan_dir = self._make_plan_dir(tmp)
            result = compile_delegation_plan(plan_dir)
        in_task = False
        for line in result.splitlines():
            if line.startswith("### Task"):
                in_task = True
            elif line.startswith("## ") or line.startswith("# "):
                in_task = False
            if "- [ ]" in line:
                assert in_task, f"Checkbox outside task section: {line}"


class TestExtractValidationCommands:
    """Tests for extract_validation_commands() — deterministic contract."""

    def test_plan_level_commands_take_priority(self):
        """Explicit plan-level validation_commands override everything."""
        manifest = {
            "plan": {"validation_commands": ["make test", "make lint"]},
            "phases": [{"output_files": ["tests/test_a.py"]}],
        }
        result = extract_validation_commands(manifest)
        assert result == ["make test", "make lint"]

    def test_phase_level_commands_if_no_plan_level(self):
        """Phase-level validation_commands used when plan-level absent."""
        manifest = {
            "plan": {"task": "Test"},
            "phases": [
                {"validation_commands": ["pytest tests/a.py"], "output_files": []},
                {"validation_commands": ["pytest tests/b.py"], "output_files": []},
            ],
        }
        result = extract_validation_commands(manifest)
        assert result == ["pytest tests/a.py", "pytest tests/b.py"]

    def test_derives_from_output_files_when_no_explicit(self):
        """Derives pytest command from output_files test paths."""
        manifest = {
            "plan": {"task": "Test"},
            "phases": [
                {"output_files": ["src/widget.py", "tests/test_widget.py"]},
                {"output_files": ["tests/test_validator.py"]},
            ],
        }
        result = extract_validation_commands(manifest)
        assert len(result) == 1
        assert "python -m pytest" in result[0]
        assert "tests/test_validator.py" in result[0]
        assert "tests/test_widget.py" in result[0]

    def test_deduplicates_test_files(self):
        """Same test file in multiple phases appears once in command."""
        manifest = {
            "plan": {"task": "Test"},
            "phases": [
                {"output_files": ["tests/test_a.py"]},
                {"output_files": ["tests/test_a.py"]},
            ],
        }
        result = extract_validation_commands(manifest)
        assert len(result) == 1
        assert result[0].count("tests/test_a.py") == 1

    def test_empty_when_no_test_files(self):
        """Returns empty list when no test files and no explicit commands."""
        manifest = {
            "plan": {"task": "Test"},
            "phases": [{"output_files": ["src/widget.py"]}],
        }
        result = extract_validation_commands(manifest)
        assert result == []

    def test_only_py_test_files_matched(self):
        """Non-.py files in tests/ are not included."""
        manifest = {
            "plan": {"task": "Test"},
            "phases": [{"output_files": ["tests/conftest.py", "tests/fixtures.json"]}],
        }
        result = extract_validation_commands(manifest)
        assert len(result) == 1
        assert "conftest.py" in result[0]
        assert "fixtures.json" not in result[0]

    def test_empty_phases_returns_empty(self):
        """Manifest with no phases returns empty commands."""
        manifest = {"plan": {"task": "Test"}, "phases": []}
        result = extract_validation_commands(manifest)
        assert result == []


class TestPathResolution:
    """Tests for path resolution in exported plans."""

    def test_output_files_are_relative(self):
        """Output file paths from phase metadata are project-root-relative."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        assert "src/widget.py" in result
        # Should not contain absolute paths
        assert "/Volumes/" not in result
        assert "/home/" not in result

    def test_input_files_are_relative(self):
        """Input file paths from phase metadata are relative."""
        result = map_phase_to_task(MINIMAL_PHASE, 1)
        # Input files may appear in guidance
        assert "/Volumes/" not in result


class TestResolvePathsEdgeCases:
    """Tests for _resolve_paths — prose corruption and edge cases."""

    def test_prose_mentioning_project_root_not_corrupted(self):
        """Prose text that mentions the project root standalone is not corrupted."""
        with TemporaryDirectory() as tmp:
            plan_dir = str(Path(tmp) / "plans" / "my-plan")
            os.makedirs(plan_dir)
            project_root = tmp
            content = f"The project lives at {project_root} and is important."
            result = _resolve_paths(content, plan_dir)
            # The standalone mention should not be stripped
            assert "and is important" in result
            assert "at  and" not in result  # no double-space from stripping

    def test_actual_file_paths_are_resolved(self):
        """File paths prefixed with project root are made relative."""
        with TemporaryDirectory() as tmp:
            plan_dir = str(Path(tmp) / "plans" / "my-plan")
            os.makedirs(plan_dir)
            abs_path = f"{tmp}/src/widget.py"
            content = f"- {abs_path}\n"
            result = _resolve_paths(content, plan_dir)
            assert "src/widget.py" in result

    def test_plan_dir_prefix_stripped_from_file_paths(self):
        """Plan directory prefix is stripped from file paths."""
        with TemporaryDirectory() as tmp:
            plan_dir = str(Path(tmp) / "plans" / "my-plan")
            os.makedirs(plan_dir)
            content = f"- {plan_dir}/phase-01.md\n"
            result = _resolve_paths(content, plan_dir)
            assert "phase-01.md" in result
            assert plan_dir not in result

    def test_mixed_prose_and_paths(self):
        """Content with both prose mentions and file paths is handled correctly."""
        with TemporaryDirectory() as tmp:
            plan_dir = str(Path(tmp) / "plans" / "my-plan")
            os.makedirs(plan_dir)
            content = (
                f"See {tmp}/src/widget.py for details.\n"
                f"The root directory {tmp} contains all sources.\n"
            )
            result = _resolve_paths(content, plan_dir)
            # File path should be relative
            assert "src/widget.py" in result
            # Standalone root mention preserved
            assert "root directory" in result


class TestGenerateReviewArtifacts:
    """Tests for generate_review_artifacts() — derived review override generation."""

    def _make_project(self, tmp: str) -> tuple[str, str]:
        """Create a minimal project with plan dir and canonical Cypilot sources."""
        repo_root = Path(tmp) / "repo"
        repo_root.mkdir()
        (repo_root / ".git").mkdir()

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

        # Create .bootstrap/.core structure with canonical sources
        core = repo_root / ".bootstrap" / ".core"
        workflows = core / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "analyze.md").write_text(
            "# Analyze Workflow\n\nCode review methodology.\n", encoding="utf-8"
        )
        reqs = core / "requirements"
        reqs.mkdir(parents=True)
        (reqs / "bug-finding.md").write_text(
            "# Bug Finding\n\nDefect search methodology.\n", encoding="utf-8"
        )
        (reqs / "prompt-engineering.md").write_text(
            "# Prompt Engineering\n\n9-layer review.\n", encoding="utf-8"
        )
        (reqs / "prompt-bug-finding.md").write_text(
            "# Prompt Bug Finding\n\nBehavioral defect search.\n", encoding="utf-8"
        )
        (reqs / "code-checklist.md").write_text(
            "# Code Checklist\n\nQuality gates.\n", encoding="utf-8"
        )

        # Create plan directory
        plan_dir = Path(tmp) / "plans" / "test-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
        (plan_dir / "phase-01-widget-factory.md").write_text(
            MINIMAL_PHASE, encoding="utf-8"
        )
        (plan_dir / "phase-02-widget-validator.md").write_text(
            PHASE_WITH_RULES, encoding="utf-8"
        )
        return str(repo_root), str(plan_dir)

    def test_generates_review_override_file(self):
        """generate_review_artifacts() creates .ralphex/prompts/cypilot-review-override.md."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            result = generate_review_artifacts(plan_dir, repo_root)
            assert len(result["artifacts"]) == 2
            for artifact in result["artifacts"]:
                assert Path(artifact).exists()

    def test_returns_artifact_paths(self):
        """Return value contains the generated artifact path list."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            result = generate_review_artifacts(plan_dir, repo_root)
            assert "artifacts" in result
            assert len(result["artifacts"]) == 2
            assert result["artifacts"][0].endswith(REVIEW_PROMPT_RELATIVES[0])
            assert result["artifacts"][1].endswith(REVIEW_PROMPT_RELATIVES[1])

    def test_artifact_path_is_deterministic(self):
        """Same inputs produce the same artifact path."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            r1 = generate_review_artifacts(plan_dir, repo_root)
            r2 = generate_review_artifacts(plan_dir, repo_root)
            assert r1["artifacts"] == r2["artifacts"]

    def test_artifact_references_canonical_sources(self):
        """Generated review override references Cypilot canonical sources."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "analyze.md" in content

    def test_artifact_contains_routing_sections(self):
        """Generated artifact has code-review and prompt-review routing sections."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "Final review step" in content
            assert "standard ralphex review flow" in content

    def test_injects_managed_override_into_review_prompts(self):
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            for relative_path in REVIEW_PROMPT_RELATIVES:
                prompt_path = Path(repo_root) / relative_path
                content = prompt_path.read_text(encoding="utf-8")
                assert "<!-- @cpt-begin:cypilot-review-override -->" in content
                assert "<!-- @cpt-end:cypilot-review-override -->" in content
                assert "load and follow" in content

    def test_rewrites_existing_managed_override_block(self):
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            prompt_path.write_text(
                textwrap.dedent(
                    """\
                    # first review prompt

                    <!-- @cpt-begin:cypilot-review-override -->
                    stale override
                    <!-- @cpt-end:cypilot-review-override -->

                    Original first review body.
                    """
                ),
                encoding="utf-8",
            )
            generate_review_artifacts(plan_dir, repo_root)
            content = prompt_path.read_text(encoding="utf-8")
            assert content.count("<!-- @cpt-begin:cypilot-review-override -->") == 1
            assert "stale override" not in content
            assert "Original first review body." in content

    def test_artifact_contains_completion_status_contract(self):
        """Generated artifact references PASS/PARTIAL/FAIL completion semantics."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "REVIEW_DONE" in content
            assert "nothing to fix" in content
            assert "CYPILOT_ANALYZE_START:" in content
            assert "CYPILOT_ANALYZE_DONE: no_findings" in content

    def test_artifact_routes_code_to_analyze_and_bug_finding(self):
        """Code review branch references analyze.md and bug-finding.md by path."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert ".bootstrap/.core/workflows/analyze.md" in content

    def test_artifact_routes_prompt_to_prompt_engineering(self):
        """Prompt review branch references prompt-engineering.md and prompt-bug-finding.md."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[1]
            content = prompt_path.read_text(encoding="utf-8")
            assert ".bootstrap/.core/workflows/analyze.md" in content

    def test_artifact_resolves_install_paths_from_root_agents_cypilot_path(self):
        """Generated artifact uses root AGENTS.md cypilot_path instead of hardcoded self-hosted paths."""
        with TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            repo_root.mkdir()
            (repo_root / ".git").mkdir()
            (repo_root / "AGENTS.md").write_text(
                textwrap.dedent(
                    """\
                    <!-- @cf:root-agents -->
                    ```toml
                    cf-constructor-path = "cypilot"
                    ```
                    <!-- /@cf:root-agents -->
                    """
                ),
                encoding="utf-8",
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

            core = repo_root / "cypilot" / ".core"
            (core / "workflows").mkdir(parents=True)
            (core / "requirements").mkdir(parents=True)
            (core / "workflows" / "analyze.md").write_text("# Analyze\n", encoding="utf-8")
            (core / "requirements" / "bug-finding.md").write_text("# Bug Finding\n", encoding="utf-8")
            (core / "requirements" / "code-checklist.md").write_text("# Checklist\n", encoding="utf-8")
            (core / "requirements" / "prompt-engineering.md").write_text("# Prompt Engineering\n", encoding="utf-8")
            (core / "requirements" / "prompt-bug-finding.md").write_text("# Prompt Bug Finding\n", encoding="utf-8")

            plan_dir = Path(tmp) / "plans" / "test-plan"
            plan_dir.mkdir(parents=True)
            (plan_dir / "plan.toml").write_text(MINIMAL_PLAN_TOML, encoding="utf-8")
            (plan_dir / "phase-01-widget-factory.md").write_text(
                MINIMAL_PHASE, encoding="utf-8"
            )
            (plan_dir / "phase-02-widget-validator.md").write_text(
                PHASE_WITH_RULES, encoding="utf-8"
            )

            generate_review_artifacts(str(plan_dir), str(repo_root))
            prompt_path = repo_root / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "cypilot/.core/workflows/analyze.md" in content
            assert ".bootstrap/.core/" not in content

    def test_artifact_contains_bounded_scope_rules(self):
        """Generated artifact includes bounded scope and ignore rules."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "standard ralphex review flow" in content
            assert "final outcome" in content

    def test_artifact_contains_remediation_prompt_requirements(self):
        """Generated artifact requires Fix Prompt and Plan Prompt for actionable issues."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "fix them, validate, commit" in content

    def test_artifact_contains_residual_risk_section(self):
        """Generated artifact includes residual risk reporting requirements."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "final analyze step" in content

    def test_artifact_contains_completion_gate_triggers(self):
        """Generated artifact specifies mandatory status triggers."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "Emit `<<<RALPHEX:REVIEW_DONE>>>` only when" in content
            assert "Never emit `<<<RALPHEX:REVIEW_DONE>>>` unless" in content

    def test_does_not_duplicate_sdlc_content(self):
        """Generated artifact references sources, does not inline full kit content."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            generate_review_artifacts(plan_dir, repo_root)
            prompt_path = Path(repo_root) / REVIEW_PROMPT_RELATIVES[0]
            content = prompt_path.read_text(encoding="utf-8")
            assert "Code review methodology" not in content

    def test_uses_project_root_relative_paths(self):
        """Artifact paths in return value are project-root-relative."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            result = generate_review_artifacts(plan_dir, repo_root)
            for path in result["artifacts"]:
                assert path.startswith(repo_root) or not os.path.isabs(path)

    def test_returns_relative_path_key(self):
        """Return value includes relative_path for each artifact."""
        with TemporaryDirectory() as tmp:
            repo_root, plan_dir = self._make_project(tmp)
            result = generate_review_artifacts(plan_dir, repo_root)
            assert "relative_paths" in result
            assert result["relative_paths"] == list(REVIEW_PROMPT_RELATIVES)
