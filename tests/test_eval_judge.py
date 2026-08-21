"""Tests for the advisory LLM-judge (utils.eval_judge)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from studio.utils.eval_harness import (RunArtifacts, Scenario, ScorerKind, gate_exit_code,
                                       structural_compliance, VERDICT_FAIL, VERDICT_PASS,
                                       VERDICT_UNKNOWN, EvalReport, ScenarioResult, ScorerResult)
from studio.utils.eval_judge import (AdvisoryJudge, Calibration, Gold, JudgeReply, JudgeRequest,
                                     build_judge_request, calibrate, load_gold,
                                     reference_stub_judge)


# --- builders --------------------------------------------------------------

def _phase(number: int, rules: Optional[str] = "follow the recipe") -> str:
    body = f"```toml\n[phase]\nnumber = {number}\n```\n\n## What\n\ndo it\n"
    if rules is not None:
        body += f"\n## Rules\n\n{rules}\n"
    return body


def _run(phase_texts=None, plan_meta=None, phases=None) -> RunArtifacts:
    if phase_texts is None:
        phase_texts = {"phase-1.md": _phase(1)}
    if phases is None:
        phases = [{"number": 1, "file": "phase-1.md"}]
    if plan_meta is None:
        plan_meta = {"task": "demo"}
    return RunArtifacts(plan_meta=plan_meta, phases=phases, phase_texts=phase_texts)


def _scenario(gold_path: Optional[Path] = None) -> Scenario:
    return Scenario(id="s", workflow="coding-gen", run_dir=Path("run"),
                    expect="compliant", gold_path=gold_path)


def _stub(verdict: str):
    return lambda request: JudgeReply(verdict=verdict, rationale=f"stub says {verdict}")


# --- prompt building (pure, no model) --------------------------------------

def test_build_request_extracts_rules_and_is_deterministic() -> None:
    run = _run(phase_texts={"phase-1.md": _phase(1, "never edit generated files"),
                            "phase-2.md": _phase(2, "keep steps ordered")})
    req = build_judge_request(run, _scenario())
    assert req.workflow == "coding-gen"
    assert req.rules == ["never edit generated files", "keep steps ordered"]
    assert build_judge_request(run, _scenario()).prompt == req.prompt   # deterministic
    assert "never edit generated files" in req.prompt


def test_phases_without_or_empty_rules_are_skipped() -> None:
    run = _run(phase_texts={"phase-1.md": _phase(1, None),          # no ## Rules
                            "phase-2.md": _phase(2, "   "),          # empty ## Rules
                            "phase-3.md": _phase(3, "a real rule")})
    assert build_judge_request(run, _scenario()).rules == ["a real rule"]


def test_no_rules_declared_prompt_is_still_built() -> None:
    run = _run(phase_texts={"phase-1.md": _phase(1, None)})
    req = build_judge_request(run, _scenario())
    assert req.rules == []
    assert "(no rules declared)" in req.prompt


def test_run_summary_tolerates_non_dict_meta_and_phases() -> None:
    # plan_meta=[] is a non-dict (and not None, so _run keeps it) — exercises the guard branch.
    run = _run(plan_meta=[], phases=[{"number": 1, "file": "p.md"}, "not-a-dict"])
    req = build_judge_request(run, _scenario())
    assert "task: " in req.prompt        # non-dict meta → empty task, no crash


# --- scoring ---------------------------------------------------------------

def test_run_none_is_unknown() -> None:
    result = AdvisoryJudge(_stub("compliant")).score(None, _scenario())
    assert result.verdict == VERDICT_UNKNOWN
    assert result.kind is ScorerKind.ADVISORY


def test_no_judge_fn_is_unknown() -> None:
    result = AdvisoryJudge().score(_run(), _scenario())
    assert result.verdict == VERDICT_UNKNOWN
    assert "no judge model" in result.findings[0]


def test_compliant_and_non_compliant_replies_map_to_pass_fail() -> None:
    assert AdvisoryJudge(_stub("compliant")).score(_run(), _scenario()).verdict == VERDICT_PASS
    assert AdvisoryJudge(_stub("non_compliant")).score(_run(), _scenario()).verdict == VERDICT_FAIL


def test_case_insensitive_and_malformed_reply() -> None:
    assert AdvisoryJudge(_stub("COMPLIANT")).score(_run(), _scenario()).verdict == VERDICT_PASS
    assert AdvisoryJudge(_stub("maybe")).score(_run(), _scenario()).verdict == VERDICT_UNKNOWN
    assert AdvisoryJudge(_stub("")).score(_run(), _scenario()).verdict == VERDICT_UNKNOWN


def test_score_pct_is_none_advisory_never_numeric() -> None:
    assert AdvisoryJudge(_stub("compliant")).score(_run(), _scenario()).score_pct is None


def test_judge_fn_that_raises_degrades_to_unknown() -> None:
    def boom(_request):
        raise RuntimeError("kaboom")
    result = AdvisoryJudge(boom).score(_run(), _scenario())
    assert result.verdict == VERDICT_UNKNOWN
    assert "kaboom" in result.findings[0]


def test_judge_fn_returning_invalid_object_is_unknown_not_crash() -> None:
    # A host that returns None (or any non-JudgeReply) must degrade to UNKNOWN, not AttributeError.
    assert AdvisoryJudge(lambda req: None).score(_run(), _scenario()).verdict == VERDICT_UNKNOWN
    assert AdvisoryJudge(lambda req: object()).score(_run(), _scenario()).verdict == VERDICT_UNKNOWN


def test_coverage_labels_validated_vs_unvalidated(tmp_path: Path) -> None:
    gold = tmp_path / "gold.toml"
    gold.write_text('[gold]\nverdict = "compliant"\n')
    validated = AdvisoryJudge(_stub("compliant")).score(_run(), _scenario(gold_path=gold))
    unvalidated = AdvisoryJudge(_stub("compliant")).score(_run(), _scenario())
    assert "validated" in validated.coverage
    assert "unvalidated" not in validated.coverage
    assert "unvalidated advisory" in unvalidated.coverage


def test_malformed_gold_is_not_reported_as_validated(tmp_path: Path) -> None:
    # A gold_path pointing at a broken gold.toml must read "unvalidated", not "gold-backed".
    bad = tmp_path / "gold.toml"
    bad.write_text("{ not toml")
    result = AdvisoryJudge(_stub("compliant")).score(_run(), _scenario(gold_path=bad))
    assert "unvalidated advisory" in result.coverage


# --- split integrity: advisory never gates ---------------------------------

def test_advisory_fail_never_moves_compliance_or_exit() -> None:
    # A judge that always FAILs alongside a structural PASS must not change the gate.
    results = [ScorerResult("structural", ScorerKind.DETERMINISTIC, VERDICT_PASS, 100.0),
               ScorerResult("rules-judge", ScorerKind.ADVISORY, VERDICT_FAIL, None,
                            ["judge disagrees"])]
    report = EvalReport([ScenarioResult("s", "coding-gen", results, "compliant")])
    compliance = structural_compliance(report)
    assert compliance == 1.0                              # advisory FAIL ignored
    assert gate_exit_code(compliance, True, 1.0) == 0     # gate stays green


# --- gold loading ----------------------------------------------------------

def test_load_gold_valid(tmp_path: Path) -> None:
    p = tmp_path / "gold.toml"
    p.write_text('[gold]\nverdict = "non_compliant"\nrationale = "broke rule 2"\n'
                 'rules_assessed = [1, 2, "x"]\n')
    gold = load_gold(p)
    assert gold is not None
    assert gold.verdict == "non_compliant"
    assert gold.rationale == "broke rule 2"
    assert gold.rules_assessed == [1, 2]        # non-int filtered out


def test_load_gold_none_path_returns_none() -> None:
    assert load_gold(None) is None


def test_load_gold_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_gold(tmp_path / "nope.toml") is None


def test_load_gold_malformed_toml_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text("{ not toml")
    assert load_gold(p) is None


def test_load_gold_missing_section_or_bad_verdict_returns_none(tmp_path: Path) -> None:
    no_section = tmp_path / "a.toml"
    no_section.write_text('title = "x"\n')
    assert load_gold(no_section) is None
    bad_verdict = tmp_path / "b.toml"
    bad_verdict.write_text('[gold]\nverdict = "maybe"\n')
    assert load_gold(bad_verdict) is None


# --- calibration -----------------------------------------------------------

def test_calibrate_accuracy_and_consistency_perfect() -> None:
    cases = [(_scenario(), _run(), Gold(verdict="compliant"))]
    cal = calibrate(cases, _stub("compliant"), runs=3)
    assert cal.accuracy == 1.0
    assert cal.consistency == 1.0
    assert cal.covered == ["s"]
    assert cal.runs_per_scenario == 3
    assert cal.per_scenario[0]["matched"] is True


def test_calibrate_accuracy_zero_on_disagreement() -> None:
    cases = [(_scenario(), _run(), Gold(verdict="compliant"))]
    cal = calibrate(cases, _stub("non_compliant"), runs=3)
    assert cal.accuracy == 0.0


def test_calibrate_consistency_below_one_on_flip_flop() -> None:
    class Flip:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, request: JudgeRequest) -> JudgeReply:
            self.n += 1
            return JudgeReply("compliant" if self.n % 2 else "non_compliant")
    cal = calibrate([(_scenario(), _run(), Gold(verdict="compliant"))], Flip(), runs=4)
    assert cal.consistency == 0.5           # 2 of 4 landed on the majority


def test_calibrate_empty_is_none_not_zero() -> None:
    cal = calibrate([], _stub("compliant"), runs=3)
    assert cal.accuracy is None
    assert cal.consistency is None


def test_calibrate_runs_clamped_to_at_least_one() -> None:
    cal = calibrate([(_scenario(), _run(), Gold(verdict="compliant"))], _stub("compliant"), runs=0)
    assert cal.runs_per_scenario == 1
    assert isinstance(cal, Calibration)


def test_calibrate_excludes_unscoreable_runs_from_metrics() -> None:
    # A case whose run failed to load (None) is a run-loading failure, not a judge miss — it is
    # excluded from accuracy/consistency and reported, so it can't drag the judge's numbers down.
    cases = [(_scenario(), _run(), Gold(verdict="compliant")),                 # scoreable, matches
             (Scenario(id="broken", workflow="w", run_dir=Path("r"), expect="compliant"),
              None, Gold(verdict="compliant"))]                                 # run failed to load
    cal = calibrate(cases, _stub("compliant"), runs=3)
    assert cal.accuracy == 1.0            # the None-run did NOT count as a mismatch
    assert cal.excluded == ["broken"]
    assert "broken" in cal.covered        # still gold-backed coverage


# --- reference stub judge (wiring aid, not a real model) --------------------

def test_reference_stub_judge_scans_evidence_not_rules() -> None:
    # A prohibitive RULE ("must not …") is NOT a violation; a marker in the EVIDENCE is.
    prohibitive_rule = ("```toml\n[phase]\nnumber = 1\n```\n\n## What\n\nwrote the module cleanly\n"
                        "\n## Rules\n\nmust not edit generated files\n")
    violating_work = ("```toml\n[phase]\nnumber = 1\n```\n\n## What\n\nignored the spec here\n"
                      "\n## Rules\n\nfollow the recipe\n")
    clean = build_judge_request(_run(phase_texts={"phase-1.md": prohibitive_rule}), _scenario())
    dirty = build_judge_request(_run(phase_texts={"phase-1.md": violating_work}), _scenario())
    assert reference_stub_judge(clean).verdict == "compliant"       # prohibitive rule, clean work
    assert reference_stub_judge(dirty).verdict == "non_compliant"   # "ignored" is in the evidence


def test_evidence_excludes_the_rules_section() -> None:
    body = ("```toml\n[phase]\nnumber = 1\n```\n\n## What\n\ndid the work\n\n"
            "## Rules\n\nmust not touch prod\n")
    req = build_judge_request(_run(phase_texts={"phase-1.md": body}), _scenario())
    assert "did the work" in req.evidence
    assert "must not touch prod" not in req.evidence     # rule text is kept out of evidence
    assert req.rules == ["must not touch prod"]


def test_evidence_allocates_per_phase_so_later_violations_are_not_hidden() -> None:
    # A long first phase must not swallow the budget and hide a later phase's violation.
    long_first = ("```toml\n[phase]\nnumber = 1\n```\n\n## What\n\n" + "filler " * 1200 + "\n")
    later = ("```toml\n[phase]\nnumber = 2\n```\n\n## What\n\nignored the spec here\n")
    req = build_judge_request(
        _run(phase_texts={"phase-1.md": long_first, "phase-2.md": later}), _scenario())
    assert "[…truncated]" in req.evidence          # the long phase was capped, with a signal
    assert "ignored the spec here" in req.evidence  # the later phase survives
    assert reference_stub_judge(req).verdict == "non_compliant"


def test_evidence_handles_empty_and_contentless_phases() -> None:
    # No phase files → empty evidence (and no divide-by-zero in the per-phase budget).
    assert build_judge_request(_run(phase_texts={}), _scenario()).evidence == ""
    # A phase whose only content is a Rules section contributes no evidence.
    only_rules = build_judge_request(_run(phase_texts={"p.md": "## Rules\nfollow\n"}), _scenario())
    assert only_rules.evidence == ""
