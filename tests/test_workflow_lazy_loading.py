"""Contract tests for lazy loading behavior in workflows/generate.md.

These tests are intentionally RED until generate.md is updated to:
- gate late workflow fragments behind explicit lazy predicates
- keep an eager minimal validation manifest language block
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATE_WORKFLOW = REPO_ROOT / "workflows" / "generate.md"
GENERATE_VALIDATION_CRITERIA = REPO_ROOT / "workflows" / "generate" / "validation-criteria.md"
GENERATE_PHASE15_AUTHOR_PLAN = REPO_ROOT / "workflows" / "generate" / "phase-1.5-author-plan.md"
GENERATE_PHASE5_INDEX = REPO_ROOT / "workflows" / "generate" / "phase-5" / "index.md"
GENERATE_PHASE6_INDEX = REPO_ROOT / "workflows" / "generate" / "phase-6" / "index.md"

LATE_FRAGMENT_RELATIVE_PATHS = (
    Path("workflows/generate/phase-1.5-author-plan.md"),
    Path("workflows/generate/phase-2-checkpoint.md"),
    Path("workflows/generate/phase-5/index.md"),
    Path("workflows/generate/phase-6/index.md"),
    Path("workflows/generate/validation-criteria.md"),
)


def _read_utf8(path: Path) -> str:
    assert path.exists(), f"Expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _is_conditionally_gated(lines: list[str], require_idx: int) -> bool:
    """Return True when REQUIRE line is nested under an IF/WHEN predicate."""
    require_line = lines[require_idx]
    require_indent = len(require_line) - len(require_line.lstrip())

    for idx in range(require_idx - 1, -1, -1):
        raw = lines[idx]
        stripped = raw.strip()

        if not stripped or stripped.startswith("//"):
            continue

        indent = len(raw) - len(raw.lstrip())

        if indent < require_indent:
            return stripped.startswith(("IF ", "WHEN ", "ELIF ", "ELSE IF "))

        if indent == require_indent:
            return False

    return False


def _contract_window(content: str, anchor: str, radius: int = 12) -> str:
    """Return an anchored line window for local predicate assertions."""
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if anchor in line:
            start = max(0, idx - radius)
            end = min(len(lines), idx + radius + 1)
            return "\n".join(lines[start:end])
    raise AssertionError(f"Expected anchor not found: {anchor}")


def test_generate_late_fragments_are_not_unconditionally_required() -> None:
    content = _read_utf8(GENERATE_WORKFLOW)
    lines = content.splitlines()

    for relative_path in LATE_FRAGMENT_RELATIVE_PATHS:
        # Related fragments should still exist; only load timing changes.
        _read_utf8(REPO_ROOT / relative_path)

        token = f"REQUIRE {{cf-studio-path}}/.core/{relative_path.as_posix()}"
        offending_indexes = [
            idx
            for idx, line in enumerate(lines)
            if line.lstrip().startswith("REQUIRE ") and token in line and not _is_conditionally_gated(lines, idx)
        ]

        assert not offending_indexes, (
            "Late fragment must not be unconditionally REQUIRED in generate.md: "
            f"{relative_path.as_posix()}"
        )


def test_generate_declares_lazy_triggers_and_eager_manifest_language() -> None:
    content = _read_utf8(GENERATE_WORKFLOW)
    lower = content.lower()

    expected_phrases = (
        "lazy-load",
        "phase 1 inputs approved",
        "first post-approval branch",
        "resumable section/state bookkeeping",
        "validation/waiver",
        "minimal validation manifest",
        "prompt_context_view",
    )

    missing = [phrase for phrase in expected_phrases if phrase not in lower]
    assert not missing, (
        "generate.md must declare explicit lazy-loading predicates and eager "
        f"minimal-validation manifest language. Missing: {missing}"
    )


def test_phase6_clean_chat_skip_is_explicitly_exempt_from_terminal_handoff_and_self_test_heading() -> None:
    """Cross-file contract: validation criteria must mirror Phase 6 clean chat-only skip."""
    phase6 = _read_utf8(GENERATE_PHASE6_INDEX).lower()
    validation = _read_utf8(GENERATE_VALIDATION_CRITERIA).lower()

    phase6_skip_tokens = (
        "skip this phase only when all are true",
        "output is chat-only",
        "no files changed",
        "remaining_findings is empty",
        "no outstanding validation or waiver decision remains",
    )
    missing_phase6_tokens = [token for token in phase6_skip_tokens if token not in phase6]
    assert not missing_phase6_tokens, (
        "Phase 6 skip contract changed; update this regression test. Missing: "
        f"{missing_phase6_tokens}"
    )

    assert "must have emitted terminal handoff menu with exactly the three canonical" in validation
    assert "### agent self-test results".lower() in validation

    expected_exemption_tokens = (
        "phase 6",
        "skip",
        "chat-only",
        "no files changed",
        "remaining_findings is empty",
        "no outstanding validation or waiver decision remains",
        "terminal handoff",
        "self-test",
    )
    missing_exemption_tokens = [
        token for token in expected_exemption_tokens if token not in validation
    ]
    assert not missing_exemption_tokens, (
        "generate/validation-criteria.md must explicitly exempt the clean "
        "chat-only Phase 6 skip path from terminal handoff and self-test heading "
        f"requirements. Missing tokens: {missing_exemption_tokens}"
    )


def test_generate_phase5_external_entry_predicate_requires_resolved_analyze_mapping() -> None:
    """Cross-file contract: generate.md lazy gate must match phase-5 external-entry preconditions."""
    generate = _read_utf8(GENERATE_WORKFLOW).lower()
    phase5 = _read_utf8(GENERATE_PHASE5_INDEX).lower()

    external_entry_contract_tokens = (
        "external entry from analyze",
        "accepted payload predicates",
        "payload shaping, and branch",
        "mapping already resolved",
    )
    missing_phase5_tokens = [token for token in external_entry_contract_tokens if token not in phase5]
    assert not missing_phase5_tokens, (
        "Phase 5 external-entry contract changed; update this regression test. Missing: "
        f"{missing_phase5_tokens}"
    )

    phase5_gate_window = _contract_window(
        generate, "workflows/generate/phase-5/index.md"
    )
    missing_generate_gate_tokens = [
        token
        for token in (
            "external analyze remediation entry",
            "accepted payload predicates",
            "branch mapping",
            "resolved",
        )
        if token not in phase5_gate_window
    ]
    assert not missing_generate_gate_tokens, (
        "generate.md Phase 5 lazy-load predicate must require analyze-side "
        "accepted payload predicates and branch mapping are already resolved. "
        f"Missing in Phase 5 gate window: {missing_generate_gate_tokens}"
    )

    payload_shaping_tokens = (
        "payload shaping",
        "mapped onto the phase 5 contract",
    )
    assert any(token in phase5_gate_window for token in payload_shaping_tokens), (
        "generate.md Phase 5 lazy-load predicate must explicitly include payload "
        "shaping/mapping onto the Phase 5 contract before loading phase-5/index.md."
    )


def test_generate_phase15_gate_requires_phase3_summary_and_no_deferral_boundary() -> None:
    """Cross-file contract: Phase 1.5 top-level gate must preserve Phase 3/no-deferral boundary."""
    generate = _read_utf8(GENERATE_WORKFLOW).lower()
    phase15 = _read_utf8(GENERATE_PHASE15_AUTHOR_PLAN).lower()

    phase15_contract_tokens = (
        "phase 3",
        "write-path selection",
        "must_not defer",
    )
    missing_phase15_tokens = [token for token in phase15_contract_tokens if token not in phase15]
    assert not missing_phase15_tokens, (
        "Phase 1.5 fragment boundary contract changed; update this regression test. Missing: "
        f"{missing_phase15_tokens}"
    )

    phase15_gate_window = _contract_window(
        generate, "workflows/generate/phase-1.5-author-plan.md"
    )
    missing_generate_phase15_gate_tokens = [
        token
        for token in (
            "phase 3 summary",
            "disk/write-path selection",
            "first post-approval branch",
        )
        if token not in phase15_gate_window
    ]
    assert not missing_generate_phase15_gate_tokens, (
        "generate.md Phase 1.5 lazy-load predicate must preserve the Phase 3 summary "
        "and no-deferral write-path boundary before loading phase-1.5-author-plan.md. "
        f"Missing in Phase 1.5 gate window: {missing_generate_phase15_gate_tokens}"
    )
