"""
Test workflow file parsing and structure validation.

Tests REAL workflow files from workflows/ directory.

Migration note (legacy multi-phase workflow removal + routing update):
- test_parse_workflow_extracts_all_sections: REWRITTEN. Previously asserted
  generate.md loaded workflows/shared/root-skill-entrypoint-bootstrap.md (deleted)
  and REQUIREd workflows/generate/phase-* fragments (deleted). generate.md is now
  a thin router; re-grounded on its GenerateBootstrap/GenerateRoute/GenerateNoMatch
  UNITs and the "NEVER load or run any legacy generate phase logic" rule.
- test_workflows_continue_root_skill_entrypoint_bootstrap: REWRITTEN. The shared
  root-skill-entrypoint-bootstrap.md was deleted, so the old check passed vacuously
  (masking). Re-grounded on the per-router Bootstrap UNITs (GenerateBootstrap /
  AnalyzeBootstrap) that own their runtime prerequisite loads without CFS_INIT.
- test_root_skill_entrypoint_bootstrap_has_fail_closed_unit: REWRITTEN. The shared
  bootstrap file was deleted; the entrypoint prerequisite gate now lives in
  skills/studio/SKILL.md UNIT SessionInit (REQUIRE {cf-studio-path} resolved before
  any LOAD), with workflow-specific rule loading kept in concrete workflows.
- test_generate_workflow_has_template_resolution: REWRITTEN to
  test_runtime_modules_have_template_var_resolution. generate.md no longer does
  template/artifact resolution; template resolution is owned by the runtime
  template-vars module, which loads command-resolution before resolve-vars.
- test_validate_all_workflows_have_required_structure: KEPT; removed the deleted
  pdsl.md from the no-steps exemption set.
"""
try:
    import pytest  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class _PytestShim:
        @staticmethod
        def fail(message: str = "") -> None:
            raise AssertionError(message)

    pytest = _PytestShim()  # type: ignore
from pathlib import Path


LOAD_DIRECTIVE_RE = __import__("re").compile(
    r"LOAD \{cf-studio-path\}/\.core/"
    r"(skills/studio/(?:modules|agents)/[A-Za-z0-9_./-]+\.md|workflows/[A-Za-z0-9_./-]+\.md)"
)


def _workflow_contract_text(root: Path, workflow_name: str) -> str:
    seen: set[Path] = set()

    def _collect(path: Path) -> list[str]:
        if path in seen or not path.is_file():
            return []
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        parts = [text]
        for rel in LOAD_DIRECTIVE_RE.findall(text):
            parts.extend(_collect(root / rel))
        return parts

    return "\n".join(_collect(root / "workflows" / workflow_name))


def test_parse_workflow_extracts_all_sections():
    """Parse the REAL generate.md thin router and verify its structure."""
    workflows_dir = Path(__file__).parent.parent / "workflows"
    assert workflows_dir.exists(), "workflows/ directory not found"

    # generate.md is now a thin router (the legacy multi-phase workflow was retired).
    workflow_path = workflows_dir / "generate.md"
    assert workflow_path.exists(), f"{workflow_path} not found"

    content = _workflow_contract_text(workflows_dir.parent, "generate.md")

    # It uses PDSL fenced blocks with the router UNITs.
    assert "```pdsl" in content, "generate.md should use ```pdsl fenced blocks"
    for unit in ("UNIT GenerateBootstrap", "UNIT GenerateRoute", "UNIT GenerateNoMatch"):
        assert unit in content, f"generate.md: missing {unit}"

    # And it must explicitly forbid the deleted legacy phase logic.
    assert "NEVER load or run any legacy generate phase logic" in content, (
        "generate.md must forbid legacy multi-phase logic"
    )


def test_validate_all_workflows_have_required_structure():
    """Validate ALL workflow files have required sections."""
    workflows_dir = Path(__file__).parent.parent / "workflows"
    assert workflows_dir.exists(), "workflows/ directory not found"

    # Get all workflow markdown files, excluding non-workflow files
    all_files = list(workflows_dir.glob("*.md"))
    # Exclude non-workflow files
    exclude_files = {'README.md', 'AGENTS.md'}
    workflow_files = [f for f in all_files if f.name not in exclude_files]
    assert len(workflow_files) > 0, "No workflow files found"

    # Thin pass-through workflows have no numbered steps structure
    no_steps_allowed = {'explain.md', 'auto-config.md', 'brainstorm.md', 'studio.md'}

    errors = []

    for workflow_path in workflow_files:
        content = workflow_path.read_text(encoding='utf-8')

        # All workflows must have type: workflow frontmatter
        if 'type: workflow' not in content:
            errors.append(f"{workflow_path.name}: Missing type: workflow frontmatter")

        # All workflows must have some executable structure: legacy headings
        # or current PDSL-style UNIT blocks.
        if workflow_path.name not in no_steps_allowed:
            has_steps = any(s in content for s in ['## Steps', '## Step', '## Phase', '\nUNIT '])
            if not has_steps:
                errors.append(f"{workflow_path.name}: Missing Steps/Phase/UNIT section")

        # All workflows must have cf: true frontmatter (or legacy cf-constructor: true)
        if 'cf: true' not in content and 'cf-constructor: true' not in content:
            errors.append(f"{workflow_path.name}: Missing cf: true frontmatter")

    if errors:
        pytest.fail(f"Workflow structure validation failed:\n" + "\n".join(errors))


def test_workflows_continue_root_skill_entrypoint_bootstrap():
    """Top-level routers must own runtime prerequisites without requiring CFS_INIT.

    The shared root-skill-entrypoint-bootstrap.md was removed; the equivalent
    behavior is now per-router Bootstrap UNITs that load command-resolution,
    workflow-resolution, and git-commit-mode directly before routing work.
    """
    workflows_dir = Path(__file__).parent.parent / "workflows"

    routers = {
        "generate.md": ("UNIT GenerateBootstrap", "CONTINUE GenerateRoute", "GenerateRoute"),
        "analyze.md": ("UNIT AnalyzeBootstrap", "CONTINUE AnalyzeRoute", "AnalyzeRoute"),
    }

    missing = []
    for name, (bootstrap_unit, continue_route, route_unit) in routers.items():
        content = (workflows_dir / name).read_text(encoding="utf-8")
        if bootstrap_unit not in content:
            missing.append(f"{name}: {bootstrap_unit}")
        if "modules/runtime/command-resolution.md" not in content:
            if "RUN WorkflowBootstrapCommandWorkflowResolution" not in content:
                missing.append(f"{name}: command-resolution load")
        if "modules/runtime/workflow-resolution.md" not in content:
            if "RUN WorkflowBootstrapCommandWorkflowResolution" not in content:
                missing.append(f"{name}: workflow-resolution load")
        if "modules/subagents/git-commit-mode.md" not in content:
            if "RUN WorkflowBootstrapRouterPrelude" not in content:
                missing.append(f"{name}: git-commit-mode load")
        if "RUN CommandResolution to resolve {cfs_cmd}" not in content:
            if "RUN WorkflowBootstrapCommandWorkflowResolution" not in content:
                missing.append(f"{name}: CommandResolution run")
        if continue_route not in content:
            missing.append(f"{name}: {continue_route}")
        if "NEVER require cf or CFS_INIT before routing" not in content:
            missing.append(f"{name}: no CFS_INIT requirement removal")
        if "REQUIRE WorkflowResolution is loaded" not in content:
            missing.append(f"{name}: {route_unit} requires WorkflowResolution")

    assert not missing, "Router bootstrap prerequisite contract missing: " + ", ".join(missing)


def test_root_skill_entrypoint_bootstrap_has_fail_closed_unit():
    """The session entrypoint must resolve cf-studio-path before runtime loads.

    Re-grounded from the deleted workflows/shared/root-skill-entrypoint-bootstrap.md
    onto skills/studio/SKILL.md UNIT SessionInit, which requires {cf-studio-path}
    is resolved before any LOAD and delegates workflow-specific gates to concrete
    workflows instead of reviving LoadCfSkillConfirm.
    """
    skill_path = Path(__file__).parent.parent / "skills" / "studio" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert "UNIT SessionInit" in content
    assert "REQUIRE {cf-studio-path} is resolved before any LOAD below" in content
    assert "modules/runtime/command-resolution.md" in content
    assert "modules/runtime/workflow-resolution.md" in content
    assert "modules/routing/root-intent-routing.md" in content
    assert "RUN CommandResolution to resolve {cfs_cmd}" in content
    assert "CONTINUE IntentRouting" in content
    assert "NEVER invoke a selected workflow" in content
    assert "ALWAYS keep workflow-specific prerequisite loading inside the selected workflow" in content
    assert "MENU LoadCfSkillConfirm" not in content

    generate = (Path(__file__).parent.parent / "workflows" / "generate.md").read_text(encoding="utf-8")
    assert "MENU LoadCfSkillConfirm" not in generate
    assert "NEVER require cf or CFS_INIT before routing" in generate


def test_runtime_modules_have_template_var_resolution():
    """Template-variable resolution is lazy-loaded from the runtime module.

    Re-grounded from the deleted multi-phase generate template-resolution logic
    onto the standalone template-vars module plus concrete workflows that load it
    before resolving templated paths.
    """
    root = Path(__file__).parent.parent
    command_resolution = (
        root / "skills" / "studio" / "modules" / "runtime" / "command-resolution.md"
    ).read_text(encoding="utf-8")
    module = (
        root / "skills" / "studio" / "modules" / "runtime" / "template-vars.md"
    ).read_text(encoding="utf-8")

    assert "UNIT CommandResolution" in command_resolution
    assert "ALWAYS resolve {cfs_cmd} before invoking any cfs command" in command_resolution
    assert "UNIT TemplateVarResolution" in module
    assert "modules/runtime/command-resolution.md" in module
    assert "RUN CommandResolution to resolve {cfs_cmd} WHEN {cfs_cmd} is unset" in module
    assert "resolve-vars" in module, "TemplateVarResolution should use {cfs_cmd} resolve-vars"
    assert "template variable" in module.lower(), "module should reference template variables"

    template_helpers = (
        "RUN WorkflowBootstrapCommandTemplateContext",
        "RUN WorkflowBootstrapDispatchTemplateContext",
        "RUN WorkflowBootstrapCommandDispatchTemplateContext",
    )
    for workflow_name in ("auto-config.md", "kit.md", "plan.md", "workspace.md", "map.md"):
        root_workflow = (root / "workflows" / workflow_name).read_text(encoding="utf-8")
        workflow = _workflow_contract_text(root, workflow_name)
        assert "modules/runtime/template-vars.md" in workflow or any(
            helper in root_workflow for helper in template_helpers
        )
