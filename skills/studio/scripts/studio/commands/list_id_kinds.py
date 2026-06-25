"""
List ID Kinds Command — list all ID kind tokens found in artifacts.

@cpt-flow:cpt-studio-flow-traceability-validation-query:p1
@cpt-dod:cpt-studio-dod-traceability-validation-queries:p1
"""

# @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-imports
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..utils.document import scan_cpt_ids
from ..utils.ui import ui
from .list_ids import (
    _collect_known_kinds,
    _get_registered_systems,
    _load_active_context,
    _resolve_registered_artifact_scan,
    _split_registered_kind_tokens,
)
# @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-imports


def _collect_artifacts_to_scan(args: argparse.Namespace) -> Optional[Tuple[object, List[Tuple[Path, str]]]]:
    """Resolve the artifact list for list-id-kinds."""
    if args.artifact:
        return _resolve_registered_artifact_scan(
            args.artifact,
            init_message="Constructor Studio not initialized",
            registry_message="Artifact not found in registry: {artifact}",
        )

    ctx = _load_active_context("Constructor Studio not initialized. Run 'cfs init' first.")
    if ctx is None:
        return None

    from ..utils.context import collect_artifacts_to_scan

    artifacts_to_scan, _path_to_source = collect_artifacts_to_scan(ctx)
    return ctx, artifacts_to_scan


def _infer_kinds(
    cpt_id: str,
    registered_systems: Set[str],
    known_kinds: Set[str],
) -> List[str]:
    """Infer ordered kind tokens from a CPT ID."""
    kind_tokens = _split_registered_kind_tokens(cpt_id, registered_systems, known_kinds)
    return [kind_tokens[index] for index in range(0, len(kind_tokens), 2)]

# @cpt-algo:cpt-studio-algo-traceability-validation-list-id-kinds:p1
# @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-scan-ids
def _collect_kind_maps(
    artifacts_to_scan: List[Tuple[Path, str]],
    registered_systems: Set[str],
    known_kinds: Set[str],
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, int]]:
    """Scan artifacts and build kind-to-template summary maps."""
    template_to_kinds: Dict[str, Set[str]] = {}
    kind_to_templates: Dict[str, Set[str]] = {}
    kind_counts: Dict[str, int] = {}

    for artifact_path, artifact_type in artifacts_to_scan:
        for hit in scan_cpt_ids(artifact_path):
            if hit.get("type") != "definition":
                continue
            cpt_id = str(hit.get("id") or "").strip()
            if not cpt_id:
                continue
            # @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-aggregate
            for kind_name in _infer_kinds(cpt_id, registered_systems, known_kinds):
                kind_to_templates.setdefault(kind_name, set()).add(artifact_type)
                template_to_kinds.setdefault(artifact_type, set()).add(kind_name)
                kind_counts[kind_name] = kind_counts.get(kind_name, 0) + 1
            # @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-aggregate
    return template_to_kinds, kind_to_templates, kind_counts
# @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-scan-ids


def _emit_kind_result(
    args: argparse.Namespace,
    artifacts_to_scan: List[Tuple[Path, str]],
    template_to_kinds: Dict[str, Set[str]],
    kind_to_templates: Dict[str, Set[str]],
    kind_counts: Dict[str, int],
) -> None:
    """Emit machine and human-readable list-id-kinds output."""
    all_kinds = sorted(kind_to_templates.keys())
    if args.artifact and artifacts_to_scan:
        artifact_path, artifact_type = artifacts_to_scan[0]
        kinds_in_artifact = sorted(template_to_kinds.get(artifact_type, set()))
        ui.result({
            "artifact": str(artifact_path),
            "artifact_type": artifact_type,
            "kinds": kinds_in_artifact,
            "kind_counts": {kind: kind_counts.get(kind, 0) for kind in kinds_in_artifact},
        }, human_fn=_human_list_id_kinds)
        return

    ui.result({
        "kinds": all_kinds,
        "kind_counts": {kind: kind_counts.get(kind, 0) for kind in all_kinds},
        "kind_to_templates": {kind: sorted(values) for kind, values in sorted(kind_to_templates.items())},
        "template_to_kinds": {kind: sorted(values) for kind, values in sorted(template_to_kinds.items())},
        "artifacts_scanned": len(artifacts_to_scan),
    }, human_fn=_human_list_id_kinds)


def cmd_list_id_kinds(argv: List[str]) -> int:
    """List ID kinds that actually exist in artifacts.

    Parses artifacts against their templates and returns only kinds
    that have at least one ID definition in the artifact(s).
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-parse-args
    p = argparse.ArgumentParser(
        prog="list-id-kinds",
        description="List ID kinds found in registered artifacts",
    )
    p.add_argument(
        "--artifact",
        default=None,
        help="Scan specific artifact (if omitted, scans all registered artifacts)",
    )
    args = p.parse_args(argv)
    # @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-parse-args

    # @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-resolve-artifacts
    # Collect artifacts to scan: (artifact_path, artifact_kind)
    resolved = _collect_artifacts_to_scan(args)
    if resolved is None:
        return 1
    ctx, artifacts_to_scan = resolved
    if not artifacts_to_scan:
        # @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-if-no-artifacts
        ui.result(
            {
                "kinds": [],
                "kind_counts": {},
                "kind_to_templates": {},
                "template_to_kinds": {},
                "artifacts_scanned": 0,
            }
        )
        return 0
        # @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-if-no-artifacts
    # @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-resolve-artifacts

    # @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-build-known
    registered_systems = _get_registered_systems(ctx)
    known_kinds = _collect_known_kinds(ctx)
    # @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-build-known

    template_to_kinds, kind_to_templates, kind_counts = _collect_kind_maps(
        artifacts_to_scan,
        registered_systems,
        known_kinds,
    )

    # @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-return
    _emit_kind_result(args, artifacts_to_scan, template_to_kinds, kind_to_templates, kind_counts)
    return 0
    # @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-return


# @cpt-begin:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-format
def _human_list_id_kinds(data: dict) -> None:
    ui.header("ID Kinds")

    artifact = data.get("artifact")
    if artifact:
        ui.detail("Artifact", str(artifact))
        ui.detail("Type", str(data.get("artifact_type", "?")))
    else:
        ui.detail("Artifacts scanned", str(data.get("artifacts_scanned", 0)))

    kinds = data.get("kinds", [])
    counts = data.get("kind_counts", {})

    if not kinds:
        ui.blank()
        ui.info("No ID kinds found.")
        ui.blank()
        return

    ui.blank()

    # Table: Kind | Count | Artifact types
    k2t = data.get("kind_to_templates", {})
    rows = []
    for k in kinds:
        c = str(counts.get(k, 0))
        templates = ", ".join(k2t.get(k, [])) if k2t else ""
        rows.append([k, c, templates] if templates else [k, c])

    headers = ["Kind", "Count", "Artifact types"] if k2t else ["Kind", "Count"]
    ui.table(headers, rows)

    # Reverse mapping: artifact type → kinds
    t2k = data.get("template_to_kinds", {})
    if t2k:
        ui.blank()
        ui.step("By artifact type:")
        for tpl, tpl_kinds in sorted(t2k.items()):
            ui.substep(f"  {tpl}: {', '.join(tpl_kinds)}")

    ui.blank()
# @cpt-end:cpt-studio-algo-traceability-validation-list-id-kinds:p1:inst-kinds-format
