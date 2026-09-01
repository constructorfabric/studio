"""Studio read-gate command — check whether a Markdown file's line count
crosses the large-read confirmation threshold, for a caller deciding
whether to pause before reading it in full.

Thin CLI wrapper around ``studio.utils.read_gate``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
"""

from typing import List

from ..utils.doc_index import get_or_build_doc_index
from ..utils.read_gate import DEFAULT_GATE_THRESHOLD_LINES, check_gate
from ..utils.ui import ui


# @cpt-begin:cpt-studio-algo-traceability-validation-read-gate:p1:inst-read-gate-cmd
def cmd_read_gate(argv: List[str]) -> int:
    """Check whether a Markdown file's line count needs read confirmation."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs read-gate",
        description="Check whether a Markdown file's line count crosses the large-read confirmation threshold.",
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument(
        "--threshold", type=int, default=DEFAULT_GATE_THRESHOLD_LINES,
        help=f"Line-count threshold (default: {DEFAULT_GATE_THRESHOLD_LINES})",
    )
    args, filepath = ui.parse_file_command(p, argv)
    if filepath is None:
        return 2

    index, rc = ui.call_with_read_error_handling(filepath, lambda: get_or_build_doc_index(filepath))
    if rc is not None:
        return rc
    gate = check_gate(index["total_lines"], args.threshold)

    output = {"file": str(filepath), **gate}
    ui.result(output, human_fn=_human_read_gate)
    return 0
# @cpt-end:cpt-studio-algo-traceability-validation-read-gate:p1:inst-read-gate-cmd


# @cpt-begin:cpt-studio-algo-traceability-validation-read-gate:p1:inst-read-gate-cmd-format
def _human_read_gate(data: dict) -> None:
    ui.header("Read Gate")
    ui.substep(f"{data['total_lines']} lines (threshold: {data['threshold']})")
    if data["needs_confirmation"]:
        ui.substep("needs confirmation -- this read crosses the threshold")
    else:
        ui.substep("no confirmation needed")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-read-gate:p1:inst-read-gate-cmd-format
