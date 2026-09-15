"""
Studio CLI output utilities — dual-mode (human / JSON) rendering.

@cpt-algo:cpt-studio-algo-core-infra-display-info:p1

Default mode (no flag): human-friendly output with colors, progress, explanations.
With ``--json``: machine-readable JSON on stdout (for AI agents).

Usage in commands::

    from ..utils.ui import ui

    # Progress messages (always go to stdout, suppressed in --json mode)
    ui.header("Constructor Studio Init")
    ui.step("Copying core files...")
    ui.success("Initialized!")
    ui.error("Cache not found")

    # Final result — JSON or human summary
    ui.result(data_dict, human_fn=_format_init)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Global output mode
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-ui-json-mode-flag
_JSON_MODE: bool = False


def set_json_mode(enabled: bool) -> None:
    """Set whether command output should be JSON."""
    global _JSON_MODE  # pylint: disable=global-statement  # module-level output mode flag toggled once at CLI startup
    _JSON_MODE = enabled


def is_json_mode() -> bool:
    """Return whether command output is JSON."""
    return _JSON_MODE
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-ui-json-mode-flag


# ---------------------------------------------------------------------------
# ANSI helpers (stdlib only, no deps)
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-display-info:p1:inst-ui-ansi-helpers
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_WHITE = "\033[37m"


def _has_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if _has_color():
        return f"{code}{text}{_RESET}"
    return text
# @cpt-end:cpt-studio-algo-core-infra-display-info:p1:inst-ui-ansi-helpers


# ---------------------------------------------------------------------------
# Public API — progress messages (stdout, suppressed in JSON mode)
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-progress-header
def header(title: str) -> None:
    """Print a bold section header."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"\n  {_c(_BOLD, title)}\n")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-progress-header

# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-progress-step
def step(msg: str) -> None:
    """Print a step indicator."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"  {_c(_CYAN, '▸')} {msg}\n")


def substep(msg: str) -> None:
    """Print an indented sub-step."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"    {msg}\n")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-progress-step

# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-status-messages
def success(msg: str) -> None:
    """Print a success message."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"\n  {_c(_GREEN, '✓')} {_c(_GREEN, msg)}\n")


def error(msg: str) -> None:
    """Print an error message."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"\n  {_c(_RED, '✗')} {_c(_RED, msg)}\n")


def warn(msg: str) -> None:
    """Print a warning message."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"  {_c(_YELLOW, '⚠')} {msg}\n")


def info(msg: str) -> None:
    """Print an informational line."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"  {msg}\n")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-status-messages

# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-detail-hint
def detail(key: str, value: str) -> None:
    """Print a key: value detail line."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"    {_c(_DIM, key + ':')} {value}\n")


def code_scan_detail(code_scanned: Optional[int], code_skipped: Optional[int]) -> None:
    """Print the shared 'Code files scanned/skipped' detail lines for `--include-code`.

    Shared by `list-ids`/`where-used` human output so the two commands don't
    drift; *code_scanned* of ``None`` means `--include-code` wasn't passed.
    """
    if code_scanned is None:
        return
    detail("Code files scanned", str(code_scanned))
    if code_skipped:
        detail("Code files skipped", str(code_skipped))


def hint(msg: str) -> None:
    """Print a dim hint/suggestion."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"    {_c(_DIM, msg)}\n")


def blank() -> None:
    """Print a blank line."""
    if _JSON_MODE:
        return
    sys.stdout.write("\n")


def divider() -> None:
    """Print a thin divider."""
    if _JSON_MODE:
        return
    sys.stdout.write(f"  {_c(_DIM, '─' * 50)}\n")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-detail-hint

# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-table
def table(headers: List[str], rows: List[List[str]], indent: int = 4) -> None:
    """Print a simple aligned table to stdout."""
    if _JSON_MODE:
        return
    if not rows:
        return
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))
            else:
                widths.append(len(cell))
    prefix = " " * indent
    # Header
    hdr = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sys.stdout.write(f"{prefix}{_c(_BOLD, hdr)}\n")
    sys.stdout.write(f"{prefix}{_c(_DIM, '─' * len(hdr))}\n")
    # Rows
    for row in rows:
        line = "  ".join(
            (row[i] if i < len(row) else "").ljust(widths[i])
            for i in range(len(widths))
        )
        sys.stdout.write(f"{prefix}{line}\n")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-table

# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-file-action
def file_action(path: str, action: str) -> None:
    """Print a file action (created/updated/unchanged)."""
    if _JSON_MODE:
        return
    icons = {
        "created": _c(_GREEN, "+"),
        "updated": _c(_YELLOW, "~"),
        "unchanged": _c(_DIM, "="),
        "skipped": _c(_DIM, "-"),
        "deleted": _c(_RED, "×"),
        "missing_in_cache": _c(_RED, "!"),
        "preserved": _c(_DIM, "="),
        "dry_run": _c(_BLUE, "?"),
    }
    icon = icons.get(action, " ")
    sys.stdout.write(f"    {icon} {path} {_c(_DIM, f'({action})')}\n")
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-file-action


# ---------------------------------------------------------------------------
# Result output — the main dual-mode function
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-result-json
def result(
    data: Dict[str, Any],
    *,
    human_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """Output command result: JSON to stdout (--json) or human summary (default).

    Args:
        data: The result dict (always printed as JSON in --json mode).
        human_fn: Optional formatter that renders *data* as human-friendly text
                  to stdout. If None, a generic fallback is used.
    """
    if _JSON_MODE:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-result-json

    # @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-result-human
    if human_fn is not None:
        human_fn(data)
        return

    # Generic fallback
    status = data.get("status", "")
    message = data.get("message", "")
    if status in ("PASS", "OK", "DRY_RUN"):
        success(f"Done ({status})" + (f" — {message}" if message else ""))
    elif status in ("FAIL", "ERROR"):
        error(message or status)
    elif status == "ABORTED":
        warn("Aborted" + (f": {message}" if message else ""))
    else:
        info(f"Status: {status}" + (f" — {message}" if message else ""))
    # @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-result-human


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-json-safe-argparse
class _ArgumentParsingError(Exception):
    """Raised by :class:`JsonSafeArgumentParser` instead of the process
    exiting directly, so :func:`parse_args_or_json_error` can turn a
    parsing failure into the standard JSON/human ERROR result."""


class JsonSafeArgumentParser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose parsing *failures* raise instead of
    printing a plain-text usage banner and calling ``sys.exit`` directly.

    A missing/malformed argument otherwise bypasses this project's own
    ``--json`` output contract entirely: ``parser.error()`` writes
    unparseable plain text to stderr and exits, never touching
    :func:`result`, so a caller that always parses stdout as JSON gets an
    empty payload and an unhandled stderr string instead of a structured
    error. ``--help``/``--version`` are unaffected -- those call
    ``exit()``, not ``error()``, and stay human-oriented on purpose.
    """

    def error(self, message: str) -> None:  # noqa: D102 - argparse's own signature
        raise _ArgumentParsingError(message)


def parse_args_or_json_error(parser: "JsonSafeArgumentParser", argv: List[str]) -> Optional[argparse.Namespace]:
    """Parse ``argv`` with ``parser``, or emit the standard ERROR result and
    return ``None`` on a parsing failure -- the caller should ``return 2``.

    ``--help``/``--version`` still exit the process directly and are not
    caught here (see :class:`JsonSafeArgumentParser`).
    """
    try:
        return parser.parse_args(argv)
    except _ArgumentParsingError as exc:
        result(
            {"status": "ERROR", "message": str(exc)},
            human_fn=lambda d: error(d["message"]),
        )
        return None
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-json-safe-argparse


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-require-existing-file
def require_existing_file(file_arg: str) -> Optional[Path]:
    """Resolve a CLI file-path argument to an existing file, or emit the
    standard "File not found" ERROR result (JSON or human, via :func:`result`)
    and return ``None``.

    Shared by every command taking a single file-path argument (``doc-index``,
    ``tfidf-score``, ``okf-status``, ...) -- previously each reimplemented the
    same resolve-and-check block independently, which pylint's duplicate-code
    check correctly caught once a third copy appeared.
    """
    filepath = Path(file_arg).resolve()
    if filepath.is_file():
        return filepath
    result(
        {"file": str(filepath), "status": "ERROR", "message": "File not found"},
        human_fn=lambda d: error(f"{d['file']}: {d['message']}"),
    )
    return None
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-require-existing-file


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-parse-file-command
def parse_file_command(
    parser: JsonSafeArgumentParser, argv: List[str], *, file_attr: str = "file",
) -> "tuple[Optional[argparse.Namespace], Optional[Path]]":
    """Parse ``argv``, then resolve+validate its ``file_attr`` positional as
    an existing file -- the two-step dance every single-file-argument
    command needs (safe argparse, then :func:`require_existing_file`),
    extracted once a third command repeated it identically enough for
    pylint's duplicate-code check to catch it (the same reason
    :func:`require_existing_file` itself exists).

    Returns ``(args, filepath)``. ``filepath`` is ``None`` on either
    failure (a parsing error or a missing/non-file path) -- the caller
    should ``return 2`` in that case; the appropriate ERROR result has
    already been emitted either way. ``args`` is also ``None`` specifically
    on a parsing failure, since there's nothing parsed to return.
    """
    args = parse_args_or_json_error(parser, argv)
    if args is None:
        return None, None
    filepath = require_existing_file(getattr(args, file_attr))
    return args, filepath
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-parse-file-command


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-report-read-error
def report_read_error(filepath: Path, exc: BaseException) -> None:
    """Emit the standard "Cannot read file" ERROR result (JSON or human) for
    an ``OSError``/``UnicodeDecodeError`` raised while reading an already-
    existing file (a non-UTF-8 file, a permissions failure, a race after
    the initial existence check).

    Shared by every command that reads a file's content after
    :func:`parse_file_command` has already confirmed it exists (``doc-index``,
    ``tfidf-score``, ...) -- extracted once a second copy of the identical
    try/except/result block appeared, the same duplicate-code trigger
    :func:`require_existing_file` and :func:`parse_file_command` were each
    extracted for.
    """
    result(
        {"file": str(filepath), "status": "ERROR", "message": f"Cannot read file: {exc}"},
        human_fn=lambda d: error(f"{d['file']}: {d['message']}"),
    )
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-report-read-error


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-call-with-read-error-handling
def call_with_read_error_handling(filepath: Path, fn: Callable[[], T]) -> Tuple[Optional[T], Optional[int]]:
    """Call ``fn()`` -- a zero-arg callable that reads *filepath*'s content
    -- catching ``OSError``/``UnicodeDecodeError`` and reporting via
    :func:`report_read_error`.

    Returns ``(result, None)`` on success, or ``(None, 2)`` on a caught
    read failure; callers should ``return exit_code`` when it isn't
    ``None``. Extracted once the identical "call the thing that reads a
    file, catch its two read-failure exceptions, report, return 2" block
    appeared across four commands (``heading-nav``, ``retrieve``,
    ``read-gate``, ``okf-status``) -- the same duplicate-code trigger
    every other shared helper in this module was extracted for.
    """
    try:
        return fn(), None
    except (OSError, UnicodeDecodeError) as exc:
        report_read_error(filepath, exc)
        return None, 2
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-call-with-read-error-handling


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-display-heading
def display_heading(heading: Optional[str]) -> str:
    """Render a retrieval section's heading for human/text display.

    ``None`` is the synthetic preamble section's heading (content before a
    document's first real heading -- see doc_index.py's
    ``_build_retrieval_sections``), never a real heading's value; shown as
    a readable label instead of the literal string "None". Shared by every
    command that prints a section's heading (``doc-index``, ``tfidf-score``,
    ``okf-status``, ...).
    """
    return heading if heading is not None else "(preamble)"
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-display-heading


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-relpath
def relpath(path: str) -> str:
    """Return *path* relative to cwd, falling back to the original on error."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return path
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-relpath


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------
# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-singleton
class _UI:  # pylint: disable=too-few-public-methods
    """Namespace object so commands can do ``from ..utils.ui import ui``."""
    header = staticmethod(header)
    step = staticmethod(step)
    substep = staticmethod(substep)
    success = staticmethod(success)
    error = staticmethod(error)
    warn = staticmethod(warn)
    info = staticmethod(info)
    detail = staticmethod(detail)
    code_scan_detail = staticmethod(code_scan_detail)
    hint = staticmethod(hint)
    blank = staticmethod(blank)
    divider = staticmethod(divider)
    table = staticmethod(table)
    file_action = staticmethod(file_action)
    result = staticmethod(result)
    require_existing_file = staticmethod(require_existing_file)
    parse_file_command = staticmethod(parse_file_command)
    report_read_error = staticmethod(report_read_error)
    call_with_read_error_handling = staticmethod(call_with_read_error_handling)
    display_heading = staticmethod(display_heading)
    JsonSafeArgumentParser = JsonSafeArgumentParser
    parse_args_or_json_error = staticmethod(parse_args_or_json_error)
    is_json = staticmethod(is_json_mode)
    relpath = staticmethod(relpath)


ui = _UI()
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-singleton
