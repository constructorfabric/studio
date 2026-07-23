"""
Whatsnew Display Utilities

Shared helpers for displaying whatsnew entries from whatsnew.toml files.
Used by both `cfs update` (core) and `cfs kit update` (kit).
"""

# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-imports
import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Tuple

from ._tomllib_compat import tomllib
from .stderr_logging import emit_stderr_message

logger = logging.getLogger(__name__)
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-imports


def _emit_terminal_message(message: str) -> None:
    """Emit human-facing terminal text through the logger channel."""
    emit_stderr_message(message.rstrip("\n") + "\n", logger_name=f"{__name__}.stderr")

# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-format
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])")
_BOLD_MARKUP_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`(.+?)`")
_ATX_HEADING_RE = re.compile(r"^(?P<indent>\s{0,3})#{1,6}\s+(?P<text>.*?)(?:\s+#+)?\s*$")
_UNORDERED_LIST_RE = re.compile(r"^(?P<indent>\s*)[-+*]\s+(?P<text>.*)$")
_ORDERED_LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)\.\s+(?P<text>.*)$")
_FENCED_CODE_OPEN_RE = re.compile(
    r"^\s*(?P<delimiter>`{3,}|~{3,})(?P<info>.*)$"
)
_INLINE_MARKDOWN_SPAN_RE = re.compile(r"\*\*.+?\*\*|`.+?`")
_ANSI_BOLD = "\033[1m"
_ANSI_CYAN = "\033[36m"
_ANSI_RESET = "\033[0m"


def strip_control_chars(text: str, *, preserve_newlines: bool = False) -> str:
    """Strip ANSI and control characters from text."""
    sanitized = _ANSI_ESCAPE_RE.sub("", str(text))
    sanitized = sanitized.replace("\x1b", "")
    if preserve_newlines:
        return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", sanitized)
    return re.sub(r"[\x00-\x1f\x7f]", "", sanitized)


def _replace_bold_markup(match: re.Match[str]) -> str:
    return match.group(1)


def _replace_bold_markup_with_ansi(match: re.Match[str]) -> str:
    return f"{_ANSI_BOLD}{match.group(1)}{_ANSI_RESET}"


def _replace_inline_code_markup(match: re.Match[str]) -> str:
    return match.group(1)


def _replace_inline_code_markup_with_ansi(match: re.Match[str]) -> str:
    return f"{_ANSI_CYAN}{match.group(1)}{_ANSI_RESET}"

# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-version-cmp
def parse_semver(version: str) -> Tuple[int, ...]:
    """Parse semantic version string into tuple (major, minor, patch).

    Handles common formats: "1.2.3", "v1.2.3", "whatsnew.1.2.3".
    Returns (0, 0, 0) for unparseable versions.
    """
    # Strip common prefixes
    v = version.strip()
    if v.startswith("whatsnew."):
        v = v[9:]
    if v.startswith("v"):
        v = v[1:]

    prerelease = False
    if "-" in v:
        v, _, _ = v.partition("-")
        prerelease = True
    elif "+" in v:
        v, _, _ = v.partition("+")

    parts = v.split(".")
    numeric_parts = []
    found_numeric = False
    for part in parts[:3]:
        match = re.match(r"(\d+)", part)
        if match:
            numeric_parts.append(int(match.group(1)))
            found_numeric = True
        else:
            numeric_parts.append(0)
    while len(numeric_parts) < 3:
        numeric_parts.append(0)
    if not found_numeric:
        return (0, 0, 0)
    release_rank = 0 if prerelease else 1
    return (numeric_parts[0], numeric_parts[1], numeric_parts[2], release_rank)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings semantically.

    Returns:
        -1 if v1 < v2
         0 if v1 == v2
         1 if v1 > v2
    """
    t1 = parse_semver(v1)
    t2 = parse_semver(v2)
    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-version-cmp


# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-ansi-check
def stderr_supports_ansi() -> bool:
    """Check if stderr supports ANSI escape codes."""
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-ansi-check

# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-format-text
def format_whatsnew_text(text: str, *, use_ansi: bool) -> str:
    """Format markdown-like text for terminal display.

    Converts **bold** and `code` to ANSI sequences when use_ansi=True,
    otherwise strips the markers.
    """
    if use_ansi:
        formatted = _BOLD_MARKUP_RE.sub(_replace_bold_markup_with_ansi, text)
        return _INLINE_CODE_RE.sub(_replace_inline_code_markup_with_ansi, formatted)
    plain = _BOLD_MARKUP_RE.sub(_replace_bold_markup, text)
    return _INLINE_CODE_RE.sub(_replace_inline_code_markup, plain)
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-format-text


def _terminal_text_width() -> int:
    """Return a stable text width for the indented whatsnew body."""
    terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    return max(20, terminal_width - 4)


def _markdown_wrap_tokens(text: str) -> list[tuple[str, bool]]:
    """Return atomic inline-Markdown tokens and whether whitespace precedes them."""
    tokens: list[tuple[str, bool]] = []
    current_token = ""
    pending_whitespace = False
    position = 0

    def consume_plain(segment: str) -> None:
        """Add plain text, retaining whitespace boundaries around inline spans."""
        nonlocal current_token, pending_whitespace
        for part in re.findall(r"\s+|\S+", segment):
            if part.isspace():
                if current_token:
                    tokens.append((current_token, pending_whitespace))
                    current_token = ""
                pending_whitespace = True
            else:
                if not current_token:
                    # The pending whitespace applies to this new contiguous token.
                    current_token = part
                else:
                    current_token += part

    for span in _INLINE_MARKDOWN_SPAN_RE.finditer(text):
        consume_plain(text[position:span.start()])
        if not current_token:
            current_token = span.group(0)
        else:
            current_token += span.group(0)
        position = span.end()

    consume_plain(text[position:])
    if current_token:
        tokens.append((current_token, pending_whitespace))
    return tokens


def _wrap_markdown_line(
    text: str,
    *,
    width: int,
    initial_indent: str = "",
    subsequent_indent: str | None = None,
) -> list[str]:
    """Wrap Markdown prose without splitting bold or inline-code spans."""
    continuation_indent = initial_indent if subsequent_indent is None else subsequent_indent
    tokens = _markdown_wrap_tokens(text)
    if not tokens:
        return [initial_indent]

    wrapped: list[str] = []
    current = initial_indent
    has_content = False
    for token, preceded_by_whitespace in tokens:
        separator = " " if has_content and preceded_by_whitespace else ""
        candidate = f"{current}{separator}{token}"
        if has_content and len(candidate) > width:
            if preceded_by_whitespace:
                wrapped.append(current)
                current = f"{continuation_indent}{token}"
            else:
                # Adjacent text and inline markup must remain visually adjacent.
                current = candidate
        else:
            current = candidate
        has_content = True
    wrapped.append(current)
    return wrapped


def _wrap_prose_line(text: str, *, width: int) -> list[str]:
    """Wrap prose while preserving the source indentation and inline Markdown."""
    indent_length = len(text) - len(text.lstrip())
    return _wrap_markdown_line(
        text[indent_length:],
        width=width,
        initial_indent=text[:indent_length],
    )


def _is_closing_code_fence(
    source_line: str,
    *,
    delimiter_char: str,
    minimum_length: int,
) -> bool:
    """Return whether a line is a compatible closing fence for an open block."""
    stripped = source_line.lstrip()
    fence_length = len(stripped) - len(stripped.lstrip(delimiter_char))
    return (
        fence_length >= minimum_length
        and fence_length > 0
        and not stripped[fence_length:].strip()
    )


def _render_regular_markdown_line(
    source_line: str,
    *,
    use_ansi: bool,
    prose_width: int,
) -> list[str]:
    """Render one non-code Markdown line."""
    if not source_line.strip():
        return [""]

    heading = _ATX_HEADING_RE.match(source_line)
    if heading:
        heading_text = format_whatsnew_text(heading.group("text"), use_ansi=use_ansi)
        if use_ansi:
            heading_text = f"{_ANSI_BOLD}{heading_text}{_ANSI_RESET}"
        return [f"{heading.group('indent')}{heading_text}"]

    unordered_item = _UNORDERED_LIST_RE.match(source_line)
    if unordered_item:
        marker = f"{unordered_item.group('indent')}- "
        return [
            format_whatsnew_text(wrapped_line, use_ansi=use_ansi)
            for wrapped_line in _wrap_markdown_line(
                unordered_item.group("text"),
                width=prose_width,
                initial_indent=marker,
                subsequent_indent=" " * len(marker),
            )
        ]

    ordered_item = _ORDERED_LIST_RE.match(source_line)
    if ordered_item:
        marker = f"{ordered_item.group('indent')}{ordered_item.group('number')}. "
        return [
            format_whatsnew_text(wrapped_line, use_ansi=use_ansi)
            for wrapped_line in _wrap_markdown_line(
                ordered_item.group("text"),
                width=prose_width,
                initial_indent=marker,
                subsequent_indent=" " * len(marker),
            )
        ]

    return [
        format_whatsnew_text(wrapped_line, use_ansi=use_ansi)
        for wrapped_line in _wrap_prose_line(source_line, width=prose_width)
    ]


def _render_whatsnew_details(details: str, *, use_ansi: bool) -> list[str]:
    """Render the supported Markdown subset as readable terminal lines."""
    rendered: list[str] = []
    code_fence: str | None = None
    prose_width = _terminal_text_width()

    for source_line in details.splitlines():
        if code_fence is not None:
            if _is_closing_code_fence(
                source_line,
                delimiter_char=code_fence[0],
                minimum_length=len(code_fence),
            ):
                code_fence = None
            else:
                rendered.append(f"  {source_line}")
            continue

        opening_fence = _FENCED_CODE_OPEN_RE.match(source_line)
        if opening_fence:
            code_fence = opening_fence.group("delimiter")
            continue

        rendered.extend(
            _render_regular_markdown_line(
                source_line,
                use_ansi=use_ansi,
                prose_width=prose_width,
            )
        )

    return rendered
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-format


# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-read-toml
def read_whatsnew(path: Path) -> Dict[str, Dict[str, str]]:
    """Read a whatsnew.toml file.

    Returns dict mapping version string to {summary, details}.
    Keys may be in format "whatsnew.X.Y.Z" (from TOML section) or just "X.Y.Z".
    """
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (FileNotFoundError, PermissionError, tomllib.TOMLDecodeError) as e:
        logger.debug("Failed to parse %s: %s", path, e)
        return {}

    result: Dict[str, Dict[str, str]] = {}

    # Handle whatsnew.toml format: [whatsnew."X.Y.Z"]
    whatsnew_section = data.get("whatsnew")
    if whatsnew_section is not None and isinstance(whatsnew_section, dict):
        for ver, entry in whatsnew_section.items():
            if isinstance(entry, dict):
                result[ver] = {
                    "summary": str(entry.get("summary", "")),
                    "details": str(entry.get("details", "")),
                }
    elif "whatsnew" not in data:
        # Fallback: direct version keys (legacy format)
        for key, entry in data.items():
            if isinstance(entry, dict):
                result[key] = {
                    "summary": str(entry.get("summary", "")),
                    "details": str(entry.get("details", "")),
                }

    return result
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-read-toml


# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-display-entries
def _display_whatsnew_entries(
    entries: list,
    title: str,
    *,
    use_ansi: bool,
) -> None:
    """Display whatsnew entries to stderr.

    Args:
        entries: List of (version, {summary, details}) tuples, sorted ascending.
        title: Header title (e.g., "What's new in Studio" or "What's new in sdlc kit").
        use_ansi: Whether to use ANSI formatting.
    """
    _emit_terminal_message(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")

    for ver, entry in entries:
        ver = strip_control_chars(ver)
        summary_source = strip_control_chars(entry["summary"])
        details_source = strip_control_chars(entry["details"], preserve_newlines=True)
        summary = format_whatsnew_text(summary_source, use_ansi=use_ansi)
        if summary_source == ver:
            version_label = f"\033[1m{ver}\033[0m" if use_ansi else ver
            _emit_terminal_message(f"\n  {version_label}")
        # If summary wasn't changed by formatting, wrap version in bold
        elif use_ansi and summary == summary_source:
            _emit_terminal_message(f"\n  \033[1m{ver}: {summary_source}\033[0m")
        else:
            version_label = f"\033[1m{ver}:\033[0m" if use_ansi else f"{ver}:"
            _emit_terminal_message(f"\n  {version_label} {summary}")

        if details_source:
            for line in _render_whatsnew_details(details_source, use_ansi=use_ansi):
                _emit_terminal_message(f"    {line}")

    _emit_terminal_message(f"\n{'=' * 60}")
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-display-entries


# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-prompt-continue
def _prompt_continue(interactive: bool) -> bool:
    """Prompt user to continue or abort.

    Returns True if user acknowledged, False if aborted.
    Non-interactive mode always returns True.
    """
    if not interactive:
        return True

    _emit_terminal_message(
        "  Why this input is needed: confirm that you reviewed the update summary "
        "before changes continue.\n"
    )
    _emit_terminal_message("  Press Enter to continue, or type `q` to abort the update:")
    try:
        response = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return response != "q"
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-prompt-continue


# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-show-core
def show_core_whatsnew(
    cache_whatsnew: Dict[str, Dict[str, str]],
    installed_whatsnew: Dict[str, Dict[str, str]],
    *,
    interactive: bool = True,
) -> bool:
    """Display core whatsnew entries present in cache but missing from installed.

    Used by `cfs update` to show changes between cache and .core/ versions.

    Returns True if user acknowledged (or non-interactive), False if declined.
    """
    # Find entries in cache that are missing from installed
    missing = sorted(
        [(v, cache_whatsnew[v]) for v in cache_whatsnew if v not in installed_whatsnew],
        key=lambda t: parse_semver(t[0]),
    )
    if not missing:
        return True

    use_ansi = stderr_supports_ansi()
    _display_whatsnew_entries(missing, "What's new in Studio", use_ansi=use_ansi)
    return _prompt_continue(interactive)
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-whatsnew-show-core


# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-read-whatsnew
# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-read-installed-version
# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-filter-versions
# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-check-no-new
# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-sort-versions
# @cpt-begin:cpt-studio-algo-kit-whatsnew-display:p1:inst-return-ack
def show_kit_whatsnew(
    kit_source_dir: Path,
    installed_version: str,
    kit_slug: str,
    *,
    interactive: bool = True,
) -> bool:
    """Display whatsnew entries for kit versions newer than installed.

    Used by `cfs kit update` to show changes between installed and source versions.

    Args:
        kit_source_dir: Path to kit source containing whatsnew.toml.
        installed_version: Currently installed version (e.g., "1.2.3").
        kit_slug: Kit identifier for display title.
        interactive: Whether to prompt for user confirmation.

    Returns:
        True if user acknowledged (or no entries to show), False if user aborted.
    """
    # Read whatsnew.toml from kit source
    whatsnew_path = kit_source_dir / "whatsnew.toml"
    whatsnew_data = read_whatsnew(whatsnew_path)

    if not whatsnew_data:
        return True  # No whatsnew file — proceed

    # Treat missing installed version as "0.0.0"
    if not installed_version:
        installed_version = "0.0.0"

    # Filter: keep versions > installed_version
    new_entries = []
    for ver, entry in whatsnew_data.items():
        if compare_versions(ver, installed_version) > 0:
            new_entries.append((ver, entry))

    if not new_entries:
        return True  # No new entries

    # Sort by version ascending
    new_entries.sort(key=lambda x: parse_semver(x[0]))

    # Display
    use_ansi = stderr_supports_ansi()
    _display_whatsnew_entries(
        new_entries,
        f"What's new in {kit_slug} kit",
        use_ansi=use_ansi,
    )
    return _prompt_continue(interactive)
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-return-ack
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-sort-versions
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-check-no-new
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-filter-versions
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-read-installed-version
# @cpt-end:cpt-studio-algo-kit-whatsnew-display:p1:inst-read-whatsnew
