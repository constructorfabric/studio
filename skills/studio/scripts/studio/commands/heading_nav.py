"""Studio heading-nav command — grep a Markdown file's retrieval sections
for a query's literal text, for inspecting/benchmarking the JIT-retrieval
mechanical gate independent of any cascade routing logic built on top of it.

Thin CLI wrapper around ``studio.utils.heading_nav``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
"""

from typing import List

from ..utils.heading_nav import find_sections
from ..utils.ui import ui


# @cpt-begin:cpt-studio-algo-traceability-validation-heading-nav:p1:inst-heading-nav-cmd
def cmd_heading_nav(argv: List[str]) -> int:
    """Find a Markdown file's retrieval sections containing a query literally."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs heading-nav",
        description="Find a Markdown file's retrieval sections containing a query's literal text.",
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument("query", help="Query text to search for, literally")
    args, filepath = ui.parse_file_command(p, argv)
    if filepath is None:
        return 2

    result, rc = ui.call_with_read_error_handling(filepath, lambda: find_sections(filepath, args.query))
    if rc is not None:
        return rc

    output = {
        "file": str(filepath),
        "query": args.query,
        "matches": result["matches"],
        "first_match": result["first_match"],
    }
    ui.result(output, human_fn=_human_heading_nav)
    return 0
# @cpt-end:cpt-studio-algo-traceability-validation-heading-nav:p1:inst-heading-nav-cmd


# @cpt-begin:cpt-studio-algo-traceability-validation-heading-nav:p1:inst-heading-nav-cmd-format
def _human_heading_nav(data: dict) -> None:
    ui.header("Heading-Nav Search")
    ui.substep(f"query: {data['query']!r}")
    if not data["matches"]:
        ui.substep("(no matches -- this method has no semantic fallback)")
        ui.blank()
        return
    for entry in data["matches"]:
        ui.substep(f"  {entry['hit_count']}x  [{entry['line_start']}-{entry['line_end']}] {entry['heading']}")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-heading-nav:p1:inst-heading-nav-cmd-format
