"""Tests for the ``cfs eval`` command."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from studio import cli
from studio.commands.eval import cmd_eval
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
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(baseline_path)])
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
    assert [r["scenario"] for r in out["regression"]["no_longer_scoreable"]] == ["gone"]


def test_cmd_eval_malformed_baseline_skips_diff(capsys, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(bad)])
    assert "regression" not in json.loads(capsys.readouterr().out)


def test_cmd_eval_non_dict_baseline_skips_diff(capsys, tmp_path: Path) -> None:
    listy = tmp_path / "list.json"
    listy.write_text("[]")
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--baseline", str(listy)])
    assert "regression" not in json.loads(capsys.readouterr().out)


def test_cmd_eval_save_writes_report(capsys, tmp_path: Path) -> None:
    saved = tmp_path / "report.json"
    with patch(_GET_CONTEXT, return_value=_ctx(tmp_path)):
        cmd_eval(["--scenarios-dir", str(FIXTURES), "--save", str(saved)])
    out = json.loads(capsys.readouterr().out)
    assert out["saved"] == str(saved)
    assert saved.is_file()
    assert json.loads(saved.read_text())["summary"]["structural_compliance"] == 0.5


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
