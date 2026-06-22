"""List Studio traceability identifiers from artifacts and code."""

# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-imports
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..utils.codebase import CodeFile
from ..utils.document import scan_cpt_ids
from ..utils.ui import ui
# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-imports


ArtifactScanList = List[Tuple[Path, str]]


# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context
def _collect_workspace_source_artifacts(ctx, source_name: str) -> List[Tuple[Path, str]]:
    """Collect artifacts from one reachable workspace source."""
    from ..utils.context import get_expanded_meta as _get_expanded_meta

    artifacts: List[Tuple[Path, str]] = []
    for sc in ctx.sources.values():
        if not sc.reachable or sc.meta is None or sc.path is None or sc.name != source_name:
            continue
        _meta = _get_expanded_meta(sc)
        if _meta is None:
            continue
        for art, _sys in _meta.iter_all_artifacts():
            art_path = (sc.path / art.path).resolve()
            if art_path.exists():
                artifacts.append((art_path, str(art.kind)))
    return artifacts


def _code_paths_for_entry(code_path: Path, extensions: List[str]) -> List[Path]:
    """Return code files covered by one registry codebase entry."""
    if not code_path.exists():
        return []
    if code_path.is_file():
        return [code_path]

    files: List[Path] = []
    for ext in extensions:
        files.extend(code_path.rglob(f"*{ext}"))
    return files


def _scan_code_references(ctx) -> Tuple[List[Dict[str, object]], int]:
    """Scan registered codebase entries for Studio marker references."""
    hits: List[Dict[str, object]] = []
    code_files_scanned = 0
    for cb_entry, _system_node in ctx.meta.iter_all_codebase():
        code_path = (ctx.project_root / cb_entry.path).resolve()
        for file_path in _code_paths_for_entry(code_path, cb_entry.extensions or [".py"]):
            try:
                rel = file_path.resolve().relative_to(ctx.project_root).as_posix()
            except (OSError, ValueError):
                rel = None
            if rel and ctx.meta.is_ignored(rel):
                continue

            cf, errs = CodeFile.from_path(file_path)
            if errs or cf is None:
                continue

            code_files_scanned += 1
            for ref in cf.references:
                hit: Dict[str, object] = {
                    "id": ref.id,
                    "kind": ref.kind or "code",
                    "type": "code_reference",
                    "artifact_type": "CODE",
                    "line": ref.line,
                    "artifact": str(file_path),
                    "marker_type": ref.marker_type,
                }
                if ref.phase is not None:
                    hit["phase"] = ref.phase
                if ref.inst:
                    hit["inst"] = ref.inst
                hits.append(hit)
    return hits, code_files_scanned
# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context


def _resolve_registered_artifact_scan(
    artifact_arg: str,
    *,
    init_message: str,
    registry_message: str,
) -> Optional[Tuple[object, ArtifactScanList]]:
    """Load context for one artifact argument and return its registered scan entry."""
    artifact_path = Path(artifact_arg).resolve()
    if not artifact_path.exists():
        ui.result({"status": "ERROR", "message": f"Artifact not found: {artifact_path}"})
        return None

    from ..utils.context import StudioContext

    ctx = StudioContext.load(artifact_path.parent)
    if not ctx:
        ui.result({"status": "ERROR", "message": init_message})
        return None

    try:
        rel_path = artifact_path.relative_to(ctx.project_root).as_posix()
    except ValueError:
        rel_path = None

    artifacts_to_scan: ArtifactScanList = []
    if rel_path:
        result = ctx.meta.get_artifact_by_path(rel_path)
        if result:
            artifact_meta, _system_node = result
            artifacts_to_scan.append((artifact_path, str(artifact_meta.kind)))

    if not artifacts_to_scan:
        ui.result({"status": "ERROR", "message": registry_message.format(artifact=artifact_arg, rel_path=rel_path)})
        return None
    return ctx, artifacts_to_scan


def _load_active_context(init_message: str) -> Optional[object]:
    """Load the active Studio context from the current working directory."""
    from ..utils.context import get_context

    ctx = get_context()
    if ctx:
        return ctx
    ui.result({"status": "ERROR", "message": init_message})
    return None


def _collect_known_kinds(ctx: object) -> Set[str]:
    """Collect known ID kinds from the active context and loaded kits."""
    from ..utils.context import collect_known_id_kinds

    return collect_known_id_kinds(ctx)


def _get_registered_systems(ctx: object) -> Set[str]:
    """Collect registered system slugs, including workspace sources when available."""
    from ..utils.context import WorkspaceContext

    if isinstance(ctx, WorkspaceContext):
        return set(ctx.get_all_registered_systems())
    return set((ctx.registered_systems or set()) if ctx else set())


def _match_system_prefix(cpt_id: str, registered_systems: Set[str]) -> Optional[str]:
    """Return the longest registered system slug that matches a CPT ID."""
    best: Optional[str] = None
    for sys_slug in registered_systems:
        prefix = f"cpt-{sys_slug}-"
        if cpt_id.lower().startswith(prefix.lower()):
            if best is None or len(sys_slug) > len(best):
                best = sys_slug
    return best


def _split_registered_kind_tokens(
    cpt_id: str,
    registered_systems: Set[str],
    known_kinds: Set[str],
) -> List[str]:
    """Return candidate kind tokens from a CPT ID after the system slug."""
    sys_slug = _match_system_prefix(cpt_id, registered_systems)
    if not sys_slug:
        return []
    remainder = cpt_id[len(f"cpt-{sys_slug}-"):]
    if not remainder:
        return []
    parts = [part.lower() for part in remainder.split("-") if part]
    if not known_kinds:
        return parts
    return [part for part in parts if part in known_kinds]


def _infer_primary_kind(
    cpt_id: str,
    registered_systems: Set[str],
    known_kinds: Set[str],
) -> Optional[str]:
    """Infer the first matching kind token from a CPT ID."""
    kind_tokens = _split_registered_kind_tokens(cpt_id, registered_systems, known_kinds)
    return kind_tokens[0] if kind_tokens else None


def _dedupe_hits(hits: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Keep the first hit per ID while preserving input order."""
    seen: Set[str] = set()
    unique_hits: List[Dict[str, object]] = []
    for hit in hits:
        id_val = str(hit.get("id", ""))
        if id_val in seen:
            continue
        seen.add(id_val)
        unique_hits.append(hit)
    return unique_hits


def _collect_artifact_hits(
    artifacts_to_scan: ArtifactScanList,
    registered_systems: Set[str],
    known_kinds: Set[str],
) -> List[Dict[str, object]]:
    """Scan artifact IDs and annotate each hit with inferred kind metadata."""
    hits: List[Dict[str, object]] = []
    for artifact_path, artifact_type in artifacts_to_scan:
        for fh in scan_cpt_ids(artifact_path):
            cid = str(fh.get("id") or "").strip()
            if not cid:
                continue
            hit: Dict[str, object] = {
                "id": cid,
                "kind": _infer_primary_kind(cid, registered_systems, known_kinds),
                "type": fh.get("type"),
                "artifact_type": artifact_type,
                "line": fh.get("line"),
                "artifact": str(artifact_path),
                "checked": bool(fh.get("checked", False)),
            }
            if fh.get("priority") is not None:
                hit["priority"] = fh.get("priority")
            hits.append(hit)
    return hits


def _apply_hit_filters(hits: List[Dict[str, object]], args: argparse.Namespace) -> List[Dict[str, object]]:
    """Apply kind, pattern, and duplicate filters to query hits."""
    filtered_hits = list(hits)
    if args.kind:
        kind_filter = str(args.kind)
        filtered_hits = [hit for hit in filtered_hits if str(hit.get("kind", "")) == kind_filter]

    if args.pattern:
        pattern = str(args.pattern)
        if args.regex:
            regex = re.compile(pattern)
            filtered_hits = [hit for hit in filtered_hits if regex.search(str(hit.get("id", ""))) is not None]
        else:
            filtered_hits = [hit for hit in filtered_hits if pattern in str(hit.get("id", ""))]

    if not args.all:
        filtered_hits = _dedupe_hits(filtered_hits)
    return filtered_hits


def _group_hits_by_kind(ids: List[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    """Group ID hits by inferred kind for human-readable output."""
    grouped_hits: Dict[str, List[Dict[str, object]]] = {}
    for hit in ids:
        kind_name = str(hit.get("kind") or "unknown")
        grouped_hits.setdefault(kind_name, []).append(hit)
    return grouped_hits


def _render_kind_hits(kind_name: str, items: List[Dict[str, object]]) -> None:
    """Render one kind section in the human formatter."""
    ui.step(f"{kind_name} ({len(items)})")
    for hit in items:
        line = hit.get("line", "")
        artifact = hit.get("artifact", "")
        suffix = f":{line}" if line else ""
        artifact_label = ui.relpath(artifact) if artifact else ""
        ui.substep(f"  {hit.get('id', '?')}  ({hit.get('type', '')}, {artifact_label}{suffix})")


# @cpt-flow:cpt-studio-flow-traceability-validation-query:p1
def cmd_list_ids(argv: List[str]) -> int:
    """List Studio IDs from artifacts.

    If no artifact is specified, scans all Studio-format artifacts from the adapter registry.
    """
    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-user-query
    p = argparse.ArgumentParser(prog="list-ids")
    p.add_argument("--artifact", default=None, help="Path to a registered artifact file (if omitted, scans all registered artifacts)")
    p.add_argument("--pattern", default=None, help="Filter IDs by substring or regex pattern")
    p.add_argument("--regex", action="store_true", help="Treat pattern as regular expression")
    p.add_argument("--kind", default=None, help="Filter by inferred ID kind")
    p.add_argument("--all", action="store_true", help="Include duplicate IDs in results")
    p.add_argument("--include-code", action="store_true", help="Also scan code files for Studio marker references")
    p.add_argument("--source", default=None, help="Filter by workspace source name (workspace mode only)")
    args = p.parse_args(argv)
    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-user-query

    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context
    # Collect artifacts to scan: (artifact_path, artifact_kind)
    artifacts_to_scan: ArtifactScanList = []
    ctx = None

    if args.artifact:
        resolved = _resolve_registered_artifact_scan(
            args.artifact,
            init_message="Constructor Studio not initialized. Run 'cfs init' first or specify --artifact.",
            registry_message="Artifact not registered in Constructor Studio registry.",
        )
        if resolved is None:
            return 1
        ctx, artifacts_to_scan = resolved
    else:
        # No artifact specified - use global context from cwd
        from ..utils.context import collect_artifacts_to_scan, WorkspaceContext

        ctx = _load_active_context("Constructor Studio not initialized. Run 'cfs init' first or specify --artifact.")
        if ctx is None:
            return 1

        is_workspace = isinstance(ctx, WorkspaceContext)

        if args.source and not is_workspace:
            ui.result({"status": "ERROR", "message": "--source requires a workspace context"})
            return 1

        if not args.source:
            # No source filter — use shared collection helper
            artifacts_to_scan, _ = collect_artifacts_to_scan(ctx)
        else:
            # --source filter: skip primary, scan only matching remote source
            if is_workspace:
                artifacts_to_scan = _collect_workspace_source_artifacts(ctx, args.source)

        if not artifacts_to_scan:
            ui.result({"count": 0, "artifacts_scanned": 0, "ids": []})
            return 0
    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-load-context

    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-scan-all
    # Parse artifacts and collect IDs
    registered_systems = _get_registered_systems(ctx)
    known_kinds = _collect_known_kinds(ctx)
    hits = _collect_artifact_hits(artifacts_to_scan, registered_systems, known_kinds)
    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-scan-all

    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-if-list-code
    # Scan code files if requested
    code_files_scanned = 0
    if args.include_code and not args.artifact and ctx:
        code_hits, code_files_scanned = _scan_code_references(ctx)
        hits.extend(code_hits)
    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-if-list-code

    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-if-list
    # Apply filters
    hits = _apply_hit_filters(hits, args)

    hits = sorted(hits, key=lambda h: (str(h.get("id", "")), int(h.get("line", 0))))

    result: Dict[str, object] = {
        "count": len(hits),
        "artifacts_scanned": len(artifacts_to_scan),
        "ids": hits,
    }
    if code_files_scanned > 0:
        result["code_files_scanned"] = code_files_scanned

    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-if-list
    # @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-return-query
    ui.result(result, human_fn=_human_list_ids)
    return 0
    # @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-return-query

# @cpt-begin:cpt-studio-flow-traceability-validation-query:p1:inst-query-format
def _human_list_ids(data: dict) -> None:
    count = data.get("count", 0)
    n_art = data.get("artifacts_scanned", 0)
    code_scanned = data.get("code_files_scanned")

    ui.header("List IDs")
    ui.detail("Artifacts scanned", str(n_art))
    if code_scanned is not None:
        ui.detail("Code files scanned", str(code_scanned))
    ui.detail("IDs found", str(count))

    ids = data.get("ids", [])
    if not ids:
        ui.blank()
        ui.info("No IDs found.")
        ui.blank()
        return

    grouped_hits = _group_hits_by_kind(ids)

    ui.blank()
    for kind_name in sorted(grouped_hits.keys()):
        _render_kind_hits(kind_name, grouped_hits[kind_name])

    ui.blank()
# @cpt-end:cpt-studio-flow-traceability-validation-query:p1:inst-query-format
