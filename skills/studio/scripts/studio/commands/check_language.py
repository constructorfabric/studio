"""check-language command — scan Markdown artifacts for disallowed Unicode scripts.

@cpt-algo:cpt-studio-flow-traceability-validation-check-language:p1
"""
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-imports
import argparse
from pathlib import Path
from typing import List

from ..utils import error_codes as EC
from ..utils.ui import ui
# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-imports


# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-cmd-check-language
def cmd_check_language(argv: List[str]) -> int:
    """Scan Markdown files for characters outside the allowed language set.

    Exit codes:
        0 — all files pass
        1 — configuration / path error
        2 — one or more language violations found
    """
    p = argparse.ArgumentParser(
        prog="check-language",
        description=(
            "Scan Markdown artifacts for characters outside the allowed Unicode "
            "script set.  Language policy is read from workspace config "
            "([validation] allowed_content_languages) or set via --languages."
        ),
    )
    p.add_argument(
        "paths",
        nargs="*",
        metavar="path",
        help="Files or directories to scan (default: project architecture/ folder)",
    )
    p.add_argument(
        "--languages",
        default=None,
        metavar="CODES",
        help="Comma-separated language codes to allow, e.g. 'en' or 'en,ru'. "
             "Overrides workspace config.",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress summary header; show violations only.",
    )
    p.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Glob pattern of files to skip (e.g. 'translations/**/*.md'). "
             "Can be repeated. Also reads ignore_paths from workspace config.",
    )
    args = p.parse_args(argv)

    from ..utils.content_language import (
        SUPPORTED_LANGUAGES,
        LangScanError,
        build_allowed_ranges,
        scan_paths,
    )

    # ── Resolve allowed languages ────────────────────────────────────────────
    if args.languages is not None:
        raw_langs = [lang_code.strip().lower() for lang_code in args.languages.split(",") if lang_code.strip()]
        unknown = [lang_code for lang_code in raw_langs if lang_code not in SUPPORTED_LANGUAGES]
        if unknown:
            ui.result({
                "status": "ERROR",
                "message": (
                    f"Unknown language code(s): {', '.join(unknown)}. "
                    f"Supported: {', '.join(SUPPORTED_LANGUAGES)}"
                ),
            })
            return 1
        allowed_langs = raw_langs
    else:
        try:
            allowed_langs = _read_config_languages()
        except ValueError as exc:
            ui.result({"status": "ERROR", "message": str(exc)})
            return 1

    # ── Resolve ignore patterns ──────────────────────────────────────────────
    ignore_patterns: List[str] = list(args.ignore)
    try:
        ignore_patterns.extend(_read_config_ignore_patterns())
    except ValueError as exc:
        ui.result({"status": "ERROR", "message": str(exc)})
        return 1

    # ── Resolve scan roots ───────────────────────────────────────────────────
    if args.paths:
        roots = [Path(pth) for pth in args.paths]
    else:
        roots = _default_roots()

    missing = [str(r) for r in roots if not r.exists()]
    if missing:
        ui.result({
            "status": "ERROR",
            "message": f"Path(s) not found: {', '.join(missing)}",
        })
        return 1

    # ── Scan ─────────────────────────────────────────────────────────────────
    allowed_ranges = build_allowed_ranges(allowed_langs)
    try:
        violations = scan_paths(roots, allowed_ranges, ignore_patterns=ignore_patterns)
    except LangScanError as exc:
        ui.result({"status": "ERROR", "message": str(exc)})
        return 1

    files_scanned = _count_md_files(roots)

    if not violations:
        result = {
            "status": "PASS",
            "allowed_languages": allowed_langs,
            "files_scanned": files_scanned,
            "violation_count": 0,
        }
        ui.result(result, human_fn=lambda d: _human_result(d, quiet=args.quiet))
        return 0

    # Group violations by file for reporting
    by_file: dict = {}
    for v in violations:
        by_file.setdefault(str(v.path), []).append(v)

    violation_items = []
    for file_path, file_violations in by_file.items():
        for v in file_violations:
            violation_items.append({
                "path": file_path,
                "line": v.lineno,
                "chars": v.bad_chars_preview(),
                "preview": v.line_preview(),
                "code": EC.CONTENT_LANGUAGE_VIOLATION,
            })

    result = {
        "status": "FAIL",
        "allowed_languages": allowed_langs,
        "files_scanned": files_scanned,
        "violation_count": len(violations),
        "file_count": len(by_file),
        "violations": violation_items,
    }
    ui.result(result, human_fn=lambda d: _human_result(d, quiet=args.quiet))
    return 2

# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-cmd-check-language


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-helpers

def _read_config_languages() -> List[str]:
    """Read allowed_content_languages from workspace config; fall back to ['en'].

    Raises ValueError if the workspace config file exists but cannot be parsed.
    """
    from ..utils.context import get_context
    from ..utils.workspace import find_workspace_config

    ctx = get_context()
    if ctx is None:
        return ["en"]
    _ws_cfg, _ws_err = find_workspace_config(ctx.project_root)
    if _ws_err:
        raise ValueError(f"Workspace config error: {_ws_err}")
    if _ws_cfg is not None and _ws_cfg.validation is not None:  # type: ignore[union-attr]
        langs = _ws_cfg.validation.allowed_content_languages  # type: ignore[union-attr]
        if langs:
            return langs
    return ["en"]


def _read_config_ignore_patterns() -> List[str]:
    """Read ignore_paths glob patterns from workspace config.

    Returns an empty list when the workspace config is absent or has no
    ignore_paths setting.  Raises ValueError if the config file cannot be
    parsed.
    """
    from ..utils.context import get_context
    from ..utils.workspace import find_workspace_config

    ctx = get_context()
    if ctx is None:
        return []
    _ws_cfg, _ws_err = find_workspace_config(ctx.project_root)
    if _ws_err:
        raise ValueError(f"Workspace config error: {_ws_err}")
    if _ws_cfg is not None and _ws_cfg.validation is not None:  # type: ignore[union-attr]
        patterns = getattr(_ws_cfg.validation, "ignore_paths", None)
        if patterns:
            return list(patterns)
    return []


def _default_roots() -> List[Path]:
    """Return the default scan root (architecture/ under project root)."""
    try:
        from ..utils.context import get_context

        ctx = get_context()
        if ctx is not None:
            return [ctx.project_root / "architecture"]
    except (ImportError, AttributeError, RuntimeError):
        pass
    return [Path.cwd() / "architecture"]


def _count_md_files(roots: List[Path]) -> int:
    count = 0
    for root in roots:
        if root.is_file():
            if root.suffix.lower() == ".md":
                count += 1
        elif root.is_dir():
            count += sum(1 for _ in root.rglob("*.md"))
    return count

# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-helpers


# ---------------------------------------------------------------------------
# Human formatter
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-human-result

def _human_result(data: dict, quiet: bool = False) -> None:
    status = data.get("status", "")
    allowed = data.get("allowed_languages", [])

    if not quiet:
        ui.header("check-language")
        ui.detail("Allowed languages", ", ".join(allowed))
        n_files = data.get("files_scanned", 0)
        ui.detail("Files scanned", str(n_files))
        ui.blank()

    if status == "PASS":
        ui.success("No language violations found.")
        ui.blank()
        return

    if status == "ERROR":
        ui.error(str(data.get("message", "Unknown error")))
        ui.blank()
        return

    n_viol = data.get("violation_count", 0)
    n_file_count = data.get("file_count", 0)
    ui.warn(f"FAIL  {n_viol} violation(s) in {n_file_count} file(s)")
    ui.blank()

    violations = data.get("violations", [])
    by_file: dict = {}
    for v in violations:
        by_file.setdefault(v["path"], []).append(v)

    for file_path, file_violations in by_file.items():
        ui.substep(f"  {ui.relpath(file_path)}  ({len(file_violations)} line(s))")
        for v in file_violations:
            ui.substep(f"    line {v['line']:>4}  [{v['chars']}]  {v['preview']}")
        ui.blank()

    ui.hint("Fix: rewrite flagged content in the allowed language(s).")
    ui.hint(
        "To allow additional scripts, add to .cf-workspace.toml:\n"
        "  [validation]\n"
        "  allowed_content_languages = [\"en\", \"ru\"]"
    )
    ui.blank()

# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-human-result
