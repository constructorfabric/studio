"""Two-tier JIT-retrieval cascade: combine heading-nav and TF-IDF into a
routing decision (Tier 1), falling back to an OKF-vs-baseline choice (Tier
2) only when Tier 1 can't resolve confidently on its own.

Pure decision logic: never reads more of the document than heading-nav/
TF-IDF/OKF status already needed, and never calls an LLM -- the actual
answering step (reading the picked section(s), or the whole document) stays
an external caller's job, same as every other module in this package.

Tier 1 routing table (real evidence, see the design session's findings):

| # | Pattern                                             | Resolution              |
|---|------------------------------------------------------|--------------------------|
| 1 | heading-nav: 0 hits                                   | escalate                |
| 2 | heading-nav>0, TF-IDF agrees, unambiguous             | resolved (Tier 1)       |
| 3 | heading-nav>0, TF-IDF disagrees                       | resolved_multi (Tier 1) |
| 4 | heading-nav>0, TF-IDF agrees, margin not unambiguous  | escalate                |

Row 2's "large margin" is deliberately restricted to ``unambiguous=True``
rather than a numeric margin cutoff: the only two real data points measured
for this design (an infinite margin on a correct pick, and 1.06x-1.58x
margins on two independently wrong picks) support "unambiguous is safe,
anything finite isn't yet proven safe" -- not a specific numeric threshold.
``margin_threshold`` exists so a numeric cutoff can be enabled later, once
there's real evidence for one, without an API change.

Tier 2 never recommends an OKF concept file known to be stale/missing for
the candidate section Tier 1 identified (see :func:`route_tier2`) -- this is
this cascade's answer to the "does staleness block or serve-stale" design
question: since nothing in this codebase can perform a background rebuild
(there is no job runner, and by design no module here ever calls an LLM),
serving a known-stale OKF pointer would be a silent wrong answer with no
mechanism to ever correct itself. Falling back to baseline is the only
option that fits what this codebase can actually guarantee.

@cpt-algo:cpt-studio-algo-traceability-validation-cascade:p1
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional, cast

from .doc_index import get_or_build_doc_index
from .heading_nav import find_sections
from .okf import get_okf_status
from .read_gate import check_gate
from .tfidf import score_sections

#: Real, measured per-query token rates (see the design session's findings).
_OKF_BUILD_COST_TOKENS = 301_187
_OKF_PER_QUERY_TOKENS = 45_735
_BASELINE_PER_QUERY_TOKENS = 333_573


def _as_candidate(section: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "heading": section["heading"],
        "line_start": section["line_start"],
        "line_end": section["line_end"],
    }


def _validate_margin_threshold(margin_threshold: Optional[float]) -> None:
    """Reject a non-finite or non-positive ``margin_threshold`` before it can
    reach row 4's comparison.

    ``commands/cascade.py``'s ``_margin_threshold_arg`` enforces this same
    rule for the CLI, but a direct Python caller of :func:`route_tier1`/
    :func:`route_query` bypasses argparse entirely -- without this check
    here too, a non-positive or non-finite threshold would make
    ``tfidf_result["margin"] >= margin_threshold`` fire on virtually any
    finite margin, silently defeating the "no finite value is yet proven
    safe" design basis this module's own docstring documents.
    """
    if margin_threshold is not None and not (math.isfinite(margin_threshold) and margin_threshold > 0):
        raise ValueError(f"margin_threshold must be a finite number > 0, got {margin_threshold!r}")


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-tier1
def route_tier1(path: Path, query: str, *, margin_threshold: Optional[float] = None) -> Dict[str, Any]:
    """Apply the Tier 1 routing table to a query against ``path``.

    Returns ``{"tier": "resolved" | "resolved_multi" | "escalate", "reason":
    str, "candidates": [...]}``. ``candidates`` is the section(s) a caller
    should actually read: one for rows 2/4 (row 4 despite escalating, since
    it's still the best Tier-1 guess to hand Tier 2), two for row 3, none
    for row 1 (heading-nav found nothing to anchor a guess to at all).
    """
    _validate_margin_threshold(margin_threshold)
    nav_first_match = find_sections(path, query)["first_match"]
    if nav_first_match is None:
        return {"tier": "escalate", "reason": "heading_nav_no_hits", "candidates": []}
    # pylint's astroid inference traces find_sections()'s "matches[0] if matches
    # else None" ternary and keeps treating this as Optional even after the
    # None-check above narrows it -- a known astroid limitation across module
    # boundaries (github.com/pylint-dev/pylint/issues/3162), not a real risk here.
    nav_pick = cast(Dict[str, Any], nav_first_match)

    tfidf_result = score_sections(path, query)
    # find_sections and score_sections both read retrieval_sections from the
    # same get_or_build_doc_index(path) call: a heading-nav match guarantees
    # at least one section exists, so TF-IDF always has one to rank too.
    tfidf_pick = tfidf_result["ranked"][0]

    if tfidf_pick["line_start"] != nav_pick["line_start"]:  # pylint: disable=unsubscriptable-object
        return {
            "tier": "resolved_multi",
            "reason": "heading_nav_tfidf_disagree",
            "candidates": [_as_candidate(nav_pick), _as_candidate(tfidf_pick)],
        }

    agree_large_margin = tfidf_result["unambiguous"] or (
        margin_threshold is not None
        and tfidf_result["margin"] is not None
        and tfidf_result["margin"] >= margin_threshold
    )
    if agree_large_margin:
        return {
            "tier": "resolved",
            "reason": "heading_nav_tfidf_agree_large_margin",
            "candidates": [_as_candidate(nav_pick)],
        }

    return {
        "tier": "escalate",
        "reason": "diffuse_margin",
        "candidates": [_as_candidate(nav_pick)],
    }
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-tier1


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-tier2
def _baseline_recommendation(expected_future_queries: Optional[int]) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"recommendation": "baseline", "reason": "no_current_okf_bundle"}
    if expected_future_queries is not None and expected_future_queries > 0:
        okf_total = _OKF_BUILD_COST_TOKENS + _OKF_PER_QUERY_TOKENS * expected_future_queries
        baseline_total = _BASELINE_PER_QUERY_TOKENS * expected_future_queries
        rec["build_okf_break_even"] = {
            "okf_total_tokens": okf_total,
            "baseline_total_tokens": baseline_total,
            "building_okf_would_pay_off": okf_total < baseline_total,
        }
    return rec


def route_tier2(
    path: Path,
    tier1_result: Dict[str, Any],
    *,
    expected_future_queries: Optional[int] = None,
) -> Dict[str, Any]:
    """Choose OKF vs. baseline once Tier 1 has escalated.

    Only called for rows 1/4 (see :func:`route_tier1`). When Tier 1 named a
    candidate section (row 4), only that section's concept file must be
    current. Row 1 has no candidate section to narrow to -- heading-nav
    found nothing, so the query could need any section -- and OKF's own
    (external, LLM-driven) file-selection step picks among *whatever this
    function hands it*; recommending OKF there while some other section is
    stale or missing would let that external step land on exactly the
    untrustworthy one. Either way, a stale or missing concept file in the
    checked set downgrades the recommendation to baseline with
    ``okf_needs_rebuild: True`` rather than risking a known-wrong summary --
    see this module's docstring for why that's the only coherent choice
    here.
    """
    status = get_okf_status(path)
    # get_okf_status() returns one entry per retrieval section regardless of
    # whether anything was ever summarized -- an "available" bundle_dir with
    # every entry "missing" means no concept file has actually been written
    # yet, which is "no bundle" for this decision, not "bundle exists."
    bundle_exists = status["available"] and any(entry["status"] != "missing" for entry in status["entries"])
    if not bundle_exists:
        return _baseline_recommendation(expected_future_queries)

    candidates = tier1_result.get("candidates", [])
    if candidates:
        by_line_start = {entry["line_start"]: entry for entry in status["entries"]}
        relevant = [by_line_start.get(c["line_start"]) for c in candidates]
        # A candidate that no longer maps to a current section (the
        # document changed structurally between Tier 1 picking it and this
        # re-derived status) can't be verified at all -- silently dropping
        # it would let an all-unresolved candidate list pass the "any
        # stale/missing" check below vacuously (empty list, no False
        # values), recommending OKF on a candidate that was never actually
        # checked. Treat "can't verify" the same as "not current".
        if any(entry is None for entry in relevant):
            rec = _baseline_recommendation(expected_future_queries)
            rec["okf_needs_rebuild"] = True
            return rec
    else:
        # No named candidate (row 1): the external selector could land on
        # any section in the bundle, so every section must be trustworthy,
        # not just some of them.
        relevant = status["entries"]

    if any(entry["status"] != "current" for entry in relevant):
        rec = _baseline_recommendation(expected_future_queries)
        rec["okf_needs_rebuild"] = True
        return rec

    return {"recommendation": "okf", "reason": "okf_bundle_current", "bundle_dir": status["bundle_dir"]}
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-tier2


# @cpt-begin:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-route
def route_query(
    path: Path,
    query: str,
    *,
    margin_threshold: Optional[float] = None,
    expected_future_queries: Optional[int] = None,
) -> Dict[str, Any]:
    """Route one query end to end: Tier 1, then Tier 2 only if it escalates.

    When Tier 2 recommends baseline (a full-document read), also runs the
    large-read confirmation gate against the document's real line count --
    the integration point this cascade exists to close, so a baseline
    fallback never happens without the caller seeing whether it crosses the
    confirmation threshold.

    Returned shape is a stable contract, not incidental: top-level ``query``,
    ``tier``, ``reason``, ``candidates`` (:func:`route_tier1`'s own return,
    merged in) are always present; ``tier2`` (:func:`route_tier2`'s return,
    with ``recommendation``/``reason``/optional ``okf_needs_rebuild``) is
    added only when Tier 1 escalated; ``read_gate``
    (:func:`studio.utils.read_gate.check_gate`'s return, with
    ``needs_confirmation``/``total_lines``/``threshold``) is added only when
    Tier 2 recommends ``"baseline"``. ``commands/cascade.py``'s
    ``_human_retrieve`` and ``tests/test_cascade.py`` both key into these
    fields by name -- changing a key here is a breaking change for both and
    should be treated as one (versioned or coordinated), not a routine edit.
    """
    tier1 = route_tier1(path, query, margin_threshold=margin_threshold)
    result: Dict[str, Any] = {"query": query, **tier1}
    if tier1["tier"] != "escalate":
        return result

    tier2 = route_tier2(path, tier1, expected_future_queries=expected_future_queries)
    result["tier2"] = tier2

    if tier2["recommendation"] == "baseline":
        index = get_or_build_doc_index(path)
        result["read_gate"] = check_gate(index["total_lines"])

    return result
# @cpt-end:cpt-studio-algo-traceability-validation-cascade:p1:inst-cascade-route
