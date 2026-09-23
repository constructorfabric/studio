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

import os
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


class TestNoProviderCutsInsideASecret:
    """`redact_secrets` matches whole values, so a cut taken *first* can land
    inside a credential and leave a prefix it no longer recognises.

    `claude_provider.py` was fixed for this. Its two siblings were not — the
    helper lived in one module, so the other two quietly did without it, and the
    bug outlived its own fix in the same diff. The helper is shared now, and this
    pins all three against the shape that hid it.
    """

    _SECRET = "sk-ant-api03-SUPERSECRETVALUE0123456789"

    def test_the_shared_head_helper_redacts_before_it_cuts(self):
        limit = _sandbox.MAX_DIAGNOSTIC_CHARS
        text = "A" * (limit - 10) + self._SECRET

        got = _sandbox.safe_head(text, {"ANTHROPIC_API_KEY": self._SECRET})

        assert self._SECRET[:10] not in got
        assert len(got) <= limit

    def test_the_shared_tail_helper_does_too(self):
        limit = _sandbox.MAX_DIAGNOSTIC_CHARS
        text = self._SECRET + "B" * (limit - 10)

        got = _sandbox.safe_tail(text, {"OPENAI_API_KEY": self._SECRET})

        assert self._SECRET[-10:] not in got
        assert len(got) <= limit

    def test_a_shorter_limit_is_honoured(self):
        """`grader_claude` passes its own, shorter ceiling."""
        got = _sandbox.safe_head("C" * 1000, {}, 400)

        assert len(got) == 400

    @pytest.mark.parametrize("module_name", ["claude_provider", "codex_provider",
                                             "grader_claude"])
    def test_no_provider_slices_a_diagnostic_before_redacting_it(self, module_name):
        """The textual shape that caused it: a slice applied to the argument of
        `redact_secrets`. Read from source, because the three providers reach
        their stderr through different call paths and only the shape is common.
        """
        import re

        path = _PROVIDERS / f"{module_name}.py"
        # A guard here is not defensive padding: this test's whole subject is the
        # source text, so a read that fails is the invariant going *unchecked*, and
        # it should say that rather than surface as a raw traceback attributed to
        # nothing (#229 review).
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            pytest.fail(f"{module_name} is not valid UTF-8, so it could not be "
                        f"checked for cut-before-redact: {exc}")
        except OSError as exc:
            pytest.fail(f"{module_name} could not be read at {path}, so it was not "
                        f"checked for cut-before-redact: {exc}")
        offenders = re.findall(r"redact_secrets\([^)]*\[[-:0-9]+\]", source)

        assert offenders == [], (
            f"{module_name} cuts before redacting: {offenders}"
        )


codex_provider = pytest.importorskip("codex_provider")


@pytest.fixture
def run_codex(monkeypatch, tmp_path):
    """Drive `codex_provider._invoke` with a fake `codex`, returning what it was given.

    The module had no test of any kind: the allowlist and the
    build-one-env-for-both-spawn-and-redaction invariant were asserted for
    `claude_provider` and `grader_claude`, and for this one only by a regex over
    its source text (#229 review).
    """
    def _make(stdout: str = "answer", stderr: str = "", returncode: int = 0):
        seen = {}

        def _fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

        monkeypatch.setattr(codex_provider.subprocess, "run", _fake_run)
        return codex_provider._invoke("do a thing", tmp_path, 0.0), seen

    return _make


class TestTheCodexChildGetsAnAllowlistToo:
    @pytest.mark.parametrize("name", ["GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY",
                                      "ANTHROPIC_API_KEY", "CF_SOMETHING_UNANTICIPATED"])
    def test_an_unrelated_variable_is_not_passed_through(self, run_codex, monkeypatch, name):
        monkeypatch.setenv(name, "should_not_travel")

        _out, seen = run_codex()

        assert name not in seen["kwargs"]["env"]
        assert "should_not_travel" not in seen["kwargs"]["env"].values()

    def test_its_own_credential_does_come_through(self, run_codex, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

        _out, seen = run_codex()

        assert seen["kwargs"]["env"]["OPENAI_API_KEY"] == "sk-openai-test"
        assert "PATH" in seen["kwargs"]["env"]

    def test_an_env_is_passed_at_all(self, run_codex):
        _out, seen = run_codex()

        assert seen["kwargs"].get("env") is not None


class TestTheCodexDiagnosticIsRedactedBeforeItIsCut:
    """The invariant the source regex only approximated, at the real call site.

    A secret straddling the truncation boundary is the case that distinguishes
    redact-then-cut from cut-then-redact: cutting first leaves a live prefix of
    the key in the diagnostic, and the regex guard cannot see that happen -- it
    only sees one textual shape (#229 review).
    """

    def test_a_key_on_stderr_of_a_failed_run_is_redacted(self, run_codex, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-SUPERSECRETVALUE")

        out, _seen = run_codex(stderr="auth failed for sk-openai-SUPERSECRETVALUE",
                               returncode=1)

        assert "SUPERSECRETVALUE" not in out["error"]
        assert "[redacted]" in out["error"]

    def test_a_key_straddling_the_cut_is_not_half_left_behind(self, run_codex, monkeypatch):
        """The specific regression: truncating first and redacting the truncation."""
        secret = "sk-openai-" + "S" * 40
        monkeypatch.setenv("OPENAI_API_KEY", secret)
        noise = "E" * (_sandbox.MAX_DIAGNOSTIC_CHARS - 20)

        out, _seen = run_codex(stderr=f"{noise}{secret}", returncode=1)

        assert "sk-openai-S" not in out["error"], (
            "a prefix of the key survived, so the cut happened before the redaction")

    def test_a_key_on_the_stderr_tail_of_a_successful_run_is_redacted(
            self, run_codex, monkeypatch):
        """The tail is kept as metadata on success, and is the other way out."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-SUPERSECRETVALUE")

        out, _seen = run_codex(stdout="fine", stderr="warn: sk-openai-SUPERSECRETVALUE")

        assert "SUPERSECRETVALUE" not in out["metadata"]["stderr_tail"]

    def test_the_env_that_spawned_the_child_is_the_env_that_redacts(
            self, run_codex, monkeypatch):
        """One mapping for both, which is the refactor's stated purpose.

        Proven by the same value doing both jobs: it reaches the child, and a
        diagnostic containing it comes back redacted.
        """
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-BOTHWAYSVALUE")

        out, seen = run_codex(stderr="boom sk-openai-BOTHWAYSVALUE", returncode=1)

        assert seen["kwargs"]["env"]["OPENAI_API_KEY"] == "sk-openai-BOTHWAYSVALUE"
        assert "BOTHWAYSVALUE" not in out["error"]


class TestTheGradedChildIsNotSilentlyRepointed:
    """A prefix match forwarded the variables that choose which service answers.

    `ANTHROPIC_BASE_URL` or `CLAUDE_CODE_USE_BEDROCK` in a maintainer's shell went
    to the child along with the key, so the suite could grade one service and
    report the numbers as another's, with nothing in the transcript saying so
    (#229 review).
    """

    @pytest.mark.parametrize("name", sorted(_sandbox.BACKEND_ROUTING_NAMES))
    def test_a_routing_variable_is_not_forwarded(self, monkeypatch, name):
        monkeypatch.setenv(name, "https://somewhere.else")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        env = _sandbox.child_env("ANTHROPIC_", "CLAUDE_")

        assert name not in env
        assert env["ANTHROPIC_API_KEY"] == "sk-test", "the credential still travels"

    def test_dropping_one_is_said_out_loud(self, monkeypatch, capsys):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://somewhere.else")

        _sandbox.child_env("ANTHROPIC_")

        assert "ANTHROPIC_BASE_URL" in capsys.readouterr().err

    def test_nothing_is_said_when_there_is_nothing_to_drop(self, monkeypatch, capsys):
        for name in _sandbox.BACKEND_ROUTING_NAMES:
            monkeypatch.delenv(name, raising=False)

        _sandbox.child_env("ANTHROPIC_")

        assert capsys.readouterr().err == ""


class TestTheChildsScratchStaysInTheSandbox:
    def test_tmpdir_points_inside_the_sandbox_when_one_is_given(self, tmp_path):
        env = _sandbox.child_env("ANTHROPIC_", tmpdir=tmp_path)

        assert Path(env["TMPDIR"]).is_relative_to(tmp_path)
        assert Path(env["TMPDIR"]).is_dir(), "the child cannot create it itself"

    def test_the_runners_tmpdir_is_used_when_none_is_given(self, monkeypatch):
        monkeypatch.setenv("TMPDIR", "/somewhere/of/the/runners")

        env = _sandbox.child_env("ANTHROPIC_")

        assert env["TMPDIR"] == "/somewhere/of/the/runners"

    def test_home_is_left_alone(self, tmp_path):
        """Remapping it does not sandbox the run, it ends it: these children
        authenticate with credentials stored under the runner's home."""
        env = _sandbox.child_env("ANTHROPIC_", tmpdir=tmp_path)

        assert env.get("HOME") == os.environ.get("HOME")


class TestTheCodexPrefixesAreBothCovered:
    """`_CHILD_ENV_PREFIXES` names two namespaces and the tests asserted one.

    `OPENAI_` was covered and `CODEX_` was not, so dropping it from the tuple --
    or the whole prefix mechanism failing for it -- would have left the suite
    green while the child lost its configuration (#229 review).
    """

    @pytest.mark.parametrize("name", ["CODEX_HOME", "CODEX_SOMETHING_ELSE"])
    def test_a_codex_prefixed_variable_survives(self, run_codex, monkeypatch, name):
        monkeypatch.setenv(name, "value")

        _out, seen = run_codex()

        assert seen["kwargs"]["env"][name] == "value"

    def test_every_allowlisted_name_survives_when_set(self, run_codex, monkeypatch):
        """The positive half of the invariant, over the whole list rather than a sample."""
        for index, name in enumerate(_sandbox.ENV_NAMES):
            monkeypatch.setenv(name, f"value-{index}")

        _out, seen = run_codex()

        env = seen["kwargs"]["env"]
        missing = [name for name in _sandbox.ENV_NAMES
                   if name != "TMPDIR" and env.get(name) is None]
        assert not missing, f"allowlisted names dropped by the filter: {missing}"

    def test_the_harness_namespace_is_not_forwarded(self, run_codex, monkeypatch):
        """`CF_UX_*` is read by this Python parent, never by the `codex` binary."""
        monkeypatch.setenv("CF_UX_CODEX_MODEL", "some-model")

        _out, seen = run_codex()

        assert "CF_UX_CODEX_MODEL" not in seen["kwargs"]["env"]


class TestTheScratchDirectoryIsCleanedUpInEveryMode:
    """`TMPDIR` is pointed inside the sandbox so the child's scratch is wiped.

    It was wiped only on the ordinary teardown path. `CF_UX_SHARED_SANDBOX` yields
    a caller-chosen directory and returns with no cleanup at all, and that path is
    usually outside `_SANDBOX_PARENT`, so the stale sweep never reached it either
    -- the scratch accumulated run after run in exactly the long-lived mode it was
    added to be scoped by (#229 review).
    """

    def test_a_shared_sandbox_keeps_its_directory_and_loses_the_scratch(
            self, tmp_path, monkeypatch):
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "a-real-file.txt").write_text("mine", encoding="utf-8")
        monkeypatch.setenv("CF_UX_SHARED_SANDBOX", str(shared))

        with _sandbox.sandbox() as cwd:
            assert cwd == shared
            _sandbox.child_env("ANTHROPIC_", tmpdir=cwd)
            assert (cwd / _sandbox.SCRATCH_DIR_NAME).is_dir()

        assert not (shared / _sandbox.SCRATCH_DIR_NAME).exists(), "scratch was left behind"
        assert (shared / "a-real-file.txt").is_file(), (
            "the shared directory belongs to its caller and must survive")

    def test_wiping_a_sandbox_with_no_scratch_is_not_an_error(self, tmp_path):
        _sandbox.wipe_scratch(tmp_path)          # nothing to remove

        assert tmp_path.is_dir()

    def test_wiping_removes_the_contents_too(self, tmp_path):
        scratch = tmp_path / _sandbox.SCRATCH_DIR_NAME
        scratch.mkdir()
        (scratch / "leftover").write_text("x", encoding="utf-8")

        _sandbox.wipe_scratch(tmp_path)

        assert not scratch.exists()


class TestAHeaderOverrideIsTreatedAsRouting:
    def test_custom_headers_are_not_forwarded(self, monkeypatch, capsys):
        """Not an endpoint, but it reaches the same place: arbitrary headers,
        including authorization ones."""
        monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "X-Whatever: 1")

        env = _sandbox.child_env("ANTHROPIC_")

        assert "ANTHROPIC_CUSTOM_HEADERS" not in env
        assert "ANTHROPIC_CUSTOM_HEADERS" in capsys.readouterr().err
