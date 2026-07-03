"""check-language command — scan Markdown artifacts for disallowed Unicode scripts."""
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-imports
import argparse
import logging
from pathlib import Path
from typing import List

from ._validation_config import add_ignore_argument, load_current_validation_config
from ..utils import error_codes as EC
from ..utils.ui import ui
logger = logging.getLogger(__name__)
_DIAGNOSTIC_LOGGER = logging.getLogger(f"{__name__}.diagnostics")
_DIAGNOSTIC_LOGGER.addHandler(logging.NullHandler())
_DIAGNOSTIC_LOGGER.propagate = False
# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-imports

# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-parse-args
def _build_language_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check-language",
        description=(
            "Scan Markdown artifacts for characters outside the allowed Unicode "
            "script set.  Language policy is read from project validation config "
            "([validation] allowed_content_languages) or set via --languages."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="path",
        help="Files or directories to scan (default: project architecture/ folder)",
    )
    parser.add_argument(
        "--languages",
        default=None,
        metavar="CODES",
        help="Comma-separated language codes to allow, e.g. 'en' or 'en,ru'. "
             "Overrides configured validation policy.",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress summary header; show violations only.",
    )
    add_ignore_argument(
        parser,
        "Glob pattern of files to skip (e.g. 'translations/**/*.md'). "
        "Can be repeated. Also reads ignore_paths from validation config.",
    )
    return parser
# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-parse-args


# @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-resolve-languages
def _normalize_allowed_languages(raw_langs: List[str], supported_languages: List[str]) -> List[str]:
    normalized = [lang_code.strip().lower() for lang_code in raw_langs if lang_code.strip()]
    unknown = [lang_code for lang_code in normalized if lang_code not in supported_languages]
    if unknown:
        supported = ", ".join(supported_languages)
        raise ValueError(f"Unknown language code(s): {', '.join(unknown)}. Supported: {supported}")
    return normalized


def _resolve_allowed_languages(args, supported_languages: List[str]) -> List[str]:
    if args.languages is None:
        return _normalize_allowed_languages(_read_config_languages(), supported_languages)
    return _normalize_allowed_languages(args.languages.split(","), supported_languages)
# @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-resolve-languages


# @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-resolve-roots
def _resolve_scan_roots(path_args: List[str]) -> List[Path]:
    roots = [Path(pth) for pth in path_args] if path_args else _default_roots()
    missing = [str(root) for root in roots if not root.exists()]
    if missing:
        raise ValueError(f"Path(s) not found: {', '.join(missing)}")
    return roots
# @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-resolve-roots


def _group_violations(violations) -> tuple[dict[str, list], list[dict]]:
    # @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-group-violations
    by_file: dict[str, list] = {}
    violation_items: list[dict] = []
    for violation in violations:
        path_str = str(violation.path)
        by_file.setdefault(path_str, []).append(violation)
        violation_items.append({
            "path": path_str,
            "line": violation.lineno,
            "chars": violation.bad_chars_preview(),
            "preview": violation.line_preview(),
            "code": EC.CONTENT_LANGUAGE_VIOLATION,
        })
    return by_file, violation_items
    # @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-group-violations


def _resolve_validation_policy(args, supported_languages: List[str]):
    """Resolve language and symbol policy inputs for one scan invocation."""
    allowed_langs = _resolve_allowed_languages(args, supported_languages)
    ignore_patterns: List[str] = list(args.ignore)
    ignore_patterns.extend(_read_config_ignore_patterns())
    symbol_sets = _read_config_symbol_sets()
    allowed_chars = _read_config_allowed_chars()
    denied_chars = _read_config_denied_chars()
    return allowed_langs, ignore_patterns, symbol_sets, allowed_chars, denied_chars


# @cpt-algo:cpt-studio-algo-traceability-validation-check-language-scan:p1
def _run_language_scan(args, supported_languages):  # pylint: disable=too-many-locals
    from ..utils.content_language import (
        LangScanError,
        build_allowed_codepoints,
        build_allowed_ranges,
        build_denied_codepoints,
        scan_paths,
    )

    # @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-resolve-ignore
    policy = _resolve_validation_policy(args, supported_languages)
    allowed_langs, ignore_patterns, symbol_sets, allowed_chars, denied_chars = policy
    # @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-resolve-ignore

    roots = _resolve_scan_roots(args.paths)
    # @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-return-scan
    # @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-count-files
    # @cpt-begin:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-scan-execution
    try:
        violations = scan_paths(
            roots,
            build_allowed_ranges(
                allowed_langs,
                symbol_sets=symbol_sets,
                allowed_chars=allowed_chars,
            ),
            allowed_codepoints=build_allowed_codepoints(
                symbol_sets=symbol_sets,
                allowed_chars=allowed_chars,
            ),
            denied_codepoints=build_denied_codepoints(denied_chars),
            ignore_patterns=ignore_patterns,
        )
    except LangScanError as exc:
        raise ValueError(str(exc)) from exc
    # @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-scan-execution

    files_scanned = _count_md_files(roots)
    # @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-count-files

    by_file, violation_items = _group_violations(violations)
    return allowed_langs, files_scanned, violations, by_file, violation_items
    # @cpt-end:cpt-studio-algo-traceability-validation-check-language-scan:p1:inst-check-lang-return-scan


# @cpt-flow:cpt-studio-flow-traceability-validation-check-language:p1
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-run-scan
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-parse-args
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-user-check-language
def cmd_check_language(argv: List[str]) -> int:
    """Scan Markdown files for characters outside the allowed language set.

    Exit codes:
        0 — all files pass
        1 — configuration / path error
        2 — one or more language violations found
    """
    requested_argv = list(argv)
    # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-user-check-language

    args = _build_language_parser().parse_args(requested_argv)
    # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-parse-args

    try:
        # @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-error
        from ..utils.content_language import SUPPORTED_LANGUAGES

        allowed_langs, files_scanned, violations, by_file, violation_items = _run_language_scan(
            args, SUPPORTED_LANGUAGES
        )
        # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-run-scan
    except ValueError as exc:  # pylint: disable=user-facing-error-without-log
        _DIAGNOSTIC_LOGGER.warning("check-language failed: %s", exc, exc_info=True)
        ui.result({"status": "ERROR", "message": str(exc)})
        return 1
    # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-error

    # @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-pass
    if not violations:
        # @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-human-output
        result = {
            "status": "PASS",
            "allowed_languages": allowed_langs,
            "files_scanned": files_scanned,
            "violation_count": 0,
        }
        ui.result(result, human_fn=lambda d: _human_result(d, quiet=args.quiet))
        return 0
        # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-human-output
    # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-pass

    # @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-fail
    # @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-human-output
    result = {
        "status": "FAIL",
        "allowed_languages": allowed_langs,
        "files_scanned": files_scanned,
        "violation_count": len(violations),
        "file_count": len(by_file),
        "violations": violation_items,
    }
    # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-fail
    ui.result(result, human_fn=lambda d: _human_result(d, quiet=args.quiet))
    return 2
    # @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-human-output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-support

def _read_config_languages() -> List[str]:
    """Read allowed_content_languages from validation policy; fall back to ['en']."""
    validation = _read_validation_config()
    langs = getattr(validation, "allowed_content_languages", None)
    if langs:
        return list(langs)
    return ["en"]


def _read_config_ignore_patterns() -> List[str]:
    """Read ignore_paths glob patterns from validation policy."""
    validation = _read_validation_config()
    patterns = getattr(validation, "ignore_paths", None)
    return list(patterns) if patterns else []


def _read_config_symbol_sets() -> List[str]:
    """Read allowed_symbol_sets from validation config."""
    validation = _read_validation_config()
    symbol_sets = getattr(validation, "allowed_symbol_sets", None)
    return list(symbol_sets) if symbol_sets else []


def _read_config_allowed_chars() -> List[str]:
    """Read allowed_chars from validation config."""
    validation = _read_validation_config()
    allowed_chars = getattr(validation, "allowed_chars", None)
    return list(allowed_chars) if allowed_chars else []


def _read_config_denied_chars() -> List[str]:
    """Read denied_chars from validation config."""
    validation = _read_validation_config()
    denied_chars = getattr(validation, "denied_chars", None)
    return list(denied_chars) if denied_chars else []


def _read_validation_config():
    """Read validation policy from core.toml first, then legacy workspace fallback."""
    return load_current_validation_config()


def _default_roots() -> List[Path]:
    """Return the default scan root (architecture/ under project root)."""
    try:
        from ..utils.context import get_context

        ctx = get_context()
        if ctx is not None:
            return [ctx.project_root / "architecture"]
    except (ImportError, AttributeError, RuntimeError) as exc:
        logger.warning(
            "check-language: project context discovery failed; falling back to %s: %s: %s",
            Path.cwd() / "architecture",
            type(exc).__name__,
            exc,
        )
    return [Path.cwd() / "architecture"]


def _count_md_files(roots: List[Path]) -> int:
    count = 0
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".md":
            count += 1
        elif root.is_dir():
            count += sum(1 for _ in root.rglob("*.md"))
    return count

# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-support


# ---------------------------------------------------------------------------
# Human formatter
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-human-output

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
        "To allow additional scripts, add to config/core.toml:\n"
        "  [validation]\n"
        "  allowed_content_languages = [\"en\", \"ru\"]"
    )
    ui.blank()

# @cpt-end:cpt-studio-flow-traceability-validation-check-language:p1:inst-check-lang-human-output
