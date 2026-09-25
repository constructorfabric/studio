"""The `studio` logger family's level, and the one environment variable that moves it.

`_configure_studio_logging` pinned the family to WARNING unconditionally, which
made every `logger.debug` call in the package unreachable through the shipped
CLI -- including the atomic-write cleanup diagnostics added so that a failed
write could be investigated (#236 review).
"""

from __future__ import annotations

import logging

import pytest

from studio import cli


class TestTheStudioLoggerLevel:
    def test_it_is_warning_when_nothing_asks_otherwise(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default has to stay quiet: these records share stderr with output."""
        monkeypatch.delenv(cli._LOG_LEVEL_ENV, raising=False)

        cli._configure_studio_logging()

        assert logging.getLogger("studio").level == logging.WARNING

    def test_the_environment_variable_lowers_it(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(cli._LOG_LEVEL_ENV, "DEBUG")

        cli._configure_studio_logging()

        assert logging.getLogger("studio").level == logging.DEBUG

    def test_a_child_logger_s_debug_record_now_reaches_a_handler(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The point of the knob, stated as the thing an investigator needs.

        A level on the parent is not the claim; the claim is that a record
        emitted by `studio.utils.atomic_io` is no longer dropped before it
        reaches the handler the CLI attached.
        """
        monkeypatch.setenv(cli._LOG_LEVEL_ENV, "DEBUG")
        cli._configure_studio_logging()

        child = logging.getLogger("studio.utils.atomic_io")

        assert child.isEnabledFor(logging.DEBUG)

    def test_a_child_logger_s_debug_record_is_dropped_by_default(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The other half: without the knob the record really is unreachable."""
        monkeypatch.delenv(cli._LOG_LEVEL_ENV, raising=False)
        cli._configure_studio_logging()

        assert not logging.getLogger("studio.utils.atomic_io").isEnabledFor(logging.DEBUG)

    @pytest.mark.parametrize("value", ["", "   ", "LOUD", "17x", "NOTALEVEL"])
    def test_an_unusable_value_falls_back_to_warning_rather_than_failing(
            self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        """A knob for investigating a failure must not become one.

        `logging.getLevelName` returns the string `"Level LOUD"` for an unknown
        name rather than raising, so the fallback has to check the type -- not
        catch an exception that never comes.
        """
        monkeypatch.setenv(cli._LOG_LEVEL_ENV, value)

        cli._configure_studio_logging()

        assert logging.getLogger("studio").level == logging.WARNING

    @pytest.mark.parametrize("value", ["debug", "Debug", " debug "])
    def test_the_value_is_read_case_and_space_insensitively(
            self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(cli._LOG_LEVEL_ENV, value)

        cli._configure_studio_logging()

        assert logging.getLogger("studio").level == logging.DEBUG
