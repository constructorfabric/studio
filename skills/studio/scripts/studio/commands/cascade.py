"""Studio retrieve command — route a query against a Markdown file through
the two-tier JIT-retrieval cascade (heading-nav + TF-IDF, falling back to an
OKF-vs-baseline choice), and report the routing decision.

Thin CLI wrapper around ``studio.utils.cascade``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
"""

import argparse
from typing import List

from ..utils.cascade import route_query
from ..utils.ui import ui


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-cmd
def cmd_retrieve(argv: List[str]) -> int:
    """Route a query against a Markdown file through the JIT-retrieval cascade."""
    p = argparse.ArgumentParser(
        prog="cfs retrieve",
        description="Route a query through the two-tier JIT-retrieval cascade and report the decision.",
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument("query", help="Query text")
    p.add_argument(
        "--margin-threshold", type=float, default=None,
        help="Enable a numeric TF-IDF margin cutoff for a large-margin Tier 1 resolution "
        "(default: disabled -- only an unambiguous score counts)",
    )
    p.add_argument(
        "--expected-future-queries", type=int, default=None,
        help="Expected future query volume against this document, for the OKF-vs-baseline break-even math",
    )
    args = p.parse_args(argv)

    filepath = ui.require_existing_file(args.file)
    if filepath is None:
        return 2

    result = route_query(
        filepath, args.query,
        margin_threshold=args.margin_threshold,
        expected_future_queries=args.expected_future_queries,
    )

    output = {"file": str(filepath), **result}
    ui.result(output, human_fn=_human_retrieve)
    return 0
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-cmd


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-cmd-format
def _human_retrieve(data: dict) -> None:
    ui.header("Retrieve")
    ui.substep(f"query: {data['query']!r}")
    ui.substep(f"tier: {data['tier']} ({data['reason']})")
    for c in data["candidates"]:
        ui.substep(f"  [{c['line_start']}-{c['line_end']}] {c['heading']}")
    if "tier2" in data:
        tier2 = data["tier2"]
        ui.substep(f"tier 2 recommendation: {tier2['recommendation']} ({tier2['reason']})")
        if tier2.get("okf_needs_rebuild"):
            ui.substep("  OKF bundle exists but is stale/missing for this candidate -- needs a rebuild")
    if "read_gate" in data and data["read_gate"]["needs_confirmation"]:
        gate = data["read_gate"]
        ui.substep(f"read gate: needs confirmation ({gate['total_lines']} lines > {gate['threshold']})")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-cmd-format
