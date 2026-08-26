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


def test_split_ignores_a_rules_heading_inside_a_fenced_block() -> None:
    # A `## Rules` inside a fenced example must not be read as a real section heading — otherwise
    # the negative evidence after it is moved out of evidence and the run can look compliant.
    body = ("## What\n\nwe did the work\n\n"
            "```markdown\n## Rules\nexample rule text\n```\n\n"
            "then we ignored the spec here\n")
    req = build_judge_request(_run(phase_texts={"p.md": body}), _scenario())
    assert "ignored the spec here" in req.evidence          # not hidden by the fenced heading
    assert reference_stub_judge(req).verdict == "non_compliant"


def test_evidence_enforces_a_hard_total_cap_with_an_omission_signal() -> None:
    # Many long phases must not blow the total budget: the whole evidence string — headers,
    # truncation markers, separators and the omission line included — stays within _EVIDENCE_CAP,
    # and the omitted phases are flagged.
    from studio.utils.eval_judge import _EVIDENCE_CAP  # noqa: PLC0415
    phases = {f"phase-{i:02d}.md": f"## What\n\n{'filler ' * 300}\n" for i in range(30)}
    req = build_judge_request(_run(phase_texts=phases), _scenario())
    assert len(req.evidence) <= _EVIDENCE_CAP              # a real hard cap, not ~2x
    assert "omitted to stay within the evidence budget" in req.evidence
    assert req.evidence_incomplete is True


def test_incomplete_evidence_forces_unknown_without_calling_the_model() -> None:
    # When whole phases are omitted, the verdict must be UNKNOWN regardless of the model — a
    # compliant answer would certify phases the judge never saw — and the model is not even called.
    phases = {f"phase-{i:02d}.md": f"## What\n\n{'filler ' * 300}\n" for i in range(30)}
    calls: list = []

    def always_compliant(_request: JudgeRequest) -> JudgeReply:
        calls.append(1)
        return JudgeReply("compliant", "looks fine")

    result = AdvisoryJudge(always_compliant).score(_run(phase_texts=phases), _scenario())
    assert result.verdict == VERDICT_UNKNOWN
    assert calls == []                                    # short-circuited: no model call


def test_trimmed_but_complete_evidence_is_still_judged() -> None:
    # A merely trimmed phase (all phases still shown, with a marker) is NOT incomplete — the judge
    # runs normally, so trimming does not collapse every real run to UNKNOWN.
    phases = {"phase-1.md": f"## What\n\n{'filler ' * 2000}\n"}   # one long phase, trimmed
    req = build_judge_request(_run(phase_texts=phases), _scenario())
    assert "[…truncated]" in req.evidence
    assert req.evidence_incomplete is False


def test_split_ignores_a_rules_heading_inside_a_tilde_fence() -> None:
    # Markdown allows ~~~ fences too — a `## Rules` inside one must not be read as a real heading.
    body = ("## What\n\nwe did the work\n\n"
            "~~~markdown\n## Rules\nexample rule text\n~~~\n\n"
            "then we ignored the spec here\n")
    req = build_judge_request(_run(phase_texts={"p.md": body}), _scenario())
    assert "ignored the spec here" in req.evidence          # not hidden by the tilde-fenced heading
    assert reference_stub_judge(req).verdict == "non_compliant"


def test_rules_and_evidence_follow_manifest_not_filename_order() -> None:
    # The manifest declares phase-2 before phase-1; rules and evidence must follow that order (the
    # same as the run summary), not a filename sort, or the prompt shows THE RUN in a different
    # sequence from RULES/EVIDENCE and distorts a phase-by-phase judgement.
    run = _run(
        phases=[{"number": 2, "file": "phase-2.md"}, {"number": 1, "file": "phase-1.md"}],
        phase_texts={"phase-1.md": "## What\n\nfirst-by-name\n\n## Rules\n\nrule-one\n",
                     "phase-2.md": "## What\n\nsecond-by-name\n\n## Rules\n\nrule-two\n"})
    req = build_judge_request(run, _scenario())
    assert req.rules == ["rule-two", "rule-one"]                       # manifest order, not sorted
    assert req.evidence.index("second-by-name") < req.evidence.index("first-by-name")


def test_a_non_closing_fence_line_does_not_end_the_fence() -> None:
    # A ```-prefixed line with trailing content is NOT a closer (CommonMark: only whitespace may
    # follow a closing fence). A `## Rules` after it stays fenced example text, so later evidence
    # is not moved out of scope and hidden.
    body = ("## What\n\nwe did the work\n\n"
            "```\n"
            "```not-a-closing-fence\n"          # trailing content → not a valid closer
            "## Rules\n"                         # still inside the fence → not a heading
            "```\n\n"                            # the real closer (only fence chars)
            "then we ignored the spec here\n")
    req = build_judge_request(_run(phase_texts={"p.md": body}), _scenario())
    assert "ignored the spec here" in req.evidence
    assert reference_stub_judge(req).verdict == "non_compliant"


def test_missing_declared_phase_is_incomplete_evidence() -> None:
    # A manifest declares two phases but one's text is unreadable (absent from phase_texts). Even
    # though the other phase carries evidence, the run is incomplete → UNKNOWN, judge not called.
    calls: list = []

    def stub(_request: JudgeRequest) -> JudgeReply:
        calls.append(1)
        return JudgeReply("compliant", "looks fine")

    run = _run(phases=[{"number": 1, "file": "phase-1.md"}, {"number": 2, "file": "phase-2.md"}],
               phase_texts={"phase-1.md": "## What\n\ndid the work\n"})   # phase-2 text missing
    result = AdvisoryJudge(stub).score(run, _scenario())
    assert result.verdict == VERDICT_UNKNOWN
    assert calls == []


def test_empty_evidence_is_unscoreable_and_the_judge_is_not_called() -> None:
    # A run whose only content is a Rules section has no usable evidence → UNKNOWN with no model
    # call, so the judge can never certify compliance from nothing observable.
    calls: list = []

    def stub(_request: JudgeRequest) -> JudgeReply:
        calls.append(1)
        return JudgeReply("compliant", "looks fine")

    result = AdvisoryJudge(stub).score(_run(phase_texts={"p.md": "## Rules\nfollow\n"}), _scenario())
    assert result.verdict == VERDICT_UNKNOWN
    assert calls == []


def test_non_string_verdict_degrades_to_unknown_not_raise() -> None:
    # A host reply whose verdict is a truthy non-string (e.g. 123) must degrade to UNKNOWN — the
    # parse runs outside the judge_fn try/except, so a raise here would abort scoring/calibration.
    class _IntVerdict:
        verdict = 123

    result = AdvisoryJudge(lambda _r: _IntVerdict()).score(_run(), _scenario())
    assert result.verdict == VERDICT_UNKNOWN


def test_calibration_excludes_a_crashing_judge() -> None:
    # A judge_fn that raises is an operational failure, not a model disagreement — the case is
    # excluded, not scored as a mismatch, so a transient crash never deflates accuracy.
    def boom(_request: JudgeRequest) -> JudgeReply:
        raise RuntimeError("api down")

    scenario = Scenario(id="c", workflow="w", run_dir=Path("run"), expect="compliant", gold_path=None)
    cal = calibrate([(scenario, _run(), Gold("compliant"))], boom, runs=2)
    assert "c" in cal.excluded
    assert cal.accuracy is None            # the only case crashed → nothing scored, not a mismatch
    assert cal.per_scenario == []          # not recorded as a matched=False row


def test_calibration_excludes_unscoreable_evidence_runs() -> None:
    # A gold-backed run whose evidence the harness cannot present (empty here) is a harness-forced
    # UNKNOWN, not a judge result — excluded from accuracy/consistency, never counted as a mismatch.
    good = Scenario(id="g", workflow="w", run_dir=Path("run"), expect="compliant", gold_path=None)
    empty = Scenario(id="e", workflow="w", run_dir=Path("run"), expect="compliant", gold_path=None)
    cases = [(good, _run(), Gold("compliant")),
             (empty, _run(phase_texts={"p.md": "## Rules\nonly\n"}), Gold("compliant"))]
    cal = calibrate(cases, reference_stub_judge, runs=2)
    assert "e" in cal.excluded
    assert set(cal.covered) == {"g", "e"}
    assert cal.accuracy == 1.0            # measured only over the one scoreable run
