"""Helpers for emitting logger-backed terminal diagnostics to stderr.

@cpt-algo:cpt-studio-algo-core-infra-display-info:p1
"""

from __future__ import annotations

import logging
import sys


# @cpt-algo:cpt-studio-algo-core-infra-render-info-human:p1
class _PlainStderrHandler(logging.StreamHandler):
    """Stream handler that preserves message text verbatim."""

    # @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-stderr-handler
    def emit(self, record: logging.LogRecord) -> None:
        """Write the formatted record without appending a newline."""
        try:
            message = self.format(record)
            self.stream.write(message)
            self.flush()
        except RecursionError:
            raise
        except Exception:  # pylint: disable=broad-exception-caught  # pragma: no cover - delegated to logging internals
            self.handleError(record)
    # @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-stderr-handler


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-stderr-handler
def _configure_stderr_logger(
    logger_name: str,
    level: int,
) -> tuple[logging.Logger, _PlainStderrHandler]:
    """Create a temporary stderr logger with a plain-text handler."""
    handler = _PlainStderrHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    emit_logger = logging.getLogger(logger_name)
    emit_logger.handlers = [handler]
    emit_logger.setLevel(level)
    emit_logger.propagate = False
    return emit_logger, handler
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-stderr-handler


# @cpt-begin:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-stderr-emit
def emit_stderr_message(
    message: str,
    *,
    level: int = logging.WARNING,
    logger_name: str = "studio.stderr",
) -> None:
    """Emit terminal text through a temporary logger handler bound to current stderr."""
    emit_logger, handler = _configure_stderr_logger(logger_name, level)
    try:
        emit_logger.log(level, "%s", message)
    finally:
        handler.close()
# @cpt-end:cpt-studio-algo-core-infra-render-info-human:p1:inst-ui-stderr-emit
