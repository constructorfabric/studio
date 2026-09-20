"""The advisory check that a resolved codex model is one the account has.

Its whole value is in when it stays quiet. A check that cries wolf on a stale
cache, an unfamiliar shape or a different account type would be turned off, and
then the outage it exists to catch goes uncaught anyway.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "studio" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from studio.utils import model_entitlements  # noqa: E402


@pytest.fixture(autouse=True)
def _forget_the_cached_read():
    """The read is cached for the process, which is the point in production and
    a cross-test leak here."""
    model_entitlements.entitled_codex_models.cache_clear()
    yield
    model_entitlements.entitled_codex_models.cache_clear()


def _cache(tmp_path: Path, monkeypatch, models) -> Path:
    home = tmp_path / "codex_home"
    home.mkdir(exist_ok=True)
    path = home / "models_cache.json"
    path.write_text(json.dumps({"models": models}), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    return path


class TestWhatTheCacheSays:
    def test_a_listed_model_is_not_withdrawn(self, tmp_path, monkeypatch):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])

        assert model_entitlements.codex_model_is_withdrawn("gpt-5.6-sol") is False

    def test_a_model_the_cache_does_not_list_is_withdrawn(self, tmp_path, monkeypatch):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])

        assert model_entitlements.codex_model_is_withdrawn("gpt-5.4-mini") is True

    def test_an_internal_entry_does_not_count_as_entitled(self, tmp_path, monkeypatch):
        """The cache carries entries the CLI hides from people. Treating one as
        entitled would make a withdrawn slug look fine."""
        _cache(tmp_path, monkeypatch, [
            {"slug": "gpt-reserve", "visibility": "hide"},
            {"slug": "gpt-5.6-sol", "visibility": "list"},
        ])

        assert model_entitlements.entitled_codex_models() == frozenset({"gpt-5.6-sol"})
        assert model_entitlements.codex_model_is_withdrawn("gpt-reserve") is True


class TestEveryUncertaintyIsSilence:
    """None and an empty set are different answers, and neither is evidence."""

    def test_a_missing_cache_reports_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nowhere"))

        assert model_entitlements.entitled_codex_models() is None
        assert model_entitlements.codex_model_is_withdrawn("anything") is False

    @pytest.mark.parametrize("content", ["not json", '{"models": "not a list"}', "{}"])
    def test_a_cache_it_cannot_read_reports_nothing(self, tmp_path, monkeypatch, content):
        home = tmp_path / "codex_home"
        home.mkdir()
        (home / "models_cache.json").write_text(content, encoding="utf-8")
        monkeypatch.setenv("CODEX_HOME", str(home))

        assert model_entitlements.entitled_codex_models() is None
        assert model_entitlements.codex_model_is_withdrawn("anything") is False

    def test_a_cache_listing_nothing_is_not_taken_as_entitled_to_nothing(
            self, tmp_path, monkeypatch):
        """Far more likely a CLI that has not populated it than an account with
        no models at all — and warning about every model would be the loudest
        possible way to be wrong."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-reserve", "visibility": "hide"}])

        assert model_entitlements.entitled_codex_models() == frozenset()
        assert model_entitlements.codex_model_is_withdrawn("anything") is False

    def test_codex_home_is_honoured(self, tmp_path, monkeypatch):
        """A non-default home must not be mistaken for a missing cache."""
        path = _cache(tmp_path, monkeypatch, [{"slug": "x", "visibility": "list"}])

        assert model_entitlements.codex_cache_path() == path


class TestTheWarningInGenerate:
    @pytest.fixture(autouse=True)
    def _forget_what_was_warned(self):
        from studio.commands import agents
        agents._ENTITLEMENT_WARNED.clear()
        yield
        agents._ENTITLEMENT_WARNED.clear()

    @staticmethod
    def _resolve(*args):
        from studio.commands.agents import _resolve_model_id
        return _resolve_model_id(*args)

    def test_a_withdrawn_model_warns_and_is_still_returned(self, tmp_path, monkeypatch, caplog):
        """Advisory: the value is unchanged whatever the answer. Making the
        *output* depend on which machine it runs on would be a worse bargain
        than the outage this warns about."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")

        with caplog.at_level(logging.WARNING):
            got = self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert got == "gone-model", "generation must not be rerouted by an advisory check"
        assert "gone-model" in caplog.text
        assert "gpt-5.6-terra" in caplog.text, "the message names what the account does have"

    def test_the_warning_is_said_once_not_once_per_agent(self, tmp_path, monkeypatch, caplog):
        """`_resolve_model_id` runs for every agent — 44 in the shipped manifest
        — and the same slug answers most of them."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")

        with caplog.at_level(logging.WARNING):
            for _ in range(44):
                self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert caplog.text.count("gone-model") == 1

    def test_a_listed_model_says_nothing(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gpt-5.6-terra")

        with caplog.at_level(logging.WARNING):
            self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert caplog.text == ""

    def test_cursor_and_copilot_are_not_judged_by_codex_s_cache(
            self, tmp_path, monkeypatch, caplog):
        """They resolve OpenAI names from their own catalogues, which this cache
        says nothing about."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            for tool in ("cursor", "copilot"):
                self._resolve(tool, "openai", "cf:tier:balanced", "generate", "codebase")

        assert caplog.text == ""

    def test_anthropic_cells_are_not_judged_by_it_either(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            self._resolve("claude", "anthropic", "cf:tier:balanced", "generate", "codebase")

        assert caplog.text == ""

    def test_a_passthrough_model_id_is_checked_too(self, tmp_path, monkeypatch, caplog):
        """A raw vendor id a kit author wrote is exactly as capable of being
        withdrawn as one the matrix holds."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            got = self._resolve("codex", "openai", "some-old-model", "generate", "codebase")

        assert got == "some-old-model"
        assert "some-old-model" in caplog.text

    def test_a_check_that_raises_does_not_break_a_generate(self, monkeypatch, caplog):
        """Advisory means advisory: nothing it does may stop a config being
        written."""
        from studio.commands import agents
        monkeypatch.setattr(agents.model_entitlements, "codex_model_is_withdrawn",
                            lambda _m: (_ for _ in ()).throw(RuntimeError("boom")))

        with caplog.at_level(logging.WARNING):
            got = self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert got is not None
        assert "boom" not in caplog.text

    def test_inherit_resolves_to_nothing_and_is_not_checked(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            assert self._resolve("codex", "openai", "cf:inherit", "generate", "codebase") is None

        assert caplog.text == ""
