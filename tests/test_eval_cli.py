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
    (run / "plan.toml").write_text('[plan]\ntask = "t"\n[[phases]]\nnumber = 1\nfile = "p.md"\n')
    (run / "p.md").write_text("# p\n")


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
