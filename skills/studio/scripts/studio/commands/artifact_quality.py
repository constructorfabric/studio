"""`cfs artifact-quality` — a read-only advisory findings command.

Scans the registered Project Markdown artifacts with the structural artifact-quality detectors and
emits advisory :class:`ArtifactFinding`s (duplication in v1) as JSON or a one-line human summary.
Read-only and never gates: it rewrites no artifact, carries no combined score, and the exit code is
``0`` whenever the scan ran, whatever it found — only a usage error is non-zero.

This command owns the feature's scale contract (``architecture/features/artifact-quality.md`` §2): the
per-section token floor and size-ratio prune in the detector bound the scan, and ``--max-findings``
bounds the *output* — the JSON carries ``total_findings`` and ``truncated`` so a consumer sees the cap.

Implements the ``Assess Artifact Quality`` flow (``cpt-studio-flow-artifact-quality-assess``).

@cpt-flow:cpt-studio-flow-artifact-quality-assess:p1
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..utils.artifact_quality import SCHEMA_VERSION, ArtifactFinding
from ..utils.artifact_quality_detectors import detect_exact_duplication
from ..utils.context import collect_artifacts_to_scan, get_context
from ..utils.ui import ui

#: Detector name → callable(artifacts, project_root) -> findings. v1 ships duplication; a later task
#: registers purpose/gap/judged here and the selector + dispatch loop already handle more than one.
_DETECTORS: Dict[str, Callable[[Sequence[Tuple[Path, str]], Optional[Path]], List[ArtifactFinding]]] = {
    "duplication": detect_exact_duplication,
}

#: Default output bound (feature doc §2 Scale). ``0`` disables the cap.
_DEFAULT_MAX_FINDINGS = 200


# @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-parse
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfs artifact-quality",
        description="Scan registered Project artifacts for advisory semantic-quality findings "
        "(read-only, never gates).",
    )
    parser.add_argument(
        "--detectors",
        action="append",
        default=None,
        metavar="<name>",
        help="Detector(s) to run. Repeatable. Choices: "
        f"{', '.join(sorted(_DETECTORS))}. An unknown name is reported, not silently skipped. "
        "Default: all.",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=_DEFAULT_MAX_FINDINGS,
        metavar="N",
        help="Cap the number of findings emitted (the deterministic first N). 0 disables the cap. "
        f"Default: {_DEFAULT_MAX_FINDINGS}.",
    )
    return parser
# @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-parse


# @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-select
def _resolve_detectors(selected: Optional[List[str]]) -> Tuple[List[str], List[str]]:
    """Split the requested detector names into (known, unknown), preserving order and de-duplicating.

    ``None`` means "all registered detectors" — never an empty selection, which would silently assess
    nothing.
    """
    if not selected:
        return sorted(_DETECTORS), []
    known: List[str] = []
    unknown: List[str] = []
    for name in selected:
        if name in _DETECTORS:
            if name not in known:
                known.append(name)
        elif name not in unknown:
            unknown.append(name)
    return known, unknown
# @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-select


def _distinct_artifact_count(artifacts: Sequence[Tuple[Path, str]]) -> int:
    """How many distinct artifacts were scanned — the detector scans a repeated path once."""
    return len({str(path) for path, _kind in artifacts})


# @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-emit
def _human_artifact_quality(data: Dict[str, object]) -> None:
    """Render the report as a one-line summary plus a compact line per finding."""
    ui.header("Artifact Quality")
    if data.get("status") == "ERROR":
        ui.error(str(data.get("message", "error")))
        return
    detectors = data.get("detectors") or []
    ui.detail("Scanned", f"{data.get('artifacts_scanned', 0)} artifacts")
    ui.detail("Detectors", ", ".join(str(name) for name in detectors) or "none")
    findings = data.get("findings") or []
    total = data.get("total_findings", 0)
    summary = f"{total} finding(s)"
    if data.get("truncated"):
        summary += f" — showing the first {len(findings)} (--max-findings)"
    ui.info(summary)
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        primary = finding.get("primary") or {}
        where = str(primary.get("artifact_path", "?"))
        anchor = primary.get("anchor")
        if anchor:
            where = f"{where}#{anchor}"
        ui.substep(
            f"  [{finding.get('detector')}/{finding.get('severity')}] {where}: "
            f"{finding.get('message')}"
        )
# @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-emit


def cmd_artifact_quality(argv: List[str]) -> int:
    """Scan registered artifacts for advisory findings. Never gates — exit 0 when the scan ran."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.max_findings < 0:
        ui.result({"status": "ERROR", "message": "--max-findings must be >= 0"})
        return 1

    # @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-select
    selected, unknown = _resolve_detectors(args.detectors)
    if unknown:
        ui.result(
            {
                "status": "ERROR",
                "message": f"unknown detector(s): {', '.join(unknown)}",
                "available": sorted(_DETECTORS),
            }
        )
        return 1
    # @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-select

    ctx = get_context()
    if ctx is None:
        ui.result(
            {"status": "ERROR", "message": "Constructor Studio not initialized. Run 'cfs init' first."}
        )
        return 1

    # @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-scan
    artifacts, _ = collect_artifacts_to_scan(ctx)
    project_root = getattr(ctx, "project_root", None)
    findings: List[ArtifactFinding] = []
    for name in selected:
        findings.extend(_DETECTORS[name](artifacts, project_root))
    # @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-scan

    # @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-bound
    cap = args.max_findings
    truncated = bool(cap) and len(findings) > cap
    emitted = findings[:cap] if cap else findings
    # @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-bound

    # @cpt-begin:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-emit
    data: Dict[str, object] = {
        "status": "OK",
        "schema_version": SCHEMA_VERSION,
        "detectors": selected,
        "artifacts_scanned": _distinct_artifact_count(artifacts),
        "total_findings": len(findings),
        "truncated": truncated,
        "findings": [finding.to_dict() for finding in emitted],
    }
    ui.result(data, human_fn=_human_artifact_quality)
    return 0
    # @cpt-end:cpt-studio-flow-artifact-quality-assess:p1:inst-aq-assess-emit
