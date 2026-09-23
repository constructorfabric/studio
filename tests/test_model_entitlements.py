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
    @pytest.fixture(autouse=True)
    def _forget_what_was_warned(self):
        from studio.commands import agents
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()
        yield
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()

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

    @pytest.fixture(autouse=True)
    def _clean(self):
        from studio.commands import agents
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()
        yield
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()

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

    @pytest.fixture(autouse=True)
    def _clean(self):
        from studio.commands import agents
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()
        yield
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()

    @staticmethod
    def _collect_one(tmp_path, monkeypatch):
        from studio.commands import agents
        _cache(tmp_path, monkeypatch, [{"slug": "gpt-5.6-terra", "visibility": "list"}])
        monkeypatch.setitem(agents._MODEL_MATRIX[("codex", "openai")]["base"],
                            "cf:tier:balanced", "gone-model")
        agents._resolve_model_id("codex", "openai", "cf:tier:balanced", "generate", "codebase")

    def test_the_v2_emitter_attaches_it(self, tmp_path, monkeypatch):
        from studio.commands import agents
        self._collect_one(tmp_path, monkeypatch)
        emitted = {}
        monkeypatch.setattr(agents.ui, "result",
                            lambda payload, **_kw: emitted.update(payload))

        agents._emit_v2_generation_result(
            agents_result={"status": "OK"}, agents_to_process=[], results={}, dry_run=True)

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
        """Both emitters call the same drain, so a run passing through two of them
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
    def _clean(self):
        from studio.commands import agents
        from studio.utils.ui import set_json_mode
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()
        set_json_mode(True)
        yield
        set_json_mode(False)
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()

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

    def test_every_emitter_that_builds_a_result_also_attaches_the_finding(self):
        """The third call site writes files, so it is pinned structurally instead.

        `_run_legacy_generate_path` completes a real write and is not worth
        driving from here, but a fourth emitter added later without the call is
        exactly the regression this class exists for. Every function that calls
        `_build_result` must also call `_attach_entitlement_warnings`.
        """
        import ast
        import inspect

        from studio.commands import agents

        tree = ast.parse(inspect.getsource(agents))
        calls = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls[node.name] = {
                    sub.func.id for sub in ast.walk(node)
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                }

        # Delegation counts: `_run_v2_generate_path` builds the dict and hands it
        # to `_emit_v2_generation_result`, which attaches. What must not exist is
        # a function that builds a result and reaches no attaching function at all.
        attaching = {name for name, called in calls.items()
                     if "_attach_entitlement_warnings" in called}
        for _ in range(len(calls)):                       # close over delegation
            grown = {name for name, called in calls.items() if called & attaching}
            if grown <= attaching:
                break
            attaching |= grown

        missing = sorted(
            name for name, called in calls.items()
            if "_build_result" in called and name not in attaching
        )

        assert not missing, (
            f"these build a result and never attach entitlement findings: {missing}")


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
        agents._ENTITLEMENT_WARNED.clear()
        agents.drain_entitlement_warnings()

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
