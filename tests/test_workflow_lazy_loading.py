"""Contract tests for workflows/generate.md routing behavior.

Migration note (legacy multi-phase workflow removal + routing update):
The original file held "intentionally RED" contract tests for lazy-loading the
legacy generate phase fragments:
- test_generate_late_fragments_are_not_unconditionally_required  (DELETED)
- test_generate_declares_lazy_triggers_and_eager_manifest_language  (DELETED)
- test_phase6_clean_chat_skip_is_explicitly_exempt_from_terminal_handoff_and_self_test_heading  (DELETED)
- test_generate_phase5_external_entry_predicate_requires_resolved_analyze_mapping  (DELETED)
- test_generate_phase15_gate_requires_phase3_summary_and_no_deferral_boundary  (DELETED)
Rationale: every one referenced deleted files (workflows/generate/phase-1.5-author-plan.md,
phase-2-checkpoint.md, phase-5/index.md, phase-6/index.md, validation-criteria.md). The
phase-lazy-loading contract is obsolete because generate.md is now a thin router with no
phases to lazy-load.

Replacement added:
- test_generate_is_thin_router_forbidding_legacy_phase_logic: asserts generate.md routes
  (GenerateRoute) and explicitly forbids loading/running any legacy generate phase logic,
  and that the deleted phase fragments no longer exist.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATE_WORKFLOW = REPO_ROOT / "workflows" / "generate.md"

# Phase fragments retired by the multi-phase workflow removal; must stay absent.
RETIRED_PHASE_FRAGMENTS = (
    Path("workflows/generate/phase-1.5-author-plan.md"),
    Path("workflows/generate/phase-2-checkpoint.md"),
    Path("workflows/generate/phase-5/index.md"),
    Path("workflows/generate/phase-6/index.md"),
    Path("workflows/generate/validation-criteria.md"),
)


def _read_utf8(path: Path) -> str:
    assert path.exists(), f"Expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def test_generate_is_thin_router_forbidding_legacy_phase_logic() -> None:
    """generate.md must be a thin router with no lazy-loaded legacy phases."""
    content = _read_utf8(GENERATE_WORKFLOW)

    # It is a router: it resolves and routes to cf-* skills.
    assert "UNIT GenerateRoute" in content, "generate.md must define GenerateRoute"
    assert "WorkflowResolution" in content, "generate.md must route via WorkflowResolution"

    # It must explicitly forbid the deleted multi-phase logic.
    assert "NEVER load or run any legacy generate phase logic" in content, (
        "generate.md must forbid legacy generate phase logic"
    )

    # It must not REQUIRE any phase fragment (lazily or otherwise).
    assert "workflows/generate/phase-" not in content, (
        "generate.md must not reference any legacy generate phase fragment"
    )

    # The retired phase fragments must no longer exist on disk.
    still_present = [p.as_posix() for p in RETIRED_PHASE_FRAGMENTS if (REPO_ROOT / p).exists()]
    assert not still_present, f"Retired phase fragments should be deleted: {still_present}"
