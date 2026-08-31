"""Heading-nav retrieval over a document's retrieval sections.

Purely mechanical, no LLM call: a case-insensitive literal-substring search
of a query against each retrieval section's own raw text -- the same
"``grep`` the query's words, then read the enclosing section" mechanism a
real ``grep -i`` invocation performs, mirrored here so it shares the same
section boundaries (:func:`studio.utils.doc_index.get_or_build_doc_index`)
every other retrieval method uses instead of re-deriving them.

See constructorfabric/studio#104.

@cpt-algo:cpt-studio-algo-traceability-validation-heading-nav:p1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .doc_index import get_or_build_doc_index, section_text


# @cpt-begin:cpt-studio-algo-traceability-validation-heading-nav:p1:inst-heading-nav-search
def find_sections(path: Path, query: str) -> Dict[str, Any]:
    """Find every retrieval section in ``path`` containing ``query`` literally.

    Case-insensitive substring match of the whole query string against each
    section's own text -- deliberately not tokenized or word-split, since
    this mirrors ``grep -i "<query>"`` against the raw content, not a
    ranking. A query that doesn't appear verbatim (different wording than
    the source) has zero hits everywhere: this method has no semantic
    fallback, by design -- that hard-failure mode is itself a real, useful
    signal for a caller deciding whether to escalate past it.

    Returns ``{"matches": [...], "first_match": {...} | None}``:

    - ``matches``: every section with at least one hit, in document order,
      each ``{"heading", "line_start", "line_end", "hit_count"}``.
    - ``first_match``: ``matches[0]``, or ``None`` when nothing matched --
      the "grep's first hit -> enclosing section" pick this method's real
      mechanism performs.

    An empty query, or a headingless document (no retrieval sections at
    all), returns ``{"matches": [], "first_match": None}``.
    """
    if not query.strip():
        return {"matches": [], "first_match": None}

    index = get_or_build_doc_index(path)
    sections = index["retrieval_sections"]
    if not sections:
        return {"matches": [], "first_match": None}

    lines = path.resolve().read_text(encoding="utf-8").split("\n")
    query_lower = query.lower()

    matches = []
    for section in sections:
        hit_count = section_text(lines, section).lower().count(query_lower)
        if hit_count:
            matches.append({
                "heading": section["heading"],
                "line_start": section["line_start"],
                "line_end": section["line_end"],
                "hit_count": hit_count,
            })

    return {"matches": matches, "first_match": matches[0] if matches else None}
# @cpt-end:cpt-studio-algo-traceability-validation-heading-nav:p1:inst-heading-nav-search
