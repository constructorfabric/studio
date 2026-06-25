"""Plain-text stderr helpers for proxy user-facing output.

@cpt-flow:cpt-studio-flow-core-infra-cli-invocation:p1
"""

from __future__ import annotations

import logging
import sys


def _emit_plain_stderr(message: str, *, logger_name: str) -> None:
    """Emit plain stderr text through a temporary logger bound to current stderr."""
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-stderr-line
    handler = logging.StreamHandler(sys.stderr)
    handler.terminator = ""
    handler.setFormatter(logging.Formatter("%(message)s"))
    emit_logger = logging.getLogger(logger_name)
    emit_logger.handlers = [handler]
    emit_logger.setLevel(logging.WARNING)
    emit_logger.propagate = False
    try:
        emit_logger.warning("%s\n", message)
    finally:
        handler.close()
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-stderr-line


def write_stderr(message: str = "") -> None:
    """Write a single plain-text line to stderr without logging metadata."""
    _emit_plain_stderr(message, logger_name="studio_proxy.stderr")


def write_stderr_lines(*lines: str) -> None:
    """Write multiple plain-text lines to stderr."""
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-stderr-lines
    for line in lines:
        _emit_plain_stderr(line, logger_name="studio_proxy.stderr.lines")
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-stderr-lines


def write_stderr_warning(message: str) -> None:
    """Write a warning line to stderr without logger formatting."""
    # @cpt-begin:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-stderr-warning
    warning = f"Warning: {message}"
    write_stderr(warning)
    # @cpt-end:cpt-studio-flow-core-infra-cli-invocation:p1:inst-cli-stderr-warning
