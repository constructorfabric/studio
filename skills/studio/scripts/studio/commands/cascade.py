"""Studio retrieve command — route a query against a Markdown file through
the two-tier JIT-retrieval cascade (heading-nav + TF-IDF, falling back to an
OKF-vs-baseline choice), and report the routing decision.

Thin CLI wrapper around ``studio.utils.cascade``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
"""

import argparse
from typing import List

from ..utils.cascade import _TIER2_BREAK_EVEN_ESCALATIONS, _check_margin_threshold_value, route_query
from ..utils.doc_index import _MAX_ESCALATION_KEY_LENGTH
from ..utils.ui import ui


def _margin_threshold_arg(value: str) -> float:
    """argparse type for --margin-threshold: a finite number > 0.

    cascade.py's own module docstring states the design basis: the only
    real evidence measured for this design is that an *infinite* margin is
    safe, while finite margins of 1.06x-1.58x still occurred on two
    independently wrong picks -- no finite value is yet proven safe. A
    non-finite (nan/inf), negative, or zero threshold would make
    ``tfidf_result["margin"] >= margin_threshold`` fire on virtually any
    result, defeating that safety margin entirely; only a genuine positive
    finite number is accepted, mirroring ``commands/eval.py``'s
    ``_compliance_arg`` validator for the same class of hazard.

    Parses the argparse string to ``float`` first (a string input like
    ``"0.5"`` is a legitimate CLI value -- unlike the direct Python API in
    ``utils/cascade.py``'s :func:`~studio.utils.cascade._validate_margin_threshold`,
    which requires an already-numeric value and rejects a string outright),
    then delegates the finite/positive check to the same shared
    ``_check_margin_threshold_value`` helper :func:`_validate_margin_threshold`
    uses, so both entry points enforce one identical policy instead of two
    independently drifting copies of it.
    """
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}") from exc
    try:
        _check_margin_threshold_value(parsed)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--margin-threshold must be a finite number > 0, got {value!r}") from exc
    return parsed


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-escalation-key-arg
def _escalation_key_arg(value: str) -> str:
    """argparse type for --escalation-key: rejects an oversized value up
    front with a clear CLI error, rather than silently degrading it to
    "no key" the way ``record_tier2_escalation`` does for a non-CLI
    caller (e.g. one composing ``route_query`` directly). The CLI is the
    direct, interactive caller here, so a caller who passes a
    multi-megabyte string almost certainly did so by mistake (e.g. piped
    in the wrong variable) and is better served by an immediate, actionable
    error than a value that gets quietly discarded several layers down.

    ``escalation_key`` is meant to be a short, opaque request-correlation
    ID (a UUID is 36 characters) -- not arbitrary data -- so this mirrors
    ``doc_index._MAX_ESCALATION_KEY_LENGTH``, the same bound
    ``record_tier2_escalation`` itself enforces as a defense-in-depth
    fallback for any other caller.
    """
    if len(value) > _MAX_ESCALATION_KEY_LENGTH:
        raise argparse.ArgumentTypeError(
            f"--escalation-key must be at most {_MAX_ESCALATION_KEY_LENGTH} characters, "
            f"got {len(value)}"
        )
    return value
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-escalation-key-arg


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-cmd
def cmd_retrieve(argv: List[str]) -> int:
    """Route a query against a Markdown file through the JIT-retrieval cascade."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs retrieve",
        description=(
            "Route a query through the two-tier JIT-retrieval cascade and report the decision. "
            "Every escalation to Tier 2 is counted per document (cfs doc-index's tier2_escalations); "
            f"once that count reaches {_TIER2_BREAK_EVEN_ESCALATIONS} (the real break-even point, derived "
            "from measured OKF-build, OKF-per-query, and baseline-per-query token costs -- see "
            "cascade.py's _TIER2_BREAK_EVEN_ESCALATIONS), the response's tier2.should_build_okf "
            "flag turns on automatically -- no --expected-future-queries guess required. This requires "
            "a resolvable Studio project cache directory: outside one, nothing can be persisted, so "
            "tier2_escalations is always null and should_build_okf is always false, regardless of real "
            "escalation volume (see test_should_build_okf_is_false_outside_a_studio_project). The same "
            "null/false degradation also happens inside a Studio project when the escalation counter's "
            "lock can't be acquired in time or the persisted write itself fails -- the count is simply "
            "unknown for that call, not necessarily zero."
        ),
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument("query", help="Query text")
    p.add_argument(
        "--margin-threshold", type=_margin_threshold_arg, default=None,
        help="Enable a numeric TF-IDF margin cutoff for a large-margin Tier 1 resolution "
        "(default: disabled -- only an unambiguous score counts). Must be a finite number > 0.",
    )
    p.add_argument(
        "--expected-future-queries", type=int, default=None,
        help="Expected future query volume against this document, for the OKF-vs-baseline break-even math "
        "-- optional: tier2.should_build_okf is computed automatically from real recorded Tier-2 "
        "escalations regardless of whether this is passed; use this only to reason about a hypothetical "
        "future volume instead of the actually-observed-so-far count.",
    )
    p.add_argument(
        "--escalation-key", type=_escalation_key_arg, default=None,
        help="Idempotency key for this specific query attempt -- optional. Pass the same value again "
        "when retrying this exact query (e.g. after a timeout or transient failure) so the retry "
        f"doesn't inflate the persisted tier2_escalations count a second time. At most "
        f"{_MAX_ESCALATION_KEY_LENGTH} characters (an opaque correlation ID, not arbitrary data). "
        "Omit for a normal, one-shot invocation.",
    )
    args, filepath = ui.parse_file_command(p, argv)
    if filepath is None:
        return 2

    result, rc = ui.call_with_read_error_handling(
        filepath,
        lambda: route_query(
            filepath, args.query,
            margin_threshold=args.margin_threshold,
            expected_future_queries=args.expected_future_queries,
            escalation_key=args.escalation_key,
        ),
    )
    if rc is not None:
        return rc

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
        escalations = tier2.get("tier2_escalations")
        if escalations is not None:
            # Render the recorded count whenever it's known, not only once
            # should_build_okf flips true (constructorfabric/studio#136,
            # round-4 review) -- the JSON output already reports this field
            # unconditionally, so the human-readable view was hiding real,
            # already-recorded information the machine-readable one showed.
            if tier2.get("should_build_okf"):
                ui.substep(
                    f"  {escalations} Tier-2 escalations recorded for this document -- "
                    "building an OKF bundle now would pay for itself"
                )
            else:
                ui.substep(f"  {escalations} Tier-2 escalations recorded for this document")
    if "read_gate" in data and data["read_gate"]["needs_confirmation"]:
        gate = data["read_gate"]
        ui.substep(f"read gate: needs confirmation ({gate['total_lines']} lines > {gate['threshold']})")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-cmd-format
