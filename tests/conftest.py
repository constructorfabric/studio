from __future__ import annotations

import sys
from pathlib import Path

import logging

import pytest

# Python <3.11 does not have stdlib tomllib; use tomli as a fallback.
if sys.version_info < (3, 11):
    try:
        import tomli as _tomli
        sys.modules.setdefault("tomllib", _tomli)
    except ImportError:
        pass


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: shells out to the real CLI; deselect with -m 'not integration'",
    )
    repo_root = Path(__file__).resolve().parents[1]
    tests_dir = repo_root / "tests"
    sys.path.insert(0, str(tests_dir))
    studio_scripts_dir = repo_root / "skills" / "studio" / "scripts"
    sys.path.insert(0, str(studio_scripts_dir))
    overwork_alert_src_dir = repo_root / "examples" / "overwork_alert" / "src"
    sys.path.insert(0, str(overwork_alert_src_dir))


@pytest.fixture(autouse=True)
def _enable_json_mode():
    """Enable JSON output mode for all tests (tests expect JSON on stdout)."""
    from studio.utils.ui import set_json_mode
    set_json_mode(True)
    yield
    set_json_mode(False)


@pytest.fixture(autouse=True)
def _restore_studio_logger():
    """Undo, after each test, whatever `cli._configure_studio_logging()` did to the
    ``studio`` logger.

    That function is right for the CLI: it attaches a stderr handler and sets
    ``propagate = False`` so diagnostics are not also re-emitted through the root
    logger. It is ruinous for a test session, because it is global and permanent. The
    first test that invokes the CLI -- and dozens do, indirectly -- detaches the whole
    ``studio.*`` tree from the root logger, and `caplog` captures at root. Every later
    test asserting on a warning then saw an empty `caplog.records` and failed, while
    passing in isolation. That is the shape of the long-standing full-suite failures:
    green one at a time, red together, and red for a reason none of them mention.

    Restoring the three fields afterwards keeps each test's logging environment its
    own, without changing what the CLI does in production.
    """
    logger = logging.getLogger("studio")
    saved = (logger.propagate, logger.level, list(logger.handlers))
    yield
    logger.propagate, logger.level = saved[0], saved[1]
    logger.handlers = saved[2]


@pytest.fixture(autouse=True)
def _isolate_decision_log(tmp_path_factory, monkeypatch):
    """Redirect decision-log telemetry (on by default) to a throwaway path.

    The command dispatcher records an ``invocation`` event per run; without this,
    that ``.cache/decisions.jsonl`` write pollutes tests that snapshot a project's
    files. The first write also prints a one-time transparency notice to stderr,
    suppressed here so it doesn't leak into ``stderr == ""`` assertions.
    Telemetry-specific tests override ``CFS_DECISION_LOG`` themselves.
    """
    from studio.utils import decision_log
    log = tmp_path_factory.mktemp("cfs_telemetry") / "decisions.jsonl"
    monkeypatch.setenv("CFS_DECISION_LOG", str(log))
    # `is_enabled()` consults the opt-out sentinel (`~/.cf-studio/decisions.off`)
    # regardless of CFS_DECISION_LOG, so redirecting the log alone does not isolate it:
    # on any machine whose owner has opted out -- a developer, or a CI agent with a
    # warmed home directory -- telemetry stayed off and every test asserting a recorded
    # event failed, for a reason nothing in the test named.
    #
    # Isolated by moving $HOME rather than by replacing `_brand_dir`: that helper is
    # `Path.home() / _BRAND_DIR`, and tests that make `Path.home()` itself raise (the
    # `docker run --user 1234` case in test_gate_log_cmd) need the real one to stay in
    # place to exercise it. Moving $HOME keeps every seam intact and still gives the
    # suite an empty brand dir.
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("cfs_home")))
    monkeypatch.setattr(decision_log, "_NOTICE_SHOWN", True)
    monkeypatch.setattr(decision_log, "_FAILURE_WARNED", False)   # each test can observe the warning
    decision_log.set_current_decision_id("")   # start each test with a clean correlation id
