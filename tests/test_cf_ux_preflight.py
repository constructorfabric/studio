"""The preconditions the pilot checks before spending anything.

Both checks exist because their absence cost a real run each: a node too old
for promptfoo fails deep inside npx talking about the package, and a withdrawn
codex model surfaces as a 400 in a table cell after every sandbox is built.
What is pinned here is that each says which one thing to change, and that
neither invents a problem out of not knowing.
"""

from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_PILOT = Path(__file__).resolve().parents[1] / "tests" / "prompts" / "cf-ux"
if str(_PILOT) not in sys.path:
    sys.path.insert(0, str(_PILOT))

preflight = pytest.importorskip("preflight")


class TestTheNodeCheck:
    def test_a_new_enough_node_says_nothing(self, monkeypatch):
        monkeypatch.setattr(preflight, "_node_version", lambda *a: (22, 22, 0))

        assert preflight.check_node() == []

    def test_an_old_node_names_the_version_and_the_floor(self, monkeypatch):
        monkeypatch.setattr(preflight, "_node_version", lambda *a: (20, 20, 0))
        monkeypatch.setattr(preflight, "_nvm_candidates", list)

        problem = "\n".join(preflight.check_node())

        assert "20.20.0" in problem and "22.22.0" in problem

    def test_a_node_that_is_only_a_shell_function_is_not_silence(self, monkeypatch):
        """nvm's lazy loader defines `node` as a shell function, so an
        interactive shell answers it and `make`, which uses `sh`, finds no
        program at all. Reporting nothing here is what sent the failure into
        npx to be rediscovered."""
        monkeypatch.setattr(preflight, "_node_version", lambda *a: None)
        monkeypatch.setattr(preflight, "_nvm_candidates", list)

        problem = "\n".join(preflight.check_node())

        assert problem, "a missing node must be reported, not assumed fine"
        assert "shell function" in problem

    def test_an_installed_nvm_node_is_offered_as_a_command_to_run(self, monkeypatch):
        """The remedy is a path, so the path is what it prints — the half hour
        this check exists to give back is spent finding exactly this."""
        newest = Path("/home/x/.nvm/versions/node/v24.21.0/bin")
        monkeypatch.setattr(preflight, "_node_version", lambda *a: (20, 20, 0))
        monkeypatch.setattr(preflight, "_nvm_candidates",
                            lambda: [((22, 22, 2), Path("/old/bin")), ((24, 21, 0), newest)])

        problem = "\n".join(preflight.check_node())

        assert f"PATH={newest}:$PATH make test-prompts" in problem
        assert "/old/bin" not in problem, "the newest qualifying node is the one to offer"


class TestTheCodexModelCheck:
    @staticmethod
    def _cache(tmp_path: Path, models: list[dict]) -> Path:
        path = tmp_path / "models_cache.json"
        path.write_text(json.dumps({"models": models}), encoding="utf-8")
        return path

    def test_a_listed_model_says_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(preflight, "MODELS_CACHE",
                            self._cache(tmp_path, [{"slug": "gpt-5.6-sol", "visibility": "list"}]))

        assert preflight.check_codex_model("gpt-5.6-sol") == []

    def test_a_withdrawn_model_names_what_is_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(preflight, "MODELS_CACHE", self._cache(tmp_path, [
            {"slug": "gpt-5.6-sol", "visibility": "list"},
            {"slug": "gpt-5.5", "visibility": "list"},
        ]))

        problem = "\n".join(preflight.check_codex_model("gpt-5.4-mini"))

        assert "gpt-5.4-mini" in problem
        assert "gpt-5.6-sol" in problem and "gpt-5.5" in problem
        assert "CF_UX_CODEX_MODEL=" in problem, "the remedy is a command, not a description"

    def test_an_internal_model_is_never_suggested(self, tmp_path, monkeypatch):
        """The cache also carries entries the CLI hides from people
        (`codex-auto-review`, `gpt-reserve`). Offering one as the model to
        switch to would be worse than saying nothing."""
        monkeypatch.setattr(preflight, "MODELS_CACHE", self._cache(tmp_path, [
            {"slug": "codex-auto-review", "visibility": "hide"},
            {"slug": "gpt-5.6-sol", "visibility": "list"},
        ]))

        problem = "\n".join(preflight.check_codex_model("gone"))

        assert "codex-auto-review" not in problem
        assert "gpt-5.6-sol" in problem

    @pytest.mark.parametrize("content", [
        "not json at all",
        json.dumps({"models": "not a list"}),
        json.dumps({"models": []}),
        json.dumps({}),
    ])
    def test_a_cache_it_cannot_read_is_not_a_verdict(self, tmp_path, monkeypatch, content):
        """Ignorance is not evidence. A preflight that blocks a run because it
        could not read a cache is worse than the 400 it was meant to pre-empt."""
        path = tmp_path / "models_cache.json"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(preflight, "MODELS_CACHE", path)

        assert preflight.check_codex_model("anything") == []

    def test_a_missing_cache_is_not_a_verdict_either(self, tmp_path, monkeypatch):
        monkeypatch.setattr(preflight, "MODELS_CACHE", tmp_path / "absent.json")

        assert preflight.check_codex_model("anything") == []


class TestTheExitCode:
    def test_a_clean_environment_exits_zero(self, monkeypatch):
        monkeypatch.setattr(preflight, "check_node", list)
        monkeypatch.setattr(preflight, "check_codex_model", lambda _model: [])

        assert preflight.main() == 0

    def test_a_problem_exits_non_zero_and_is_reported(self, monkeypatch, capsys):
        monkeypatch.setattr(preflight, "check_node", lambda: ["node is wrong"])
        monkeypatch.setattr(preflight, "check_codex_model", lambda _model: [])

        assert preflight.main() == 1
        assert "node is wrong" in capsys.readouterr().err


class TestAMisconfiguredEnvVar:
    """Importing the provider *runs* it: its module body reads the CF_UX_* knobs,
    and `int(CF_UX_CODEX_CONTEXT)` raises on anything non-numeric. A preflight
    whose whole job is to replace a traceback with a sentence must not end in one
    of its own."""

    def test_a_non_numeric_context_is_a_sentence_not_a_traceback(self, monkeypatch, capsys):
        monkeypatch.setenv("CF_UX_CODEX_CONTEXT", "abc")
        for module in [name for name in sys.modules if name == "codex_provider"]:
            monkeypatch.delitem(sys.modules, module)

        assert preflight.main() == 1
        assert "CF_UX_CODEX_CONTEXT" in capsys.readouterr().err


class TestWhatTheCheckCannotDoItSays:
    """A preflight that stays silent on its own inability is worse than no
    preflight: it reports success it never established."""

    def test_an_unimportable_provider_is_reported(self, monkeypatch, capsys):
        monkeypatch.delenv("CF_UX_CODEX_MODEL", raising=False)
        monkeypatch.setattr(preflight, "check_node", list)
        real_import = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name == "codex_provider":
                raise ImportError("boom")
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "codex_provider", raising=False)
        monkeypatch.setattr(builtins, "__import__", refuse)

        assert preflight.main() == 1
        assert "will not import" in capsys.readouterr().err

    def test_an_override_still_lets_the_run_proceed(self, monkeypatch, capsys):
        """The env var is the escape hatch; it must keep working."""
        monkeypatch.setenv("CF_UX_CODEX_MODEL", "gpt-5.6-sol")
        monkeypatch.setattr(preflight, "check_node", list)
        monkeypatch.setattr(preflight, "check_codex_model", lambda _m: [])
        real_import = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name == "codex_provider":
                raise ImportError("boom")
            return real_import(name, *args, **kwargs)

        monkeypatch.delitem(sys.modules, "codex_provider", raising=False)
        monkeypatch.setattr(builtins, "__import__", refuse)

        assert preflight.main() == 0

    def test_node_only_skips_the_account_check(self, monkeypatch):
        """`install-prompt-tests` caches an npm package. It needs a node, and has
        no business requiring a live account."""
        monkeypatch.setattr(preflight, "check_node", list)
        monkeypatch.setattr(preflight, "check_codex_model",
                            lambda _m: pytest.fail("the account must not be consulted"))

        assert preflight.main(["--node-only"]) == 0


class TestTheSuggestedModel:
    def test_the_cli_s_own_priority_decides_not_the_alphabet(self, tmp_path, monkeypatch):
        """Alphabetically `gpt-5.5` — the previous generation — led the list, which
        is a worse default than the one the CLI itself would offer."""
        path = tmp_path / "models_cache.json"
        path.write_text(json.dumps({"models": [
            {"slug": "gpt-5.5", "visibility": "list", "priority": 12},
            {"slug": "gpt-5.6-sol", "visibility": "list", "priority": 0},
        ]}), encoding="utf-8")
        monkeypatch.setattr(preflight, "MODELS_CACHE", path)

        problem = "\n".join(preflight.check_codex_model("gone"))

        assert "CF_UX_CODEX_MODEL=gpt-5.6-sol" in problem


class TestTheNvmScan:
    def test_an_unreadable_nvm_directory_is_not_a_traceback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NVM_DIR", str(tmp_path))
        (tmp_path / "versions" / "node").mkdir(parents=True)
        monkeypatch.setattr(Path, "glob", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))

        assert preflight._nvm_candidates() == []

    @staticmethod
    def _install(root: Path, names: list[str]) -> None:
        for name in names:
            (root / name / "bin").mkdir(parents=True)
            (root / name / "bin" / "node").touch()

    def _probe_order(self, tmp_path, monkeypatch, names: list[str]) -> list[str]:
        self._install(tmp_path / "versions" / "node", names)
        monkeypatch.setenv("NVM_DIR", str(tmp_path))
        seen: list[str] = []
        monkeypatch.setattr(
            preflight, "_node_version",
            lambda binary="node": seen.append(Path(binary).parent.parent.name) or None)
        preflight._nvm_candidates()
        return seen

    def test_the_number_of_probes_is_capped(self, tmp_path, monkeypatch):
        """Each probe is a process with a timeout, and a long-lived nvm directory
        accumulates dozens of versions."""
        seen = self._probe_order(tmp_path, monkeypatch,
                                 [f"v{i}.0.0" for i in range(40)])

        assert len(seen) == preflight.NVM_PROBE_LIMIT

    def test_the_newest_is_probed_first_not_the_alphabetically_last(self, tmp_path, monkeypatch):
        """Sorting paths as text puts `v9.0.0` above `v24.21.0`, so a cap could
        discard every node new enough to qualify and report that none was
        installed."""
        monkeypatch.setattr(preflight, "NVM_PROBE_LIMIT", 2)

        seen = self._probe_order(tmp_path, monkeypatch,
                                 ["v8.0.0", "v9.0.0", "v20.20.0", "v22.22.2", "v24.21.0"])

        assert seen == ["v24.21.0", "v22.22.2"]

    def test_a_directory_with_no_version_in_its_name_sorts_last(self, tmp_path, monkeypatch):
        """nvm aliases (`system`, a named install) carry no version. Still worth a
        probe if there is room, but never ahead of a real one."""
        monkeypatch.setattr(preflight, "NVM_PROBE_LIMIT", 2)

        seen = self._probe_order(tmp_path, monkeypatch, ["system", "v18.0.0", "v22.22.2"])

        assert seen == ["v22.22.2", "v18.0.0"]


class TestTheReportContract:
    """`_report` is what every path returns through, so its two guarantees —
    exit code and the problems reaching stderr — are pinned directly rather than
    inferred from whichever caller happened to be under test."""

    def test_no_problems_is_a_clean_exit_and_silence(self, capsys):
        assert preflight._report([]) == 0

        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == ""

    def test_problems_exit_non_zero_and_all_reach_stderr(self, capsys):
        assert preflight._report(["first thing", "second thing"]) == 1

        captured = capsys.readouterr()
        assert "first thing" in captured.err and "second thing" in captured.err
        assert captured.out == "", "diagnostics belong on stderr, not in a pipeline's output"


class TestTheVersionParsingItself:
    """`_node_version` is monkeypatched everywhere else, so its own parsing —
    the part that decides whether a node qualifies — is exercised here."""

    def test_a_real_node_style_version_string_parses(self, monkeypatch):
        monkeypatch.setattr(preflight.subprocess, "run",
                            lambda *a, **k: SimpleNamespace(returncode=0, stdout="v22.22.2\n"))

        assert preflight._node_version() == (22, 22, 2)

    def test_a_non_zero_exit_is_no_version(self, monkeypatch):
        monkeypatch.setattr(preflight.subprocess, "run",
                            lambda *a, **k: SimpleNamespace(returncode=1, stdout="v22.22.2"))

        assert preflight._node_version() is None

    def test_output_with_no_version_in_it_is_no_version(self, monkeypatch):
        monkeypatch.setattr(preflight.subprocess, "run",
                            lambda *a, **k: SimpleNamespace(returncode=0, stdout="not a version"))

        assert preflight._node_version() is None

    def test_a_binary_that_will_not_run_is_no_version(self, monkeypatch):
        def refuse(*a, **k):
            raise OSError("denied")
        monkeypatch.setattr(preflight.subprocess, "run", refuse)

        assert preflight._node_version() is None


class TestTheClaudeVersionFloor:
    """The grading reads a result with no `is_error` key as a success.

    That is the shape claude-code emits, measured rather than promised by any
    schema. On a CLI older than the measurement the shape is unknown, and every
    verdict in the run would be wrong the same way — silently, since a misread
    success looks exactly like a success (#229 review).
    """

    @staticmethod
    def _claude_says(monkeypatch, stdout: str, returncode: int = 0,
                     raises: Exception | None = None):
        def _fake_run(cmd, **_kwargs):
            if raises is not None:
                raise raises
            return subprocess.CompletedProcess(cmd, returncode, stdout, "")

        monkeypatch.setattr(preflight.subprocess, "run", _fake_run)

    def test_the_measured_version_passes(self, monkeypatch):
        self._claude_says(monkeypatch, "2.1.276 (Claude Code)")

        assert preflight.check_claude() == []

    def test_a_newer_version_passes(self, monkeypatch):
        """A floor, not a pin: refusing anything newer would be the thing that breaks."""
        self._claude_says(monkeypatch, "3.0.1 (Claude Code)")

        assert preflight.check_claude() == []

    def test_an_older_version_is_refused_with_the_reason(self, monkeypatch):
        self._claude_says(monkeypatch, "2.1.100 (Claude Code)")

        problem = "\n".join(preflight.check_claude())

        assert "2.1.100" in problem
        assert "2.1.276" in problem
        assert "is_error" in problem, "the reason has to name the shape it depends on"

    @pytest.mark.parametrize("scenario", ["unreadable", "nonzero", "missing"])
    def test_an_unanswerable_version_is_not_invented_into_a_problem(
            self, monkeypatch, scenario):
        """Unknown is not broken — the rule the rest of this file follows."""
        if scenario == "unreadable":
            self._claude_says(monkeypatch, "not a version at all")
        elif scenario == "nonzero":
            self._claude_says(monkeypatch, "", returncode=1)
        else:
            self._claude_says(monkeypatch, "", raises=FileNotFoundError("no claude"))

        assert preflight.check_claude() == []

    def test_the_opt_out_skips_it(self, monkeypatch, capsys):
        monkeypatch.setenv("CF_UX_SKIP_CLAUDE_VERSION_CHECK", "1")
        monkeypatch.setattr(preflight, "check_node", list)
        monkeypatch.setattr(preflight, "check_codex_model", lambda _model: [])

        def _must_not_be_called():
            raise AssertionError("the version check ran despite the opt-out")

        monkeypatch.setattr(preflight, "check_claude", _must_not_be_called)

        assert preflight.main(["--node-only"]) == 0
        capsys.readouterr()
