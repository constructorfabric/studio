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
import sys
from pathlib import Path

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

    def test_the_number_of_probes_is_capped(self, tmp_path, monkeypatch):
        """Each probe is a process with a timeout, and a long-lived nvm directory
        accumulates dozens of versions."""
        root = tmp_path / "versions" / "node"
        for i in range(40):
            (root / f"v{i}.0.0" / "bin").mkdir(parents=True)
            (root / f"v{i}.0.0" / "bin" / "node").touch()
        monkeypatch.setenv("NVM_DIR", str(tmp_path))
        probed = []
        monkeypatch.setattr(preflight, "_node_version",
                            lambda binary="node": probed.append(binary) or None)

        preflight._nvm_candidates()

        assert len(probed) == preflight.NVM_PROBE_LIMIT
