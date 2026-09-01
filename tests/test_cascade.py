"""Tests for the two-tier JIT-retrieval cascade (cascade.py).

See constructorfabric/studio#104.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.commands.cascade import cmd_retrieve
from studio.utils.cascade import route_query, route_tier1, route_tier2
from studio.utils.doc_index import get_or_build_doc_index
from studio.utils.okf import write_concept_file

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


def _write(tmp_path: Path, content: str = _SAMPLE, name: str = "doc.md") -> Path:
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


class TestRouteTier1:
    def test_row1_heading_nav_no_hits_escalates(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = route_tier1(f, "making up")
        assert result == {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}

    def test_row2_agree_unambiguous_resolves_at_tier1(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        result = route_tier1(f, "KAPING")
        assert result["tier"] == "resolved"
        assert result["reason"] == "heading_nav_tfidf_agree_large_margin"
        assert result["candidates"] == [{"heading": "Introduction", "line_start": 1, "line_end": 4}]

    def test_row3_disagreement_resolves_multi_with_both_candidates(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DISAGREEMENT_SAMPLE)
        result = route_tier1(f, "gadget")
        assert result["tier"] == "resolved_multi"
        assert result["reason"] == "heading_nav_tfidf_disagree"
        headings = {c["heading"] for c in result["candidates"]}
        assert headings == {"SectionA", "SectionB"}

    def test_row4_agree_diffuse_margin_escalates(self, tmp_path: Path, monkeypatch):
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

    @pytest.mark.parametrize("bad_threshold", [0, -1, float("nan"), float("inf")])
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
        with pytest.raises(ValueError, match="margin_threshold"):
            route_tier1(f, "widget", margin_threshold=bad_threshold)

    def test_route_query_also_rejects_an_invalid_margin_threshold(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        with pytest.raises(ValueError, match="margin_threshold"):
            route_query(f, "widget", margin_threshold=-1.0)


class TestRouteTier2:
    def test_no_bundle_at_all_recommends_baseline(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}
        result = route_tier2(f, tier1)
        assert result == {"recommendation": "baseline", "reason": "no_current_okf_bundle"}

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

        tier1 = {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "baseline"
        assert result["okf_needs_rebuild"] is True

    def test_no_candidate_with_a_fully_current_bundle_recommends_okf(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        for section in index["retrieval_sections"]:
            write_concept_file(f, section["line_start"], description="d", body="b")

        tier1 = {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"

    def test_current_bundle_for_candidate_recommends_okf(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path, _DIFFUSE_MARGIN_SAMPLE)
        index = get_or_build_doc_index(f)
        section_a = index["retrieval_sections"][0]
        write_concept_file(f, section_a["line_start"], description="d", body="b")

        tier1 = route_tier1(f, "widget")
        result = route_tier2(f, tier1)
        assert result["recommendation"] == "okf"
        assert result["bundle_dir"]

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
        tier1 = {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}
        result = route_tier2(f, tier1, expected_future_queries=20)
        breakeven = result["build_okf_break_even"]
        assert breakeven["okf_total_tokens"] == 301_187 + 45_735 * 20
        assert breakeven["baseline_total_tokens"] == 333_573 * 20
        assert breakeven["building_okf_would_pay_off"] is True

    def test_no_expected_future_queries_omits_break_even_math(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("studio.utils.files.find_studio_directory", lambda *_a, **_k: tmp_path)
        f = _write(tmp_path)
        tier1 = {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}
        result = route_tier2(f, tier1)
        assert "build_okf_break_even" not in result

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
