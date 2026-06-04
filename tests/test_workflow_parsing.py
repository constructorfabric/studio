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
  AnalyzeBootstrap) that fail-closed until the cf skill is loaded (CFS_INIT == true).
- test_root_skill_entrypoint_bootstrap_has_fail_closed_unit: REWRITTEN. The shared
  bootstrap file was deleted; the fail-closed entrypoint gate now lives in
  skills/studio/SKILL.md UNIT SessionInit (REQUIRE {cf-studio-path} resolved before
  any LOAD) and the routers' LoadCfSkillConfirm menu (2 stop -> STOP_TURN).
- test_generate_workflow_has_template_resolution: REWRITTEN to
  test_root_skill_has_template_var_resolution. generate.md no longer does
  template/artifact resolution; that behavior moved to skills/studio/SKILL.md
  UNIT TemplateVarResolution (+ CommandResolution / resolve-vars).
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


def test_parse_workflow_extracts_all_sections():
    """Parse the REAL generate.md thin router and verify its structure."""
    workflows_dir = Path(__file__).parent.parent / "workflows"
    assert workflows_dir.exists(), "workflows/ directory not found"

    # generate.md is now a thin router (the legacy multi-phase workflow was retired).
    workflow_path = workflows_dir / "generate.md"
    assert workflow_path.exists(), f"{workflow_path} not found"

    content = workflow_path.read_text(encoding="utf-8")

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
    """Top-level routers must fail closed until the cf skill is loaded.

    The shared root-skill-entrypoint-bootstrap.md was removed; the equivalent
    behavior is now a per-router Bootstrap UNIT that requires CFS_INIT == true
    before any routing work.
    """
    workflows_dir = Path(__file__).parent.parent / "workflows"

    routers = {
        "generate.md": ("UNIT GenerateBootstrap", "CONTINUE GenerateRoute"),
        "analyze.md": ("UNIT AnalyzeBootstrap", "CONTINUE AnalyzeRoute"),
    }

    missing = []
    for name, (bootstrap_unit, continue_route) in routers.items():
        content = (workflows_dir / name).read_text(encoding="utf-8")
        if bootstrap_unit not in content:
            missing.append(f"{name}: {bootstrap_unit}")
        if "CFS_INIT == true" not in content:
            missing.append(f"{name}: CFS_INIT gate")
        if continue_route not in content:
            missing.append(f"{name}: {continue_route}")

    assert not missing, "Router bootstrap gate missing: " + ", ".join(missing)


def test_root_skill_entrypoint_bootstrap_has_fail_closed_unit():
    """The session entrypoint must fail closed before doing any work.

    Re-grounded from the deleted workflows/shared/root-skill-entrypoint-bootstrap.md
    onto skills/studio/SKILL.md UNIT SessionInit, which requires {cf-studio-path}
    is resolved before any LOAD, and onto the routers' LoadCfSkillConfirm menu
    which stops the turn when the user declines to load cf.
    """
    skill_path = Path(__file__).parent.parent / "skills" / "studio" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert "UNIT SessionInit" in content
    assert "REQUIRE {cf-studio-path} is resolved before CommandResolution and before any LOAD" in content

    # Routers fail closed when the user declines to load cf.
    generate = (Path(__file__).parent.parent / "workflows" / "generate.md").read_text(encoding="utf-8")
    assert "MENU LoadCfSkillConfirm" in generate
    assert "2 stop -> STOP_TURN" in generate


def test_root_skill_has_template_var_resolution():
    """Template-variable resolution now lives in the consolidated root studio skill.

    Re-grounded from the deleted multi-phase generate template-resolution logic
    onto skills/studio/SKILL.md UNIT TemplateVarResolution.
    """
    skill_path = Path(__file__).parent.parent / "skills" / "studio" / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")

    assert "UNIT TemplateVarResolution" in content, "SKILL.md should define TemplateVarResolution"
    assert "UNIT CommandResolution" in content, "SKILL.md should define CommandResolution"
    assert "resolve-vars" in content, "TemplateVarResolution should use {cfs_cmd} resolve-vars"
    assert "template variable" in content.lower(), "SKILL.md should reference template variables"
