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
def _forget_the_cached_read(monkeypatch):
    """The read is cached for the process, which is the point in production and
    a cross-test leak here.

    The opt-out is cleared too. It is the documented way to silence the check, so
    a developer or runner can have it exported, and with it set 18 of these tests
    failed for a reason that had nothing to do with the code (CodeRabbit, #245).
    Tests that exercise the opt-out set it themselves.

    `CODEX_HOME` is cleared for the whole suite in `conftest.py`, not here: every
    agent-generation test resolves codex models, not only these.
    """
    monkeypatch.delenv("CF_SKIP_MODEL_ENTITLEMENT_CHECK", raising=False)
    # And the findings `agents` keeps between calls, reset the way production resets
    # them: once here, for every test, instead of six hand-copied class fixtures of
    # which one cleared a different pair and one class had none (#245 review).
    from studio.commands import agents
    agents._begin_entitlement_run()
    model_entitlements.entitled_codex_models.cache_clear()
    yield
    model_entitlements.entitled_codex_models.cache_clear()
    agents._begin_entitlement_run()


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

    def test_the_message_list_is_bounded(self, tmp_path, monkeypatch):
        """It goes into a line a person reads; a vendor listing fifty models
        should not turn that into a page."""
        many = [{"slug": f"m-{i:02d}", "visibility": "list"} for i in range(40)]
        _cache(tmp_path, monkeypatch, many)

        message = model_entitlements.listed_for_message(
            model_entitlements.entitled_codex_models())

        assert message.count(",") < 40
        assert "more" in message

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

    def test_entries_that_are_all_unlisted_read_as_unknown_not_as_empty(
            self, tmp_path, monkeypatch):
        """Models are described but none match what this reads as "offered to a
        person". Far likelier that the shape moved than that an account is
        entitled to nothing, and the two are indistinguishable from here — so
        the answer is that nothing is known, not that nothing is allowed."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-reserve", "visibility": "hide"}])

        assert model_entitlements.entitled_codex_models() is None
        assert model_entitlements.codex_model_is_withdrawn("anything") is False

    def test_a_cache_with_no_entries_at_all_is_unknown(self, tmp_path, monkeypatch):
        _cache(tmp_path, monkeypatch, [])

        assert model_entitlements.entitled_codex_models() == frozenset()
        assert model_entitlements.codex_model_is_withdrawn("anything") is False

    def test_no_home_is_an_answer_not_an_exception(self, monkeypatch):
        """`Path.home()` raises where no home can be determined. This function
        promises an answer to a caller that must not fail."""
        monkeypatch.delenv("CODEX_HOME", raising=False)
        monkeypatch.setattr(model_entitlements.Path, "home",
                            staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("no home"))))

        assert model_entitlements.entitled_codex_models() is None

    def test_the_default_path_is_under_the_home_directory(self, monkeypatch, tmp_path):
        """The branch taken when `CODEX_HOME` is unset — every other test sets
        it, so nothing was exercising the default."""
        monkeypatch.delenv("CODEX_HOME", raising=False)
        monkeypatch.setattr(model_entitlements.Path, "home", staticmethod(lambda: tmp_path))

        assert model_entitlements.codex_cache_path() == tmp_path / ".codex" / "models_cache.json"

    def test_codex_home_is_honoured(self, tmp_path, monkeypatch):
        """A non-default home must not be mistaken for a missing cache."""
        path = _cache(tmp_path, monkeypatch, [{"slug": "x", "visibility": "list"}])

        assert model_entitlements.codex_cache_path() == path


class TestTheWarningInGenerate:
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
        written. But it says so — a check that fails silently is
        indistinguishable from one that found nothing, and the CLI never raises
        its level above WARNING, so a debug line would be unreadable by anyone."""
        from studio.commands import agents
        monkeypatch.setattr(agents.model_entitlements, "codex_model_is_withdrawn",
                            lambda _m: (_ for _ in ()).throw(RuntimeError("boom")))

        with caplog.at_level(logging.WARNING):
            got = self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert got is not None, "generation must survive the check failing"
        assert "could not run" in caplog.text
        assert "boom" in caplog.text

    def test_a_failing_check_says_so_once_not_per_agent(self, monkeypatch, caplog):
        from studio.commands import agents
        monkeypatch.setattr(agents.model_entitlements, "codex_model_is_withdrawn",
                            lambda _m: (_ for _ in ()).throw(RuntimeError("boom")))

        with caplog.at_level(logging.WARNING):
            for _ in range(10):
                self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert caplog.text.count("could not run") == 1

    def test_the_check_can_be_turned_off(self, tmp_path, monkeypatch, caplog):
        """Anything advisory needs a way off: an account on an API key has a
        different entitlement set from the ChatGPT-plan cache this reads."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")
        monkeypatch.setenv(agents._ENTITLEMENT_OPT_OUT, "1")

        with caplog.at_level(logging.WARNING):
            got = self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert got == "gone-model"
        assert caplog.text == ""
        assert agents.drain_entitlement_warnings() == []

    def test_the_warning_names_the_cache_it_consulted(self, tmp_path, monkeypatch, caplog):
        """Which file was read is the first thing anyone disputing the warning
        needs to know."""
        path = _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")

        with caplog.at_level(logging.WARNING):
            self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert str(path) in caplog.text
        assert agents._ENTITLEMENT_OPT_OUT in caplog.text

    def test_the_finding_is_collected_for_json_consumers(self, tmp_path, monkeypatch, caplog):
        """A `--json` caller reads the result dict and never sees stderr."""
        path = _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")

        with caplog.at_level(logging.WARNING):
            self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")
        notices = agents.drain_entitlement_warnings()

        assert notices == [{
            "kind": "model-not-entitled", "tool": "codex", "provider": "openai",
            "model": "gone-model", "entitled": ["gpt-5.6-terra"], "source": str(path),
        }]

    def test_draining_clears_so_a_second_run_does_not_repeat_the_first(
            self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        from studio.commands import agents
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")

        with caplog.at_level(logging.WARNING):
            self._resolve("codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert len(agents.drain_entitlement_warnings()) == 1
        assert agents.drain_entitlement_warnings() == []

    def test_every_shipped_tier_reaches_the_checker_as_a_bare_slug(
            self, tmp_path, monkeypatch, caplog):
        """Plumbing, not entitlement: the tier resolves to something checkable.

        Building the cache from the matrix means this can never fail on a real
        withdrawal, and it should not be read as covering one -- the negative
        below is what has teeth (#245 review). What it does catch is the
        resolution path handing the checker something that is not a slug at all:
        a `cf:tier:` prefix left on, a `None` for a tier that has a model, an
        override that resolves to a key rather than a value.
        """
        from studio.commands import agents
        shipped = agents._MODEL_MATRIX[("codex", "openai")]["base"]
        _cache(tmp_path, monkeypatch,
               [{"slug": slug, "visibility": "list"} for slug in shipped.values()])

        with caplog.at_level(logging.WARNING):
            resolved = [self._resolve("codex", "openai", tier, "generate", "codebase")
                        for tier in shipped]

        assert resolved == [shipped[tier] for tier in shipped], (
            "a tier reached the checker as something other than its matrix slug")
        assert caplog.text == "", "every shipped slug must pass against a cache that lists it"
        assert agents.drain_entitlement_warnings() == []

    def test_a_cache_listing_none_of_the_shipped_slugs_warns_for_every_tier(
            self, tmp_path, monkeypatch, caplog):
        """The same pairing, against a cache that disagrees with it.

        This is the shape a real withdrawal takes: codex still answers, still
        lists models, and the ones this repository ships are not among them. It
        fails if the checker stops looking at shipped slugs -- which the positive
        above, built from the matrix itself, cannot.
        """
        from studio.commands import agents
        shipped = agents._MODEL_MATRIX[("codex", "openai")]["base"]
        _cache(tmp_path, monkeypatch,
               [{"slug": "some-model-nobody-ships", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            for tier in shipped:
                self._resolve("codex", "openai", tier, "generate", "codebase")

        warned = agents.drain_entitlement_warnings()
        assert len(warned) == len(shipped), (
            f"{len(shipped)} shipped tiers, {len(warned)} warnings")
        assert all(slug in caplog.text for slug in shipped.values())

    def test_inherit_resolves_to_nothing_and_is_not_checked(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            assert self._resolve("codex", "openai", "cf:inherit", "generate", "codebase") is None

        assert caplog.text == ""


class TestTheResultDictGetsTheFinding:
    """`_attach_entitlement_warnings` is what puts a finding where `--json`
    consumers look. Tested directly, because the command that calls it needs a
    whole generate to run."""

    def test_a_clean_run_keeps_the_output_shape_it_had(self):
        from studio.commands import agents
        result = {"status": "OK"}

        agents._attach_entitlement_warnings(result)

        assert result == {"status": "OK"}, "no findings must not invent a warnings key"

    def test_a_finding_is_appended_beside_any_existing_warning(self, tmp_path, monkeypatch):
        from studio.commands import agents
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")
        agents._resolve_model_id("codex", "openai", "cf:tier:balanced", "generate", "codebase")
        result = {"warnings": [{"kind": "something-else"}]}

        agents._attach_entitlement_warnings(result)

        assert [w["kind"] for w in result["warnings"]] == ["something-else", "model-not-entitled"]


class TestEveryEmitterCarriesTheFinding:
    """A notice collected during model resolution must reach whichever response
    is actually emitted. Attaching it only to the successful legacy write meant a
    `--dry-run` — the natural way to ask what a generate would do — answered
    without it."""

    @staticmethod
    def _collect_one(tmp_path, monkeypatch):
        from studio.commands import agents
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")
        agents._resolve_model_id("codex", "openai", "cf:tier:balanced", "generate", "codebase")

    def test_the_v2_emitter_carries_it(self, tmp_path, monkeypatch):
        """Given what the v2 path really hands it -- a `_build_result` result, which is
        where the finding is attached now."""
        from studio.commands import agents
        self._collect_one(tmp_path, monkeypatch)
        emitted = {}
        monkeypatch.setattr(agents.ui, "result",
                            lambda payload, **_kw: emitted.update(payload))
        built = agents._build_result({}, [], tmp_path, tmp_path, None, {}, dry_run=True)

        agents._emit_v2_generation_result(
            agents_result=built, agents_to_process=[], results={}, dry_run=True)

        assert [w["kind"] for w in emitted["warnings"]] == ["model-not-entitled"]

    def test_a_clean_v2_run_keeps_its_shape(self, monkeypatch):
        from studio.commands import agents
        emitted = {}
        monkeypatch.setattr(agents.ui, "result",
                            lambda payload, **_kw: emitted.update(payload))

        agents._emit_v2_generation_result(
            agents_result={"status": "OK"}, agents_to_process=[], results={}, dry_run=False)

        assert "warnings" not in emitted

    def test_draining_means_one_emitter_does_not_repeat_another(self, tmp_path, monkeypatch):
        """Every result is attached through the same drain, so a run passing through two of them
        reports the finding once, not twice."""
        from studio.commands import agents
        self._collect_one(tmp_path, monkeypatch)
        monkeypatch.setattr(agents.ui, "result", lambda payload, **_kw: None)
        first = {"status": "OK"}
        second = {"status": "OK"}

        agents._attach_entitlement_warnings(first)
        agents._attach_entitlement_warnings(second)

        assert len(first["warnings"]) == 1
        assert "warnings" not in second


class TestTheMessageListBoundary:
    """`_MAX_LISTED_IN_MESSAGE` decides where a readable line stops. Its two
    interesting inputs are exactly at the cap and one past it."""

    def test_at_the_cap_everything_is_named_and_nothing_is_elided(self, tmp_path, monkeypatch):
        cap = model_entitlements._MAX_LISTED_IN_MESSAGE
        slugs = [f"m-{i:02d}" for i in range(cap)]
        _cache(tmp_path, monkeypatch, [{"slug": s, "visibility": "list"} for s in slugs])

        message = model_entitlements.listed_for_message(
            model_entitlements.entitled_codex_models())

        assert "more" not in message
        for slug in slugs:
            assert slug in message

    def test_one_past_the_cap_elides_exactly_one(self, tmp_path, monkeypatch):
        cap = model_entitlements._MAX_LISTED_IN_MESSAGE
        slugs = [f"m-{i:02d}" for i in range(cap + 1)]
        _cache(tmp_path, monkeypatch, [{"slug": s, "visibility": "list"} for s in slugs])

        message = model_entitlements.listed_for_message(
            model_entitlements.entitled_codex_models())

        assert "and 1 more" in message
        assert slugs[-1] not in message


class TestTheLegacyEmittersCarryTheFinding:
    """The v2 emitter was covered end to end; the three legacy ones were not.

    `_attach_entitlement_warnings` was tested against hand-built dicts, and
    `_emit_v2_generation_result` through a whole generate, but the legacy
    dry-run preview, the JSON preview and the no-change short-circuit were only
    covered by reading the source. Omitting the call from one of them, or making
    it before `_build_result` has filled the dict, left the suite green
    (#245 review).
    """

    @pytest.fixture(autouse=True)
    def _json_mode(self):
        from studio.utils.ui import set_json_mode
        set_json_mode(True)
        yield
        set_json_mode(False)

    @staticmethod
    def _queue_a_finding(tmp_path, monkeypatch):
        """Resolve a tier whose slug the cache does not list, leaving a notice pending."""
        from studio.commands import agents
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")
        agents._resolve_model_id("codex", "openai", "cf:tier:balanced", "generate", "codebase")

    def test_the_legacy_preview_emits_the_finding(self, tmp_path, monkeypatch, capsys):
        from studio.commands import agents
        self._queue_a_finding(tmp_path, monkeypatch)

        emitted = agents._emit_legacy_preview_result(
            {}, [], tmp_path, tmp_path, None, None, True, None)

        assert [w["kind"] for w in emitted.get("warnings", [])] == ["model-not-entitled"]
        assert "model-not-entitled" in capsys.readouterr().out

    def test_the_finding_is_attached_after_the_result_is_built(
            self, tmp_path, monkeypatch):
        """Ordering, stated as an observable rather than as a line number.

        Attaching before `_build_result` would lose the warning, because the
        dict the emitter returns is the one the build produces.
        """
        from studio.commands import agents
        self._queue_a_finding(tmp_path, monkeypatch)

        emitted = agents._emit_legacy_preview_result(
            {}, [], tmp_path, tmp_path, None, None, False, None)

        assert "warnings" in emitted, "the warning did not survive the build"
        assert {"status", "agents", "results"} <= set(emitted), (
            "the built result's own keys are still there")

    def test_the_no_change_short_circuit_emits_the_finding(
            self, tmp_path, monkeypatch, capsys):
        """It delegates to the preview emitter in JSON mode; that path is the one at risk."""
        from studio.commands import agents
        self._queue_a_finding(tmp_path, monkeypatch)

        agents._emit_legacy_no_changes({}, [], tmp_path, tmp_path, None, None, None)

        assert "model-not-entitled" in capsys.readouterr().out

    def test_a_clean_run_through_the_legacy_preview_invents_no_warnings_key(
            self, tmp_path, capsys):
        from studio.commands import agents

        emitted = agents._emit_legacy_preview_result(
            {}, [], tmp_path, tmp_path, None, None, True, None)

        assert "warnings" not in emitted
        capsys.readouterr()

    def test_the_result_constructor_attaches_the_finding_itself(self, tmp_path, monkeypatch):
        """The invariant is structural now: every emitter's result comes from
        `_build_result`, and `_build_result` attaches. This replaced an AST walk
        over `agents.py` that checked each emitter remembered to (#245 review)."""
        from studio.commands import agents
        self._queue_a_finding(tmp_path, monkeypatch)

        result = agents._build_result({}, ["codex"], tmp_path, tmp_path, None, {}, dry_run=True)

        assert [w["model"] for w in result.get("warnings", [])
                if isinstance(w, dict) and w.get("kind") == "model-not-entitled"]
        assert agents.drain_entitlement_warnings() == [], "drained, so nothing repeats"

    def test_no_emitter_attaches_a_second_time(self):
        """One place, so a later emitter cannot re-add what the constructor drained."""
        import inspect
        from studio.commands import agents

        callers = [name for name, fn in vars(agents).items()
                   if inspect.isfunction(fn)
                   and name not in ("_build_result", "_attach_entitlement_warnings")
                   and "_attach_entitlement_warnings(" in inspect.getsource(fn)]
        assert callers == [], callers


class TestWhatTheCacheFailuresAreReportedAs:
    """A missing cache and a broken one are different events and are said so.

    Everything here used to go to `logger.debug`, which this repository's own
    lint contract does not count as a visible signal at all -- `debug` is left
    out of `_VISIBLE_SIGNAL_NAMES` in `scripts/pylint_plugins/silent_exceptions.py`
    on purpose. So a cache that existed and could not be read disabled
    entitlement checking for the whole run and said nothing anywhere
    (#245 review).
    """

    @staticmethod
    def _entitled(monkeypatch):
        from studio.utils import model_entitlements
        model_entitlements.entitled_codex_models.cache_clear()
        return model_entitlements.entitled_codex_models()

    def test_a_missing_cache_stays_quiet(self, tmp_path, monkeypatch, caplog):
        """Codex has not run here. Not a problem, and not worth a line of output."""
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nowhere"))

        with caplog.at_level(logging.WARNING):
            assert self._entitled(monkeypatch) is None

        assert caplog.text == ""

    def test_a_cache_that_exists_and_cannot_be_decoded_is_reported(
            self, tmp_path, monkeypatch, caplog):
        home = tmp_path / "codex_home"
        home.mkdir()
        (home / "models_cache.json").write_bytes(b"\xff\xfe not utf-8")
        monkeypatch.setenv("CODEX_HOME", str(home))

        with caplog.at_level(logging.WARNING):
            assert self._entitled(monkeypatch) is None

        assert "cannot be read" in caplog.text
        assert str(home) in caplog.text, "the message must name the file it failed on"

    def test_the_message_names_the_real_path_not_a_placeholder(
            self, tmp_path, monkeypatch, caplog):
        """The diagnostic overwrote `path` with `<unresolved>` before using it, so
        it never named the file it had just failed to read."""
        home = tmp_path / "codex_home"
        home.mkdir()
        (home / "models_cache.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("CODEX_HOME", str(home))

        with caplog.at_level(logging.WARNING):
            self._entitled(monkeypatch)

        assert "<unresolved>" not in caplog.text

    def test_an_unfamiliar_shape_is_reported(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, "not-a-list")

        with caplog.at_level(logging.WARNING):
            assert self._entitled(monkeypatch) is None

        assert "unfamiliar shape" in caplog.text


class TestABlankSlugNamesNoModel:
    """An entry with `visibility: list` and an empty slug is not an entitlement.

    Counting it made the set non-empty, which is the difference between "nothing
    is known" and "one model is entitled" -- and under the latter every real
    model looks withdrawn, so every agent draws a false warning (#245 review).
    """

    @staticmethod
    def _entitled():
        from studio.utils import model_entitlements
        model_entitlements.entitled_codex_models.cache_clear()
        return model_entitlements.entitled_codex_models()

    @pytest.mark.parametrize("slug", ["", "   ", "\t", "\n"])
    def test_a_blank_slug_is_not_counted(self, tmp_path, monkeypatch, slug):
        _cache(tmp_path, monkeypatch, [{"slug": slug, "visibility": "list"}])

        assert self._entitled() is None, (
            "entries present and none of them naming a model is 'unknown', not a set of one")

    def test_a_blank_slug_beside_a_real_one_leaves_only_the_real_one(
            self, tmp_path, monkeypatch):
        _cache(tmp_path, monkeypatch, [{"slug": "  ", "visibility": "list"},
                                       {"slug": "gpt-5.6-sol", "visibility": "list"}])

        assert self._entitled() == frozenset({"gpt-5.6-sol"})

    def test_a_blank_slug_alone_does_not_make_every_model_look_withdrawn(
            self, tmp_path, monkeypatch, caplog):
        """The consequence, stated where it would have been seen."""
        from studio.commands import agents
        _cache(tmp_path, monkeypatch, [{"slug": "", "visibility": "list"}])

        with caplog.at_level(logging.WARNING):
            agents._resolve_model_id("codex", "openai", "cf:tier:balanced",
                                     "generate", "codebase")

        assert agents.drain_entitlement_warnings() == []


class TestTheScopeIsReadOffTheProviderTable:
    """The pair was a second hand-written literal under a comment claiming it was
    derived from the tables -- the drift the comment promised to prevent
    (#245 review)."""

    def test_it_matches_the_table(self):
        from studio.commands import agents

        assert agents._entitlement_scope() == ("codex", "openai")

    def test_it_follows_the_table_rather_than_a_literal(self, monkeypatch):
        from studio.commands import agents
        monkeypatch.setitem(agents._TOOL_PROVIDER_SUPPORT, "codex", {"someone-else"})

        assert agents._entitlement_scope() == ("codex", "someone-else")

    def test_an_ambiguous_table_raises_rather_than_guessing(self, monkeypatch):
        from studio.commands import agents
        monkeypatch.setitem(agents._TOOL_PROVIDER_SUPPORT, "codex", {"openai", "another"})

        with pytest.raises(ValueError, match="cannot choose between them"):
            agents._entitlement_scope()


class TestTheCheckCannotStopGeneration:
    """The guarantee the whole `try` exists for: advisory means advisory.

    `_entitlement_scope()` raises when the provider table stops naming exactly
    one provider for codex -- on purpose, because choosing one would be a guess.
    It was called *before* the guard, so an unrelated edit to that table would
    have raised out of every codex model resolution and stopped generation
    outright. A check that can break the thing it advises on is worse than no
    check (#245 review).
    """

    def test_an_ambiguous_provider_table_does_not_raise_out_of_resolution(
            self, monkeypatch, caplog):
        from studio.commands import agents
        monkeypatch.setitem(agents._TOOL_PROVIDER_SUPPORT, "codex", {"openai", "another"})

        with caplog.at_level(logging.WARNING):
            resolved = agents._resolve_model_id(
                "codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert resolved is not None, "the model must still be resolved"
        assert "cannot choose between them" in caplog.text, (
            "the failure has to be visible; a silent one is indistinguishable from a pass")

    def test_it_is_said_once_rather_than_per_agent(self, monkeypatch, caplog):
        """44 agents must not produce 44 copies of the same broken-table notice."""
        from studio.commands import agents
        monkeypatch.setitem(agents._TOOL_PROVIDER_SUPPORT, "codex", {"openai", "another"})

        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                agents._resolve_model_id(
                    "codex", "openai", "cf:tier:balanced", "generate", "codebase")

        assert caplog.text.count("cannot choose between them") == 1

    def test_a_tool_outside_the_scope_never_reaches_the_table_at_all(self, monkeypatch):
        """The opt-out and the None check still short-circuit ahead of everything."""
        from studio.commands import agents

        def _must_not_be_called():
            raise AssertionError("the scope was resolved for a tool it does not cover")

        monkeypatch.setattr(agents, "_entitlement_scope", _must_not_be_called)

        assert agents._resolve_model_id(
            "claude", "anthropic", "cf:tier:balanced", "generate", "codebase") is not None

    def test_the_opt_out_short_circuits_before_the_table_is_read(self, monkeypatch):
        from studio.commands import agents
        monkeypatch.setenv(agents._ENTITLEMENT_OPT_OUT, "1")

        def _must_not_be_called():
            raise AssertionError("the scope was resolved despite the opt-out")

        monkeypatch.setattr(agents, "_entitlement_scope", _must_not_be_called)

        assert agents._resolve_model_id(
            "codex", "openai", "cf:tier:balanced", "generate", "codebase") is not None


class TestTheOrdinaryMissIsNotAnException:
    """"No cache" is a condition, not a failure to absorb.

    It used to be a caught `FileNotFoundError` whose handler only logged at
    debug, which this repository's contract does not count as a visible signal --
    so it read as a swallowed exception. Asking `is_file()` first says what is
    actually true and leaves no handler to route anywhere (#245 review).
    """

    @staticmethod
    def _entitled():
        from studio.utils import model_entitlements
        model_entitlements.entitled_codex_models.cache_clear()
        return model_entitlements.entitled_codex_models()

    def test_a_missing_cache_file_is_unknown_and_quiet(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "never-used"))

        with caplog.at_level(logging.WARNING):
            assert self._entitled() is None

        assert caplog.text == ""

    def test_a_directory_where_the_cache_should_be_is_also_a_miss(
            self, tmp_path, monkeypatch, caplog):
        """Not a readable file either, and not worth a warning: still just absent."""
        home = tmp_path / "codex_home"
        (home / "models_cache.json").mkdir(parents=True)
        monkeypatch.setenv("CODEX_HOME", str(home))

        with caplog.at_level(logging.WARNING):
            assert self._entitled() is None

        assert caplog.text == ""

    def test_no_resolvable_home_is_a_warned_miss_rather_than_a_crash(self, monkeypatch, caplog):
        """A container with no `$HOME`, no passwd entry and no `CODEX_HOME`. Still an
        answer, not an exception -- but said at WARNING, because the check is off for
        the run and "codex cannot have run here" is an assumption (#245 review)."""
        from studio.utils import model_entitlements

        def _no_home():
            raise RuntimeError("Could not determine home directory")

        monkeypatch.delenv("CODEX_HOME", raising=False)
        monkeypatch.setattr(model_entitlements.Path, "home", staticmethod(_no_home))

        with caplog.at_level(logging.WARNING):
            assert self._entitled() is None

        assert "withdrawn-model check is skipped" in caplog.text
        assert "CODEX_HOME" in caplog.text, "and names the way to point it somewhere"


class TestEachGenerateStartsWithNoCarriedFindings:
    """The notices and the warned-once set were module-level and lived for the
    process. A generate that ended any way but a completed emit -- `n` at the
    preview, an early error -- left both filled: the next generate in the same
    process drained the stale notices into its own result, and said nothing about
    models the earlier one had already warned for (#245 review)."""

    @staticmethod
    def _an_earlier_run_that_did_not_finish(tmp_path, monkeypatch):
        from studio.commands import agents
        monkeypatch.delenv(agents._ENTITLEMENT_OPT_OUT, raising=False)
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        agents._checked("codex", "openai", "gpt-withdrawn")
        assert agents._ENTITLEMENT_NOTICES and agents._ENTITLEMENT_WARNED, "precondition"

    def test_the_entry_point_clears_what_an_earlier_run_left(self, tmp_path, monkeypatch):
        """Driven through `cmd_generate_agents` itself, stopped at its first step: the
        reset has to happen before anything else can run, or an early exit would
        still leave the state behind."""
        from studio.commands import agents
        self._an_earlier_run_that_did_not_finish(tmp_path, monkeypatch)
        monkeypatch.setattr(agents, "_resolve_agents_context", lambda *_a, **_k: None)

        assert agents.cmd_generate_agents([]) == 1

        assert agents._ENTITLEMENT_NOTICES == [], "stale notices would reach the next result"
        assert agents._ENTITLEMENT_WARNED == set(), "and the next run would stay silent"

    def test_a_second_run_reports_the_same_model_again(self, tmp_path, monkeypatch, caplog):
        from studio.commands import agents
        self._an_earlier_run_that_did_not_finish(tmp_path, monkeypatch)
        agents._begin_entitlement_run()

        with caplog.at_level(logging.WARNING):
            agents._checked("codex", "openai", "gpt-withdrawn")

        assert [n["model"] for n in agents.drain_entitlement_warnings()] == ["gpt-withdrawn"]


class TestTheCacheIsOnlyEvidenceForTheLoginItDescribes:
    """The cache lists a ChatGPT plan's models. Under an API-key login the same
    file is no evidence about the account, and reading it as evidence produced a
    confident false "withdrawn" -- left to the person to diagnose and opt out of
    (#245 review). codex records the login type in `auth.json` beside the cache.

    Only the API-key test fails without the change; the rest pin that the new
    condition does not reach past it -- an unknown login keeps the check running."""

    @staticmethod
    def _login(tmp_path, content):
        (tmp_path / "codex_home").mkdir(exist_ok=True)
        (tmp_path / "codex_home" / "auth.json").write_text(content, encoding="utf-8")

    def test_an_api_key_login_is_unknown_not_withdrawn(self, tmp_path, monkeypatch):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        self._login(tmp_path, json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-x"}))

        assert model_entitlements.entitled_codex_models() is None
        assert model_entitlements.codex_model_is_withdrawn("gpt-something-else") is False

    def test_a_chatgpt_login_is_checked_as_before(self, tmp_path, monkeypatch):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        self._login(tmp_path, json.dumps({"auth_mode": "chatgpt", "tokens": {}}))

        assert model_entitlements.codex_model_is_withdrawn("gpt-something-else") is True

    @pytest.mark.parametrize("content", [None, "{not json", "[]", '{"no_mode": 1}', '{"auth_mode": 7}'])
    def test_not_knowing_the_login_type_keeps_the_check(self, tmp_path, monkeypatch, content):
        """Unknown is not evidence of a different account: the check stays as it was."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        if content is not None:
            self._login(tmp_path, content)

        assert model_entitlements.codex_model_is_withdrawn("gpt-something-else") is True

    def test_what_it_read_is_never_logged(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        self._login(tmp_path, json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "sk-SECRETVALUE"}))

        with caplog.at_level(logging.DEBUG):
            model_entitlements.entitled_codex_models()

        assert "sk-SECRETVALUE" not in caplog.text


class TestTheSuiteNeverSeesTheRunnersCodexHome:
    """`conftest.py` clears `CODEX_HOME` for every test. Meaningful where the runner
    has one exported -- a developer who uses codex -- which is exactly where the
    leak was measured (#245 review)."""

    def test_codex_home_is_unset_inside_a_test(self):
        import os

        assert "CODEX_HOME" not in os.environ

    def test_so_the_default_cache_is_under_the_isolated_home(self):
        from pathlib import Path

        assert model_entitlements.codex_cache_path() == Path.home() / ".codex" / "models_cache.json"
        assert not model_entitlements.codex_cache_path().exists()


class TestAnUnfamiliarLoginTypeIsSaidOutLoud:
    """`"chatgpt"` is the one spelling measured. Any other value switched the check
    off with only a debug line, so a codex release renaming it would have disabled
    the check for every ChatGPT user in silence (#245 review)."""

    @staticmethod
    def _login(tmp_path, mode):
        (tmp_path / "codex_home").mkdir(exist_ok=True)
        (tmp_path / "codex_home" / "auth.json").write_text(
            json.dumps({"auth_mode": mode, "OPENAI_API_KEY": "sk-NOTLOGGED-0123456789"}),
            encoding="utf-8")

    @pytest.mark.parametrize("mode", ["apikey", "chatgpt-v2", "oauth"])
    def test_it_is_named_at_warning_and_the_check_is_off(self, tmp_path, monkeypatch, caplog, mode):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        self._login(tmp_path, mode)

        with caplog.at_level(logging.WARNING):
            assert model_entitlements.entitled_codex_models() is None

        assert repr(mode) in caplog.text and "check is off" in caplog.text
        assert "sk-NOTLOGGED" not in caplog.text

    def test_the_measured_spelling_says_nothing(self, tmp_path, monkeypatch, caplog):
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        self._login(tmp_path, "chatgpt")

        with caplog.at_level(logging.WARNING):
            assert model_entitlements.entitled_codex_models() == frozenset({"gpt-5.6-sol"})

        assert caplog.text == ""

    def test_an_unreadable_login_record_is_said_without_its_content(
            self, tmp_path, monkeypatch, caplog):
        """The check keeps running, on an assumption it could not confirm -- worth a
        line. Only the exception's type is named: the file holds tokens."""
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-sol", "visibility": "list"}])
        (tmp_path / "codex_home" / "auth.json").write_text(
            '{"tokens": "sk-NOTLOGGED-0123456789", broken', encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            assert model_entitlements.codex_model_is_withdrawn("gpt-other") is True

        assert "cannot read codex's login record" in caplog.text
        assert "sk-NOTLOGGED" not in caplog.text
