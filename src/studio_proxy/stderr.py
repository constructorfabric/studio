"""Plain-text stderr helpers for proxy user-facing output."""

from __future__ import annotations

import logging
import sys


def write_stderr(message: str = "") -> None:
    """Write a single plain-text line to stderr without logging metadata."""
    handler = logging.StreamHandler(sys.stderr)
    handler.terminator = ""
    handler.setFormatter(logging.Formatter("%(message)s"))
    emit_logger = logging.getLogger("studio_proxy.stderr")
    emit_logger.handlers = [handler]
    emit_logger.setLevel(logging.WARNING)
    emit_logger.propagate = False
    try:
        emit_logger.warning("%s\n", message)
    finally:
        handler.close()


def write_stderr_lines(*lines: str) -> None:
    """Write multiple plain-text lines to stderr."""
    for line in lines:
        write_stderr(line)


def write_stderr_warning(message: str) -> None:
    """Write a warning line to stderr without logger formatting."""
    write_stderr(f"Warning: {message}")
