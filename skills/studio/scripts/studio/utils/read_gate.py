"""Large-read confirmation gate: a free line-count pre-check for a document
that's about to be read in full.

Pure decision logic, no I/O -- deliberately not an interactive prompt.
This is a deterministic CLI, not the caller that actually reads a file and
answers a query; that caller (e.g. an agent) is the one positioned to ask a
human for confirmation. This module only produces the structured flag that
decision depends on, the same "boolean-in-the-result for an external caller
to act on" shape ``commands/chunk_input.py``'s ``plan_required`` already
uses for its own (differently-scoped) line-count threshold.

@cpt-algo:cpt-studio-algo-traceability-validation-read-gate:p1
"""

from __future__ import annotations

from typing import Any, Dict

#: Real threshold measured this project's design session: the only read
#: among nine real candidate targets that crossed it was a whole-document
#: baseline read. Not a universal constant -- callers needing a different
#: threshold pass one explicitly.
DEFAULT_GATE_THRESHOLD_LINES = 5000


# @cpt-begin:cpt-studio-algo-traceability-validation-read-gate:p1:inst-read-gate-check
def check_gate(total_lines: int, threshold: int = DEFAULT_GATE_THRESHOLD_LINES) -> Dict[str, Any]:
    """Decide whether a read of ``total_lines`` should pause for confirmation.

    Returns ``{"needs_confirmation": bool, "total_lines": int, "threshold":
    int}`` -- a structured verdict, not a side effect. A negative
    ``total_lines`` (a caller's bug) is clamped to 0 rather than trusted, so
    this can never claim confirmation is needed off of a nonsensical count.
    """
    total_lines = max(0, total_lines)
    return {
        "needs_confirmation": total_lines > threshold,
        "total_lines": total_lines,
        "threshold": threshold,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-read-gate:p1:inst-read-gate-check
