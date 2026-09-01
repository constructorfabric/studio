"""Studio usage-report command — aggregate the local decision log's logged
read events into a per-method token table, and a summary of everything else
logged.

Thin CLI wrapper around ``studio.utils.decision_log``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
"""

from typing import List

from ..utils import decision_log
from ..utils.ui import ui


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-usage-report-cmd
def cmd_usage_report(argv: List[str]) -> int:
    """Aggregate the local decision log into a per-method usage report."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs usage-report",
        description="Aggregate the local decision log's read events into a per-method token table.",
    )
    if ui.parse_args_or_json_error(p, argv) is None:
        return 2

    output = {
        "summary": decision_log.summarize(),
        "reads": decision_log.summarize_reads(),
    }
    ui.result(output, human_fn=_human_usage_report)
    return 0
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-usage-report-cmd


# @cpt-begin:cpt-studio-algo-core-infra-decision-log:p1:inst-usage-report-cmd-format
def _human_usage_report(data: dict) -> None:
    ui.header("Usage Report")
    summary = data["summary"]
    if not summary["exists"]:
        ui.substep("no decision log found yet")
        ui.blank()
        return
    ui.substep(f"log: {summary['path']}")
    ui.substep(f"{summary['total_events']} event(s) across {summary['runs']} run(s)")
    if summary["first_ts"] or summary["last_ts"]:
        ui.substep(f"time range: {summary['first_ts']} .. {summary['last_ts']}")
    if summary["event_counts"]:
        counts = ", ".join(f"{name}: {count}" for name, count in sorted(summary["event_counts"].items()))
        ui.substep(f"by event type: {counts}")

    reads = data["reads"]
    if not reads["methods"]:
        ui.substep("no read events logged yet")
        ui.blank()
        return
    ui.step(f"By method ({reads['total_tokens']} tokens total)")
    for method, stats in sorted(reads["methods"].items()):
        ui.substep(
            f"  {method}: {stats['count']} read(s), "
            f"{stats['total_tokens']} tokens, {stats['total_lines']} lines"
        )
    ui.blank()
# @cpt-end:cpt-studio-algo-core-infra-decision-log:p1:inst-usage-report-cmd-format
