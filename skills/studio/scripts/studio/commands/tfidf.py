"""Studio tfidf-score command — score a Markdown file's retrieval sections
against a query via TF-IDF, for inspecting/benchmarking the JIT-retrieval
mechanical gate independent of any cascade routing logic built on top of it.

Thin CLI wrapper around ``studio.utils.tfidf``.
"""

import logging
from typing import List

from ..utils.tfidf import score_sections
from ..utils.ui import ui

logger = logging.getLogger(__name__)


# @cpt-begin:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-cmd
def cmd_tfidf_score(argv: List[str]) -> int:
    """Score a Markdown file's retrieval sections against a query via TF-IDF."""
    p = ui.JsonSafeArgumentParser(
        prog="cfs tfidf-score",
        description=(
            "Rank a Markdown file's retrieval sections against a query via TF-IDF. "
            "The result includes a margin/unambiguous confidence signal -- check it "
            "before trusting the top-ranked section, since a nonzero score is never "
            "a correctness guarantee on its own."
        ),
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument("query", help="Query text to score sections against")
    args, filepath = ui.parse_file_command(p, argv)
    if filepath is None:
        return 2

    try:
        result = score_sections(filepath, args.query)
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("tfidf-score: cannot read %s: %s", filepath, exc)
        ui.report_read_error(filepath, exc)
        return 2

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
        heading = ui.display_heading(entry["heading"])
        ui.substep(f"  {entry['score']:.6f}  [{entry['line_start']}-{entry['line_end']}] {heading}")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-cmd-format
