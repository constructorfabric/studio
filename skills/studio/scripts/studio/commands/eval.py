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
from pathlib import Path
from typing import Dict, List, Optional

from ..utils import eval_harness
from ..utils.ui import ui

logger = logging.getLogger(__name__)
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
    """Atomically write the report JSON so it can serve as a later baseline: write a sibling
    temp file (inheriting the umask default mode) then replace, so a crash mid-write can
    never corrupt an existing baseline. Returns an error string on failure, else None — a
    save failure must not change the eval outcome."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        tmp.replace(path)
    except OSError as exc:
        logger.warning("eval: could not save report to %s: %s", path, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError as cleanup_exc:  # pragma: no cover - best-effort cleanup
            logger.debug("eval: could not remove temp save file %s: %s", tmp, cleanup_exc)
        return str(exc)
    return None
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-save-report


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-human-report
def _human_report(data: Dict[str, object]) -> None:
    """Render a short human summary (JSON mode prints the full report instead)."""
    summary = data.get("summary", {})
    ui.info(f"eval: {summary.get('scored', 0)} scored / {summary.get('unknown', 0)} unknown "
            f"({summary.get('results', 0)} result(s) across {summary.get('scenarios', 0)} scenario(s))")
    compliance = summary.get("structural_compliance")
    ui.info(f"structural compliance: {compliance * 100:.0f}%" if compliance is not None
            else "structural compliance: n/a (nothing scored)")
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-human-report


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
    report = eval_harness.run_suite(scenarios_dir, [eval_harness.ReferencePresenceScorer()])
    payload = eval_harness.report_to_dict(report)
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
