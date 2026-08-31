"""Studio tfidf-score command — score a Markdown file's retrieval sections
against a query via TF-IDF, for inspecting/benchmarking the JIT-retrieval
mechanical gate independent of any cascade routing logic built on top of it.

Thin CLI wrapper around ``studio.utils.tfidf``.

@cpt-flow:cpt-studio-flow-traceability-validation-validate:p1
"""

import argparse
from typing import List

from ..utils.tfidf import score_sections
from ..utils.ui import ui


# @cpt-begin:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-cmd
def cmd_tfidf_score(argv: List[str]) -> int:
    """Score a Markdown file's retrieval sections against a query via TF-IDF."""
    p = argparse.ArgumentParser(
        prog="cfs tfidf-score",
        description="Rank a Markdown file's retrieval sections against a query via TF-IDF.",
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument("query", help="Query text to score sections against")
    args = p.parse_args(argv)

    filepath = ui.require_existing_file(args.file)
    if filepath is None:
        return 2

    result = score_sections(filepath, args.query)

    output = {
        "file": str(filepath),
        "query": args.query,
        "margin": result["margin"],
        "unambiguous": result["unambiguous"],
        "ranked": result["ranked"],
    }
    ui.result(output, human_fn=_human_tfidf_score)
    return 0
# @cpt-end:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-cmd


# @cpt-begin:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-cmd-format
def _human_tfidf_score(data: dict) -> None:
    ui.header("TF-IDF Score")
    ui.substep(f"query: {data['query']!r}")
    if not data["ranked"]:
        ui.substep("(no retrieval sections in this document)")
        ui.blank()
        return
    if data["unambiguous"]:
        ui.substep("confidence: unambiguous (top score positive, every other section scores 0)")
    elif data["margin"] is not None:
        ui.substep(f"confidence: margin {data['margin']:.2f}x over the runner-up")
    else:
        ui.substep("confidence: none (top score is 0 -- no query term matched anywhere)")
    for entry in data["ranked"]:
        ui.substep(f"  {entry['score']:.6f}  [{entry['line_start']}-{entry['line_end']}] {entry['heading']}")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-cmd-format
