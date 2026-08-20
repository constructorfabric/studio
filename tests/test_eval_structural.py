"""Tests for the deterministic ``StructuralScorer`` (utils.eval_structural)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from studio.utils.eval_harness import (RunArtifacts, Scenario, ScorerKind,
                                       VERDICT_FAIL, VERDICT_PASS, VERDICT_UNKNOWN)
from studio.utils.eval_structural import CHECKS, StructuralScorer, _capped


# --- fixture builders ------------------------------------------------------

def _phase_body(number: int, total: int, *, depends_on: Optional[List[int]] = None,
                outputs: bool = True,
                sections: Tuple[str, ...] = ("Preamble", "What", "Rules")) -> str:
    """A phase file body with a valid ``[phase]`` frontmatter block and ``##`` sections."""
    lines = ["```toml", "[phase]", f"number = {number}", f"total = {total}",
             f"depends_on = {depends_on if depends_on is not None else []}"]
    if outputs:
        lines.append('output_files = ["step.out"]')
    lines += ["```", "", f"# Phase {number}", ""]
    for section in sections:
        lines += [f"## {section}", "", "body", ""]
    return "\n".join(lines)


def _run(plan_meta: Optional[Dict[str, object]] = None,
         manifest_phases: Optional[List[Dict[str, object]]] = None,
         phase_texts: Optional[Dict[str, str]] = None) -> RunArtifacts:
    """A compliant two-phase run by default; callers override one piece to craft a defect."""
    if phase_texts is None:
        phase_texts = {"phase-1.md": _phase_body(1, 2),
                       "phase-2.md": _phase_body(2, 2, depends_on=[1])}
    if manifest_phases is None:
        manifest_phases = [{"number": 1, "file": "phase-1.md"},
                           {"number": 2, "file": "phase-2.md"}]
    if plan_meta is None:
        plan_meta = {"task": "t", "total_phases": len(manifest_phases)}
    return RunArtifacts(plan_meta=plan_meta, phases=manifest_phases, phase_texts=phase_texts)


def _scenario(workflow: str = "coding-gen") -> Scenario:
    return Scenario(id="s", workflow=workflow, run_dir=Path("run"), expect="compliant")


def _score(run: Optional[RunArtifacts], **kwargs):
    return StructuralScorer(**kwargs).score(run, _scenario())


def _findings_for(run: RunArtifacts) -> Dict[str, str]:
    """Map failed check name -> its finding string, for asserting exactly which check tripped."""
    result = _score(run)
    return {finding.split(":", 1)[0]: finding for finding in result.findings}


# --- the happy path + the two UNKNOWN gates --------------------------------

def test_fully_compliant_run_passes_100() -> None:
    result = _score(_run())
    assert result.verdict == VERDICT_PASS
    assert result.score_pct == 100.0
    assert result.findings == []
    assert result.kind is ScorerKind.DETERMINISTIC


def test_run_none_is_unknown_not_zero() -> None:
    result = _score(None)
    assert result.verdict == VERDICT_UNKNOWN
    assert result.score_pct is None


def test_no_parseable_frontmatter_is_unknown() -> None:
    # A different workflow shape (plain markdown phases) is unscoreable, never a 0.
    run = _run(phase_texts={"phase-1.md": "# Phase 1\n\nNo frontmatter here.\n"})
    result = _score(run)
    assert result.verdict == VERDICT_UNKNOWN
    assert result.score_pct is None


# --- one crafted known-bad per check ---------------------------------------

def test_phase_numbers_unique_fails_on_duplicate() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2),
                            "phase-1-copy.md": _phase_body(1, 2)})
    # Two files both declare phase 1 → duplicate; the manifest still lists 1 & 2.
    assert "phase-numbers-unique" in _findings_for(run)


def test_manifest_present_fails_when_manifest_lists_no_phase() -> None:
    run = _run(manifest_phases=[])           # [plan] present, but no [[phases]] entries
    assert "manifest-present" in _findings_for(run)


def test_manifest_total_matches_entries_fails_on_mismatch() -> None:
    run = _run(plan_meta={"task": "t", "total_phases": 5})   # says 5, lists 2
    assert "manifest-total-matches-entries" in _findings_for(run)


def test_manifest_matches_files_fails_when_sets_differ() -> None:
    run = _run(manifest_phases=[{"number": 1}, {"number": 3}])   # declares {1,3}, files give {1,2}
    assert "manifest-matches-files" in _findings_for(run)


def test_numbering_contiguous_fails_on_gap() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2),
                            "phase-3.md": _phase_body(3, 2)},
               manifest_phases=[{"number": 1}, {"number": 3}],
               plan_meta={"task": "t", "total_phases": 2})
    assert "numbering-contiguous-from-1" in _findings_for(run)


def test_phase_total_consistent_fails_when_totals_disagree() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2),
                            "phase-2.md": _phase_body(2, 3, depends_on=[1])})   # 2 vs 3
    assert "phase-total-consistent" in _findings_for(run)


def test_phase_total_matches_count_fails_when_total_wrong() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 9),
                            "phase-2.md": _phase_body(2, 9, depends_on=[1])})   # total 9, count 2
    assert "phase-total-matches-count" in _findings_for(run)


def test_dependencies_resolve_fails_on_missing_target() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2),
                            "phase-2.md": _phase_body(2, 2, depends_on=[7])})   # 7 does not exist
    assert "dependencies-resolve" in _findings_for(run)


def test_dependencies_not_forward_fails_on_forward_dep() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, depends_on=[2]),   # forward
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])})
    assert "dependencies-not-forward" in _findings_for(run)


def test_every_phase_declares_output_fails_when_missing() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, outputs=False),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])})
    assert "every-phase-declares-an-output" in _findings_for(run)


def test_required_sections_fails_when_section_missing() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, sections=("Preamble", "What")),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])})   # phase 1 lacks Rules
    assert "required-sections-present" in _findings_for(run)


def test_heading_inside_frontmatter_does_not_satisfy_required_sections() -> None:
    # A '## Rules' line inside the TOML frontmatter must NOT count as the real Markdown section.
    body = ('```toml\n[phase]\nnumber = 1\ntotal = 1\noutput_files = ["x"]\n'
            'notes = """\n## Rules\ninside the toml block, not a real section\n"""\n```\n\n'
            '## Preamble\n\nx\n\n## What\n\nx\n')   # no real ## Rules in the body
    run = _run(phase_texts={"phase-1.md": body},
               manifest_phases=[{"number": 1}], plan_meta={"task": "t", "total_phases": 1})
    finding = _findings_for(run)["required-sections-present"]
    assert "Rules" in finding


def test_heading_inside_a_code_fence_does_not_satisfy_required_sections() -> None:
    # '## Rules' inside a fenced code block is a sample, not a real heading — must not count.
    body = ('```toml\n[phase]\nnumber = 1\ntotal = 1\noutput_files = ["x"]\n```\n\n'
            '## Preamble\n\nx\n\n## What\n\n'
            '```\n## Rules\nthis is a code sample, not a real section\n```\n')
    run = _run(phase_texts={"phase-1.md": body},
               manifest_phases=[{"number": 1}], plan_meta={"task": "t", "total_phases": 1})
    finding = _findings_for(run)["required-sections-present"]
    assert "Rules" in finding


def test_a_single_defect_leaves_the_other_checks_passing() -> None:
    # The forward-dep fixture must trip exactly one check, not cascade into others.
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, depends_on=[2]),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])})
    result = _score(run)
    assert result.verdict == VERDICT_FAIL
    assert list(_findings_for(run)) == ["dependencies-not-forward"]
    assert result.score_pct == round((len(CHECKS) - 1) / len(CHECKS) * 100, 2)


def test_invalid_phase_file_is_flagged_not_silently_dropped() -> None:
    # phase-2 is present but declares an invalid number; the manifest lists only phase 1, so
    # no other check catches it. phase-frontmatter-valid must fail — no vacuous pass.
    run = _run(
        phase_texts={"phase-1.md": _phase_body(1, 1),
                     "phase-2.md": _phase_body(2, 1).replace("number = 2", "number = 0")},
        manifest_phases=[{"number": 1, "file": "phase-1.md"}],
        plan_meta={"task": "t", "total_phases": 1})
    result = _score(run)
    assert result.verdict == VERDICT_FAIL
    assert "phase-frontmatter-valid" in _findings_for(run)


def test_unparseable_phase_file_alongside_a_valid_one_fails() -> None:
    # A present-but-frontmatter-less phase file must be retained and flagged, not dropped.
    run = _run(
        phase_texts={"phase-1.md": _phase_body(1, 1),
                     "phase-2.md": "# Phase 2\n\nno frontmatter block here\n"},
        manifest_phases=[{"number": 1, "file": "phase-1.md"}],
        plan_meta={"task": "t", "total_phases": 1})
    assert "phase-frontmatter-valid" in _findings_for(run)


def test_manifest_duplicate_number_is_flagged() -> None:
    run = _run(manifest_phases=[{"number": 1}, {"number": 1}, {"number": 2}],
               plan_meta={"task": "t", "total_phases": 2})
    assert "manifest-numbers-unique" in _findings_for(run)


# --- registry: skip by name and by tag -------------------------------------

def test_skip_by_name_removes_a_check() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, depends_on=[2]),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])})
    result = _score(run, skip=("dependencies-not-forward",))
    assert result.verdict == VERDICT_PASS      # the only failing check was skipped
    assert result.score_pct == 100.0


def test_skip_by_tag_removes_a_family() -> None:
    run = _run(manifest_phases=[])             # trips manifest-present (a "manifest" check)
    result = _score(run, skip=("manifest",))
    assert result.verdict == VERDICT_PASS


def test_skipping_every_check_is_unknown_not_pass() -> None:
    all_tags = {tag for check in CHECKS for tag in check.tags}
    result = _score(_run(), skip=tuple(all_tags))
    assert result.verdict == VERDICT_UNKNOWN
    assert result.score_pct is None


# --- per-workflow required sections ----------------------------------------

def test_verification_workflow_does_not_require_rules() -> None:
    # A "verify" workflow legitimately omits ## Rules — that must not be a false-fail.
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, sections=("Preamble", "What")),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1],
                                                      sections=("Preamble", "What"))})
    result = StructuralScorer().score(run, _scenario(workflow="verify"))
    assert result.verdict == VERDICT_PASS


# --- detail is preserved in the finding ------------------------------------

def test_finding_detail_names_the_offending_phase() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2, depends_on=[2]),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])})
    finding = _findings_for(run)["dependencies-not-forward"]
    assert "phase 1 -> 2" in finding


def test_malformed_toml_block_scores_fail_not_unknown() -> None:
    # A phase that *has* a ```toml block but broken TOML is a failing run, not a different
    # shape — it must score FAIL, never hide as UNKNOWN.
    run = _run(phase_texts={"phase-1.md": "```toml\nthis is = = broken !!!\n```\n\n# P\n"})
    result = _score(run)
    assert result.verdict == VERDICT_FAIL
    assert "phase-frontmatter-valid" in result.findings[0]


def test_present_but_invalid_phase_number_scores_fail() -> None:
    # A [phase] block that parses but declares number = 0 is broken → FAIL, not UNKNOWN.
    body = ('```toml\n[phase]\nnumber = 0\ntotal = 1\noutput_files = ["x"]\n```\n\n'
            "## Preamble\n\nx\n\n## What\n\nx\n\n## Rules\n\nx\n")
    result = _score(_run(phase_texts={"phase-1.md": body}))
    assert result.verdict == VERDICT_FAIL


def test_no_frontmatter_block_at_all_is_unknown() -> None:
    # No ```toml block anywhere → a genuinely different workflow shape → UNKNOWN, not FAIL.
    run = _run(phase_texts={"phase-1.md": "# Phase 1\n\njust prose, no fenced block\n"})
    result = _score(run)
    assert result.verdict == VERDICT_UNKNOWN
    assert result.score_pct is None


def test_non_integer_dependency_is_unresolved() -> None:
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2),
                            "phase-2.md": _phase_body(2, 2, depends_on=["one"])})
    assert "dependencies-resolve" in _findings_for(run)


def test_non_list_depends_on_is_unresolved() -> None:
    # A scalar depends_on is a malformed declaration; it must fail, not vacuously pass.
    body = ('```toml\n[phase]\nnumber = 2\ntotal = 2\ndepends_on = "one"\n'
            'output_files = ["x"]\n```\n\n## Preamble\n\nx\n\n## What\n\nx\n\n## Rules\n\nx\n')
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2), "phase-2.md": body})
    finding = _findings_for(run)["dependencies-resolve"]
    assert "must be an array" in finding


def test_absent_depends_on_is_treated_as_no_dependencies() -> None:
    # A phase that omits depends_on entirely has no dependency problems (absent != malformed).
    body = ('```toml\n[phase]\nnumber = 1\ntotal = 1\noutput_files = ["x"]\n```\n\n'
            '## Preamble\n\nx\n\n## What\n\nx\n\n## Rules\n\nx\n')
    run = _run(phase_texts={"phase-1.md": body},
               manifest_phases=[{"number": 1}], plan_meta={"task": "t", "total_phases": 1})
    assert _score(run).verdict == VERDICT_PASS


@pytest.mark.parametrize("bad_total", ["oops", None])
def test_unparseable_phase_total_is_handled_not_crashed(bad_total: object) -> None:
    # A non-integer `total` must degrade the consistency checks, never raise.
    body = ("```toml\n[phase]\nnumber = 1\n"
            + (f'total = "{bad_total}"\n' if bad_total is not None else "")
            + 'depends_on = []\noutput_files = ["x"]\n```\n\n'
            "## Preamble\n\nx\n\n## What\n\nx\n\n## Rules\n\nx\n")
    result = _score(_run(phase_texts={"phase-1.md": body},
                         manifest_phases=[{"number": 1}],
                         plan_meta={"task": "t", "total_phases": 1}))
    assert result.verdict == VERDICT_FAIL          # inconsistent total, but no crash


# --- ainetx review remediations --------------------------------------------

def test_manifest_number_to_file_pairing_is_checked_not_just_the_set() -> None:
    # Files declare 1 and 2, but the manifest swaps which file carries which number: set-equal
    # yet the pairing is wrong, so manifest-matches-files must still fail.
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2),
                            "phase-2.md": _phase_body(2, 2, depends_on=[1])},
               manifest_phases=[{"number": 1, "file": "phase-2.md"},
                                {"number": 2, "file": "phase-1.md"}])
    finding = _findings_for(run)["manifest-matches-files"]
    assert "declares" in finding or "pairs" in finding


@pytest.mark.parametrize("typo", ["dependsOn", "depend_on", "dependencies"])
def test_misspelled_depends_on_key_is_flagged(typo: str) -> None:
    # A typo'd dependency key must be reported, not silently read as "no dependencies".
    body = (f'```toml\n[phase]\nnumber = 2\ntotal = 2\n{typo} = [1]\n'
            'output_files = ["x"]\n```\n\n## Preamble\n\nx\n\n## What\n\nx\n\n## Rules\n\nx\n')
    run = _run(phase_texts={"phase-1.md": _phase_body(1, 2), "phase-2.md": body})
    assert "misspelled depends_on" in _findings_for(run)["dependencies-resolve"]


def test_malformed_manifest_entry_is_flagged() -> None:
    # A [[phases]] entry with a non-integer number is malformed — other manifest checks drop it
    # quietly, so manifest-entries-valid must surface it.
    run = _run(manifest_phases=[{"number": 1, "file": "phase-1.md"},
                                {"number": 2, "file": "phase-2.md"},
                                {"number": "bad", "file": "x.md"}],
               plan_meta={"task": "t", "total_phases": 2})
    assert "manifest-entries-valid" in _findings_for(run)


def test_leading_bom_frontmatter_still_parses() -> None:
    run = _run(phase_texts={"phase-1.md": "﻿" + _phase_body(1, 1)},
               manifest_phases=[{"number": 1, "file": "phase-1.md"}],
               plan_meta={"task": "t", "total_phases": 1})
    assert _score(run).verdict == VERDICT_PASS     # a BOM is tolerated, not a false UNKNOWN


def test_unrecognized_skip_token_warns(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        StructuralScorer(skip=("no-such-check-or-tag",))
    assert "unrecognized" in caplog.text


def test_capped_reports_the_remaining_count() -> None:
    assert _capped(["a", "b", "c", "d"], 3) == "a; b; c (+1 more)"
    assert _capped(["a", "b"], 3) == "a; b"        # no "(+N more)" when nothing is hidden


def test_registry_check_names_are_unique() -> None:
    names = [check.name for check in CHECKS]
    assert len(names) == len(set(names))


def test_registry_check_names_contain_no_colon() -> None:
    # Findings serialise as "name: detail"; a colon in a name would break that contract.
    assert all(":" not in check.name for check in CHECKS)
