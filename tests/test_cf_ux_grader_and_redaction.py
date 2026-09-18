"""Tests for the cf-ux grader provider and the shared secret redaction.

`grader_claude.py` had no test anywhere in `tests/` — it spawns `claude -p` just as
unattended as the provider it grades for, and its environment allowlist and its stderr
redaction were both added untested (constructorfabric/studio#229 review).

The prompt suite these back cannot run here: `claude` is a CLI this repository does not
vendor, and a real call costs money and needs credentials. So the provider is driven
with a faked `subprocess.run`, which is enough to pin what this module decides on its
own — what the child is given, and what comes back out of it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PROVIDERS = Path(__file__).resolve().parents[1] / "tests" / "prompts" / "cf-ux" / "providers"
if str(_PROVIDERS) not in sys.path:
    sys.path.insert(0, str(_PROVIDERS))

grader_claude = pytest.importorskip("grader_claude")
_sandbox = pytest.importorskip("_sandbox")


@pytest.fixture
def run_grader(monkeypatch):
    """Drive `call_api` against a canned process result; hand back the call's kwargs."""
    seen: dict = {}

    def _make(stdout: str = "8", returncode: int = 0, stderr: str = ""):
        def _fake_run(cmd, **kwargs):
            seen["cmd"] = list(cmd)
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

        monkeypatch.setattr(grader_claude.subprocess, "run", _fake_run)
        return grader_claude.call_api("grade this"), seen

    return _make


class TestTheGraderChildGetsAnAllowlistToo:
    """The same fix as the other two providers, which is why it needs the same test:
    `grader_claude` was the one of the three with no coverage at all."""

    @pytest.mark.parametrize("name", ["GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY",
                                      "CF_SOMETHING_NOBODY_ANTICIPATED"])
    def test_an_unrelated_variable_is_not_passed_through(self, run_grader, monkeypatch, name):
        monkeypatch.setenv(name, "should_not_travel")

        _out, seen = run_grader()

        assert name not in seen["kwargs"]["env"]
        assert "should_not_travel" not in seen["kwargs"]["env"].values()

    def test_its_own_credential_does_come_through(self, run_grader, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        _out, seen = run_grader()

        assert seen["kwargs"]["env"]["ANTHROPIC_API_KEY"] == "sk-test"
        assert "PATH" in seen["kwargs"]["env"]

    def test_an_env_is_passed_at_all(self, run_grader):
        _out, seen = run_grader()

        assert seen["kwargs"].get("env") is not None


class TestTheGraderDoesNotReturnItsOwnCredential:
    def test_a_key_echoed_on_stderr_is_redacted(self, run_grader, monkeypatch):
        key = "sk-ant-grader-secret-value"
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)

        out, _seen = run_grader(returncode=2, stderr=f"invalid x-api-key: {key}")

        assert key not in out["error"]
        assert "[redacted]" in out["error"]

    def test_an_ordinary_failure_stays_readable(self, run_grader, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-grader-secret-value")

        out, _seen = run_grader(returncode=127, stderr="command not found: claude")

        assert "command not found: claude" in out["error"]


class TestRedactionHandlesOverlappingValues:
    """`redact_secrets` sorts longest-first so "a value containing another is not left
    half-substituted" — its own docstring. Nothing exercised that: every existing test
    used a single distinct key (#229 review)."""

    def test_a_secret_containing_another_is_fully_replaced(self):
        short, long = "sk-abcdefgh", "sk-abcdefgh-with-a-longer-tail"
        env = {"A_KEY": short, "B_KEY": long}

        out = _sandbox.redact_secrets(f"saw {long} here", env)

        assert long not in out and short not in out
        assert out == f"saw {_sandbox.REDACTED} here"

    def test_the_shorter_secret_is_still_replaced_on_its_own(self):
        short, long = "sk-abcdefgh", "sk-abcdefgh-with-a-longer-tail"
        env = {"A_KEY": short, "B_KEY": long}

        assert _sandbox.redact_secrets(f"saw {short} here", env) == f"saw {_sandbox.REDACTED} here"

    def test_a_short_value_is_not_redacted_at_all(self):
        """Below the minimum length, or a one-letter LANG would match everywhere and
        turn a readable diagnostic into a wall of markers."""
        assert _sandbox.redact_secrets("abc def", {"A_KEY": "abc"}) == "abc def"

    def test_non_credential_names_are_left_alone(self):
        """PATH and HOME appear in real diagnostics constantly."""
        env = {"PATH": "/usr/local/bin:/usr/bin", "HOME": "/home/someone"}

        assert _sandbox.redact_secrets("looked in /usr/local/bin", env) == "looked in /usr/local/bin"
