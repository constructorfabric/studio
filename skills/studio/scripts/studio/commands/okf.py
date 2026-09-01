"""Studio okf-status command — report an OKF bundle's state for a Markdown
file: which concept files exist, are stale, or are missing entirely,
relative to the document's current retrieval sections.

Read-only. Writing a concept file is an external caller's job (an agent
that has actually produced a summary) via
``studio.utils.okf.write_concept_file`` -- this command never invokes an
LLM itself.

Thin CLI wrapper around ``studio.utils.okf``.
"""

from typing import List

from ..utils.okf import get_okf_status
from ..utils.ui import ui


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-cmd
def cmd_okf_status(argv: List[str]) -> int:
    """Report an OKF bundle's state for a Markdown file."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs okf-status",
        description="Report which OKF concept files exist, are stale, or are missing for a Markdown file.",
    )
    p.add_argument("file", help="Markdown file path")
    _args, filepath = ui.parse_file_command(p, argv)
    if filepath is None:
        return 2

    status, rc = ui.call_with_read_error_handling(filepath, lambda: get_okf_status(filepath))
    if rc is not None:
        return rc
    output = {"file": str(filepath), **status}
    ui.result(output, human_fn=_human_okf_status)
    return 0
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-cmd


# @cpt-begin:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-cmd-format
def _human_okf_status(data: dict) -> None:
    ui.header("OKF Status")
    if not data["available"]:
        ui.substep("no Studio directory found -- OKF is unavailable for this file")
        ui.blank()
        return
    ui.substep(f"bundle: {data['bundle_dir']}")
    counts: dict = {}
    for entry in data["entries"]:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items())) or "no sections"
    ui.substep(summary)
    for entry in data["entries"]:
        heading = ui.display_heading(entry["heading"])
        ui.substep(
            f"  [{entry['status']:>7}] [{entry['line_start']}-{entry['line_end']}] "
            f"{heading} -> {entry['concept_file']}"
        )
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-okf:p1:inst-okf-cmd-format
