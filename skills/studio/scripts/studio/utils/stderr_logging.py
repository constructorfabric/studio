"""Helpers for emitting logger-backed terminal diagnostics to stderr."""

from __future__ import annotations

import logging
import sys


def emit_stderr_message(
    message: str,
    *,
    level: int = logging.WARNING,
    logger_name: str = "studio.stderr",
) -> None:
    """Emit terminal text through a temporary logger handler bound to current stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.terminator = ""
    handler.setFormatter(logging.Formatter("%(message)s"))
    emit_logger = logging.getLogger(logger_name)
    emit_logger.handlers = [handler]
    emit_logger.setLevel(level)
    emit_logger.propagate = False
    try:
        emit_logger.log(level, "%s", message)
    finally:
        handler.close()
