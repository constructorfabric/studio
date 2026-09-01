"""TF-IDF scoring over a document's retrieval sections.

Purely mechanical, no LLM call: tokenize each retrieval section's text,
weight terms by rarity across the whole document, score a query as the sum
of term-frequency x inverse-document-frequency over the query's own terms.

Scale assumption: this is JIT-retrieval infrastructure for a single real
document's worth of sections (the real corpus this was validated against
was a 166-page technical document, ~9 top-level sections) -- there's
deliberately no hard cap on section count or file size here, since any
concrete number would be an arbitrary guess with no real document behind
it, the same "real numbers, not assumptions" standard the rest of this
feature holds itself to. A caller feeding this an adversarially large or
malformed file is a resource-management concern for that caller, not
something this module should silently paper over with an unvalidated
threshold.

See constructorfabric/studio#104.

@cpt-algo:cpt-studio-algo-traceability-validation-tfidf:p1
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from .doc_index import get_or_build_doc_index, section_text

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LENGTH = 3


# @cpt-begin:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-tokenize
def tokenize(text: str) -> List[str]:
    """Lowercase, alphanumeric-only tokens, dropping anything shorter than 3
    characters. Short tokens (``up``, ``is``, ``a``) are common-word noise
    that dilutes real signal without adding any -- a real query tested
    during this feature's design ("making up") lost its only distinguishing
    word this way once ``up`` was filtered, reducing to the common word
    ``making`` and producing a confidently wrong top-ranked section; that's
    a real, documented failure mode of this scoring method, not a defect in
    the filter itself.
    """
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) >= _MIN_TOKEN_LENGTH]
# @cpt-end:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-tokenize


# @cpt-begin:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-score-helpers
def _inverse_document_frequency(doc_tokens: List[List[str]]) -> Dict[str, float]:
    """Standard idf: rarer terms (across this document's own sections) score
    higher. ``+1`` keeps a term present in every section from scoring zero
    weight rather than vanishing entirely."""
    section_count = len(doc_tokens)
    document_frequency: Counter = Counter()
    for tokens in doc_tokens:
        for term in set(tokens):
            document_frequency[term] += 1
    return {
        term: math.log(section_count / (1 + count)) + 1
        for term, count in document_frequency.items()
    }


def _rank_sections(
    sections: List[Dict[str, Any]],
    doc_tokens: List[List[str]],
    query_terms: List[str],
    idf: Dict[str, float],
) -> List[Dict[str, Any]]:
    """Score each section as sum(tf(term, section) x idf(term)) over the
    query's own terms, sorted descending."""
    ranked = []
    for section, tokens in zip(sections, doc_tokens, strict=True):
        term_count = len(tokens) or 1
        term_frequency = Counter(tokens)
        score = sum(
            (term_frequency.get(term, 0) / term_count) * idf.get(term, 0.0)
            for term in query_terms
        )
        ranked.append({
            "heading": section["heading"],
            "line_start": section["line_start"],
            "line_end": section["line_end"],
            "score": score,
        })
    ranked.sort(key=lambda entry: entry["score"], reverse=True)
    return ranked


def _confidence(ranked: List[Dict[str, Any]]) -> tuple:
    """See :func:`score_sections` for what ``margin``/``unambiguous`` mean.

    A single section with a positive score is unambiguous by definition --
    there is nothing else it could be confused with, the same as a section
    that beat every rival's zero score outright.
    """
    if not ranked or ranked[0]["score"] <= 0:
        return None, False
    if len(ranked) == 1:
        return None, True
    second_score = ranked[1]["score"]
    if not second_score:
        return None, True
    return ranked[0]["score"] / second_score, False
# @cpt-end:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-score-helpers


# @cpt-begin:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-score
def score_sections(path: Path, query: str) -> Dict[str, Any]:
    """Score every retrieval section in ``path`` against ``query`` via TF-IDF.

    Reuses :func:`get_or_build_doc_index` for section boundaries (read once
    per file, same as every other JIT-retrieval consumer), then reads the
    file once more to tokenize each section's own text -- TF-IDF is
    query-dependent, so unlike the structural index this can't be cached
    across different queries.

    Returns ``{"ranked": [...], "margin": float | None, "unambiguous":
    bool}``:

    - ``ranked``: sections sorted by score, descending, each
      ``{"heading", "line_start", "line_end", "score"}``.
    - ``margin``: ``top_score / second_score`` when both are positive and
      finite; ``None`` when there are fewer than two sections, or the top
      score itself is zero (no query term matched anywhere -- a margin
      computed from zero would be meaningless, not just infinite).
    - ``unambiguous``: ``True`` when the top score is positive and every
      other section scores exactly zero -- the real, distinctive-term case
      (a query like "KAPING" against a real document scored 0.0010 on its
      one relevant section and 0.0000 everywhere else). Kept as an
      explicit boolean rather than folding into ``margin`` as infinity,
      since ``float("inf")`` doesn't round-trip through JSON.

    A headingless document (no retrieval sections at all) returns
    ``{"ranked": [], "margin": None, "unambiguous": False}``.
    """
    index = get_or_build_doc_index(path)
    sections = index["retrieval_sections"]
    if not sections:
        return {"ranked": [], "margin": None, "unambiguous": False}

    lines = path.resolve().read_text(encoding="utf-8").split("\n")
    doc_tokens = [tokenize(section_text(lines, section)) for section in sections]
    idf = _inverse_document_frequency(doc_tokens)
    ranked = _rank_sections(sections, doc_tokens, tokenize(query), idf)
    margin, unambiguous = _confidence(ranked)

    return {"ranked": ranked, "margin": margin, "unambiguous": unambiguous}
# @cpt-end:cpt-studio-algo-traceability-validation-tfidf:p1:inst-tfidf-score
