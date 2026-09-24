"""Unit tests for the workflow eval-harness scaffold."""
from __future__ import annotations

from pathlib import Path

import pytest

from studio.utils import eval_harness as eh

FIXTURES = Path(__file__).parent / "fixtures" / "eval"


# --- helpers ---------------------------------------------------------------

class _StubScorer:
    """A scorer whose kind and verdict are fixed — for the gate-contract tests."""

    def __init__(self, name: str, kind: eh.ScorerKind, verdict: str):
        self.name = name
        self.kind = kind
        self._verdict = verdict

    def score(self, run, scenario):  # run/scenario unused: signature matches the Scorer protocol
        score = None if self._verdict == eh.VERDICT_UNKNOWN else 0.0
        return eh.ScorerResult(self.name, self.kind, self._verdict, score, [], "")


def _scenario(run_dir: Path, sid: str = "s") -> eh.Scenario:
    return eh.Scenario(id=sid, workflow="w", run_dir=run_dir, expect="compliant")


def _result(kind: eh.ScorerKind, verdict: str) -> eh.ScorerResult:
    return eh.ScorerResult("x", kind, verdict, None if verdict == eh.VERDICT_UNKNOWN else 0.0)


def _report(*results: eh.ScorerResult) -> eh.EvalReport:
    return eh.EvalReport([eh.ScenarioResult("s", "w", list(results))])


# --- load_run --------------------------------------------------------------

def test_load_run_reads_plan_and_phases() -> None:
    run = eh.load_run(FIXTURES / "compliant" / "run")
    assert run is not None
    assert run.plan_meta["task"] == "demo compliant run"
    assert "phase-1.md" in run.phase_texts


def test_load_run_missing_plan_is_unknown_not_error(tmp_path: Path) -> None:
    assert eh.load_run(tmp_path) is None


def test_load_run_malformed_plan_is_unknown(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text("this = = not toml")
    assert eh.load_run(tmp_path) is None


def test_load_run_without_plan_section_is_unknown(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('title = "no plan section"\n')
    assert eh.load_run(tmp_path) is None


def test_load_run_with_non_list_phases_is_unknown(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('phases = "nope"\n[plan]\ntask = "t"\n')
    assert eh.load_run(tmp_path) is None


def test_load_run_absent_phase_file_is_simply_missing(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text(
        '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "here.md"\n'
        '[[phases]]\nnumber = 2\nfile = "gone.md"\n')
    (tmp_path / "here.md").write_text("# here\n")
    run = eh.load_run(tmp_path)
    assert run is not None
    assert "here.md" in run.phase_texts
    assert "gone.md" not in run.phase_texts


def test_load_run_undecodable_phase_file_is_missing_not_fatal(tmp_path: Path) -> None:
    """Non-UTF-8 bytes in one phase must not abort the suite.

    UnicodeDecodeError is a ValueError, not an OSError, so it used to escape load_run,
    propagate through load_cases into run_suite, and discard every other scenario's
    result. An undecodable file is just one more way a declared phase cannot be read.
    """
    (tmp_path / "plan.toml").write_text(
        '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "ok.md"\n'
        '[[phases]]\nnumber = 2\nfile = "bad.md"\n')
    (tmp_path / "ok.md").write_text("# ok\n")
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe invalid utf-8")
    run = eh.load_run(tmp_path)
    assert run is not None
    assert "ok.md" in run.phase_texts
    assert "bad.md" not in run.phase_texts


def test_load_run_phase_without_file_key_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('[plan]\ntask = "t"\n[[phases]]\nnumber = 1\n')
    run = eh.load_run(tmp_path)
    assert run is not None
    assert run.phase_texts == {}


def test_load_run_drops_non_dict_phase_entries(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('phases = ["x", "y"]\n[plan]\ntask = "t"\n')
    run = eh.load_run(tmp_path)
    assert run is not None
    assert run.phases == []


def test_load_run_non_string_file_does_not_crash(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = 123\n')
    run = eh.load_run(tmp_path)                        # must not raise TypeError
    assert run is not None
    assert run.phase_texts == {}
    result = eh.ReferencePresenceScorer().score(run, _scenario(tmp_path))
    assert result.verdict == eh.VERDICT_UNKNOWN        # no checkable file → UNKNOWN, not a crash


def test_load_run_phase_file_traversal_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text(
        '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "../../etc/passwd"\n')
    run = eh.load_run(tmp_path)
    assert run is not None
    assert run.phase_texts == {}  # escaping path never read
    result = eh.ReferencePresenceScorer().score(run, _scenario(tmp_path))
    assert result.verdict == eh.VERDICT_FAIL           # reported missing, not read


# --- reference scorer ------------------------------------------------------

def test_reference_scorer_passes_when_all_phases_present() -> None:
    result = eh.ReferencePresenceScorer().score(
        eh.load_run(FIXTURES / "compliant" / "run"), _scenario(Path(".")))
    assert result.verdict == eh.VERDICT_PASS
    assert result.score_pct == 100.0
    assert result.kind is eh.ScorerKind.DETERMINISTIC


def test_reference_scorer_fails_on_missing_phase() -> None:
    result = eh.ReferencePresenceScorer().score(
        eh.load_run(FIXTURES / "non_compliant" / "run"), _scenario(Path(".")))
    assert result.verdict == eh.VERDICT_FAIL
    assert result.score_pct == 0.0
    assert any("phase-2.md" in finding for finding in result.findings)


def test_reference_scorer_unknown_when_run_absent() -> None:
    result = eh.ReferencePresenceScorer().score(None, _scenario(Path(".")))
    assert result.verdict == eh.VERDICT_UNKNOWN
    assert result.score_pct is None


def test_reference_scorer_survives_non_dict_phases(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('phases = ["x"]\n[plan]\ntask = "t"\n')
    result = eh.ReferencePresenceScorer().score(eh.load_run(tmp_path), _scenario(tmp_path))
    assert result.verdict == eh.VERDICT_UNKNOWN     # zero phases → unscoreable, not a crash


def test_reference_scorer_unknown_when_no_phases(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text('[plan]\ntask = "t"\n')
    result = eh.ReferencePresenceScorer().score(eh.load_run(tmp_path), _scenario(tmp_path))
    assert result.verdict == eh.VERDICT_UNKNOWN
    assert result.score_pct is None


def test_reference_scorer_ignores_fileless_phase(tmp_path: Path) -> None:
    (tmp_path / "plan.toml").write_text(
        '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "p.md"\n[[phases]]\nnumber = 2\n')
    (tmp_path / "p.md").write_text("# p\n")
    result = eh.ReferencePresenceScorer().score(eh.load_run(tmp_path), _scenario(tmp_path))
    assert result.verdict == eh.VERDICT_PASS


def test_reference_scorer_unknown_when_no_checkable_file(tmp_path: Path) -> None:
    # Every phase omits `file` → nothing verifiable → UNKNOWN, not a vacuous 100% pass.
    (tmp_path / "plan.toml").write_text(
        '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\n[[phases]]\nnumber = 2\n')
    result = eh.ReferencePresenceScorer().score(eh.load_run(tmp_path), _scenario(tmp_path))
    assert result.verdict == eh.VERDICT_UNKNOWN
    assert result.score_pct is None


# --- load_scenarios --------------------------------------------------------

def test_load_scenarios_discovers_fixture_suite() -> None:
    assert [s.id for s in eh.load_scenarios(FIXTURES)] == ["compliant-run", "non-compliant-run"]


def test_load_scenarios_skips_malformed_and_idless(tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "scenario.toml").write_text("= = broken")
    (tmp_path / "noid").mkdir()
    (tmp_path / "noid" / "scenario.toml").write_text('[scenario]\nworkflow = "w"\n')
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "scenario.toml").write_text('[scenario]\nid = "good"\n')
    assert [s.id for s in eh.load_scenarios(tmp_path)] == ["good"]


def test_load_scenarios_skips_duplicate_ids(tmp_path: Path) -> None:
    # Two descriptors claiming the same id would make calibration identities (covered/excluded/
    # rows) ambiguous — the first by sorted path is kept, the later duplicate is skipped.
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "scenario.toml").write_text('[scenario]\nid = "dup"\n')
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "scenario.toml").write_text('[scenario]\nid = "unique"\n')
    assert [s.id for s in eh.load_scenarios(tmp_path)] == ["dup", "unique"]   # one "dup", not two


def test_load_scenarios_skips_scalar_scenario_section(tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "scenario.toml").write_text('scenario = "not a table"\n')
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "scenario.toml").write_text('[scenario]\nid = "ok"\n')
    assert [s.id for s in eh.load_scenarios(tmp_path)] == ["ok"]


def test_load_scenarios_reads_optional_gold_path(tmp_path: Path) -> None:
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "scenario.toml").write_text(
        '[scenario]\nid = "g"\n[scenario.gold]\npath = "gold.toml"\n')
    scenario = eh.load_scenarios(tmp_path)[0]
    assert scenario.gold_path == tmp_path / "g" / "gold.toml"
    assert scenario.run_dir == tmp_path / "g" / "run"


def test_load_scenarios_skips_absolute_run_dir(tmp_path: Path) -> None:
    (tmp_path / "abs").mkdir()
    (tmp_path / "abs" / "scenario.toml").write_text('[scenario]\nid = "abs"\nrun_dir = "/tmp/x"\n')
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "scenario.toml").write_text('[scenario]\nid = "ok"\n')
    assert [s.id for s in eh.load_scenarios(tmp_path)] == ["ok"]


def test_load_scenarios_skips_dotdot_escape(tmp_path: Path) -> None:
    (tmp_path / "esc").mkdir()
    (tmp_path / "esc" / "scenario.toml").write_text(
        '[scenario]\nid = "esc"\nrun_dir = "../../elsewhere"\n')
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "scenario.toml").write_text('[scenario]\nid = "ok"\n')
    assert [s.id for s in eh.load_scenarios(tmp_path)] == ["ok"]


def test_load_scenarios_ignores_absolute_gold_path(tmp_path: Path) -> None:
    (tmp_path / "g").mkdir()
    (tmp_path / "g" / "scenario.toml").write_text(
        '[scenario]\nid = "g"\n[scenario.gold]\npath = "/abs/gold.toml"\n')
    assert eh.load_scenarios(tmp_path)[0].gold_path is None


# --- run_scenario / run_suite ----------------------------------------------

def test_run_scenario_isolates_a_raising_scorer(tmp_path: Path) -> None:
    class _Boom:
        name = "boom"
        kind = eh.ScorerKind.DETERMINISTIC

        def score(self, run, scenario):
            raise RuntimeError("kaboom")

    result = eh.run_scenario(_scenario(tmp_path), [_Boom()]).results[0]
    assert result.verdict == eh.VERDICT_UNKNOWN
    assert "kaboom" in result.findings[0]


def test_run_suite_scores_the_fixture_suite() -> None:
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    verdicts = {sr.scenario_id: sr.results[0].verdict for sr in report.scenarios}
    assert verdicts == {"compliant-run": eh.VERDICT_PASS, "non-compliant-run": eh.VERDICT_FAIL}


# --- compliance + the gate contract ----------------------------------------

def test_structural_compliance_is_deterministic_pass_ratio() -> None:
    assert eh.structural_compliance(eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])) == 0.5


def test_advisory_verdicts_never_affect_compliance() -> None:
    report = _report(_result(eh.ScorerKind.DETERMINISTIC, eh.VERDICT_PASS),
                     _result(eh.ScorerKind.ADVISORY, eh.VERDICT_FAIL))
    assert eh.structural_compliance(report) == 1.0            # advisory FAIL ignored
    assert eh.gate_exit_code(eh.structural_compliance(report), True, 1.0) == 0


def test_compliance_is_none_when_nothing_deterministic_scored() -> None:
    report = _report(_result(eh.ScorerKind.DETERMINISTIC, eh.VERDICT_UNKNOWN))
    assert eh.structural_compliance(report) is None


def test_gate_is_opt_in_and_threshold_aware() -> None:
    assert eh.gate_exit_code(0.5, False, 1.0) == 0     # no --check → never gates
    assert eh.gate_exit_code(0.5, True, 1.0) == 2      # below floor → exit 2
    assert eh.gate_exit_code(1.0, True, 1.0) == 0      # meets floor
    assert eh.gate_exit_code(0.5, True, 0.4) == 0      # above a lower floor
    # Nothing scored under a positive floor is a failure to assess, not a pass (HYP-2961) —
    # the same rule spec-coverage applies. A non-positive floor demands nothing, so it clears.
    assert eh.gate_exit_code(None, True, 1.0) == 2     # positive floor, nothing scored → fail
    assert eh.gate_exit_code(None, True, 0.0) == 0     # no floor demanded → empty is fine
    assert eh.gate_exit_code(None, False, 1.0) == 0    # no --check → never gates, even empty


# --- report serialisation --------------------------------------------------

def test_report_to_dict_shape_and_histogram() -> None:
    payload = eh.report_to_dict(eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()]))
    summary = payload["summary"]
    assert payload["schema_version"] == eh.SCHEMA_VERSION
    assert summary["scenarios"] == 2
    assert summary["structural_compliance"] == 0.5
    assert "reference-presence (deterministic)" in summary["coverage"]
    assert payload["failing_checks"] == {"reference-presence": 1}   # the non-compliant one
    per = {row["scenario"]: row for row in payload["per_scenario"]}
    assert per["compliant-run"]["compliance"] == 1.0
    assert per["compliant-run"]["expect"] == "compliant"
    assert per["non-compliant-run"]["compliance"] == 0.0


def test_report_counts_unknown_separately(tmp_path: Path) -> None:
    (tmp_path / "u").mkdir()
    (tmp_path / "u" / "scenario.toml").write_text('[scenario]\nid = "u"\n')  # run absent → UNKNOWN
    payload = eh.report_to_dict(eh.run_suite(tmp_path, [eh.ReferencePresenceScorer()]))
    assert payload["summary"]["scored"] == 0
    assert payload["summary"]["unknown"] == 1
    assert payload["summary"]["structural_compliance"] is None


def test_report_notes_when_no_scorers_ran(tmp_path: Path) -> None:
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "scenario.toml").write_text('[scenario]\nid = "s"\n')
    payload = eh.report_to_dict(eh.run_suite(tmp_path, []))
    assert payload["summary"]["coverage"] == "no scorers ran"
    assert payload["failing_checks"] == {}


# --- bucketed regression diff ----------------------------------------------

def test_diff_reports_flags_regression_and_removal() -> None:
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])   # compliant 1.0, non 0.0
    baseline = {"summary": {"structural_compliance": 1.0}, "per_scenario": [
        {"scenario": "compliant-run", "compliance": 1.0},
        {"scenario": "non-compliant-run", "compliance": 1.0},   # 1.0 → 0.0 = regressed
        {"scenario": "gone", "compliance": 1.0}]}               # removed = no-longer-scoreable
    diff = eh.diff_reports(report, baseline)
    assert [r["scenario"] for r in diff["regressed"]] == ["non-compliant-run"]
    assert [r["scenario"] for r in diff["no_longer_scoreable"]] == ["gone"]
    assert diff["has_regression"] is True
    assert diff["aggregate_before"] == 1.0
    assert diff["aggregate_after"] == 0.5


def test_diff_reports_flags_improvement_and_newly_scoreable() -> None:
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])   # compliant 1.0, non 0.0
    baseline = {"summary": {"structural_compliance": 0.0}, "per_scenario": [
        {"scenario": "compliant-run", "compliance": 0.0}]}            # 0.0 → 1.0 = improved;
    diff = eh.diff_reports(report, baseline)                           # non-compliant absent = newly
    assert [r["scenario"] for r in diff["improved"]] == ["compliant-run"]
    assert [r["scenario"] for r in diff["newly_scoreable"]] == ["non-compliant-run"]
    assert diff["has_regression"] is False


def test_diff_reports_broke_scenario_is_a_regression(tmp_path: Path) -> None:
    # A scenario still in the suite but whose run no longer scores (broke) IS a regression.
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "scenario.toml").write_text('[scenario]\nid = "x"\n')   # no run → UNKNOWN
    report = eh.run_suite(tmp_path, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {"structural_compliance": 1.0},
                "per_scenario": [{"scenario": "x", "compliance": 1.0}]}
    diff = eh.diff_reports(report, baseline)
    assert [r["scenario"] for r in diff["regressed"]] == ["x"]
    assert diff["has_regression"] is True


def test_diff_reports_ignores_non_numeric_baseline_compliance(tmp_path: Path) -> None:
    # A hand-corrupted baseline (string compliance) must not crash diff_reports.
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {}, "per_scenario": [
        {"scenario": "compliant-run", "compliance": "0.9"},   # non-numeric → no comparison
        {"scenario": "non-compliant-run"}]}                   # missing key → no comparison
    diff = eh.diff_reports(report, baseline)
    assert diff["has_regression"] is False
    assert diff["regressed"] == []


def test_diff_reports_ignores_boolean_compliance() -> None:
    # bool is a subclass of int; a baseline `true`/`false` must not be read as a score.
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])   # non-compliant-run = 0.0
    baseline = {"summary": {}, "per_scenario": [
        {"scenario": "non-compliant-run", "compliance": True}]}       # true → no comparison
    diff = eh.diff_reports(report, baseline)
    assert diff["has_regression"] is False
    assert diff["regressed"] == []


def test_diff_reports_skips_non_string_scenario_id() -> None:
    # A baseline row whose scenario id is unhashable/non-string must not crash diff_reports.
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {}, "per_scenario": [
        {"scenario": [], "compliance": 0.5},        # unhashable id
        {"scenario": 123, "compliance": 0.5}]}      # non-string id
    diff = eh.diff_reports(report, baseline)
    assert diff["has_regression"] is False


def test_diff_reports_robust_to_bad_baseline_shape() -> None:
    # diff_reports is a public util; a wrong-shaped baseline must not crash it.
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    diff = eh.diff_reports(report, {"per_scenario": "nope", "summary": "nope"})
    assert diff["has_regression"] is False
    assert diff["aggregate_before"] is None


def test_diff_reports_identical_has_no_regression() -> None:
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    diff = eh.diff_reports(report, eh.report_to_dict(report))
    assert diff["has_regression"] is False
    assert diff["regressed"] == []
    assert diff["improved"] == []


# --- a baseline that is not a number in any usable sense --------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")],
                         ids=["nan", "inf", "-inf"])
def test_diff_reports_treats_a_non_finite_baseline_as_no_baseline(bad: float) -> None:
    """NaN survived the type guard and then vanished through comparison.

    `isinstance(before, (int, float))` accepts NaN -- it is a float. Every comparison
    against it is then False, so `now < before` and `now > before` both fail and the
    scenario joined neither bucket: `has_regression` stayed False for a drop from a
    corrupt baseline to zero. Non-finite means "no usable baseline", which the module
    already has a behaviour for.
    """
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])   # compliant 1.0, non 0.0
    baseline = {"summary": {}, "per_scenario": [
        {"scenario": "non-compliant-run", "compliance": bad}]}

    diff = eh.diff_reports(report, baseline)

    assert diff["regressed"] == []
    # Not silently dropped either: with no baseline to compare against, a scenario that
    # scores now is newly scoreable, exactly as a missing entry would be.
    assert "non-compliant-run" in [r["scenario"] for r in diff["newly_scoreable"]]


def test_diff_reports_still_flags_a_real_regression_beside_a_nan_one() -> None:
    """The guard must not swallow the scenarios around it."""
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {}, "per_scenario": [
        {"scenario": "non-compliant-run", "compliance": 1.0},        # 1.0 → 0.0, regressed
        {"scenario": "compliant-run", "compliance": float("nan")}]}  # unusable

    diff = eh.diff_reports(report, baseline)

    assert [r["scenario"] for r in diff["regressed"]] == ["non-compliant-run"]
    assert diff["has_regression"] is True


def test_a_non_finite_baseline_for_a_departed_scenario_is_not_reported() -> None:
    """The same guard governs the `no_longer_scoreable` tail."""
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {}, "per_scenario": [
        {"scenario": "gone", "compliance": float("nan")}]}

    diff = eh.diff_reports(report, baseline)

    assert diff["no_longer_scoreable"] == []


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "0.9", None],
                         ids=["nan", "inf", "bool", "string", "none"])
def test_a_corrupt_aggregate_baseline_is_reported_as_missing(bad: object) -> None:
    """The aggregate was left unguarded while the per-scenario values were hardened.

    It is the number a reader *sees*: NaN rendered beside a real `aggregate_after` reads
    as a measurement rather than as missing data, and `True` renders as `True` (#234
    review).
    """
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {"structural_compliance": bad}, "per_scenario": []}

    assert eh.diff_reports(report, baseline)["aggregate_before"] is None


def test_a_usable_aggregate_baseline_still_comes_through() -> None:
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {"structural_compliance": 0.75}, "per_scenario": []}

    assert eh.diff_reports(report, baseline)["aggregate_before"] == 0.75


class TestTheDeclaredOracleIsCompared:
    """`expect` travelled into the report for this and nothing performed the comparison."""

    @staticmethod
    def _result(scenario_id: str, expect: str, verdict: str):
        return eh.ScenarioResult(scenario_id, "wf", [eh.ScorerResult(
            "structural", eh.ScorerKind.DETERMINISTIC, verdict,
            0.0 if verdict == eh.VERDICT_FAIL else 100.0, [], "")], expect)

    def test_a_scenario_that_does_not_score_what_it_declares_is_named(self) -> None:
        """The field carried a comment reading "surfaced for declared-vs-actual" and nothing
        compared it to anything. A fixture written to demonstrate a failure could stop
        demonstrating it and the suite would read healthier, not worse — it simply contributed
        less. Raised by QA as the clincher on a neighbouring defect.
        """
        rows = eh.oracle_mismatches([
            self._result("wants-fail-but-passed", "non_compliant", eh.VERDICT_PASS),
            self._result("wants-pass-but-failed", "compliant", eh.VERDICT_FAIL),
        ])
        assert len(rows) == 2, rows
        assert any("wants-fail-but-passed" in r and "expects FAIL" in r for r in rows), rows
        assert any("wants-pass-but-failed" in r and "expects PASS" in r for r in rows), rows

    def test_an_unscoreable_scenario_counts_as_a_mismatch_against_either_claim(self) -> None:
        """This is the shape that hides: the suite looks smaller rather than worse.

        A scenario declaring itself non-compliant that comes back UNKNOWN is dropped from the
        denominator, so nothing about the result says the claim went unchecked.
        """
        rows = eh.oracle_mismatches([
            self._result("claims-but-unscoreable", "non_compliant", eh.VERDICT_UNKNOWN)])
        assert len(rows) == 1, rows
        assert "UNKNOWN" in rows[0], rows

    @pytest.mark.parametrize("expect", ["compliant", "non_compliant"])
    def test_unknown_is_a_mismatch_against_either_claim_not_just_one(self, expect: str) -> None:
        """Only the `non_compliant` half was exercised, so an asymmetric special case for
        `compliant` would have gone unnoticed. The rule is symmetric; the test now is too.
        Raised in review."""
        rows = eh.oracle_mismatches([self._result("s", expect, eh.VERDICT_UNKNOWN)])
        assert len(rows) == 1, rows
        assert "UNKNOWN" in rows[0], rows
        assert eh.gating_oracle_mismatches([self._result("s", expect, eh.VERDICT_UNKNOWN)]) == []

    @pytest.mark.parametrize("expect, verdict", [
        ("compliant", eh.VERDICT_PASS), ("non_compliant", eh.VERDICT_FAIL),
        ("unknown", eh.VERDICT_PASS), ("unknown", eh.VERDICT_FAIL), ("unknown", eh.VERDICT_UNKNOWN),
    ])
    def test_agreement_and_an_absent_claim_are_never_mismatches(
            self, expect: str, verdict: str) -> None:
        """`unknown` claims nothing, so it can never disagree — otherwise every scenario that
        declines to predict its own outcome would be reported as broken."""
        assert eh.oracle_mismatches([self._result("s", expect, verdict)]) == []


class TestTheLoaderRecordsWhatTheManifestIgnores:
    """The fact the scorers act on has to be gathered where the directory is visible."""

    def test_phase_files_the_manifest_does_not_declare_are_recorded(self, tmp_path) -> None:
        """Collected in the loader, not the scorer, on purpose.

        Only the loader knows the run directory. A scorer that went back to disk for this
        would be reading a tree that may have moved since the snapshot the rest of the report
        was built from, and the suite deliberately loads once so report and calibration can
        never measure different versions of the same files.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text('[plan]\ntask = "t"\ntotal_phases = 2\n',
                                           encoding="utf-8")
        (run_dir / "phase-01-a.md").write_text("body", encoding="utf-8")
        (run_dir / "phase-02-b.md").write_text("body", encoding="utf-8")
        (run_dir / "notes.md").write_text("not a phase file", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.phases == [], run.phases
        assert run.undeclared_phase_files == ["phase-01-a.md", "phase-02-b.md"], \
            run.undeclared_phase_files

    def test_a_file_the_manifest_does_declare_is_not_reported_as_undeclared(
            self, tmp_path) -> None:
        """Otherwise every ordinary run would look broken — the guard has to distinguish
        'present and claimed' from 'present and ignored', which is the whole distinction it
        exists to draw."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text(
            '[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
            'file = "phase-01-a.md"\n', encoding="utf-8")
        (run_dir / "phase-01-a.md").write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.undeclared_phase_files == [], run.undeclared_phase_files


class TestWhatTheFirstVersionOfThisChangeGotWrong:
    """Six defects, all introduced by the fix above. Each case is one of them."""

    @staticmethod
    def _r(sid, expect, verdict):
        return eh.ScenarioResult(sid, "wf", [eh.ScorerResult(
            "structural", eh.ScorerKind.DETERMINISTIC, verdict,
            0.0 if verdict == eh.VERDICT_FAIL else 100.0, [], "")], expect)

    def test_an_unscoreable_scenario_is_reported_but_never_gates(self) -> None:
        """The contract is that unscoreable is not a failure, and the first version broke it.

        Gating on every mismatch meant a suite of one healthy scenario and one unreadable
        `plan.toml` printed 100% compliance and exited 2 — inverted by a change whose whole
        subject was how unscoreable runs are treated. Reporting and gating are separate
        questions and now have separate functions.
        """
        rows = [self._r("cannot-load", "non_compliant", eh.VERDICT_UNKNOWN)]
        assert eh.oracle_mismatches(rows), "still worth reporting"
        assert eh.gating_oracle_mismatches(rows) == [], "must not fail a build"

    @pytest.mark.parametrize("expect, verdict", [
        ("compliant", eh.VERDICT_FAIL),
        ("non_compliant", eh.VERDICT_PASS),
    ])
    def test_a_definite_disagreement_still_gates(self, expect: str, verdict: str) -> None:
        """Otherwise the fix above would have removed the guard rather than bounded it.

        Both directions, because only the `compliant` + FAIL one was asserted here. The other
        was exercised through `oracle_mismatches`, which is a different function with a
        different rule, so narrowing `definite` to `{VERDICT_FAIL}` left the whole suite green
        while a scenario claiming non-compliance could pass without failing a build. Raised in
        review; confirmed by that mutation before this test was written.
        """
        rows = [self._r("mislabelled", expect, verdict)]
        assert eh.gating_oracle_mismatches(rows), rows

    def test_a_declared_file_written_with_a_leading_dot_is_not_called_undeclared(
            self, tmp_path) -> None:
        """`Path.name` was differenced against the raw manifest string.

        A plan declaring `./phase-1.md` therefore reported that file as undeclared, and a
        scorer acting on that returned FAIL 0.0 where the honest answer was UNKNOWN — the
        false 0% this scorer promises never to produce, reintroduced through a string compare.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text(
            '[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
            'file = "./phase-1.md"\n', encoding="utf-8")
        (run_dir / "phase-1.md").write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.undeclared_phase_files == [], run.undeclared_phase_files

    def test_an_unrecognised_expect_is_warned_about_not_silently_ignored(
            self, tmp_path, caplog) -> None:
        """`expect` decides whether a scenario is checked against its own claim at all.

        One typo — `non-compliant` for `non_compliant` — opted a scenario out of the
        comparison with nothing anywhere saying so. It still degrades to `unknown` rather than
        raising, because one malformed descriptor must not sink a suite; the warning is what
        makes the opt-out visible.
        """
        import logging  # noqa: PLC0415

        scenario = tmp_path / "s"
        scenario.mkdir()
        (scenario / "scenario.toml").write_text(
            '[scenario]\nid = "s"\nworkflow = "w"\nrun_dir = "run"\n'
            'expect = "non-compliant"\n', encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger=eh.logger.name):
            loaded = eh.load_scenarios(tmp_path)

        # Kept **as written**, not rewritten to "unknown". Normalising it made a typo
        # indistinguishable from a deliberate no-claim: the report showed `unknown` for both,
        # so the only trace was a log line. Left alone, a reader sees the hyphen in the report.
        assert loaded[0].expect == "non-compliant", loaded[0]
        assert any("not one of compliant" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]
        # ...and it still claims nothing, so it can never be reported as a mismatch.
        result = eh.ScenarioResult("s", "w", [eh.ScorerResult(
            "structural", eh.ScorerKind.DETERMINISTIC, eh.VERDICT_FAIL, 0.0, [], "")],
            loaded[0].expect)
        assert eh.oracle_mismatches([result]) == []



class TestWhatTheSecondRoundOfReviewFound:
    """Cases the first fix drew its line just short of. One more lives in the structural tests."""

    def test_a_scenario_with_no_deterministic_result_resolves_to_unknown(self) -> None:
        """Both functions `continue`d past it, contradicting their own stated policy.

        The docstrings say UNKNOWN counts against either claim — and the scenario that produced
        nothing at all to judge was the one being skipped. Raised in review.
        """
        advisory_only = eh.ScenarioResult("no-deterministic", "w", [eh.ScorerResult(
            "judge", eh.ScorerKind.ADVISORY, eh.VERDICT_UNKNOWN, None, [], "")], "non_compliant")

        assert eh.oracle_mismatches([advisory_only]), "a claim nothing assessed is still a claim"
        assert eh.gating_oracle_mismatches([advisory_only]) == [], "but it must not gate"

    def test_a_nested_orphan_phase_file_is_seen(self, tmp_path) -> None:
        """The orphan scan saw less than the loader it guards.

        `load_run` accepts any relative path beneath the run directory as a declared phase
        file, so a non-recursive glob for orphans missed exactly the nested file the manifest
        had ignored. Raised in review; reported relative to the run directory so a nested
        orphan is identifiable rather than just named.
        """
        run_dir = tmp_path / "run"
        (run_dir / "steps").mkdir(parents=True)
        (run_dir / "plan.toml").write_text('[plan]\ntask = "t"\ntotal_phases = 1\n',
                                           encoding="utf-8")
        (run_dir / "steps" / "phase-01-a.md").write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.undeclared_phase_files == ["steps/phase-01-a.md"], run.undeclared_phase_files

class TestTheTwoPathNormalisationsMustAgree:
    """`load_run` normalises a manifest `file` twice, and the pair is the defect surface.

    Once to open the file, once to build the declared set the orphan scan subtracts. The
    comments at both sites record that rewriting only one of them is how this broke before —
    twice — each time producing the same shape: a file read but still called an orphan, or a
    file skipped but counted as declared. Named for the subject rather than a review round,
    because the pair outlives the round that found it unguarded.
    """

    def test_a_manifest_path_written_with_backslashes_is_read_and_counted_as_declared(
            self, tmp_path) -> None:
        """Both normalisations, pinned together — they are the pair that broke twice.

        `load_run` normalises a manifest `file` in two places: once to open the file, and once
        to build the declared set the orphan scan subtracts. The comments at both sites record
        that rewriting only one of them is how this went wrong before, each time producing the
        same shape — a file read but still reported as an orphan, or vice versa. Nothing in the
        suite declared a path with a backslash, so either half could be dropped silently.

        Asserting both halves in one test is the point: the bug is disagreement between them,
        which neither half can show on its own. Raised in review.
        """
        run_dir = tmp_path / "run"
        (run_dir / "steps").mkdir(parents=True)
        (run_dir / "plan.toml").write_text(
            '[plan]\ntask = "t"\ntotal_phases = 1\n'
            '[[phases]]\nnumber = 1\nfile = "steps\\\\phase-1.md"\n', encoding="utf-8")
        (run_dir / "steps" / "phase-1.md").write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        # read: the backslash path resolved to a file that was actually opened
        assert any("phase-1.md" in key for key in run.phase_texts), run.phase_texts
        # declared: and the same file is not then reported as an orphan of itself
        assert run.undeclared_phase_files == [], run.undeclared_phase_files


class TestWhatTheThirdRoundFound:
    """Side effects of the second round's fixes — each fix broke a neighbouring one."""

    @staticmethod
    def _run(phases, undeclared):
        return eh.RunArtifacts({"task": "t"}, phases, {}, undeclared)

    def test_the_finding_does_not_claim_a_manifest_declares_nothing_when_it_declares_two(
            self) -> None:
        """The false message, reintroduced by widening the condition and not the sentence.

        A manifest listing two entries that carry no `file` declares phases perfectly well.
        Saying "the plan declares no phases" about it was a defect this change had already
        fixed once, in the same file, with a comment warning against it. Raised in review.
        """
        finding = eh.lost_run_finding(self._run([{"number": 1}, {"number": 2}], ["p.md"]))

        assert finding is not None
        assert "declares no phases" not in finding, finding
        assert "names no phase file" in finding, finding

    def test_a_nested_orphan_is_not_excused_by_a_top_level_declaration(self, tmp_path) -> None:
        """The scan was widened to `rglob` while the comparison still used base names.

        So a nested `old/phase-1.md` was matched against a top-level declaration of
        `phase-1.md` and silently excused — the orphan the wider scan existed to find. Both
        halves of a comparison have to be widened together. Raised in review.
        """
        run_dir = tmp_path / "run"
        (run_dir / "old").mkdir(parents=True)
        (run_dir / "plan.toml").write_text(
            '[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
            'file = "phase-1.md"\n', encoding="utf-8")
        (run_dir / "phase-1.md").write_text("body", encoding="utf-8")
        (run_dir / "old" / "phase-1.md").write_text("an orphan", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.undeclared_phase_files == ["old/phase-1.md"], run.undeclared_phase_files

    def test_a_non_string_expect_is_not_reported_as_a_string_nobody_wrote(
            self, tmp_path, caplog) -> None:
        """TOML `expect = true` reached the report as the string "True". Raised in review."""
        import logging  # noqa: PLC0415

        scenario = tmp_path / "s"
        scenario.mkdir()
        (scenario / "scenario.toml").write_text(
            '[scenario]\nid = "s"\nworkflow = "w"\nrun_dir = "run"\nexpect = true\n',
            encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger=eh.logger.name):
            loaded = eh.load_scenarios(tmp_path)

        assert loaded[0].expect == "unknown", loaded[0]
        assert any("not a string" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]


class TestTheOneShapeThisChangeCovers:
    """Narrowed deliberately, after six rounds of widening produced a defect each time."""

    def test_a_plan_naming_nothing_beside_real_phase_files_is_a_lost_run(
            self, tmp_path) -> None:
        """The case this change set out to fix, and now the only one it claims.

        It scored UNKNOWN and was excluded from the denominator, so the worse a run was broken
        the less it moved the headline. The evidence needs nothing but the manifest and a
        directory listing: the plan names no phase file, and phase files are sitting there
        unclaimed.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text('[plan]\ntask = "t"\ntotal_phases = 2\n',
                                           encoding="utf-8")
        for name in ("phase-01.md", "phase-02.md"):
            (run_dir / name).write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.undeclared_phase_files == ["phase-01.md", "phase-02.md"]
        finding = eh.lost_run_finding(run)
        assert finding is not None
        assert "names no phase file" in finding, finding

    def test_every_orphan_is_reported_not_a_truncated_prefix(self, tmp_path) -> None:
        """A capped version of this was tried and reverted.

        Truncating the list corrupted every count derived from it — the finding said "(+97
        more)" and the coverage line "100" for 105 orphans — and it did not bound the walk
        either, because `sorted` materialises the whole result before any slice. The list is
        complete, and the finding names three of them with an accurate overflow count.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text('[plan]\ntask = "t"\ntotal_phases = 1\n',
                                           encoding="utf-8")
        for i in range(105):
            (run_dir / f"phase-{i:04d}.md").write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert len(run.undeclared_phase_files) == 105, len(run.undeclared_phase_files)
        assert "+102 more" in eh.lost_run_finding(run), eh.lost_run_finding(run)
        assert eh._lost_run_coverage(run) == "105 undeclared phase file(s)"

    @pytest.mark.parametrize("declared, orphan", [
        ("phase-1.md", "steps/phase-1.md"),   # same base name, different file
        ("steps/phase-1.md", "phase-1.md"),   # and the other way round
    ])
    def test_a_file_is_only_declared_if_the_manifest_names_that_path(
            self, tmp_path, declared, orphan) -> None:
        """`undeclared_phase_files` carries its own contract, whatever the finding uses it for.

        Compared by base name, a nested `steps/phase-1.md` was excused by a top-level
        declaration of `phase-1.md` — the orphan the recursive scan exists to find. Both sides
        are relative paths. Asserted directly on the field, because the narrowed finding only
        fires when the plan names nothing, so it cannot exercise this by itself.
        """
        run_dir = tmp_path / "run"
        (run_dir / "steps").mkdir(parents=True)
        (run_dir / "plan.toml").write_text(
            f'[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
            f'file = "{declared}"\n', encoding="utf-8")
        for name in (declared, orphan):
            (run_dir / name).write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert run.undeclared_phase_files == [orphan], run.undeclared_phase_files

    def test_a_named_file_with_broken_frontmatter_fails_rather_than_staying_unknown(
            self, tmp_path) -> None:
        """The distinction the spec draws: outside *this finding* is not the same as UNKNOWN.

        An earlier wording said a plan naming any file "stays UNKNOWN". It does not — a named
        file whose `[phase]` block will not parse scores FAIL through the ordinary checks, and a
        parsing one can score either way. Raised in review; asserted here so the claim cannot
        drift back.
        """
        from studio.utils.eval_structural import StructuralScorer  # noqa: PLC0415

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text(
            '[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
            'file = "phase-1.md"\n', encoding="utf-8")
        (run_dir / "phase-1.md").write_text(
            '```toml\n[phase]\nnumber = "not a number"\n```\n\n# P\n', encoding="utf-8")

        run = eh.load_run(run_dir)
        assert run is not None
        scenario = eh.Scenario(id="s", workflow="w", run_dir=Path("run"), expect="unknown")

        assert eh.lost_run_finding(run) is None, "outside this finding"
        assert StructuralScorer().score(run, scenario).verdict == eh.VERDICT_FAIL

    @pytest.mark.parametrize("plan, files, why", [
        ('[plan]\ntask = "t"\ntotal_phases = 1\n', [], "names nothing, nothing on disk"),
        ('[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
         'file = "phase-1.md"\n', ["phase-1.md"], "names a file that is there"),
        ('[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
         'file = "phase-a.md"\n', ["phase-1.md"], "names a file that is not there"),
        ('[plan]\ntask = "t"\ntotal_phases = 1\n\n[[phases]]\nnumber = 1\n'
         'file = "../phase-1.md"\n', ["phase-1.md"], "names a file outside the run dir"),
    ])
    def test_every_other_shape_keeps_the_verdict_it_had_before(
            self, tmp_path, plan, files, why) -> None:
        """Each of these was failed by some earlier version of this change, and each widening
        needed another fact about the loader's internals — a path normalised in one place and
        not another, an entry counted as declared before the read that proved it absent, a
        relative-path computation that could raise and abort the whole suite.

        A plan that names any file at all is outside **this finding**, whatever became of that
        file. This asserts only that the finding does not fire — deliberately nothing about the
        verdict, which the ordinary path decides and which for these four fixtures (phase files
        containing no frontmatter block) is UNKNOWN.

        Two earlier wordings here were wrong in opposite directions: the first claimed these
        runs stay UNKNOWN, the second that they score PASS or FAIL. Both were describing the
        verdict, which is not what this test checks. Raised in review, twice.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "plan.toml").write_text(plan, encoding="utf-8")
        for name in files:
            (run_dir / name).write_text("body", encoding="utf-8")

        run = eh.load_run(run_dir)

        assert run is not None
        assert eh.lost_run_finding(run) is None, why
