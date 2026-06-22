"""Show content scoped to a Studio traceability identifier."""

# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-imports
import argparse
import logging
from pathlib import Path
from typing import List

from ..utils.codebase import CodeFile
from ..utils.document import get_content_scoped
from ..utils.ui import ui
from .list_ids import _resolve_registered_artifact_scan
# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-imports

logger = logging.getLogger(__name__)


def _emit_code_content(args: argparse.Namespace) -> int:
    """Resolve and print scoped content for a code file."""
    code_path = Path(args.code).resolve()
    if not code_path.is_file():
        ui.result({"status": "ERROR", "message": f"Code file not found: {code_path}"})
        return 1

    cf, errs = CodeFile.from_path(code_path)
    if errs or cf is None:
        ui.result({"status": "ERROR", "message": f"Failed to parse code file: {errs}"})
        return 1

    content = cf.get_by_inst(args.inst) if args.inst else None
    if content is None:
        content = cf.get(args.id)
    if content is None:
        ui.result({"status": "NOT_FOUND", "id": args.id, "inst": args.inst})
        return 2

    ui.result({"status": "FOUND", "id": args.id, "inst": args.inst, "text": content}, human_fn=_human_get_content)
    return 0


def _emit_artifact_content(args: argparse.Namespace) -> int:
    """Resolve and print scoped content for a registered artifact."""
    resolved = _resolve_registered_artifact_scan(
        args.artifact,
        init_message="Constructor Studio not initialized",
        registry_message="Artifact not registered: {rel_path}",
        outside_root_message="Artifact not under project root: {artifact}",
    )
    if resolved is None:
        return 1

    ctx, artifacts_to_scan = resolved
    artifact_path, artifact_kind = artifacts_to_scan[0]
    result = get_content_scoped(artifact_path, id_value=args.id)
    if result is None:
        ui.result({"status": "NOT_FOUND", "id": args.id})
        return 2

    try:
        rel_path = artifact_path.relative_to(ctx.project_root).as_posix()
    except ValueError as exc:
        logger.warning(
            "Artifact path %s is not under project root %s",
            artifact_path,
            ctx.project_root,
            exc_info=exc,
        )
        ui.result({"status": "ERROR", "message": f"Artifact not under project root: {artifact_path}"})
        return 1

    artifact_entry = ctx.meta.get_artifact_by_path(rel_path)
    if artifact_entry is None:
        ui.result({"status": "ERROR", "message": f"Artifact not registered: {rel_path}"})
        return 1

    _artifact_meta, system = artifact_entry
    text, start_line, end_line = result
    ui.result({
        "status": "FOUND",
        "id": args.id,
        "text": text,
        "artifact": str(artifact_path),
        "start_line": start_line,
        "end_line": end_line,
        "kind": artifact_kind,
        "system": system.name,
        "traceability": getattr(_artifact_meta, "traceability", None),
    }, human_fn=_human_get_content)
    return 0

# @cpt-flow:cpt-studio-flow-traceability-validation-query:p1
def cmd_get_content(argv: List[str]) -> int:
    """Get best-effort content block for a specific Studio ID."""
    p = argparse.ArgumentParser(prog="get-content", description="Get content block for a specific Studio ID")
    p.add_argument("--artifact", default=None, help="Path to Studio artifact file")
    p.add_argument("--code", default=None, help="Path to code file (alternative to --artifact)")
    p.add_argument("--id", required=True, help="Studio ID to retrieve content for")
    p.add_argument("--inst", default=None, help="Instruction ID for code blocks (e.g., 'inst-validate-input')")
    args = p.parse_args(argv)

    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-if-get-content
    # Handle code file path
    if args.code:
        return _emit_code_content(args)

    # Handle artifact path
    if not args.artifact:
        ui.result({"status": "ERROR", "message": "Either --artifact or --code must be specified"})
        return 1
    return _emit_artifact_content(args)
    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-if-get-content

# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-format
def _human_get_content(data: dict) -> None:
    status = data.get("status", "")
    cid = data.get("id", "?")

    ui.header("Get Content")
    ui.detail("ID", cid)

    if status in ("NOT_FOUND",):
        inst = data.get("inst")
        if inst:
            ui.detail("Inst", inst)
        ui.blank()
        ui.warn("Content not found.")
        ui.blank()
        return

    if status in ("ERROR",):
        ui.error(data.get("message", "Unknown error"))
        ui.blank()
        return

    artifact = data.get("artifact")
    if artifact:
        artifact = ui.relpath(str(artifact))
        ui.detail("Artifact", str(artifact))
    kind = data.get("kind")
    if kind:
        ui.detail("Kind", str(kind))
    system = data.get("system")
    if system:
        ui.detail("System", str(system))
    start = data.get("start_line")
    end = data.get("end_line")
    if start is not None and end is not None:
        ui.detail("Lines", f"{start}-{end}")
    traceability = data.get("traceability")
    if traceability:
        ui.detail("Traceability", str(traceability))
    inst = data.get("inst")
    if inst:
        ui.detail("Inst", inst)

    text = data.get("text", "")
    if text:
        ui.blank()
        ui.divider()
        for line in text.splitlines():
            ui.info(line)
        ui.divider()

    ui.blank()
# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-format
