"""PDSL command family."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Sequence

from ..utils.pdsl import (
    PdslSource,
    build_envelope,
    error_result,
    exit_code_for_results,
    read_source_file,
    validate_source,
)
from ..utils.ui import ui


# @cpt-begin:cpt-studio-dod-pdsl-validation-cli-command-surface:p1:inst-cli-thin-wrapper
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-user-help
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-return-help
def cmd_pdsl(argv: List[str]) -> int:
    """Dispatch the validate-only PDSL command family."""
    if not argv or argv[0] in ("-h", "--help"):
        _emit_pdsl_help()
        return 0
    subcommand = argv[0]
    rest = argv[1:]
    if subcommand == "validate":
        return _cmd_pdsl_validate(rest)
    ui.result(
        {
            "status": "ERROR",
            "message": f"Unsupported cfs pdsl command: {subcommand}",
            "supported": ["validate"],
        },
        human_fn=lambda _data: (
            ui.error(f"Unsupported cfs pdsl command: {subcommand}"),
            ui.hint("v1 supports only: cfs pdsl validate"),
            ui.hint("Scaffold generation is deferred beyond this MVP."),
        ),
    )
    return 1
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-return-help
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-user-help


# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-render-help
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-state-boundary
def _emit_pdsl_help() -> None:
    ui.result(
        {
            "status": "PASS",
            "command": "pdsl",
            "supported": ["validate"],
            "scope": "validate-only MVP",
            "deferred": ["scaffold", "aliases such as cfs validate --pdsl"],
        },
        human_fn=lambda _data: (
            ui.header("cfs pdsl"),
            ui.info("Validate PDSL instruction blocks in prompts and files."),
            ui.blank(),
            ui.step("Commands"),
            ui.substep("validate               Validate PDSL from --text, stdin -, or files"),
            ui.blank(),
            ui.info("Scope: v1 is validate-only."),
            ui.hint("Scaffold generation and aliases such as cfs validate --pdsl are deferred."),
            ui.hint("Run 'cfs pdsl validate --help' for validation options."),
        ),
    )
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-state-boundary
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-command-help:p1:inst-render-help


# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-user-validate
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-parse-args
def _cmd_pdsl_validate(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pdsl validate",
        description="Validate PDSL blocks from --text, stdin -, or file paths.",
    )
    parser.add_argument("paths", nargs="*", help="Files to validate, or '-' for stdin")
    parser.add_argument("--text", default=None, help="Inline PDSL text to validate")
    parser.add_argument("--verbose", action="store_true", help="Include expanded finding context")
    args = parser.parse_args(list(argv))
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-parse-args

# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-normalize-sources
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-input-safety
    selector_count = (
        int(args.text is not None)
        + int("-" in args.paths)
        + int(bool([p for p in args.paths if p != "-"]))
    )
    if selector_count != 1:
        data = {
            "command": "pdsl validate",
            "ok": False,
            "summary": {"pass_count": 0, "fail_count": 0, "error_count": 1, "finding_count": 0},
            "results": [{
                "source": "<invocation>",
                "status": "ERROR",
                "findings": [],
                "errors": [{
                    "message": "Provide exactly one input selector: --text, stdin '-', or one or more file paths",
                    "source_path": "<invocation>",
                    "kind": "INVOCATION_ERROR",
                }],
            }],
        }
        ui.result(data, human_fn=_render_human)
        return 1

    sources: List[PdslSource] = []
    results = []
    if args.text is not None:
        sources.append(PdslSource(source="<text>", text=args.text))
    elif "-" in args.paths:
        sources.append(PdslSource(source="<stdin>", text=sys.stdin.read()))
    else:
        for raw_path in args.paths:
            path = Path(raw_path)
            text, error = read_source_file(path)
            if error is not None:
                results.append(error_result(str(path), error))
            elif text is not None:
                results.append(validate_source(PdslSource(source=str(path), text=text), verbose=bool(args.verbose)))
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-input-safety
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-normalize-sources

# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-foreach-source
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-source-scan
# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-source-validate
    for source in sources:
        results.append(validate_source(source, verbose=bool(args.verbose)))
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-source-validate
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-source-scan
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-foreach-source

    _emit_validation_result(results, bool(args.verbose))
    exit_code = exit_code_for_results(results)
    # @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-if-error
    if exit_code == 1:
        # @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-return-error
        return 1
        # @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-return-error
    # @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-if-error
    # @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-else-if-fail
    if exit_code == 2:
        # @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-return-fail
        return 2
        # @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-return-fail
    # @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-else-if-fail
    # @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-else-pass
    # @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-return-pass
    return 0
    # @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-return-pass
    # @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-else-pass
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-user-validate


# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-select-output
def _emit_validation_result(results: List[object], verbose: bool) -> None:
    envelope = _build_validation_envelope(results, verbose)
    ui.result(envelope, human_fn=_render_human)
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-select-output


# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-build-summary
def _build_validation_envelope(results: List[object], verbose: bool) -> Dict[str, object]:
    return build_envelope(results, command="pdsl validate", verbose=verbose)
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-build-summary


# @cpt-begin:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-cli-thin-wrapper
def _render_human(data: Dict[str, object]) -> None:
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    results = data.get("results", []) if isinstance(data.get("results"), list) else []
    ok = bool(data.get("ok"))
    if ok:
        ui.success("PDSL validation PASS")
    else:
        ui.error("PDSL validation did not pass")
    ui.detail("summary", (
        f"pass={summary.get('pass_count', 0)} "
        f"fail={summary.get('fail_count', 0)} "
        f"error={summary.get('error_count', 0)} "
        f"findings={summary.get('finding_count', 0)}"
    ))
    for result in results:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status", ""))
        source = str(result.get("source", ""))
        ui.blank()
        ui.step(f"{source}: {status}")
        for error in result.get("errors", []) if isinstance(result.get("errors"), list) else []:
            if isinstance(error, dict):
                ui.error(str(error.get("message", "error")))
        for finding in result.get("findings", []) if isinstance(result.get("findings"), list) else []:
            if not isinstance(finding, dict):
                continue
            loc = f"{finding.get('line')}:{finding.get('column')}"
            ui.warn(f"{finding.get('rule_id')} {loc} {finding.get('message')}")
            hint = finding.get("hint")
            if hint:
                ui.hint(str(hint))
# @cpt-end:cpt-studio-flow-pdsl-validation-cli-validate-input:p1:inst-cli-thin-wrapper
# @cpt-end:cpt-studio-dod-pdsl-validation-cli-command-surface:p1:inst-cli-thin-wrapper
