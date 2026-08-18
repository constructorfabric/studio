"""Unit tests for the workflow eval-harness scaffold."""
from __future__ import annotations

from pathlib import Path

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
    assert result.verdict == eh.VERDICT_PASS           # non-string file ignored, not a crash


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
    assert eh.gate_exit_code(None, True, 1.0) == 0     # nothing scored never fails


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


def test_diff_reports_became_unscoreable_is_a_regression(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "scenario.toml").write_text('[scenario]\nid = "x"\n')   # no run → UNKNOWN
    report = eh.run_suite(tmp_path, [eh.ReferencePresenceScorer()])
    baseline = {"summary": {"structural_compliance": 1.0},
                "per_scenario": [{"scenario": "x", "compliance": 1.0}]}
    diff = eh.diff_reports(report, baseline)
    assert [r["scenario"] for r in diff["no_longer_scoreable"]] == ["x"]
    assert diff["has_regression"]


def test_diff_reports_identical_has_no_regression() -> None:
    report = eh.run_suite(FIXTURES, [eh.ReferencePresenceScorer()])
    diff = eh.diff_reports(report, eh.report_to_dict(report))
    assert diff["has_regression"] is False
    assert diff["regressed"] == []
    assert diff["improved"] == []
