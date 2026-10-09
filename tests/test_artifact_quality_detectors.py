"""Tests for the structural artifact-quality detectors (HYP-2720 T2).

Covers the §3b A/B/C perspectives: correctness/adversarial (empty input, token floor,
self-comparison, threshold boundary), the advisory invariants (structural verdict,
severity, no edit payload), evidence being grep-verifiable, and determinism.
"""

import os
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils import artifact_quality_detectors as aqd  # noqa: E402
from studio.utils.artifact_quality import SEVERITIES  # noqa: E402

# A paragraph with well over the 12-token floor, reused where identical content is wanted.
_PARA = (
    "The passive radar subsystem correlates reflected illuminator signals against the "
    "direct reference channel to estimate bistatic range and doppler for every detected "
    "target track across the surveillance region."
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _scan(*paths: Path):
    return [(p, "feature") for p in paths]


# --- A: correctness / adversarial ------------------------------------------------

def test_no_artifacts_yields_no_findings(tmp_path: Path) -> None:
    assert aqd.detect_exact_duplication([], tmp_path) == []


def test_a_lone_section_is_never_compared_to_itself(tmp_path: Path) -> None:
    solo = _write(tmp_path, "solo.md", f"# Solo\n\n{_PARA}\n")
    assert aqd.detect_exact_duplication(_scan(solo), tmp_path) == []


def test_identical_sections_across_two_artifacts_are_flagged(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    findings = aqd.detect_exact_duplication(_scan(a, b), tmp_path)
    assert len(findings) == 1
    f = findings[0]
    assert f.detector == "duplication"
    assert {f.primary.artifact_path, f.related.artifact_path} == {"a.md", "b.md"}


def test_distinct_content_is_not_flagged(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    other = (
        "Procurement schedules the quarterly vendor review, reconciles the outstanding "
        "invoices, and publishes the approved supplier list to the finance channel."
    )
    b = _write(tmp_path, "b.md", f"# Beta\n\n{other}\n")
    assert aqd.detect_exact_duplication(_scan(a, b), tmp_path) == []


def test_a_section_below_the_token_floor_is_skipped(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", "# Tiny\n\nToo short to compare.\n")
    b = _write(tmp_path, "b.md", "# Also\n\nToo short to compare.\n")
    assert aqd.detect_exact_duplication(_scan(a, b), tmp_path) == []


def test_partial_overlap_respects_the_threshold(tmp_path: Path) -> None:
    left = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
    right = "alpha bravo charlie delta echo foxtrot mike november oscar papa quebec romeo"
    a = _write(tmp_path, "a.md", f"# A\n\n{left}\n")
    b = _write(tmp_path, "b.md", f"# B\n\n{right}\n")
    # ~0.33 overlap: not flagged strictly, flagged when the bar is low.
    assert aqd.detect_exact_duplication(_scan(a, b), tmp_path, threshold=0.9) == []
    assert len(aqd.detect_exact_duplication(_scan(a, b), tmp_path, threshold=0.3)) == 1


def test_within_one_document_duplication_is_flagged(tmp_path: Path) -> None:
    doc = _write(tmp_path, "d.md", f"# One\n\n{_PARA}\n\n# Two\n\n{_PARA}\n")
    findings = aqd.detect_exact_duplication(_scan(doc), tmp_path)
    assert len(findings) == 1
    assert findings[0].primary.artifact_path == "d.md"


# --- B: advisory invariants + evidence -------------------------------------------

def test_findings_are_structural_and_advisory(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    for f in aqd.detect_exact_duplication(_scan(a, b), tmp_path):
        assert f.kind == "structural"
        assert f.verdict is None
        assert f.severity in SEVERITIES
        assert f.severity != "error"
        assert "score" not in f.to_dict()  # advisory: no combined score, no edit payload


def test_evidence_is_a_substring_of_the_primary_source(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    findings = aqd.detect_exact_duplication(_scan(a, b), tmp_path)
    assert findings
    for f in findings:
        source = (tmp_path / f.primary.artifact_path).read_text(encoding="utf-8")
        assert f.evidence
        assert f.evidence in source


# --- C: determinism --------------------------------------------------------------

def test_output_is_deterministic(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.md", f"# Alpha\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# Beta\n\n{_PARA}\n")
    first = [f.to_dict() for f in aqd.detect_exact_duplication(_scan(a, b), tmp_path)]
    second = [f.to_dict() for f in aqd.detect_exact_duplication(_scan(a, b), tmp_path)]
    assert first
    assert first == second


def test_unicode_content_does_not_crash(tmp_path: Path) -> None:
    text = f"# Ünïcödé 🎯\n\n{_PARA} — with an em dash and an emoji 🛰️.\n"
    a = _write(tmp_path, "a.md", text)
    b = _write(tmp_path, "b.md", text)
    findings = aqd.detect_exact_duplication(_scan(a, b), tmp_path)
    assert isinstance(findings, list)
    assert len(findings) == 1


# --- defensive branches (leak-safe path, anchor rejection, empty inputs) ----------

def test_rel_posix_degrades_to_the_bare_filename(tmp_path: Path) -> None:
    # No root at all, and a file outside the root: both degrade to the name, never an
    # absolute path (the leak-safe guarantee the Locus also enforces).
    assert aqd._rel_posix(Path("/nowhere/deep/plan.md"), None) == "plan.md"
    assert aqd._rel_posix(Path("/outside/plan.md"), tmp_path) == "plan.md"


def test_evidence_keeps_a_hash_prefixed_content_line() -> None:
    # '#billing' (no space after the '#') is content, not an ATX heading, so it stays
    # eligible as evidence; only '# '..'###### ' headings are skipped. The old
    # startswith("#") test wrongly dropped it and returned no quote.
    assert aqd._evidence_of("# Heading\n\n#billing covers card payments") == "#billing covers card payments"
    assert aqd._evidence_of("## Still A Heading\n\nreal body line") == "real body line"


def test_evidence_keeps_a_fenced_hash_comment_line() -> None:
    # A '# comment' INSIDE a ``` code fence is content, not a heading — document.py's parser
    # excludes fenced lines via its fence flag, so evidence must too. Without fence tracking this
    # line is wrongly skipped as a heading and the section can be left with no evidence.
    text = "## Heading\n\n```bash\n# configure the client\nrun --now\n```\n"
    assert aqd._evidence_of(text) == "# configure the client"


@pytest.mark.parametrize("exc", [OSError("EACCES"), RuntimeError("symlink loop")])
def test_rel_posix_survives_a_resolve_failure(monkeypatch, exc) -> None:
    # resolve() can raise OSError (inaccessible component) or, on some CPython versions,
    # RuntimeError (symlink loop in non-strict mode) -- neither is a ValueError. An
    # advisory scan must degrade to the bare name on either, never crash on one odd path.
    def boom(self, *args, **kwargs):
        raise exc
    monkeypatch.setattr(Path, "resolve", boom)
    assert aqd._rel_posix(Path("/outside/plan.md"), Path("/root")) == "plan.md"


def test_detect_survives_a_symlink_loop_artifact(tmp_path: Path) -> None:
    # The finding is about detect_exact_duplication aborting on one bad path, so test it end-to-end,
    # not just _rel_posix: a self-referential symlink loop alongside a valid near-duplicate pair must
    # be skipped while the valid pair is still reported — in BOTH scan modes (project_root and None).
    loop = tmp_path / "loop.md"
    try:
        os.symlink(loop, loop)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    a = _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# B\n\n{_PARA}\n")
    scan = [(loop, "feature"), (a, "feature"), (b, "feature")]
    assert len(aqd.detect_exact_duplication(scan, tmp_path)) == 1
    assert len(aqd.detect_exact_duplication(scan, None)) == 1


def test_evidence_is_capped_at_the_cap_length() -> None:
    # A body line longer than the cap is truncated to exactly _EVIDENCE_CAP chars; a line AT the
    # cap is kept whole. Pins the truncation boundary so an off-by-one slice ([:cap-1]/[:cap+1])
    # is caught (the input length is fixed, independent of the constant).
    assert aqd._evidence_of("# H\n\n" + "x" * 250) == "x" * aqd._EVIDENCE_CAP
    exact = "y" * aqd._EVIDENCE_CAP
    assert aqd._evidence_of("# H\n\n" + exact) == exact


def test_clean_anchor_rejects_unusable_titles() -> None:
    assert aqd._clean_anchor([]) is None               # no heading
    assert aqd._clean_anchor([""]) is None             # empty title
    assert aqd._clean_anchor(["x" * 500]) is None      # over the length bound
    assert aqd._clean_anchor(["ok heading"]) == "ok heading"


def test_jaccard_is_zero_when_a_set_is_empty() -> None:
    assert aqd._jaccard(set(), {"alpha"}) == 0.0
    assert aqd._jaccard({"alpha"}, set()) == 0.0


def test_a_heading_only_section_has_no_evidence_and_is_skipped(tmp_path: Path) -> None:
    # A long heading carries enough tokens to pass the floor but has no body line, so it
    # yields no grep-verifiable quote and is dropped (never emitted as a finding).
    heading = "# alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
    a = _write(tmp_path, "a.md", heading + "\n")
    b = _write(tmp_path, "b.md", heading + "\n")
    assert aqd.detect_exact_duplication(_scan(a, b), tmp_path) == []


def test_empty_and_unreadable_artifacts_are_skipped(tmp_path: Path) -> None:
    empty = _write(tmp_path, "empty.md", "")
    missing = tmp_path / "missing.md"          # never created → unreadable
    a = _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n")
    # Empty and unreadable artifacts contribute no sections; the real pair is unaffected.
    assert aqd.detect_exact_duplication(_scan(empty, missing), tmp_path) == []
    b = _write(tmp_path, "b.md", f"# B\n\n{_PARA}\n")
    assert len(aqd.detect_exact_duplication(_scan(a, b, empty, missing), tmp_path)) == 1


def test_a_pathological_path_is_skipped_not_crashed(tmp_path: Path) -> None:
    # A path deeper than the Locus segment limit must not crash the scan — the odd
    # artifact is dropped, a normal pair alongside it is still reported.
    deep = tmp_path
    for _ in range(70):  # > Locus's 64-segment limit
        deep = deep / "d"
    deep.mkdir(parents=True)
    bad = deep / "bad.md"
    bad.write_text(f"# Bad\n\n{_PARA}\n", encoding="utf-8")
    a = _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# B\n\n{_PARA}\n")
    findings = aqd.detect_exact_duplication(_scan(a, b, bad), tmp_path)
    assert len(findings) == 1
    assert "d/d/d" not in findings[0].primary.artifact_path


def test_the_same_artifact_listed_twice_is_scanned_once(tmp_path: Path) -> None:
    # A path listed twice must not duplicate against itself (a finding cannot relate a
    # section to itself) — the artifact is scanned once.
    a = _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n")
    assert aqd.detect_exact_duplication([(a, "feature"), (a, "feature")], tmp_path) == []


def test_an_artifact_listed_twice_does_not_duplicate_findings(tmp_path: Path) -> None:
    # 'a' listed twice alongside a matching 'b' must still yield exactly one a~b finding,
    # not two — the dedup, not just the identical-locus skip, is what guarantees this.
    a = _write(tmp_path, "a.md", f"# A\n\n{_PARA}\n")
    b = _write(tmp_path, "b.md", f"# B\n\n{_PARA}\n")
    findings = aqd.detect_exact_duplication([(a, "feature"), (a, "feature"), (b, "feature")], tmp_path)
    assert len(findings) == 1


def test_two_files_sharing_a_bare_name_locus_do_not_crash(tmp_path: Path) -> None:
    # Two distinct files OUTSIDE the project root degrade to the same bare-name locus
    # ("spec.md", same heading, same line) — identical loci, so the pair is skipped.
    root = tmp_path / "root"
    root.mkdir()
    one, two = tmp_path / "one" / "spec.md", tmp_path / "two" / "spec.md"
    for path in (one, two):
        path.parent.mkdir()
        path.write_text(f"# Same\n\n{_PARA}\n", encoding="utf-8")
    assert aqd.detect_exact_duplication([(one, "feature"), (two, "feature")], root) == []
