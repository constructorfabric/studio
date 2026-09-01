"""Studio doc-index command — build/reuse a cached structural index for a
Markdown file, so heading-based JIT retrieval reads a file's structure once,
not once per query.

Thin CLI wrapper around ``studio.utils.doc_index``.
"""

import argparse
import logging
from pathlib import Path
from typing import List

from ..utils.doc_index import get_or_build_doc_index
from ..utils.ui import ui

logger = logging.getLogger(__name__)


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-cmd
def cmd_doc_index(argv: List[str]) -> int:
    """Build (or reuse the cached) structural index for a Markdown file."""
    p = argparse.ArgumentParser(
        prog="cfs doc-index",
        description=(
            "Build or reuse a cached heading/section index for a Markdown file, "
            "so navigation reads the file's structure once, not once per query."
        ),
    )
    p.add_argument("file", help="Markdown file path")
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Force a fresh build even if a valid cached index exists",
    )
    args = p.parse_args(argv)

    filepath = Path(args.file).resolve()
    if not filepath.is_file():
        ui.result(
            {"file": str(filepath), "status": "ERROR", "message": "File not found"},
            human_fn=lambda d: ui.error(f"{d['file']}: {d['message']}"),
        )
        return 2

    try:
        index = get_or_build_doc_index(filepath, force_rebuild=args.rebuild)
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("doc-index: cannot read %s: %s", filepath, exc)
        ui.result(
            {"file": str(filepath), "status": "ERROR", "message": f"Cannot read file: {exc}"},
            human_fn=lambda d: ui.error(f"{d['file']}: {d['message']}"),
        )
        return 2

    output = {
        "file": str(filepath),
        "cache_hit": index["cache_hit"],
        "total_lines": index["total_lines"],
        "section_count": len(index["sections"]),
        "sections": index["sections"],
    }
    ui.result(output, human_fn=_human_doc_index)
    return 0
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-cmd


# @cpt-begin:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-cmd-format
def _human_doc_index(data: dict) -> None:
    ui.header("Doc Index")
    ui.substep(data["file"])
    hit = "cache hit — reused existing index" if data["cache_hit"] else "cache miss — built fresh index"
    ui.substep(hit)
    ui.substep(f"{data['section_count']} section(s), {data['total_lines']} total lines")
    for s in data["sections"]:
        summary = f" — {s['summary']}" if s.get("summary") else ""
        ui.substep(f"  H{s['level']} [{s['line_start']}-{s['line_end']}] {s['heading']}{summary}")
    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-doc-index:p1:inst-doc-index-cmd-format
