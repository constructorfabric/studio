"""Tests for the ``cfs eval`` command."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from studio import cli
from studio.commands.eval import _build_parser, cmd_eval
from studio.utils import ui as ui_module

FIXTURES = Path(__file__).parent / "fixtures" / "eval"
_GET_CONTEXT = "studio.utils.context.get_context"


def _ctx(project_root: Path) -> MagicMock:
    ctx = MagicMock()
    ctx.project_root = project_root
    return ctx


def _write_compliant(root: Path, sid: str = "ok") -> None:
    run = root / sid / "run"
    run.mkdir(parents=True)
    (root / sid / "scenario.toml").write_text(
        f'[scenario]\nid = "{sid}"\nworkflow = "w"\nrun_dir = "run"\nexpect = "compliant"\n')
    (run / "plan.toml").write_text(
        '[plan]\ntask = "t"\ntotal_phases = 1\n[[phases]]\nnumber = 1\nfile = "p.md"\n')
    # A single, fully structurally-compliant phase: numbered 1 of 1, no forward deps, a
    # declared output, and the default required sections — so StructuralScorer scores PASS.
    (run / "p.md").write_text(
        '```toml\n[phase]\nnumber = 1\ntotal = 1\ndepends_on = []\n'
        'output_files = ["out.txt"]\n```\n\n'
        "# P\n\n## Preamble\n\nContext.\n\n## What\n\nDo it.\n\n## Rules\n\nFollow them.\n")


# --- wiring + errors -------------------------------------------------------

def test_eval_is_wired_into_the_dispatch(capsys) -> None:
    handler = cli._resolve_command_handler("eval")
    assert handler is not None
    with patch(_GET_CONTEXT, return_value=None):
        assert handler([]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"


def test_cmd_eval_errors_without_context(capsys) -> None:
    with patch(_GET_CONTEXT, return_value=None):
        assert cmd_eval([]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"


def test_cmd_eval_missing_scenarios_dir_errors(capsys, tmp_path: Path) -> None:
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(tmp_path / "nope")])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"


@pytest.mark.parametrize("bad", ["nan", "inf", "-0.1", "1.5", "abc"])
def test_cmd_eval_rejects_invalid_min(bad: str) -> None:
    # argparse rejects a non-finite / out-of-range --min so a failing run can't slip past --check.
    with pytest.raises(SystemExit):
        cmd_eval(["--min", bad, "--scenarios-dir", "unused"])


def test_cmd_eval_gate_field_matches_exit(capsys, tmp_path: Path) -> None:
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check"])   # 0.5 < 1.0 → fail
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["gate"] == "fail"
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES)])              # report only → pass
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["gate"] == "pass"


def test_cmd_eval_gate_pass_under_check_when_compliant(capsys, tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    _write_compliant(scenarios)
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(scenarios), "--check"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["gate"] == "pass"


def test_check_help_documents_baseline_regression() -> None:
    assert "regression" in _build_parser().format_help()   # A2: full gate contract documented


def test_cmd_eval_empty_suite_is_honest_zero(capsys, tmp_path: Path) -> None:
    # An existing but empty scenarios dir scores nothing → honest exit 0, compliance null.
    empty = tmp_path / "empty"
    empty.mkdir()
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(empty), "--check"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["summary"]["scenarios"] == 0
    assert out["summary"]["structural_compliance"] is None


def test_cmd_eval_check_gates_on_broke_scenario(capsys, tmp_path: Path) -> None:
    # A scenario still in the suite whose run broke (UNKNOWN) fails --check vs a baseline.
    scenarios = tmp_path / "scenarios"
    (scenarios / "x").mkdir(parents=True)
    (scenarios / "x" / "scenario.toml").write_text('[scenario]\nid = "x"\n')   # no run → UNKNOWN
    baseline = {"summary": {"structural_compliance": 1.0},
                "per_scenario": [{"scenario": "x", "compliance": 1.0}]}
    baseline_path = tmp_path / "b.json"
    baseline_path.write_text(json.dumps(baseline))
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(scenarios), "--check", "--min", "0.0",
                       "--baseline", str(baseline_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert out["regression"]["has_regression"] is True


def test_cmd_eval_zero_parseable_frontmatter_is_unknown_not_gated(capsys, tmp_path: Path) -> None:
    # plan.toml loads, but every phase file lacks a parseable [phase] block → UNKNOWN, never a
    # gate failure (the real-world "different workflow shape" path, exercised end-to-end).
    scenarios = tmp_path / "scenarios"
    run = scenarios / "z" / "run"
    run.mkdir(parents=True)
    (scenarios / "z" / "scenario.toml").write_text(
        '[scenario]\nid = "z"\nworkflow = "coding-gen"\nrun_dir = "run"\nexpect = "unknown"\n')
    (run / "plan.toml").write_text('[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "p.md"\n')
    (run / "p.md").write_text("# Phase 1\n\nno frontmatter block here\n")
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(scenarios), "--check", "--min", "0.0"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["summary"]["structural_compliance"] is None
    assert out["summary"]["unknown"] >= 1


# --- reporting + opt-in gating ---------------------------------------------

def test_cmd_eval_reports_without_gating(capsys, tmp_path: Path) -> None:
    # Without --check, a failing scenario still exits 0 — eval reports, it does not gate.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["summary"]["scenarios"] == 2
    assert out["summary"]["structural_compliance"] == 0.5


def test_cmd_eval_check_gates_below_min(capsys, tmp_path: Path) -> None:
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check"])
    assert rc == 2                                   # compliance 0.5 < default min 1.0
    assert json.loads(capsys.readouterr().out)["summary"]["structural_compliance"] == 0.5


def test_cmd_eval_check_passes_above_min(capsys, tmp_path: Path) -> None:
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check", "--min", "0.4"])
    assert rc == 0                                   # 0.5 >= 0.4


def test_cmd_eval_check_passes_when_all_compliant(capsys, tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    _write_compliant(scenarios)
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(scenarios), "--check"])
    assert rc == 0


def test_cmd_eval_defaults_to_project_eval_dir(capsys, tmp_path: Path) -> None:
    _write_compliant(tmp_path / "eval")
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval([])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["summary"]["scenarios"] == 1


# --- baseline diff + save --------------------------------------------------

def test_cmd_eval_baseline_reports_regression(capsys, tmp_path: Path) -> None:
    baseline = {"summary": {"structural_compliance": 1.0}, "per_scenario": [
        {"scenario": "non-compliant-run", "compliance": 1.0}]}   # was 1.0, now 0.0 → regression
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(baseline_path)])
    assert rc == 0                          # AC#4: --baseline alone never changes the exit code
    regression = json.loads(capsys.readouterr().out)["regression"]
    assert regression["has_regression"] is True
    assert [r["scenario"] for r in regression["regressed"]] == ["non-compliant-run"]


def test_cmd_eval_check_gates_on_regression(capsys, tmp_path: Path) -> None:
    # compliance 0.5 >= --min 0.4, but a regression vs baseline must still fail --check.
    baseline = {"summary": {"structural_compliance": 1.0},
                "per_scenario": [{"scenario": "non-compliant-run", "compliance": 1.0}]}
    baseline_path = tmp_path / "b.json"
    baseline_path.write_text(json.dumps(baseline))
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check", "--min", "0.4",
                       "--baseline", str(baseline_path)])
    assert rc == 2                                    # regression fails --check despite ≥ --min
    assert json.loads(capsys.readouterr().out)["regression"]["has_regression"] is True


def test_cmd_eval_check_unusable_baseline_surfaced_not_gated(capsys, tmp_path: Path) -> None:
    # An unusable --baseline is surfaced via the regression `error` field but does not, by
    # itself, fail --check — the --min floor still applies (documented warn-and-skip).
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check", "--min", "0.0",
                       "--baseline", str(tmp_path / "missing.json")])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "error" in out["regression"]
    assert out["gate"] == "pass"


def test_cmd_eval_check_does_not_gate_on_removed_scenario(capsys, tmp_path: Path) -> None:
    # A baseline scenario that no longer exists is surfaced but must not fail --check.
    baseline = {"summary": {"structural_compliance": 1.0}, "per_scenario": [
        {"scenario": "compliant-run", "compliance": 1.0},
        {"scenario": "non-compliant-run", "compliance": 0.0},   # unchanged → no regression
        {"scenario": "gone", "compliance": 1.0}]}               # removed
    baseline_path = tmp_path / "b.json"
    baseline_path.write_text(json.dumps(baseline))
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check", "--min", "0.4",
                       "--baseline", str(baseline_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0                                    # a removal does not gate
    assert out["regression"]["has_regression"] is False
    assert [r["scenario"] for r in out["regression"]["no_longer_scoreable"]] == ["gone"]


def test_cmd_eval_malformed_baseline_reports_error(capsys, tmp_path: Path) -> None:
    # Schema stability: --baseline always yields a `regression` key, an error object here.
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(bad)])
    regression = json.loads(capsys.readouterr().out)["regression"]
    assert "error" in regression


def test_cmd_eval_non_dict_baseline_reports_error(capsys, tmp_path: Path) -> None:
    listy = tmp_path / "list.json"
    listy.write_text("[]")
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(listy)])
    assert "error" in json.loads(capsys.readouterr().out)["regression"]


def test_cmd_eval_malformed_shape_baseline_reports_error(capsys, tmp_path: Path) -> None:
    # A dict whose per_scenario is not a list of objects must not reach diff_reports.
    bad = tmp_path / "shape.json"
    bad.write_text(json.dumps({"summary": {}, "per_scenario": "nope"}))
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(bad)])
    assert "error" in json.loads(capsys.readouterr().out)["regression"]


def test_cmd_eval_bad_summary_baseline_reports_error(capsys, tmp_path: Path) -> None:
    bad = tmp_path / "sum.json"
    bad.write_text(json.dumps({"summary": "not a dict", "per_scenario": []}))
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(bad)])
    assert "error" in json.loads(capsys.readouterr().out)["regression"]


def test_cmd_eval_save_writes_report(capsys, tmp_path: Path) -> None:
    saved = tmp_path / "report.json"
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--save", str(saved)])
    out = json.loads(capsys.readouterr().out)
    assert out["saved"] == str(saved)
    assert saved.is_file()
    assert json.loads(saved.read_text())["summary"]["structural_compliance"] == 0.5


def test_cmd_eval_save_to_missing_dir_reports_error(capsys, tmp_path: Path) -> None:
    # A --save path whose parent dir does not exist fails at temp creation, not with a crash.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--save", str(tmp_path / "nope" / "r.json")])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["saved"] is None
    assert "save_error" in out


def test_cmd_eval_save_error_is_reported_not_raised(capsys, tmp_path: Path) -> None:
    # Saving onto a directory path fails; the run must still succeed and report the error.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--save", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["saved"] is None
    assert "save_error" in out


# --- advisory judge + calibration ------------------------------------------

def test_cmd_eval_calibrate_reports_judge_coverage(capsys, tmp_path: Path) -> None:
    # --calibrate surfaces which scenarios carry a gold set; the fixtures carry none.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--calibrate"])
    cal = json.loads(capsys.readouterr().out)["judge_calibration"]
    assert cal["gold_backed"] == []
    assert cal["accuracy"] is None
    assert cal["judge"] == "reference-stub"


def test_cmd_eval_calibrate_measures_the_stub_on_a_gold_backed_scenario(capsys,
                                                                        tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    _write_compliant(scenarios, sid="g")
    (scenarios / "g" / "scenario.toml").write_text(
        '[scenario]\nid = "g"\nworkflow = "coding-gen"\nrun_dir = "run"\nexpect = "compliant"\n'
        '[scenario.gold]\npath = "gold.toml"\n')
    (scenarios / "g" / "gold.toml").write_text('[gold]\nverdict = "compliant"\n')
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(scenarios), "--calibrate"])
    cal = json.loads(capsys.readouterr().out)["judge_calibration"]
    assert cal["gold_backed"] == ["g"]
    assert cal["accuracy"] == 1.0            # stub agrees with the compliant label


def test_cmd_eval_includes_advisory_judge_without_gating(capsys, tmp_path: Path) -> None:
    # The advisory judge rides along (UNKNOWN, no model) but never moves compliance/exit.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check", "--min", "0.4"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0                                   # advisory judge never gates
    assert "rules-judge (advisory)" in out["summary"]["coverage"]


# --- human report ----------------------------------------------------------

def test_human_report_shows_compliance(capsys, tmp_path: Path) -> None:
    ui_module.set_json_mode(False)
    try:
        with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
            rc = cmd_eval(["--scenarios-dir", str(FIXTURES)])
    finally:
        ui_module.set_json_mode(True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "compliance" in out


def test_human_report_explains_advisory_unknown(capsys, tmp_path: Path) -> None:
    # A no-model run: the advisory judge is UNKNOWN for every scenario. Human mode must say so —
    # those UNKNOWNs are the unwired judge (advisory), not structurally unscoreable runs.
    ui_module.set_json_mode(False)
    try:
        with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
            rc = cmd_eval(["--scenarios-dir", str(FIXTURES)])
    finally:
        ui_module.set_json_mode(True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "scorers:" in out
    assert "advisory" in out
    assert "does not affect the gate" in out


def test_human_report_prints_calibration_under_flag(capsys, tmp_path: Path) -> None:
    # Without this fix --calibrate was invisible outside --json; the metrics must now print.
    ui_module.set_json_mode(False)
    try:
        with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
            rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--calibrate"])
    finally:
        ui_module.set_json_mode(True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "calibrate" in out
    assert "accuracy" in out
    assert "calibrate note:" in out                # the note explaining the stub figure is printed


def test_human_report_renders_regression(capsys) -> None:
    # A --baseline regression must be visible in the terminal, not only in --json — otherwise a
    # regressed run exits 2 with no explanation of what broke.
    from studio.commands.eval import _report_regression  # noqa: PLC0415
    ui_module.set_json_mode(False)
    try:
        _report_regression({"has_regression": True,
                            "regressed": [{"scenario": "x", "from": 1.0, "to": 0.5}],
                            "no_longer_scoreable": [{"scenario": "y"}]})
        _report_regression({"has_regression": False, "regressed": []})   # clean vs baseline
        _report_regression({"error": "baseline unreadable"})             # unusable baseline
        _report_regression({"has_regression": True,                      # more than the cap
                            "regressed": [{"scenario": f"s{i}", "from": 1.0, "to": 0.0}
                                          for i in range(12)]})
    finally:
        ui_module.set_json_mode(True)
    out = capsys.readouterr().out
    assert "1 scenario(s) regressed" in out
    assert "x: 1.0 -> 0.5" in out
    assert "no longer scoreable" in out
    assert "regression: none vs baseline" in out
    assert "baseline not usable" in out
    assert "more" in out                            # "(+2 more)" — 12 regressed, cap 10


def test_human_report_warns_on_save_error(capsys) -> None:
    from studio.commands.eval import _human_report  # noqa: PLC0415
    ui_module.set_json_mode(False)
    try:
        _human_report({"summary": {"scored": 1, "unknown": 0, "results": 1, "scenarios": 1,
                                   "structural_compliance": 1.0, "coverage": "structural (deterministic)"},
                       "per_scenario": [], "save_error": "could not save report to /x: disk full"})
    finally:
        ui_module.set_json_mode(True)
    assert "save failed" in capsys.readouterr().out


def test_save_error_omits_the_internal_temp_path(capsys, tmp_path: Path) -> None:
    # A failed --save reports the user-supplied destination and reason, never the mkstemp temp name.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--save", str(tmp_path / "nope" / "r.json")])
    payload = json.loads(capsys.readouterr().out)
    assert payload["saved"] is None
    assert "could not save report to" in payload["save_error"]
    assert ".tmp" not in payload["save_error"]      # no internal temp-file name leaked


def test_advisory_count_only_counts_the_unwired_judge() -> None:
    # Only advisory UNKNOWNs caused by an unwired judge are counted. A structural UNKNOWN, a wired
    # advisory verdict, and — the CodeRabbit case — an advisory UNKNOWN from an *unreadable run*
    # (also advisory UNKNOWN, but not benign) must all be excluded, or the "no judge wired" note
    # would misattribute a broken run.
    from studio.commands.eval import _count_advisory_unknown  # noqa: PLC0415
    data = {"per_scenario": [
        {"results": [{"kind": "deterministic", "verdict": "UNKNOWN"},              # structural, not counted
                     {"kind": "advisory", "verdict": "UNKNOWN",
                      "coverage": "no judge_fn: model supplied out-of-tree; x"}]},  # counted
        {"results": [{"kind": "advisory", "verdict": "UNKNOWN",
                      "coverage": "unscoreable: no readable run; x"}]},             # broken run, NOT counted
        {"results": [{"kind": "advisory", "verdict": "compliant",
                      "coverage": "1 rule(s) assessed; x"}]}]}                      # wired judge, not unknown
    assert _count_advisory_unknown(data) == 1


@pytest.mark.parametrize("data", [
    {},                                          # no per_scenario key
    {"per_scenario": None},                      # wrong type
    {"per_scenario": [123, "x"]},                # non-dict rows
    {"per_scenario": [{"results": 5}]},          # non-list results
    {"per_scenario": [{"results": ["x", 1]}]},   # non-dict results
])
def test_advisory_count_is_failsafe_on_malformed_payload(data: dict) -> None:
    from studio.commands.eval import _count_advisory_unknown  # noqa: PLC0415
    assert _count_advisory_unknown(data) == 0  # never raises, never a false count


def test_no_note_or_calibration_line_when_absent(capsys) -> None:
    # No advisory UNKNOWNs → no note; no judge_calibration → no calibrate line.
    from studio.commands.eval import _human_report  # noqa: PLC0415
    ui_module.set_json_mode(False)
    try:
        _human_report({"summary": {"scored": 1, "unknown": 0, "results": 1, "scenarios": 1,
                                   "structural_compliance": 1.0, "coverage": "structural (deterministic)"},
                       "per_scenario": [{"results": [{"kind": "deterministic", "verdict": "PASS"}]}]})
    finally:
        ui_module.set_json_mode(True)
    out = capsys.readouterr().out
    assert "advisory UNKNOWN" not in out
    assert "calibrate" not in out


def test_report_calibration_flags_malformed_vs_empty(capsys) -> None:
    # A malformed payload (wrong field types) must be reported distinctly, not coerced to the same
    # "0 gold-backed, 0 excluded" a *valid empty* calibration shows.
    from studio.commands.eval import _report_calibration  # noqa: PLC0415
    ui_module.set_json_mode(False)
    try:
        _report_calibration(None)                                    # not a dict → prints nothing
        _report_calibration({"gold_backed": [], "excluded_unscoreable": []})   # valid empty
        _report_calibration({"gold_backed": 7, "excluded_unscoreable": None})  # malformed (non-list)
    finally:
        ui_module.set_json_mode(True)
    out = capsys.readouterr().out
    # Exclusive: exactly one gold-backed line (the valid-empty call) and one malformed line — the
    # malformed payload must NOT also be rendered as an empty calibration.
    assert out.count("0 gold-backed, 0 excluded") == 1
    assert out.count("malformed calibration payload") == 1


def test_calibration_distinguishes_broken_gold_from_absent(capsys, tmp_path: Path) -> None:
    # A configured-but-unloadable gold file (malformed here) is reported as broken_gold, distinct
    # from a scenario that simply declares no gold at all.
    scenarios = tmp_path / "s"
    broke_run = scenarios / "broke" / "run"
    broke_run.mkdir(parents=True)
    (scenarios / "broke" / "scenario.toml").write_text(
        '[scenario]\nid = "broke"\nworkflow = "w"\nrun_dir = "run"\n'
        '[scenario.gold]\npath = "gold.toml"\n')
    (scenarios / "broke" / "gold.toml").write_text("= = not valid toml")   # configured but broken
    (broke_run / "plan.toml").write_text('[plan]\ntask = "t"\n')
    (scenarios / "nogold").mkdir()
    (scenarios / "nogold" / "scenario.toml").write_text('[scenario]\nid = "nogold"\nworkflow = "w"\n')
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(scenarios), "--calibrate"])
    cal = json.loads(capsys.readouterr().out)["judge_calibration"]
    assert cal["broken_gold"] == ["broke"]             # the broken one only; "nogold" is absent, not broken


def test_calibrate_never_affects_the_gate(capsys, tmp_path: Path) -> None:
    # --calibrate is advisory reporting only: the exit code still comes solely from structural
    # compliance (and baseline regression), never from calibration data.
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(FIXTURES), "--check", "--calibrate"])  # 0.5 < 1.0
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2                                      # structural gates; calibrate cannot change it
    assert "judge_calibration" in payload              # yet calibration still ran and reported
    scenarios = tmp_path / "s"
    scenarios.mkdir()
    _write_compliant(scenarios)
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        rc = cmd_eval(["--scenarios-dir", str(scenarios), "--check", "--calibrate"])
    assert rc == 0                                      # compliant suite still passes with --calibrate
