"""Tests for stderr logging helpers."""

import logging
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils.stderr_logging import emit_stderr_message


def test_emit_stderr_message_writes_plain_text_to_stderr(capsys):
    emit_stderr_message("plain stderr message")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "plain stderr message"


def test_emit_stderr_message_uses_custom_logger_name_and_level(capsys):
    logger = logging.getLogger("studio.tests.stderr")
    logger.handlers = []
    logger.propagate = True

    emit_stderr_message("warn\n", level=logging.ERROR, logger_name="studio.tests.stderr")

    captured = capsys.readouterr()
    assert captured.err == "warn\n"
    assert logger.level == logging.ERROR
    assert logger.propagate is False
    assert len(logger.handlers) == 1
