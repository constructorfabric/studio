"""``cfs eval`` — run the workflow eval-harness over a suite of scenarios.

Thin CLI over ``utils.eval_harness``: resolve a scenarios directory, run every
scenario through the (placeholder) reference scorer, and emit a JSON report.
Gating is opt-in: ``--check`` fails the build (exit 2) only when structural compliance
falls below ``--min``; without it, eval reports and exits 0. Advisory scorers never gate.

@cpt-flow:cpt-studio-flow-eval-harness-run:p1
@cpt-dod:cpt-studio-dod-eval-harness-report:p1
"""
# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-eval-imports
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..utils import eval_harness
from ..utils.ui import ui

logger = logging.getLogger(__name__)
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-eval-imports


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-build-parser
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
        help="Exit 2 when structural compliance is below --min (gating is off by default).")
    parser.add_argument(
        "--min", type=float, default=1.0,
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
    """Read a baseline report JSON. Missing/malformed → warn and skip, never raise."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("eval: baseline not usable, skipping regression diff (%s): %s", path, exc)
        return None
    return data if isinstance(data, dict) else None
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-load-baseline


# @cpt-begin:cpt-studio-flow-eval-harness-run:p1:inst-save-report
def _save_report(payload: Dict[str, object], path: Path) -> Optional[str]:
    """Write the report JSON so it can serve as a later baseline. Returns an error string
    on failure, else None — a save failure must not change the eval outcome."""
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("eval: could not save report to %s: %s", path, exc)
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
        if baseline is not None:
            payload["regression"] = eval_harness.diff_reports(report, baseline)
    if args.save:
        error = _save_report(payload, Path(args.save))
        payload["saved"] = None if error else args.save
        if error:
            payload["save_error"] = error
    ui.result(payload, human_fn=_human_report)
    compliance = payload["summary"]["structural_compliance"]
    exit_code = eval_harness.gate_exit_code(compliance, args.check, args.min)
    regression = payload.get("regression")
    if args.check and isinstance(regression, dict) and regression.get("regressed"):
        # A per-scenario compliance drop fails --check even above the floor. A scenario
        # merely removed / unavailable is surfaced (no_longer_scoreable) but does not gate.
        exit_code = 2
    return exit_code
    # @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-run-and-report
# @cpt-end:cpt-studio-flow-eval-harness-run:p1:inst-user-eval
