"""Plain-text stderr helpers for proxy user-facing output."""

from __future__ import annotations

import sys


def write_stderr(message: str = "") -> None:
    """Write a single plain-text line to stderr without logging metadata."""
    print(message, file=sys.stderr)


def write_stderr_lines(*lines: str) -> None:
    """Write multiple plain-text lines to stderr."""
    for line in lines:
        write_stderr(line)


def write_stderr_warning(message: str) -> None:
    """Write a warning line to stderr without logger formatting."""
    write_stderr(f"Warning: {message}")
