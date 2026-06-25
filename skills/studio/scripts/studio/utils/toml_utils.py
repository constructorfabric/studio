"""
TOML utilities for Constructor Studio config files.

- Reading: stdlib ``tomllib`` (Python 3.11+)
- Writing: minimal serializer for the subset Constructor Studio uses
- Markdown: extract ``toml`` fenced code blocks from AGENTS.md
- Locking: ``_with_core_toml_lock`` context manager for safe concurrent writes

@cpt-algo:cpt-studio-algo-core-infra-config-management:p1
"""

# @cpt-begin:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-datamodel
import contextlib
import datetime
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from ._tomllib_compat import tomllib

TomlData = Dict[str, Any]

_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TOML_FENCE_RE = re.compile(
    r"```toml\s*\n(.*?)```",
    re.DOTALL,
)
logger = logging.getLogger(__name__)
# @cpt-end:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-datamodel


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-parse
def loads(text: str) -> TomlData:
    """Parse a TOML string using stdlib tomllib."""
    return tomllib.loads(text)


def load(path: Path) -> TomlData:
    """Read and parse a TOML file."""
    with open(path, "rb") as f:
        return tomllib.load(f)
# @cpt-end:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-parse


# @cpt-begin:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-from-markdown
def parse_toml_from_markdown(text: str) -> TomlData:
    """
    Extract and merge all ``toml`` fenced code blocks from markdown text.

    Used to read config variables embedded in AGENTS.md, e.g.::

        ```toml
        cfs = ".cf-adapter"
        ```

    If multiple blocks exist, later blocks override earlier keys.
    Returns empty dict if no TOML blocks found.
    """
    merged: TomlData = {}
    for m in _TOML_FENCE_RE.finditer(text):
        try:
            data = tomllib.loads(m.group(1))
            _deep_merge(merged, data)
        except tomllib.TOMLDecodeError as exc:
            logger.warning("Invalid TOML fenced block ignored: %s", exc)
            continue
    return merged
# @cpt-end:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-from-markdown


# @cpt-begin:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-datamodel
def _deep_merge(base: TomlData, override: TomlData) -> None:
    """Merge *override* into *base* in place (nested dicts are merged)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
# @cpt-end:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-datamodel


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-serialize
def dumps(data: TomlData, header_comment: Optional[str] = None) -> str:
    """Serialize a nested dict to TOML format.

    Supports tables (``[table]``) and arrays of tables (``[[table]]``).
    """
    _validate_lists(data)
    lines: List[str] = []
    if header_comment:
        for cl in header_comment.splitlines():
            lines.append(f"# {cl}" if cl else "#")
        lines.append("")

    _write_body(lines, data, prefix=[])

    # Strip trailing blank lines, ensure single trailing newline
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def dump(data: TomlData, path: Path, header_comment: Optional[str] = None) -> None:
    """Serialize and write a TOML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(data, header_comment), encoding="utf-8")


def _validate_lists(node: Any) -> None:
    """Raise TypeError if any list in *node* mixes dict and non-dict items."""
    if isinstance(node, dict):
        for v in node.values():
            _validate_lists(v)
    elif isinstance(node, list):
        dict_count = sum(1 for x in node if isinstance(x, dict))
        non_dict_count = sum(1 for x in node if not isinstance(x, dict))
        if dict_count > 0 and non_dict_count > 0:
            raise TypeError(
                "TOML serializer cannot mix dict and scalar items in the same list"
            )
        for v in node:
            _validate_lists(v)


def _is_array_of_tables(value: Any) -> bool:
    """True if *value* is a non-empty list where every element is a dict."""
    return isinstance(value, list) and len(value) > 0 and all(isinstance(v, dict) for v in value)


def _write_body(lines: List[str], data: TomlData, prefix: List[str]) -> None:
    """Write key-value pairs, then sub-tables, then arrays of tables."""
    # Phase 1: scalars and simple arrays
    wrote_scalar = False
    for key, value in data.items():
        if isinstance(value, dict) or _is_array_of_tables(value):
            continue
        lines.append(_format_kv(key, value))
        wrote_scalar = True
    if wrote_scalar:
        lines.append("")

    # Phase 2: regular tables (dict values)
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        full = prefix + [key]
        lines.append(f"[{_join_prefix(full)}]")
        _write_body(lines, value, full)

    # Phase 3: arrays of tables (list-of-dict values)
    for key, value in data.items():
        if not _is_array_of_tables(value):
            continue
        full = prefix + [key]
        for item in value:
            lines.append(f"[[{_join_prefix(full)}]]")
            _write_body(lines, item, full)


def _join_prefix(parts: List[str]) -> str:
    return ".".join(_quote_key(k) for k in parts)


def _quote_key(key: str) -> str:
    if _BARE_KEY_RE.match(key):
        return key
    return f'"{key}"'


def _format_kv(key: str, value: Any) -> str:
    return f"{_quote_key(key)} = {_format_value(value)}"


def _escape_toml_string(value: str) -> str:
    """Return a TOML-safe double-quoted string literal."""
    escaped: List[str] = []
    replacements = {
        "\\": "\\\\",
        '"': '\\"',
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
    }
    for ch in value:
        replacement = replacements.get(ch)
        if replacement is not None:
            escaped.append(replacement)
            continue
        codepoint = ord(ch)
        escaped.append(f"\\u{codepoint:04X}" if codepoint < 0x20 or codepoint == 0x7F else ch)
    return '"' + "".join(escaped) + '"'


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise TypeError(f"TOML cannot serialize non-finite float: {value!r}")
        return repr(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, str):
        return _escape_toml_string(value)
    if isinstance(value, list):
        items = ", ".join(_format_value(v) for v in value)
        return f"[{items}]"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")
# @cpt-end:cpt-studio-algo-core-infra-toml-utils:p1:inst-toml-serialize


# ---------------------------------------------------------------------------
# File locking
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _with_core_toml_lock(core_toml_path: Path) -> Generator[None, None, None]:
    """Context manager that holds an exclusive lock while the caller writes to
    *core_toml_path*.

    On POSIX systems ``fcntl.flock`` is used for advisory locking.  On
    platforms where ``fcntl`` is unavailable (Windows) a ``.lock`` sentinel
    file is created with ``O_CREAT | O_EXCL`` and a short retry loop is used
    to wait for concurrent writers to finish.

    Usage::

        with _with_core_toml_lock(core_toml_path):
            toml_utils.dump(data, core_toml_path, header_comment=...)
    """
    try:
        import fcntl  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        logger.warning(
            "fcntl unavailable for TOML locking; falling back to sentinel lock files: %s",
            exc,
        )
        fcntl = None

    if fcntl is not None:
        with _with_posix_core_toml_lock(core_toml_path, fcntl):
            yield
        return
    with _with_windows_core_toml_lock(core_toml_path):
        yield


@contextlib.contextmanager
def _with_posix_core_toml_lock(core_toml_path: Path, fcntl: Any) -> Generator[None, None, None]:
    """Hold an advisory flock on the TOML sidecar lock file."""
    lock_file = core_toml_path.with_suffix(core_toml_path.suffix + ".lock")
    file_handle = None
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        file_handle = open(lock_file, "a", encoding="utf-8")
        fcntl.flock(file_handle, fcntl.LOCK_EX)
        yield
    finally:
        if file_handle is not None:
            try:
                fcntl.flock(file_handle, fcntl.LOCK_UN)
            except OSError as exc:  # pragma: no cover
                logger.warning("Failed to unlock %s: %s", lock_file, exc)
            file_handle.close()
        # Intentionally leave the .lock sentinel on disk; advisory flock locking
        # is independent of the file's existence between runs and unlinking it
        # introduces a TOCTOU race with concurrent acquirers.


def _wait_for_windows_lock(lock_path: Path) -> Optional[int]:
    """Acquire a best-effort Windows lock sentinel."""
    deadline = time.monotonic() + 10.0
    while True:
        try:
            return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() > deadline:
                try:
                    mtime = lock_path.stat().st_mtime
                    if time.time() - mtime > 10.0:
                        lock_path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Failed to inspect or clear stale lock %s: %s", lock_path, exc)
                logger.warning(
                    "cf could not acquire lock on %s within 10 s; proceeding without lock",
                    lock_path,
                )
                return None
            time.sleep(0.05)


@contextlib.contextmanager
def _with_windows_core_toml_lock(core_toml_path: Path) -> Generator[None, None, None]:
    """Hold a Windows-compatible lock sentinel while writing core.toml."""
    lock_path = core_toml_path.with_suffix(core_toml_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = _wait_for_windows_lock(lock_path)
    try:
        yield
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
            try:
                os.unlink(str(lock_path))
            except OSError as exc:
                logger.warning("Failed to remove lock file %s: %s", lock_path, exc)
