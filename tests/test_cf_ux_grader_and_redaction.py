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

    def test_home_is_the_runners_unless_isolation_is_asked_for(self, tmp_path):
        """Not because remapping it would break authentication -- an earlier
        version of this docstring said so, and it was measured false -- but
        because the runner's home is where the plugins live that the pilot
        measures the skill against. Isolating it is a different measurement,
        so it is a request, not a default (#229 review)."""
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


class TestTheGraderDiagnosticIsRedactedBeforeItIsCut:
    """The third provider's own boundary case, at its own boundary.

    `claude_provider` and `codex_provider` each got a behavioural test placing a
    secret across the truncation point; the grader had only the source regex,
    which sees one textual shape and misses a cut-then-redact written with an
    intermediate variable. Its cap is its own (`_STDERR_CHARS`, shorter than the
    providers'), so the case has to be built against that number rather than the
    shared one (#229 review).
    """

    def test_a_key_straddling_the_cut_is_not_half_left_behind(self, run_grader, monkeypatch):
        secret = "sk-ant-" + "S" * 40
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        noise = "E" * (grader_claude._STDERR_CHARS - 20)

        out, _seen = run_grader(returncode=1, stderr=f"{noise}{secret}")

        assert "sk-ant-S" not in out["error"], (
            "a prefix of the key survived, so the cut happened before the redaction")
        assert "[redacted]" in out["error"]

    def test_the_diagnostic_is_still_cut_to_the_graders_own_ceiling(
            self, run_grader, monkeypatch):
        """Redacting first must not stop it being bounded."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        out, _seen = run_grader(returncode=1, stderr="E" * 5000)

        head = out["error"].split(": ", 1)[1]
        assert len(head) == grader_claude._STDERR_CHARS

    def test_that_ceiling_stays_below_the_shared_one(self):
        """Derived, so the inequality the comment claims cannot be inverted."""
        assert grader_claude._STDERR_CHARS < _sandbox.MAX_DIAGNOSTIC_CHARS


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits and unprivileged symlinks (#229 review)")
class TestAnIsolatedHomeHoldsOnlyALinkToTheCredential:
    """`CF_UX_ISOLATED_HOME=1` gives the child a home inside the sandbox. It holds
    one thing, a link to the CLI's credential: linked rather than copied so a
    token refreshed mid-run lands in the runner's store, and removed on every
    teardown path, the kept sandbox included (#229 review).

    Not claimed here: that a CLI authenticates against such a home. That was
    measured on Linux for claude 2.1.281 and codex 0.154.0; macOS keeps claude's
    credential in the Keychain, and the mode is expected to decline there.
    """

    @pytest.fixture
    def credential(self, tmp_path):
        store = tmp_path / "runner-store" / ".credentials.json"
        store.parent.mkdir()
        store.write_text('{"token": "real"}', encoding="utf-8")
        return store

    def test_off_by_default(self, tmp_path, credential, monkeypatch):
        monkeypatch.delenv(_sandbox.ISOLATED_HOME_ENV, raising=False)

        assert _sandbox.isolated_home(tmp_path, credential, ".claude/.credentials.json") is None
        assert not (tmp_path / _sandbox.ISOLATED_HOME_DIR_NAME).exists()

    def test_on_request_the_home_holds_the_link_and_nothing_else(
            self, tmp_path, credential, monkeypatch):
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()

        home = _sandbox.isolated_home(sandbox_dir, credential, ".claude/.credentials.json")

        assert home == sandbox_dir / _sandbox.ISOLATED_HOME_DIR_NAME
        link = home / ".claude" / ".credentials.json"
        assert link.is_symlink() and link.resolve() == credential.resolve()
        assert link.read_text(encoding="utf-8") == '{"token": "real"}'
        everything = sorted(p.relative_to(home) for p in home.rglob("*"))
        assert everything == [Path(".claude"), Path(".claude/.credentials.json")]
        assert oct(home.stat().st_mode & 0o777) == "0o700"
        assert oct((home / ".claude").stat().st_mode & 0o777) == "0o700"

    def test_a_missing_credential_declines_out_loud(self, tmp_path, monkeypatch, capsys):
        """A run asked to isolate that quietly did not would report under the
        wrong label. macOS is the ordinary way to get here."""
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")
        absent = tmp_path / "nowhere" / ".credentials.json"

        home = _sandbox.isolated_home(tmp_path, absent, ".claude/.credentials.json")

        assert home is None
        err = capsys.readouterr().err
        assert _sandbox.ISOLATED_HOME_ENV in err and str(absent) in err
        assert "runner's home" in err
        assert not (tmp_path / _sandbox.ISOLATED_HOME_DIR_NAME).exists()

    def test_the_child_env_points_at_it_and_drops_the_config_roots(
            self, tmp_path, credential, monkeypatch):
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/runner/.claude")
        monkeypatch.setenv("CODEX_HOME", "/runner/.codex")
        monkeypatch.setenv("CLAUDE_SOMETHING_ELSE", "kept")
        home = _sandbox.isolated_home(tmp_path, credential, ".claude/.credentials.json")

        env = _sandbox.child_env("ANTHROPIC_", "CLAUDE_", "CODEX_", tmpdir=tmp_path, home=home)

        assert env["HOME"] == str(home)
        assert "CLAUDE_CONFIG_DIR" not in env and "CODEX_HOME" not in env
        assert env["CLAUDE_SOMETHING_ELSE"] == "kept", "only the roots are dropped"

    def test_without_an_isolated_home_the_config_roots_still_travel(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/runner/.claude")

        env = _sandbox.child_env("CLAUDE_")

        assert env["CLAUDE_CONFIG_DIR"] == "/runner/.claude"

    def test_wiping_the_home_leaves_the_credential_itself_alone(
            self, tmp_path, credential, monkeypatch):
        """The one thing this must never do: follow the link."""
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")
        home = _sandbox.isolated_home(tmp_path, credential, ".claude/.credentials.json")

        _sandbox.wipe_isolated_home(tmp_path)

        assert not home.exists()
        assert credential.read_text(encoding="utf-8") == '{"token": "real"}'
        assert home not in _sandbox._LIVE_HOMES

    def test_a_shared_sandbox_loses_the_home_and_keeps_its_own_files(
            self, tmp_path, credential, monkeypatch):
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "a-real-file.txt").write_text("mine", encoding="utf-8")
        monkeypatch.setenv("CF_UX_SHARED_SANDBOX", str(shared))
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")

        with _sandbox.sandbox() as cwd:
            home = _sandbox.isolated_home(cwd, credential, ".claude/.credentials.json")
            assert home.is_dir()

        assert not home.exists(), "a link to the credential store was left behind"
        assert (shared / "a-real-file.txt").is_file()

    def test_a_kept_sandbox_keeps_its_scratch_and_not_the_home(
            self, tmp_path, credential, monkeypatch):
        monkeypatch.setattr(_sandbox, "_SANDBOX_PARENT", tmp_path / "parent")
        monkeypatch.setattr(_sandbox, "_init_sandbox", lambda root: None)
        monkeypatch.setenv("CF_UX_KEEP_SANDBOX", "1")
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")

        with _sandbox.sandbox() as cwd:
            home = _sandbox.isolated_home(cwd, credential, ".claude/.credentials.json")
            _sandbox.child_env("ANTHROPIC_", tmpdir=cwd, home=home)

        assert cwd.is_dir(), "kept, as asked"
        assert (cwd / _sandbox.SCRATCH_DIR_NAME).is_dir(), "scratch is what keeping is for"
        assert not home.exists(), "the credential link is not"

    def test_the_atexit_sweep_knows_about_homes_in_shared_sandboxes(
            self, tmp_path, credential, monkeypatch):
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")
        home = _sandbox.isolated_home(tmp_path, credential, ".claude/.credentials.json")
        assert home in _sandbox._LIVE_HOMES

        _sandbox._atexit_cleanup()

        assert not home.exists()
        assert credential.is_file()


class TestTheCodexChildCanHaveAnIsolatedHomeToo:
    def test_by_default_the_report_says_runner(self, run_codex, monkeypatch):
        monkeypatch.delenv(_sandbox.ISOLATED_HOME_ENV, raising=False)

        out, seen = run_codex()

        assert out["metadata"]["home"] == "runner"
        assert seen["kwargs"]["env"]["HOME"] == os.environ["HOME"]

    def test_on_request_it_is_inside_the_sandbox_and_codex_home_is_dropped(
            self, run_codex, monkeypatch, tmp_path):
        credential = tmp_path / "store" / "auth.json"
        credential.parent.mkdir()
        credential.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(codex_provider, "_codex_credential", lambda: credential)
        monkeypatch.setenv(_sandbox.ISOLATED_HOME_ENV, "1")
        monkeypatch.setenv("CODEX_HOME", "/the/runners/.codex")

        out, seen = run_codex()

        env = seen["kwargs"]["env"]
        assert out["metadata"]["home"] == "isolated"
        assert Path(env["HOME"]).is_relative_to(tmp_path)
        assert (Path(env["HOME"]) / ".codex" / "auth.json").is_symlink()
        assert "CODEX_HOME" not in env

    def test_the_credential_follows_codex_home_when_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "cx"))

        assert codex_provider._codex_credential() == tmp_path / "cx" / "auth.json"


class TestTheAnswerIsRedactedInTheSiblingsToo:
    """The review named the claude provider's answer; codex returns its answer the
    same way, and the grader returns its verdict the same way (#229 review)."""

    _SECRET = "sk-proj-ANSWERSECRETVALUE0123456789"

    def test_codex_answer(self, run_codex, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", self._SECRET)

        out, _seen = run_codex(stdout=f"the key is {self._SECRET}\n" + "B" * 5000)

        assert self._SECRET not in out["output"]
        assert out["output"].startswith("the key is [redacted]")
        assert out["output"].endswith("B" * 5000), "redacted, not cut"

    def test_grader_verdict(self, run_grader, monkeypatch):
        secret = "sk-ant-api03-GRADERSECRETVALUE0123456789"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

        out, _seen = run_grader(stdout=f"8 -- the answer leaked {secret}")

        assert secret not in out["output"]
        assert out["output"] == "8 -- the answer leaked [redacted]"


class TestCleanupSaysWhenItCouldNotClean:
    """`rmtree(ignore_errors=True)` made every cleanup failure silent, including the
    one the unattended child can cause by swapping its scratch directory for a
    symlink (#229 review). Applied to all three things this harness removes: the
    scratch, the isolated home, and the sandbox itself."""

    def test_a_scratch_swapped_for_a_symlink_is_unlinked_not_followed(
            self, tmp_path, capsys):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("not the harness's", encoding="utf-8")
        sandbox_dir = tmp_path / "sandbox"
        sandbox_dir.mkdir()
        (sandbox_dir / _sandbox.SCRATCH_DIR_NAME).symlink_to(outside, target_is_directory=True)

        _sandbox.wipe_scratch(sandbox_dir)

        assert not (sandbox_dir / _sandbox.SCRATCH_DIR_NAME).exists()
        assert not (sandbox_dir / _sandbox.SCRATCH_DIR_NAME).is_symlink(), "the link is gone"
        assert (outside / "keep.txt").is_file(), "and what it pointed at is untouched"
        assert "replaced by a symlink" in capsys.readouterr().err

    def test_a_failure_to_remove_is_named(self, tmp_path, capsys, monkeypatch):
        scratch = tmp_path / _sandbox.SCRATCH_DIR_NAME
        scratch.mkdir()
        (scratch / "stuck").write_text("x", encoding="utf-8")

        def _failing_rmtree(path, **kwargs):
            hook = kwargs.get("onexc") or kwargs.get("onerror")
            error = PermissionError(13, "Permission denied")
            hook(None, str(path / "stuck"), error if "onexc" in kwargs else (type(error), error, None))

        monkeypatch.setattr(_sandbox.shutil, "rmtree", _failing_rmtree)

        _sandbox.wipe_scratch(tmp_path)

        err = capsys.readouterr().err
        assert "could not fully remove the scratch directory" in err and "Permission denied" in err

    def test_nothing_is_said_when_there_is_nothing_to_remove(self, tmp_path, capsys):
        """A guard: reporting failures must not turn into noise on the ordinary path."""
        _sandbox.wipe_scratch(tmp_path)

        assert capsys.readouterr().err == ""

    def test_the_isolated_home_and_the_sandbox_use_the_same_removal(self):
        """The shape, not an example: no cleanup in the module keeps a silent rmtree."""
        import inspect

        source = inspect.getsource(_sandbox)
        assert "ignore_errors=True)" not in source.replace("`rmtree(ignore_errors=True)`", "")


class TestTheCodexChildIsNotRepointedEither:
    """The routing list held only ANTHROPIC_/CLAUDE_ names while the codex provider
    forwards OPENAI_/CODEX_ wholesale (#229 review). Driven through the codex
    provider, not `child_env` with the claude prefixes: that sibling test passes for
    an OPENAI_ name whatever the list says, since its prefixes never admit one."""

    _CODEX_ROUTING = sorted(n for n in _sandbox.BACKEND_ROUTING_NAMES
                            if n.startswith(("OPENAI_", "CODEX_")))

    def test_the_list_names_the_codex_family_at_all(self):
        assert {"OPENAI_BASE_URL", "CODEX_URL"} <= set(self._CODEX_ROUTING)

    @pytest.mark.parametrize("name", _CODEX_ROUTING)
    def test_a_codex_routing_variable_is_not_forwarded(self, run_codex, monkeypatch, name):
        monkeypatch.setenv(name, "https://somewhere.else")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-value")
        monkeypatch.setenv("CODEX_HOME", "/runner/.codex")

        _out, seen = run_codex()

        env = seen["kwargs"]["env"]
        assert name not in env
        assert env["OPENAI_API_KEY"] == "sk-test-value" and env["CODEX_HOME"] == "/runner/.codex"


class TestProxyAndCaSettingsTravel:
    """Connectivity settings were outside the allowlist, so on a runner that reaches
    the API only through a proxy or a corporate CA both CLIs failed to connect
    (#229 review). A proxy URL can carry credentials, so its value is redacted."""

    @pytest.mark.parametrize("name", ["HTTPS_PROXY", "https_proxy", "NO_PROXY", "SSL_CERT_FILE",
                                      "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS"])
    def test_it_reaches_the_child(self, run_codex, monkeypatch, name):
        monkeypatch.setenv(name, "/some/value")

        _out, seen = run_codex()

        assert seen["kwargs"]["env"][name] == "/some/value"

    def test_a_proxy_with_credentials_is_redacted_from_diagnostics(self, run_codex, monkeypatch):
        proxy = "http://ci-user:Pr0xyPassw0rd@proxy.internal:3128"
        monkeypatch.setenv("HTTPS_PROXY", proxy)

        out, _seen = run_codex(stderr=f"connect failed via {proxy}", returncode=1)

        assert "Pr0xyPassw0rd" not in out["error"]
