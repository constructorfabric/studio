"""``cfs eval`` — run the workflow eval-harness over a suite of scenarios.

Thin CLI over ``utils.eval_harness``: resolve a scenarios directory, run every
scenario through the (placeholder) reference scorer, and emit a JSON report.
Gating is opt-in: ``--check`` fails the build (exit 2) when structural compliance falls
below ``--min``, or when ``--baseline`` shows a per-scenario regression; without it, eval
reports and exits 0. Advisory scorers never gate.

@cpt-flow:cpt-studio-flow-eval-harness-run:p1
@cpt-dod:cpt-studio-dod-eval-harness-report:p1
"""
# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-eval-imports
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from ..utils import eval_harness
from ..utils.eval_judge import AdvisoryJudge, calibrate, load_gold, reference_stub_judge
from ..utils.eval_structural import StructuralScorer
from ..utils.ui import ui

logger = logging.getLogger(__name__)

#: Prefix of the advisory scorer's coverage reason when its UNKNOWN is *only* an unwired judge
#: (vs. an unreadable run, which also yields advisory UNKNOWN but is not benign). The human note
#: explains only the former, so it filters on this.
_NO_JUDGE_REASON = "no judge_fn"
#: Cap on regressed scenarios listed in the human summary (the rest are summarised as "+N more").
_REGRESSION_CAP = 10
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-eval-imports


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-build-parser
def _compliance_arg(value: str) -> float:
    """argparse type for --min: a finite number in [0.0, 1.0] (rejects nan/inf/out-of-range)."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError(
            f"--min must be a finite number in [0.0, 1.0], got {value!r}")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfs eval",
        description="Run the workflow eval-harness over a suite of scenarios.")
    parser.add_argument(
        "--scenarios-dir", default=None,
        help="Directory of scenarios (each a subdir with scenario.toml). "
             "Defaults to <project>/eval.")
    parser.add_argument(
        "--check", action="store_true",
        help="Exit 2 when structural compliance is below --min, or when --baseline shows "
             "a per-scenario regression (gating is off by default).")
    parser.add_argument(
        "--min", type=_compliance_arg, default=1.0,
        help="Minimum structural compliance for --check (default 1.0).")
    parser.add_argument(
        "--baseline", default=None,
        help="A previous report JSON to diff this run against (regression check).")
    parser.add_argument(
        "--save", default=None,
        help="Write this run's report JSON to a file, to become a later baseline.")
    parser.add_argument(
        "--calibrate", action="store_true",
        help="Report reference-stub calibration over gold-backed scenarios: the built-in "
             "reference stub's accuracy + consistency (wire a real judge_fn out-of-tree for "
             "model-quality metrics).")
    return parser
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-build-parser


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-load-baseline
def _load_baseline(path: Path) -> Optional[Dict[str, object]]:
    """Read + shape-check a baseline report JSON. Missing/malformed/wrong-shape → warn and
    return None (never raise); the shape guard keeps diff_reports from crashing on bad data."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("eval: baseline not usable, skipping regression diff (%s): %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("eval: baseline is not a report object, skipping regression diff: %s", path)
        return None
    per_scenario = data.get("per_scenario", [])
    if not isinstance(per_scenario, list) or not all(isinstance(row, dict) for row in per_scenario):
        logger.warning("eval: baseline per_scenario is malformed, skipping regression diff: %s", path)
        return None
    if not isinstance(data.get("summary", {}), dict):
        logger.warning("eval: baseline summary is malformed, skipping regression diff: %s", path)
        return None
    return data
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-load-baseline


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-save-report
def _save_report(payload: Dict[str, object], path: Path) -> Optional[str]:
    """Atomically write the report JSON so it can serve as a later baseline: write a *unique*
    temp file in the target directory then replace, so a crash mid-write can never corrupt an
    existing baseline and no unrelated file is clobbered by a concurrent save. Returns an error
    string on failure, else None — a save failure must not change the eval outcome. (SonarCloud
    flags the user-supplied ``--save`` path here as S8707 path-traversal; that is a false
    positive for a CLI file argument and is marked as such.)"""
    tmp: Optional[Path] = None
    try:
        handle_fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        tmp = Path(tmp_name)
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except OSError as exc:
        logger.warning("eval: could not save report to %s: %s", path, exc)
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError as cleanup_exc:  # pragma: no cover - best-effort cleanup
                logger.debug("eval: could not remove temp save file %s: %s", tmp, cleanup_exc)
        # Report the user-supplied destination and the reason, not the internal mkstemp temp path.
        return f"could not save report to {path}: {exc.strerror or 'write failed'}"
    return None
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-save-report


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-human-report
def _human_report(data: Dict[str, object]) -> None:
    """Render a short human summary (JSON mode prints the full report instead).

    Beyond the aggregate counters it surfaces the advisory context the JSON already carries, so a
    default (non-JSON) run is not misread: the scorer coverage line, an explicit note when the
    only reason for UNKNOWN results is an unwired advisory judge (which never gates), and the
    calibration metrics under ``--calibrate`` (otherwise visible only in the ``--json`` payload).
    """
    summary = data.get("summary", {})
    ui.info(f"eval: {summary.get('scored', 0)} scored / {summary.get('unknown', 0)} unknown "
            f"({summary.get('results', 0)} result(s) across {summary.get('scenarios', 0)} scenario(s))")
    coverage = summary.get("coverage")
    if coverage:
        ui.info(f"scorers: {coverage}")
    _report_advisory_unknown(data)
    compliance = summary.get("structural_compliance")
    ui.info(f"structural compliance: {compliance * 100:.0f}%" if compliance is not None
            else "structural compliance: n/a (nothing scored)")
    _report_regression(data.get("regression"))
    _report_calibration(data.get("judge_calibration"))
    save_error = data.get("save_error")
    if save_error:
        ui.warn(f"save failed: {save_error}")
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-human-report


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-human-advisory
def _count_advisory_unknown(data: Dict[str, object]) -> int:
    """Count scorer-results that are UNKNOWN *and* advisory — the unwired-judge UNKNOWNs a reader
    must not mistake for structurally unscoreable runs. A structural UNKNOWN (a genuinely
    unscoreable run) is deliberately not counted here. Reads the per-scenario results already in
    the payload (adding no JSON field) and tolerates any malformed shape without raising."""
    total = 0
    rows = data.get("per_scenario")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        results = row.get("results")
        for result in results if isinstance(results, list) else []:
            if (isinstance(result, dict)
                    and result.get("kind") == eval_harness.ScorerKind.ADVISORY.value
                    and result.get("verdict") == eval_harness.VERDICT_UNKNOWN
                    and str(result.get("coverage", "")).startswith(_NO_JUDGE_REASON)):
                total += 1
    return total


def _report_advisory_unknown(data: Dict[str, object]) -> None:
    """Explain advisory-only UNKNOWNs so a healthy no-model run does not look half-broken."""
    count = _count_advisory_unknown(data)
    if count:
        ui.info(f"note: {count} advisory UNKNOWN — no judge model wired "
                "(advisory only; does not affect the gate)")
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-human-advisory


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-human-calibration
def _report_calibration(calibration: object) -> None:
    """Surface the calibration metrics in human mode; without this ``--calibrate`` prints nothing
    unless the caller reads the raw ``--json`` payload. Tolerates a malformed payload."""
    if not isinstance(calibration, dict):
        return
    gold = calibration.get("gold_backed")
    excluded = calibration.get("excluded_unscoreable")
    # A required field present with the wrong type is a *malformed* payload — say so, rather than
    # coercing it to zero and rendering it identically to a valid empty calibration.
    if (gold is not None and not isinstance(gold, list)) or \
            (excluded is not None and not isinstance(excluded, list)):
        ui.info("calibrate: malformed calibration payload (unexpected field types)")
        return
    accuracy = calibration.get("accuracy")
    consistency = calibration.get("consistency")
    broken = calibration.get("broken_gold")
    broken_note = f", {len(broken)} broken-gold" if isinstance(broken, list) and broken else ""
    ui.info(f"calibrate ({calibration.get('judge', 'reference-stub')}): {len(gold or [])} "
            f"gold-backed, {len(excluded or [])} excluded{broken_note}, "
            f"accuracy {accuracy if accuracy is not None else 'n/a'}, "
            f"consistency {consistency if consistency is not None else 'n/a'}")
    # The metrics are meaningless without knowing what produced them — e.g. the reference stub's
    # 1.0 is keyword self-consistency, not a real judge. Print the note so nobody misreads it.
    note = calibration.get("note")
    if note:
        ui.info(f"calibrate note: {note}")
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-human-calibration


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-human-regression
def _report_regression(regression: object) -> None:
    """Surface a ``--baseline`` regression in human mode; without this a regressed run exits 2 with
    no terminal explanation of what broke. Tolerates a malformed/absent regression object."""
    if not isinstance(regression, dict):
        return
    if regression.get("error"):
        ui.warn(f"regression: baseline not usable ({regression['error']})")
        return
    regressed = regression.get("regressed")
    regressed = regressed if isinstance(regressed, list) else []
    if not regression.get("has_regression"):
        ui.info(f"regression: none vs baseline ({len(regressed)} regressed)")
        return
    ui.warn(f"regression: {len(regressed)} scenario(s) regressed")
    for row in regressed[:_REGRESSION_CAP]:
        if isinstance(row, dict):
            ui.warn(f"  - {row.get('scenario')}: {row.get('from')} -> {row.get('to')}")
    if len(regressed) > _REGRESSION_CAP:
        ui.warn(f"  (+{len(regressed) - _REGRESSION_CAP} more)")
    gone = regression.get("no_longer_scoreable")
    if isinstance(gone, list) and gone:
        ui.info(f"regression: {len(gone)} scenario(s) no longer scoreable (not gated)")
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-human-regression


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-judge-calibration
def _judge_calibration(cases: list) -> Dict[str, object]:
    """Calibrate the reference stub over gold-backed scenarios (coverage derived, not hardcoded).

    Takes the already-loaded ``(scenario, run)`` pairs from the report so calibration measures the
    same disk snapshot — no second read that could diverge. The bare CLI has no model, so it
    measures the deterministic reference stub; a real ``judge_fn`` out-of-tree yields a real one.
    """
    gold_cases = []
    broken_gold = []
    for scenario, run in cases:
        gold = load_gold(scenario.gold_path)
        if gold is not None:
            gold_cases.append((scenario, run, gold))
        elif scenario.gold_path is not None:
            # A gold file was configured but could not be loaded (unreadable / malformed / bad
            # verdict) — distinct from a scenario that simply declares no gold at all.
            broken_gold.append(scenario.id)
    result = calibrate(gold_cases, reference_stub_judge)
    return {
        "judge": "reference-stub",
        "gold_backed": result.covered,
        "excluded_unscoreable": result.excluded,
        "broken_gold": broken_gold,
        "accuracy": result.accuracy,
        "consistency": result.consistency,
        "runs_per_scenario": result.runs_per_scenario,
        "note": ("reference-stub calibration (cfs runs stdlib-only, no model); wire a real "
                 "judge_fn out-of-tree for a real judge accuracy + consistency measurement"),
    }
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-judge-calibration


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-user-eval
def cmd_eval(argv: List[str]) -> int:
    """Entry point for ``cfs eval``."""
    args = _build_parser().parse_args(argv)

    # @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-load-context
    from ..utils.context import get_context  # noqa: PLC0415 - local keeps get_context patchable
    ctx = get_context()
    if not ctx:
        ui.result({"status": "ERROR",
                   "message": "Constructor Studio not initialized. Run 'cfs init' first."})
        return 1
    # @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-load-context

    # @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-run-and-report
    scenarios_dir = Path(args.scenarios_dir) if args.scenarios_dir else ctx.project_root / "eval"
    if not scenarios_dir.is_dir():
        # A missing directory is an error, not a vacuous green pass.
        ui.result({"status": "ERROR", "message": f"Scenarios directory not found: {scenarios_dir}"})
        return 1
    # The advisory judge rides alongside the deterministic scorer. With no model wired it is
    # UNKNOWN (never gates); a host/agent injects a real judge_fn out-of-tree.
    cases = eval_harness.load_cases(scenarios_dir)   # one disk snapshot for report + calibration
    report = eval_harness.run_suite_over(cases, [StructuralScorer(), AdvisoryJudge()])
    payload = eval_harness.report_to_dict(report)
    if args.calibrate:
        payload["judge_calibration"] = _judge_calibration(cases)
    if args.baseline:
        baseline = _load_baseline(Path(args.baseline))
        # Always set a stable-shaped regression field when --baseline is given — even when
        # the baseline could not be loaded — so the JSON schema doesn't shift under callers.
        payload["regression"] = (eval_harness.diff_reports(report, baseline) if baseline is not None
                                 else {"error": f"baseline not usable: {args.baseline}"})
    compliance = payload["summary"]["structural_compliance"]
    exit_code = eval_harness.gate_exit_code(compliance, args.check, args.min)
    regression = payload.get("regression")
    if args.check and isinstance(regression, dict) and regression.get("has_regression"):
        # A per-scenario compliance drop, or a scenario that broke, fails --check even above
        # the floor. A removed scenario, or an unusable --baseline (surfaced via the
        # regression `error` field), is reported but does not by itself fail the build.
        exit_code = 2
    # Redundant machine-readable gate signal, consistent with the exit code, so a CI step
    # can cross-check from --json output even if a wrapper mangles the process exit code.
    payload["gate"] = "fail" if exit_code == 2 else "pass"
    if args.save:
        error = _save_report(payload, Path(args.save))
        payload["saved"] = None if error else args.save
        if error:
            payload["save_error"] = error
    ui.result(payload, human_fn=_human_report)
    return exit_code
    # @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-run-and-report
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-user-eval
