"""Tests for the two-tier JIT-retrieval cascade (cascade.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

import pytest

from studio.commands.cascade import cmd_retrieve
from studio.utils import cascade
from studio.utils.cascade import route_query, route_tier1, route_tier2
from studio.utils.doc_index import get_or_build_doc_index
from studio.utils.okf import _okf_bundle_dir, write_concept_file

_SAMPLE = (
    "## Introduction\n\n"
    "This section introduces the KAPING framework for knowledge graphs.\n\n"
    "## Related Work\n\n"
    "This section covers unrelated background material with no overlap.\n"
)

# Same shape as findings.md's "zero-shot" adversarial test: heading-nav and
# TF-IDF agree on the same section (both pick SectionA -- three raw hits),
# but the margin is finite (not unambiguous), since the query term also
# appears once, diluted, in SectionB's much longer text.
_DIFFUSE_MARGIN_SAMPLE = (
    "## SectionA\n\nwidget widget widget banana.\n\n"
    "## SectionB\n\n" + ("filler word text here. " * 40) + "widget mentioned once here.\n"
)

# Heading-nav's first hit (SectionA, more raw occurrences) disagrees with TF-IDF's
# length-normalized top pick (SectionB, denser but shorter) -- same shape as
# findings.md's real LongMemEval split.
_DISAGREEMENT_SAMPLE = (
    "## SectionA\n\ngadget appears here. " + ("filler filler filler filler. " * 60) + "\n\n"
    "## SectionB\n\ngadget gadget gadget.\n"
)

# constructorfabric/studio#134, Oleg67's suggestion #4: a real single-signal
# failure -- the source hyphenates "KAPING-framework", so the literal
# two-word query substring "KAPING framework" never appears anywhere
# (heading-nav: 0 hits), but TF-IDF tokenizes on `[a-z0-9]+` regardless of
# the hyphen, so "kaping"/"framework" both land as real, distinctive terms
# scoring 0 everywhere except Introduction -- unambiguous.
_TFIDF_ONLY_UNAMBIGUOUS_SAMPLE = (
    "## Introduction\n\nThis section introduces the KAPING-framework for knowledge graphs.\n\n"
    "## Related Work\n\nThis section covers unrelated background material with no overlap.\n"
)

# Same hyphenation gap (heading-nav: 0 hits for "gizmo thing" -- the exact
# two-word phrase never appears contiguously in either section), but this
# time both terms independently occur in *both* sections, so TF-IDF scores
# positively on both -- a real signal, just not an unambiguous one.
_TFIDF_ONLY_DIFFUSE_SAMPLE = (
    "## SectionA\n\nA gizmo-thing sits here alone.\n\n"
    "## SectionB\n\nThe gizmo hums. " + ("filler word text here. " * 30) + "A thing rattles.\n"
)

# Same hyphenation gap as _TFIDF_ONLY_UNAMBIGUOUS_SAMPLE (heading-nav: 0 hits
# for "KAPING framework"), but with a single retrieval section: score_sections'
# `_confidence` has two separate ways to return `unambiguous=True` -- a
# positive top score beating a real second candidate's score, or (this
# fixture) a positive top score with no second candidate to compare against
# at all, since `len(ranked) == 1`. Every other row-2 fixture in this file
# has two sections and only exercises the former path.
_SINGLE_SECTION_TFIDF_UNAMBIGUOUS_SAMPLE = (
    "## Overview\n\nThis document describes the KAPING-framework in detail.\n"
)


def _write(tmp_path: Path, content: str = _SAMPLE, name: str = "doc.md") -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


# route_tier2 never reads tier1_result["reason"] -- these TestRouteTier2
# fixtures only need the row-1 *shape* (escalate, no candidates), so the
# exact reason string doesn't affect what's under test. Kept as one named
# constant rather than a literal repeated across every fixture: a bare
# string copy-pasted five times silently drifted out of sync with
# route_tier1's real reason ("heading_nav_no_hits" was retired and renamed
# to "no_signal_from_either_method" without any of these being updated --
# constructorfabric/studio#137 review) with nothing to catch it, since nothing
# here actually exercises route_tier1 itself.
_NO_CANDIDATE_ESCALATION = {"tier": "escalate", "reason": "no_signal_from_either_method", "candidates": []}


class TestRouteTier1:
    def test_row1_neither_method_has_signal_escalates(self, tmp_path: Path, monkeypatch):
        """"making up" is tfidf.py's own documented adversarial case: "up" is
        filtered by the 3-char minimum, and "making" never appears anywhere
        in this fixture, so TF-IDF has nothing either -- both methods
        genuinely have zero signal, not just heading-nav."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = route_tier1(f, "making up")
        assert result == {"tier": "escalate", "reason": "no_signal_from_either_method", "candidates": []}

    def test_row2_tfidf_only_unambiguous_resolves_at_tier1(self, tmp_path: Path, monkeypatch):
        """constructorfabric/studio#134, Oleg67's suggestion #4: heading-nav's
        exact-phrase match misses on a hyphenation difference, but TF-IDF's
        word-level tokenization doesn't -- and its own unambiguous signal is
        enough to resolve at Tier 1 without ever reaching Tier 2/OKF."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _TFIDF_ONLY_UNAMBIGUOUS_SAMPLE)
        result = route_tier1(f, "KAPING framework")
        assert result == {
            "tier": "resolved",
            "reason": "tfidf_only_unambiguous",
            "candidates": [{"heading": "Introduction", "line_start": 1, "line_end": 4}],
        }

    def test_row2_tfidf_only_unambiguous_with_single_section_document(self, tmp_path: Path, monkeypatch):
        """A single-section document is a distinct code path for
        `unambiguous`, not just a smaller instance of the two-section case:
        `_confidence` returns `unambiguous=True` here purely because there is
        no second section to compare against at all (`len(ranked) == 1`),
        never by beating a real rival's score. Verified directly against
        tfidf.py's own `_confidence` logic, not asserted blindly."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _SINGLE_SECTION_TFIDF_UNAMBIGUOUS_SAMPLE)
        index = get_or_build_doc_index(f)
        (section,) = index["retrieval_sections"]
        result = route_tier1(f, "KAPING framework")
        assert result == {
            "tier": "resolved",
            "reason": "tfidf_only_unambiguous",
            "candidates": [
                {"heading": "Overview", "line_start": section["line_start"], "line_end": section["line_end"]}
            ],
        }

    def test_row2_tfidf_only_unambiguous_never_calls_route_tier2_or_okf(self, tmp_path: Path, monkeypatch):
        """Row 2 resolves entirely within Tier 1 -- route_query must never
        fall through to route_tier2 (and, by extension, an OKF lookup) for
        it. The other row-2 test above checks the returned dict's shape but
        never spies on route_tier2/OKF to confirm neither was touched."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _TFIDF_ONLY_UNAMBIGUOUS_SAMPLE)
        with mock.patch("studio.utils.cascade.route_tier2") as mock_tier2, mock.patch(
            "studio.utils.cascade.get_okf_status"
        ) as mock_okf_status:
            result = route_query(f, "KAPING framework")
        assert result["tier"] == "resolved"
        assert result["reason"] == "tfidf_only_unambiguous"
        assert "tier2" not in result
        mock_tier2.assert_not_called()
        mock_okf_status.assert_not_called()

    def test_row3_tfidf_only_diffuse_escalates_with_tfidf_pick_as_candidate(self, tmp_path: Path, monkeypatch):
        """Heading-nav still has nothing, and TF-IDF has a real but diffuse
        signal (both sections score positively) -- escalates, but hands
        along TF-IDF's own top pick as the best Tier-1 guess, the same way
        row 4/7 hand along heading-nav's pick despite escalating."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _TFIDF_ONLY_DIFFUSE_SAMPLE)
        result = route_tier1(f, "gizmo thing")
        assert result == {
            "tier": "escalate",
            "reason": "heading_nav_no_hits_diffuse_tfidf",
            "candidates": [{"heading": "SectionA", "line_start": 1, "line_end": 4}],
        }

    def test_row4_heading_nav_hit_but_tfidf_has_no_signal_escalates(self, tmp_path: Path, monkeypatch):
        """Real bug caught during review (constructorfabric/studio#137):
        `tfidf_ranked[0]` is still a real dict entry when every section
        scores exactly 0 -- just an arbitrary document-order tie-break, not
        a genuine pick. The old code compared it against heading-nav's real
        pick unconditionally, fabricating a "disagreement" (`resolved_multi`
        with a bogus second candidate TF-IDF never actually found relevant)
        out of a signal that was never there. Must escalate on heading-nav's
        single, unconfirmed signal instead."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## Alpha\n\nNo relevant terms here besides filler filler filler.\n\n"
                             "## Beta\n\nThis talks about it up here too.\n")
        result = route_tier1(f, "it up")
        assert result == {
            "tier": "escalate",
            "reason": "heading_nav_only_no_tfidf_signal",
            "candidates": [{"heading": "Beta", "line_start": 5, "line_end": 8}],
        }

    def test_row6_agree_unambiguous_resolves_at_tier1(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = route_tier1(f, "KAPING")
        assert result["tier"] == "resolved"
        assert result["reason"] == "heading_nav_tfidf_agree_large_margin"
        assert result["candidates"] == [{"heading": "Introduction", "line_start": 1, "line_end": 4}]

    def test_row5_disagreement_resolves_multi_with_both_candidates(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DISAGREEMENT_SAMPLE)
        result = route_tier1(f, "gadget")
        assert result["tier"] == "resolved_multi"
        assert result["reason"] == "heading_nav_tfidf_disagree"
        headings = {c["heading"] for c in result["candidates"]}
        assert headings == {"SectionA", "SectionB"}

    def test_row7_agree_diffuse_margin_escalates(self, tmp_path: Path, monkeypatch):
        """Real, reproduced shape of findings.md's "zero-shot" adversarial
        test: heading-nav and TF-IDF agree on the same section, but the
        margin is finite (not unambiguous) -- and that agreed pick is
        documented as the wrong answer. Confirms the conservative default
        (only unambiguous counts as a safe large margin) escalates here."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        result = route_tier1(f, "widget")
        assert result["tier"] == "escalate"
        assert result["reason"] == "diffuse_margin"
        assert result["candidates"] == [{"heading": "SectionA", "line_start": 1, "line_end": 4}]

    def test_margin_threshold_can_enable_a_numeric_large_margin_resolution(self, tmp_path: Path, monkeypatch):
        """The default (None) requires unambiguous; passing a numeric
        threshold is an explicit opt-in to a less conservative policy."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        result = route_tier1(f, "widget", margin_threshold=1.0)
        assert result["tier"] == "resolved"
        assert result["reason"] == "heading_nav_tfidf_agree_large_margin"

    #: Non-finite/non-positive numeric values, plus a non-numeric string and
    #: a bool -- the latter two exist to pin down a real bug (studio#135's
    #: review): math.isfinite() raises TypeError for either, which would
    #: propagate out before the intended ValueError ever ran, defeating
    #: _validate_margin_threshold's documented contract for exactly the
    #: direct-Python-caller case its docstring exists for. bool is checked
    #: separately from the numeric cases since it subclasses int and would
    #: otherwise slip past a bare isinstance(x, (int, float)) check.
    _BAD_MARGIN_THRESHOLDS = [0, -1, float("nan"), float("inf"), "0.5", True]

    @pytest.mark.parametrize("bad_threshold", _BAD_MARGIN_THRESHOLDS)
    def test_margin_threshold_rejects_invalid_values_at_the_callable_api(
        self, tmp_path: Path, monkeypatch, bad_threshold,
    ):
        """A direct Python caller bypasses commands/cascade.py's argparse
        validation entirely -- without a check here too, a non-positive or
        non-finite threshold would make the row-4 margin comparison fire on
        virtually any finite margin, defeating the "no finite value is yet
        proven safe" design basis."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        expected = re.escape(f"margin_threshold must be a finite number > 0, got {bad_threshold!r}")
        with pytest.raises(ValueError, match=f"^{expected}$"):
            route_tier1(f, "widget", margin_threshold=bad_threshold)

    @pytest.mark.parametrize("bad_threshold", _BAD_MARGIN_THRESHOLDS)
    def test_route_query_rejects_the_same_invalid_margin_thresholds_as_route_tier1(
        self, tmp_path: Path, monkeypatch, bad_threshold,
    ):
        """route_query shares _validate_margin_threshold with route_tier1 via
        the same call path -- mirrors that test's full matrix instead of a
        single hard-coded value, so a future refactor that decoupled the two
        validation paths would be caught here rather than silently letting
        an invalid threshold through route_query specifically."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        expected = re.escape(f"margin_threshold must be a finite number > 0, got {bad_threshold!r}")
        with pytest.raises(ValueError, match=f"^{expected}$"):
            route_query(f, "widget", margin_threshold=bad_threshold)

    @pytest.mark.parametrize("route_fn", [route_tier1, route_query])
    def test_a_large_finite_margin_threshold_is_accepted_not_just_rejected_values(
        self, tmp_path: Path, monkeypatch, route_fn,
    ):
        """The accept path, not just the reject path: a legitimately large
        but finite threshold (e.g. an explicit, permissive opt-in) must not
        itself be treated as invalid by either entry point."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        result = route_fn(f, "widget", margin_threshold=1e10)  # must not raise
        assert "tier" in result

    def test_route_tier1_never_touches_okf(self, tmp_path: Path, monkeypatch):
        """The module docstring guarantees route_tier1 stays free and
        deterministic by never touching the OKF bundle, but nothing
        automated backed that up before this test. Patches
        get_okf_status with a mock that raises if called at all, then
        exercises every routing-table row this class covers (1 through 7,
        plus the margin_threshold opt-in) -- a future edit that
        reintroduces an OKF call from inside route_tier1 fails this test
        immediately instead of only being caught by manual review."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        with mock.patch("studio.utils.cascade.get_okf_status") as mock_okf_status:
            mock_okf_status.side_effect = AssertionError("route_tier1 must never call get_okf_status")

            route_tier1(_write(tmp_path, _SAMPLE, "row1.md"), "making up")
            route_tier1(_write(tmp_path, _TFIDF_ONLY_UNAMBIGUOUS_SAMPLE, "row2.md"), "KAPING framework")
            route_tier1(_write(tmp_path, _TFIDF_ONLY_DIFFUSE_SAMPLE, "row3.md"), "gizmo thing")
            route_tier1(
                _write(
                    tmp_path,
                    "## Alpha\n\nNo relevant terms here besides filler filler filler.\n\n"
                    "## Beta\n\nThis talks about it up here too.\n",
                    "row4.md",
                ),
                "it up",
            )
            route_tier1(_write(tmp_path, _DISAGREEMENT_SAMPLE, "row5.md"), "gadget")
            route_tier1(_write(tmp_path, _SAMPLE, "row6.md"), "KAPING")
            row7_doc = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE, "row7.md")
            route_tier1(row7_doc, "widget")
            route_tier1(row7_doc, "widget", margin_threshold=1.0)

        mock_okf_status.assert_not_called()


class TestRouteTier2:
    def test_no_bundle_at_all_recommends_baseline(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = _NO_CANDIDATE_ESCALATION
        result = route_tier2(f, tier1)
        assert result == {
            "recommendation": "baseline",
            "reason": "no_current_okf_bundle",
            "tier2_escalations": 1,
            "should_build_okf": False,
        }

    def test_bundle_exists_but_only_missing_entries_is_treated_as_no_bundle(self, tmp_path: Path, monkeypatch):
        """Real bug caught during manual verification: get_okf_status()
        returns one entry per retrieval section even when nothing has ever
        been summarized, all with status "missing" -- an available
        bundle_dir with every entry missing means no concept file has
        actually been written, which is "no bundle" for this decision."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        tier1 = route_tier1(f, "widget")
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "baseline"
        assert "okf_needs_rebuild" not in result

    def test_no_candidate_with_a_partially_summarized_bundle_falls_back_to_baseline(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #111: row 1 (heading-nav found zero hits) has no
        candidate section to narrow to, so the external OKF file-selector
        could land on any section in the bundle. Recommending OKF while
        even one other section is stale/missing would let that external
        step pick exactly the untrustworthy one."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")  # SectionB left missing

        tier1 = _NO_CANDIDATE_ESCALATION
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "baseline"
        assert result["okf_needs_rebuild"] is True

    def test_no_candidate_with_a_fully_current_bundle_recommends_okf(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        for section in index["retrieval_sections"]:
            write_concept_file(f, section["line_start"], description="d", body="b")

        tier1 = _NO_CANDIDATE_ESCALATION
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"

    def test_row3_tfidf_sourced_candidate_recommends_okf_when_current(self, tmp_path: Path, monkeypatch):
        """Row 3's escalate candidate is TF-IDF-sourced -- SectionA, picked
        because it's TF-IDF's own top pick, not because heading-nav ever
        matched it (heading-nav has zero hits in this fixture). Every other
        route_tier2 test before this one only ever passed a heading-nav-
        sourced candidate (rows 4/7) or no candidate at all (row 1); this is
        the first to exercise that new provenance. Builds the row-3 result
        via a real route_tier1 call rather than hand-building the dict, so
        this test breaks if row 3's actual shape ever changes."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _TFIDF_ONLY_DIFFUSE_SAMPLE)
        tier1 = route_tier1(f, "gizmo thing")
        assert tier1["tier"] == "escalate"
        assert tier1["reason"] == "heading_nav_no_hits_diffuse_tfidf"  # sanity: genuinely row 3

        index = get_or_build_doc_index(f)
        for section in index["retrieval_sections"]:
            write_concept_file(f, section["line_start"], description="d", body="b")

        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"
        assert result["bundle_dir"] == str(_okf_bundle_dir(f))

    def test_row3_tfidf_sourced_candidate_narrows_staleness_to_only_that_section(
        self, tmp_path: Path, monkeypatch
    ):
        """The test above writes *every* retrieval section's concept file
        current before calling route_tier2, so a route_tier2 that (bug)
        validated the whole bundle instead of narrowing to just row 3's
        named candidate would still pass it undetected. Here, only
        SectionA -- TF-IDF's own top pick, and row 3's sole candidate --
        gets a current concept file; SectionB's is deliberately left
        missing. route_tier2 must still recommend okf: it proves the
        staleness check only ever looked at the named candidate's own
        section. A route_tier2 that instead fell back to checking
        `status["entries"]` (every section) regardless of `candidates`
        would see SectionB's still-missing entry and downgrade to
        baseline with `okf_needs_rebuild`, failing this assertion."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _TFIDF_ONLY_DIFFUSE_SAMPLE)
        tier1 = route_tier1(f, "gizmo thing")
        assert tier1["tier"] == "escalate"
        assert tier1["reason"] == "heading_nav_no_hits_diffuse_tfidf"  # sanity: genuinely row 3
        assert tier1["candidates"] == [{"heading": "SectionA", "line_start": 1, "line_end": 4}]

        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        assert section_a["heading"] == "SectionA"
        write_concept_file(f, section_a["line_start"], description="d", body="b")
        # SectionB's concept file deliberately left missing.

        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"
        assert result["bundle_dir"] == str(_okf_bundle_dir(f))

    def test_row4_heading_nav_sourced_candidate_recommends_okf_when_current(self, tmp_path: Path, monkeypatch):
        """Row 4's escalate candidate is heading-nav-sourced (TF-IDF found no
        signal at all, unlike row 3's TF-IDF-sourced candidate) -- but
        nothing before this test fed a real row-4 result into route_tier2 at
        all, even though row 4 escalates and names a candidate exactly like
        row 3 does. Same template as
        test_row3_tfidf_sourced_candidate_recommends_okf_when_current:
        builds the escalate result via a real route_tier1 call rather than
        hand-building the dict, so this test breaks if row 4's actual shape
        ever changes."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(
            tmp_path,
            "## Alpha\n\nNo relevant terms here besides filler filler filler.\n\n"
            "## Beta\n\nThis talks about it up here too.\n",
        )
        tier1 = route_tier1(f, "it up")
        assert tier1["tier"] == "escalate"
        assert tier1["reason"] == "heading_nav_only_no_tfidf_signal"  # sanity: genuinely row 4

        index = get_or_build_doc_index(f)
        for section in index["retrieval_sections"]:
            write_concept_file(f, section["line_start"], description="d", body="b")

        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"
        assert result["bundle_dir"] == str(_okf_bundle_dir(f))

    def test_current_bundle_for_candidate_recommends_okf(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")

        tier1 = route_tier1(f, "widget")
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"
        assert result["bundle_dir"] == str(_okf_bundle_dir(f))

    def test_stale_bundle_for_candidate_falls_back_to_baseline_with_rebuild_flag(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")

        f.write_text(_DIFFUSE_MARGIN_SAMPLE.replace("banana.", "banana banana."), encoding="utf-8")
        tier1 = route_tier1(f, "widget")
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "baseline"
        assert result["okf_needs_rebuild"] is True

    def test_expected_future_queries_adds_break_even_math(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = _NO_CANDIDATE_ESCALATION
        result = route_tier2(f, tier1, expected_future_queries=20)
        breakeven = result["build_okf_break_even"]
        assert breakeven["okf_total_tokens"] == 301_187 + 45_735 * 20
        assert breakeven["baseline_total_tokens"] == 333_573 * 20
        assert breakeven["building_okf_would_pay_off"] is True

    def test_no_expected_future_queries_omits_break_even_math(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = _NO_CANDIDATE_ESCALATION
        result = route_tier2(f, tier1)
        assert "build_okf_break_even" not in result

    def test_tier2_escalations_counts_up_across_calls_without_a_human_supplied_guess(
        self, tmp_path: Path, monkeypatch
    ):
        """constructorfabric/studio#134: should_build_okf must derive from
        real, observed escalations against this document, not a human-typed
        `expected_future_queries` guess -- no such guess is passed here at
        all."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = _NO_CANDIDATE_ESCALATION

        first = route_tier2(f, tier1)
        assert first["tier2_escalations"] == 1

        second = route_tier2(f, tier1)
        assert second["tier2_escalations"] == 2

    def test_should_build_okf_flips_true_once_escalations_cross_the_real_break_even(
        self, tmp_path: Path, monkeypatch
    ):
        """The break-even point is derived from cascade.py's own hardcoded,
        measured per-query rates -- 301_187 / (333_573 - 45_735), which
        rounds up to 2 -- not the ~15-48 total-query-volume figures from
        constructorfabric/studio#104's earlier comments (those measured a
        different population: total queries against a document, most of
        which resolve at Tier 1 and never reach this function)."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = _NO_CANDIDATE_ESCALATION

        assert route_tier2(f, tier1)["should_build_okf"] is False  # 1st escalation
        assert route_tier2(f, tier1)["should_build_okf"] is True  # 2nd escalation, at break-even

    def test_should_build_okf_is_false_outside_a_studio_project(self, tmp_path: Path, monkeypatch):
        """No cache location means no way to persist a real escalation
        count, so this must never fabricate a True recommendation from
        nothing -- None (untracked), not 0, and never above the threshold."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: None)
        f = _write(tmp_path)
        tier1 = _NO_CANDIDATE_ESCALATION
        result = route_tier2(f, tier1)
        assert result["tier2_escalations"] is None
        assert result["should_build_okf"] is False

    def test_break_even_constant_is_exactly_two(self):
        """cascade.py's own docstring/comment claims
        _TIER2_BREAK_EVEN_ESCALATIONS evaluates to 2 (301_187 / (333_573 -
        45_735), rounded up) -- the existing tests only assert the
        *behavioral* consequence (should_build_okf False at 1, True at 2),
        never the constant's value directly. Pin it here so a future edit
        to the hardcoded rates that silently changed the break-even point
        gets caught even if it happened to preserve that 1-vs-2 boundary
        behavior by coincidence."""
        assert cascade._TIER2_BREAK_EVEN_ESCALATIONS == 2

    def test_route_tier2_does_not_double_count_a_caller_retry_with_the_same_escalation_key(
        self, tmp_path: Path, monkeypatch
    ):
        """constructorfabric/studio#136 (second review pass, Major):
        record_tier2_escalation was called unconditionally on every
        route_tier2 invocation with no way to distinguish a fresh
        escalation from a caller re-invoking route_tier2 for the same
        logical query after a transient failure/timeout. Simulates exactly
        that retry: the same escalation_key passed twice must only advance
        the persisted count once; a genuinely new key still counts."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}

        first = route_tier2(f, tier1, escalation_key="req-1")
        assert first["tier2_escalations"] == 1

        retried = route_tier2(f, tier1, escalation_key="req-1")
        assert retried["tier2_escalations"] == 1  # retry of the same request -- not double-counted

        genuinely_new = route_tier2(f, tier1, escalation_key="req-2")
        assert genuinely_new["tier2_escalations"] == 2

    def test_candidate_that_no_longer_matches_any_section_falls_back_to_baseline(
        self, tmp_path: Path, monkeypatch
    ):
        """CodeRabbit PR #111: if the document changed structurally between
        Tier 1 picking a candidate and this re-derived status (a real,
        if narrow, race), the candidate's line_start may no longer match
        any current section. Silently dropping it would leave `relevant`
        empty, and `any(... for entry in [])` is vacuously False --
        recommending OKF on a candidate that was never actually verified."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")

        bogus_tier1 = {
            "tier": "escalate", "reason": "diffuse_margin",
            "candidates": [{"heading": "Ghost", "line_start": 99999, "line_end": 99999}],
        }
        result = route_tier2(f, bogus_tier1)
        assert result["recommendation"] == "baseline"
        assert result["okf_needs_rebuild"] is True

    def test_docstrings_row_number_cross_reference_matches_actual_escalating_reasons(
        self, tmp_path: Path, monkeypatch
    ):
        """route_tier2's docstring claims it's "only called for the
        escalating rows: row 1 ... row 3 ... row 4 ... and row 7", naming
        each row's exact reason string -- but the implementation never
        reads tier1_result["reason"] at all, so nothing enforces that list
        against route_tier1's real behavior. It already drifted once during
        this PR's own renumbering (constructorfabric/studio#137 review).
        Exercise route_tier1 against a fixture for every row in its own
        table (1-7, using the exact same samples/queries as each
        TestRouteTier1 row test) and assert the rows/reasons that actually
        come back `tier == "escalate"` are EXACTLY what route_tier2's
        docstring claims -- so a future table change that adds, removes, or
        renames an escalating row fails this test instead of only drifting
        in prose."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        row_fixtures = {
            1: (_SAMPLE, "making up"),
            2: (_TFIDF_ONLY_UNAMBIGUOUS_SAMPLE, "KAPING framework"),
            3: (_TFIDF_ONLY_DIFFUSE_SAMPLE, "gizmo thing"),
            4: (
                "## Alpha\n\nNo relevant terms here besides filler filler filler.\n\n"
                "## Beta\n\nThis talks about it up here too.\n",
                "it up",
            ),
            5: (_DISAGREEMENT_SAMPLE, "gadget"),
            6: (_SAMPLE, "KAPING"),
            7: (_DIFFUSE_MARGIN_SAMPLE, "widget"),
        }
        escalating_reasons_by_row = {}
        for row, (content, query) in row_fixtures.items():
            f = _write(tmp_path, content, f"docstring_row{row}.md")
            result = route_tier1(f, query)
            if result["tier"] == "escalate":
                escalating_reasons_by_row[row] = result["reason"]

        # The exact rows/reasons route_tier2's docstring names as the ones
        # it's "only called for".
        assert escalating_reasons_by_row == {
            1: "no_signal_from_either_method",
            3: "heading_nav_no_hits_diffuse_tfidf",
            4: "heading_nav_only_no_tfidf_signal",
            7: "diffuse_margin",
        }


class TestRouteQuery:
    def test_resolved_at_tier1_never_calls_tier2(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = route_query(f, "KAPING")
        assert result["tier"] == "resolved"
        assert "tier2" not in result
        assert "read_gate" not in result

    def test_resolved_multi_never_calls_tier2(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DISAGREEMENT_SAMPLE)
        result = route_query(f, "gadget")
        assert result["tier"] == "resolved_multi"
        assert "tier2" not in result

    def test_escalation_to_baseline_wires_in_the_read_gate(self, tmp_path: Path, monkeypatch):
        """The integration point findings.md flagged as still-missing: when
        Tier 2 recommends baseline, the read-gate check runs against the
        real doc-index line count instead of leaving it disconnected."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## A\n\n" + "\n".join(f"line {i}" for i in range(20)) + "\n")
        result = route_query(f, "making up")
        assert result["tier"] == "escalate"
        assert result["tier2"]["recommendation"] == "baseline"
        assert result["read_gate"]["needs_confirmation"] is False
        assert result["read_gate"]["total_lines"] == get_or_build_doc_index(f)["total_lines"]

    def test_escalation_to_okf_does_not_run_the_read_gate(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")

        result = route_query(f, "widget")
        assert result["tier2"]["recommendation"] == "okf"
        assert "read_gate" not in result

    def test_route_query_retry_with_the_same_escalation_key_does_not_double_count(
        self, tmp_path: Path, monkeypatch
    ):
        """Same regression as TestRouteTier2's version, exercised through
        the full route_query entry point a real caller (e.g. cmd_retrieve)
        actually uses, since escalation_key must survive both hops
        (route_query -> route_tier2 -> record_tier2_escalation) intact."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)

        first = route_query(f, "making up", escalation_key="req-1")
        retried = route_query(f, "making up", escalation_key="req-1")
        assert first["tier2"]["tier2_escalations"] == 1
        assert retried["tier2"]["tier2_escalations"] == 1


class TestCmdRetrieve:
    def test_missing_file(self, tmp_path: Path, capsys):
        rc = cmd_retrieve([str(tmp_path / "nope.md"), "query"])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_missing_required_argument_emits_json_error_not_a_plain_text_banner(self, capsys):
        """CodeRabbit PR #111: cmd_retrieve now uses JsonSafeArgumentParser
        (like every other single-file command), so omitting a required
        positional must still emit the project's own --json ERROR
        contract, not argparse's default usage banner + SystemExit."""
        rc = cmd_retrieve([])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"

    def test_margin_threshold_rejects_non_positive_values(self, capsys):
        """CodeRabbit PR #111: a negative or zero --margin-threshold would
        make the safety-relevant margin comparison fire on virtually any
        result, defeating the cascade's own documented safety margin."""
        rc = cmd_retrieve(["doc.md", "query", "--margin-threshold", "-1"])
        assert rc == 2
        assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
        rc = cmd_retrieve(["doc.md", "query", "--margin-threshold", "0"])
        assert rc == 2
        assert json.loads(capsys.readouterr().out)["status"] == "ERROR"

    def test_margin_threshold_rejects_non_finite_values(self, capsys):
        rc = cmd_retrieve(["doc.md", "query", "--margin-threshold", "nan"])
        assert rc == 2
        assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
        rc = cmd_retrieve(["doc.md", "query", "--margin-threshold", "inf"])
        assert rc == 2
        assert json.loads(capsys.readouterr().out)["status"] == "ERROR"

    def test_escalation_key_rejects_an_oversized_value(self, tmp_path: Path, capsys, monkeypatch):
        """constructorfabric/studio#136 (round-5, Minor): a literal "doc.md" was
        never created here, so the old test couldn't tell "key rejected" from
        "file not found" -- both gave rc==2/ERROR. Asserting the error message
        names --escalation-key specifically closes that gap."""
        from studio.utils.doc_index import _MAX_ESCALATION_KEY_LENGTH

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        oversized_key = "x" * (_MAX_ESCALATION_KEY_LENGTH + 1)
        rc = cmd_retrieve([str(f), "query", "--escalation-key", oversized_key])
        assert rc == 2
        out = json.loads(capsys.readouterr().out)
        assert out["status"] == "ERROR"
        assert "--escalation-key" in out["message"]
        assert str(_MAX_ESCALATION_KEY_LENGTH) in out["message"]

    def test_escalation_key_accepts_a_value_at_the_length_boundary(
        self, tmp_path: Path, capsys, monkeypatch,
    ):
        """The cap is inclusive -- a key exactly at the limit is a normal,
        valid idempotency token, not an edge case to reject."""
        from studio.utils.doc_index import _MAX_ESCALATION_KEY_LENGTH

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        boundary_key = "x" * _MAX_ESCALATION_KEY_LENGTH
        rc = cmd_retrieve([str(f), "making up", "--escalation-key", boundary_key])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier2"]["tier2_escalations"] == 1

    def test_basic_json_output(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        rc = cmd_retrieve([str(f), "KAPING"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier"] == "resolved"

    def test_margin_threshold_flag(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        rc = cmd_retrieve([str(f), "widget", "--margin-threshold", "1.0"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier"] == "resolved"

    def test_human_output_escalation_with_read_gate(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, "## A\n\n" + "\n".join(f"line {i}" for i in range(6000)) + "\n")
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_retrieve([str(f), "making up"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        out = capsys.readouterr().out
        assert "tier 2 recommendation" in out
        assert "needs confirmation" in out

    def test_human_output_resolved(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_retrieve([str(f), "KAPING"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "Introduction" in capsys.readouterr().out

    def test_json_output_exposes_tier2_escalations_and_should_build_okf_at_baseline(
        self, tmp_path: Path, capsys, monkeypatch,
    ):
        """constructorfabric/studio#136 (second review pass): route_tier2's
        baseline recommendation carries tier2_escalations/should_build_okf,
        and cmd_retrieve passes route_query's result straight through into
        its JSON output -- but every existing JSON-output test here only
        ever hits the resolved (Tier 1) tier, never a baseline Tier-2
        recommendation, so this machine-readable contract was never
        actually exercised end to end through the CLI."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)

        rc = cmd_retrieve([str(f), "making up"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier2"]["tier2_escalations"] == 1
        assert out["tier2"]["should_build_okf"] is False

        rc = cmd_retrieve([str(f), "making up"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier2"]["tier2_escalations"] == 2
        assert out["tier2"]["should_build_okf"] is True  # at cascade._TIER2_BREAK_EVEN_ESCALATIONS

    def test_human_output_shows_the_recorded_escalation_count_before_break_even(
        self, tmp_path: Path, capsys, monkeypatch,
    ):
        """Real gap caught in review (constructorfabric/studio#136, round-4,
        Minor): _human_retrieve only rendered tier2_escalations inside the
        should_build_okf branch, even though the JSON output above already
        reports the count unconditionally as soon as it's known -- the
        human-readable view was hiding real, already-recorded information
        the machine-readable one showed. Only the first (below-break-even)
        escalation is exercised here; the at-break-even case is already
        covered by the JSON test above and shares the same rendering path
        once should_build_okf is true."""
        from studio.utils.ui import set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)

        set_json_mode(False)
        try:
            rc = cmd_retrieve([str(f), "making up"])
        finally:
            set_json_mode(True)  # restore the autouse fixture's invariant for later tests
        assert rc == 0
        out = capsys.readouterr().out
        assert "1 Tier-2 escalations recorded for this document" in out
        assert "pay for itself" not in out  # not yet at break-even

    def test_escalation_key_flag_prevents_a_cli_retry_from_double_counting(
        self, tmp_path: Path, capsys, monkeypatch,
    ):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)

        cmd_retrieve([str(f), "making up", "--escalation-key", "req-1"])
        first = json.loads(capsys.readouterr().out)
        cmd_retrieve([str(f), "making up", "--escalation-key", "req-1"])
        retried = json.loads(capsys.readouterr().out)

        assert first["tier2"]["tier2_escalations"] == 1
        assert retried["tier2"]["tier2_escalations"] == 1

    @pytest.mark.parametrize("escalation_key", [None, "req-1"], ids=["no_key", "with_key"])
    def test_exit_code_and_status_truth_table_resolves_at_tier1(
        self, tmp_path: Path, capsys, monkeypatch, escalation_key,
    ):
        """constructorfabric/studio#136 (round-4 review, Minor): --escalation-key
        added a new input path to cmd_retrieve, but no single test asserted
        return code + JSON shape across the meaningfully distinct outcomes
        crossed with the flag's presence. This is row 1 of that truth
        table: a query that resolves entirely at Tier 1, so no escalation
        happens at all -- --escalation-key is inert here either way."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _TFIDF_ONLY_UNAMBIGUOUS_SAMPLE)
        argv = [str(f), "KAPING framework"]
        if escalation_key is not None:
            argv += ["--escalation-key", escalation_key]

        rc = cmd_retrieve(argv)

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier"] == "resolved"
        assert "tier2" not in out

    @pytest.mark.parametrize("escalation_key", [None, "req-1"], ids=["no_key", "with_key"])
    def test_exit_code_and_status_truth_table_escalates_to_baseline(
        self, tmp_path: Path, capsys, monkeypatch, escalation_key,
    ):
        """Row 2: Tier 1 escalates and Tier 2 recommends baseline (no OKF
        bundle exists yet)."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        argv = [str(f), "making up"]
        if escalation_key is not None:
            argv += ["--escalation-key", escalation_key]

        rc = cmd_retrieve(argv)

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier"] == "escalate"
        assert out["tier2"]["recommendation"] == "baseline"
        assert out["tier2"]["tier2_escalations"] == 1
        assert out["tier2"]["should_build_okf"] is False

    @pytest.mark.parametrize("escalation_key", [None, "req-1"], ids=["no_key", "with_key"])
    def test_exit_code_and_status_truth_table_escalates_to_okf(
        self, tmp_path: Path, capsys, monkeypatch, escalation_key,
    ):
        """Row 3: Tier 1 escalates (no named candidate, row 1) and Tier 2
        recommends okf, since every retrieval section already has a
        current concept file."""
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        for section in index["retrieval_sections"]:
            write_concept_file(f, section["line_start"], description="d", body="b")
        argv = [str(f), "making up"]
        if escalation_key is not None:
            argv += ["--escalation-key", escalation_key]

        rc = cmd_retrieve(argv)

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["tier"] == "escalate"
        assert out["tier2"]["recommendation"] == "okf"

    def test_human_output_okf_needs_rebuild(self, tmp_path: Path, capsys, monkeypatch):
        from studio.utils.ui import is_json_mode, set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")
        f.write_text(_DIFFUSE_MARGIN_SAMPLE.replace("banana.", "banana banana."), encoding="utf-8")

        orig = is_json_mode()
        set_json_mode(False)
        try:
            rc = cmd_retrieve([str(f), "widget"])
        finally:
            set_json_mode(orig)
        assert rc == 0
        assert "needs a rebuild" in capsys.readouterr().out

    def test_escalation_lock_timeout_degrades_the_whole_cli_call_gracefully(
        self, tmp_path: Path, capsys, monkeypatch,
    ):
        """constructorfabric/studio#136 (round-5, Minor): every existing test
        for the escalation-lock-timeout degradation exercised
        record_tier2_escalation directly, never the full cmd_retrieve CLI
        path. Same technique as test_doc_index.py's
        test_returns_none_within_a_bounded_time_when_the_lock_is_held_by_someone_else
        (hold the lock externally, run the real call on a background
        thread), applied here at the CLI level for both JSON and human
        output."""
        import fcntl
        import threading

        import studio.utils.doc_index as di
        from studio.utils.ui import set_json_mode

        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        # A short timeout keeps this test fast; the mechanism under test
        # (giving up on a genuinely stuck lock) doesn't depend on the
        # timeout's exact magnitude.
        monkeypatch.setattr(di, "_ESCALATION_LOCK_TIMEOUT_SECONDS", 0.2)
        f = _write(tmp_path)

        cache_path = di._escalation_cache_path(f)
        lock_path = cache_path.with_name(f"{cache_path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder = open(lock_path, "a", encoding="utf-8")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)

        def _run_bounded(argv: list[str]) -> dict:
            result: dict = {}

            def call() -> None:
                result["rc"] = cmd_retrieve(argv)

            t = threading.Thread(target=call)
            t.start()
            # Comfortably above the 0.2s lock timeout, so a genuine fix
            # regression (a real hang) still fails this assertion instead
            # of blocking the suite indefinitely.
            t.join(timeout=5)
            assert not t.is_alive(), "cmd_retrieve hung instead of degrading past the lock timeout"
            return result

        try:
            result = _run_bounded([str(f), "making up"])
            assert result["rc"] == 0
            out = json.loads(capsys.readouterr().out)
            assert out["tier2"]["tier2_escalations"] is None
            assert out["tier2"]["should_build_okf"] is False

            set_json_mode(False)
            try:
                result = _run_bounded([str(f), "making up"])
            finally:
                set_json_mode(True)  # restore the autouse fixture's invariant for later tests
            assert result["rc"] == 0
            human_out = capsys.readouterr().out
            assert "tier 2 recommendation: baseline" in human_out
            # The count is unknown (not zero), so the escalation-count
            # substep must be omitted entirely, not rendered as "0" or
            # skipped for the wrong reason.
            assert "Tier-2 escalations recorded" not in human_out
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()
