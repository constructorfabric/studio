from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Python <3.11 does not have stdlib tomllib; use tomli as a fallback.
if sys.version_info < (3, 11):
    try:
        import tomli as _tomli
        sys.modules.setdefault("tomllib", _tomli)
    except ImportError:
        pass


def pytest_configure() -> None:
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
    monkeypatch.setattr(decision_log, "_NOTICE_SHOWN", True)
    monkeypatch.setattr(decision_log, "_FAILURE_WARNED", False)   # each test can observe the warning
    decision_log.set_current_decision_id("")   # start each test with a clean correlation id
