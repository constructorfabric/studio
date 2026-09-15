"""Tests for resolving a gate's decision key against a plan's declarations.

The contract these pin is short and unforgiving: exact match or ask, three outcomes, and
`absent` kept apart from `ambiguous` because only one of them means the plan has a gap.
"""
from __future__ import annotations

import ast
import dataclasses
import logging
import os
import re
import threading
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.utils import plan_decisions as pd  # noqa: E402


def _plan(tmp_path: Path, body: str) -> Path:
    """Write a plan.toml and return the directory holding it."""
    (tmp_path / pd.PLAN_FILE).write_text(body, encoding="utf-8")
    return tmp_path


DIRECT = '''
[plan]
task = "demo"

[[gate_decisions]]
key = "runtime.base-image"
value = "ubuntu-24.04"
'''

POLICY = '''
[plan]
task = "demo"

[[gate_decisions]]
key = "review.follow-up-depth"
dimension = "register.classification"
[gate_decisions.policy]
serious = "full-review"
normal = "spot-check"
'''


class TestAnExactMatchResolvesAndNothingElseDoes:
    """The rule the whole contract rests on."""

    def test_a_declared_key_resolves_to_its_value(self, tmp_path: Path) -> None:
        found = pd.resolve("runtime.base-image", _plan(tmp_path, DIRECT))
        assert found.status == "resolved", found
        assert found.value == "ubuntu-24.04", found
        assert found.provenance == "plan", found
        assert found.resolved is True, found

    @pytest.mark.parametrize("near_miss", [
        "Runtime.Base-Image",          # case
        " runtime.base-image",         # leading space
        "runtime.base-image ",         # trailing space
        "runtime_base_image",          # separator
        "runtime.base-imag",           # truncation
        "runtime.base-images",         # plural
    ])
    def test_a_near_miss_never_resolves(self, tmp_path: Path, near_miss: str) -> None:
        """Each of these is one normalisation away from the declared key.

        Every one of them would match under a casefold, a strip or a separator fold, which
        is why none of those is done: a resolver that normalises here readmits similarity
        matching, and the value it then returns is one nobody wrote.
        """
        found = pd.resolve(near_miss, _plan(tmp_path, DIRECT))
        assert found.status != "resolved", (near_miss, found)
        assert found.value == pd.UNSPECIFIED, found

    def test_the_key_it_would_have_to_normalise_to_find_is_the_declared_one(
            self, tmp_path: Path) -> None:
        """Guards the parametrized cases above against becoming vacuous.

        If the fixture's declared key were edited, every near miss would still fail to
        resolve — for the wrong reason, and the test would stay green while testing
        nothing. This pins that they are near misses *of something present*.
        """
        assert pd.resolve("runtime.base-image", _plan(tmp_path, DIRECT)).resolved


class TestSilenceAndIndecisionAreDifferentAnswers:
    """`absent` is the plan saying nothing; `ambiguous` is the plan not deciding."""

    def test_an_undeclared_key_is_absent(self, tmp_path: Path) -> None:
        found = pd.resolve("deploy.region", _plan(tmp_path, DIRECT))
        assert found.status == "absent", found

    def test_two_declarations_of_one_key_are_ambiguous_never_first_wins(
            self, tmp_path: Path) -> None:
        """First-wins would resolve, silently, to whichever the author wrote first."""
        body = DIRECT + '''
[[gate_decisions]]
key = "runtime.base-image"
value = "debian-12"
'''
        found = pd.resolve("runtime.base-image", _plan(tmp_path, body))
        assert found.status == "ambiguous", found
        assert found.value == pd.UNSPECIFIED, "a duplicate key resolved to one of its values"

    def test_a_declaration_carrying_both_a_value_and_a_policy_is_ambiguous(
            self, tmp_path: Path) -> None:
        body = '''
[[gate_decisions]]
key = "k"
value = "direct"
dimension = "d"
[gate_decisions.policy]
row = "via-policy"
'''
        found = pd.resolve("k", _plan(tmp_path, body), case="row")
        assert found.status == "ambiguous", found


class TestAPolicyResolvesOnADeclaredDimension:
    """The one permitted indirection, and the line it must not cross."""

    def test_a_declared_row_resolves_through_the_policy(self, tmp_path: Path) -> None:
        found = pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY), case="serious")
        assert found.status == "resolved", found
        assert found.value == "full-review", found
        assert found.provenance == "policy", "a policy resolution is not provenance 'plan'"

    def test_a_dimension_covered_without_this_case_is_ambiguous_not_absent(
            self, tmp_path: Path) -> None:
        """The distinction the contract turns on, and the easiest one to collapse.

        The plan declared a policy over classification and has no row for `urgent`. That is
        not silence: the plan claimed the dimension and failed to determine this case.
        Reporting it as `absent` would file a gap in the plan under the same heading as a
        question the plan never undertook to answer.
        """
        found = pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY), case="urgent")
        assert found.status == "ambiguous", found
        assert "no row for" in found.why, found.why

    def test_a_policy_with_no_case_supplied_is_ambiguous(self, tmp_path: Path) -> None:
        found = pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY))
        assert found.status == "ambiguous", found

    def test_a_policy_that_does_not_name_its_dimension_is_ambiguous(
            self, tmp_path: Path) -> None:
        """The alternative design, refused: inferring the dimension from the table's shape.

        A resolver that guessed would resolve this, and would then be unable to tell a
        policy that misses a case from one that was never about this dimension.
        """
        body = '''
[[gate_decisions]]
key = "k"
[gate_decisions.policy]
serious = "full-review"
'''
        found = pd.resolve("k", _plan(tmp_path, body), case="serious")
        assert found.status == "ambiguous", found
        assert "dimension" in found.why, found.why

    def test_a_case_is_matched_exactly_like_a_key(self, tmp_path: Path) -> None:
        """The no-normalisation rule applies to the enum value, not only to the key.

        Fixing exactness on one side and not the other leaves the back door open on the
        side nobody looked at.
        """
        found = pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY), case="Serious")
        assert found.status == "ambiguous", found


class TestNothingIsRemembered:
    """A cached `resolved` is a stale authority."""

    def test_editing_the_plan_changes_the_next_answer(self, tmp_path: Path) -> None:
        plan_dir = _plan(tmp_path, DIRECT)
        assert pd.resolve("runtime.base-image", plan_dir).value == "ubuntu-24.04"
        _plan(tmp_path, DIRECT.replace("ubuntu-24.04", "debian-12"))
        assert pd.resolve("runtime.base-image", plan_dir).value == "debian-12", (
            "the resolver answered from a cache, so a plan edited mid-run would not take "
            "effect until the process restarted"
        )

    def test_removing_the_declaration_stops_resolving_it(self, tmp_path: Path) -> None:
        """The other direction: a cache would keep answering after the plan stopped saying so."""
        plan_dir = _plan(tmp_path, DIRECT)
        assert pd.resolve("runtime.base-image", plan_dir).resolved
        _plan(tmp_path, '[plan]\ntask = "demo"\n')
        assert not pd.resolve("runtime.base-image", plan_dir).resolved


class TestAPlanThatCannotBeReadIsNotAPlanThatSaidNothing:
    """`absent` asserts something about the plan's contents."""

    def test_a_missing_plan_is_absent_and_silent(self, tmp_path: Path, caplog) -> None:
        """No plan is the ordinary case for a task that was never decomposed."""
        with caplog.at_level(logging.WARNING, logger=pd.logger.name):
            found = pd.resolve("k", tmp_path)
        assert found.status == "absent", found
        assert not caplog.records, [r.getMessage() for r in caplog.records]

    def test_an_unparseable_plan_is_ambiguous_and_warned_about(
            self, tmp_path: Path, caplog) -> None:
        """It stops every gate that consults it, so it must not read as a normal omission."""
        plan_dir = _plan(tmp_path, "[[decisions]\nkey = broken")
        with caplog.at_level(logging.WARNING, logger=pd.logger.name):
            found = pd.resolve("k", plan_dir)
        assert found.status == "ambiguous", found
        assert any("not valid TOML" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_a_plan_past_the_size_bound_is_not_read(self, tmp_path: Path) -> None:
        plan_dir = _plan(tmp_path, "# " + "x" * (pd._MAX_PLAN_BYTES + 1))
        found = pd.resolve("k", plan_dir)
        assert found.status == "ambiguous", found

    def test_the_read_is_what_enforces_the_bound_not_the_size_it_was_told(
            self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The size is now read from the descriptor, which closes the path-level race.

        It does not close all of it: a file can still grow between the `fstat` and the last
        byte read, and only the read observes that. So the read keeps its own bound and
        this proves the read is what stops — by making the reported size a lie.

        Rewritten when the open moved to `os.open`/`os.fstat` for the FIFO fix. The earlier
        version patched `Path.stat`, which the code no longer calls, so it would have gone
        on passing while testing nothing.
        """
        plan_dir = _plan(tmp_path, "# " + "x" * (pd._MAX_PLAN_BYTES + 4096))
        real_fstat = pd.os.fstat

        def _understate(fd):
            info = real_fstat(fd)

            class _Small:
                st_mode = info.st_mode
                st_size = 10
            return _Small()

        monkeypatch.setattr(pd.os, "fstat", _understate)
        found = pd.resolve("k", plan_dir)
        assert found.status == "ambiguous", "an oversized plan was parsed on a stale size"
        assert "grew past" in found.why, found.why


class TestAMalformedEntryIsSkippedAndSaidOutLoud:
    """One bad entry must not hide the good declarations beside it — or itself."""

    def test_a_malformed_entry_does_not_hide_its_neighbours(self, tmp_path: Path) -> None:
        body = '''
[[gate_decisions]]
notakey = "x"

[[gate_decisions]]
key = "runtime.base-image"
value = "ubuntu-24.04"
'''
        assert pd.resolve("runtime.base-image", _plan(tmp_path, body)).resolved

    def test_an_absence_beside_a_malformed_entry_says_so(self, tmp_path: Path) -> None:
        """Otherwise an author who wrote the decision and mistyped its shape is told the
        plan does not mention it, which reads as though they never wrote it."""
        body = '''
[[gate_decisions]]
notakey = "x"
'''
        found = pd.resolve("runtime.base-image", _plan(tmp_path, body))
        assert found.status == "absent", found
        assert "malformed" in found.why, found.why


class TestTheOutcomeSharesTheLedgersShape:
    """A second vocabulary would make a reader map between two to answer one question."""

    def test_the_four_frozen_field_names_match_the_ledger_field_for_field(self) -> None:
        from studio.utils import decision_log as dl  # noqa: PLC0415

        ruling = {f.name for f in dataclasses.fields(dl.GateRuling)}
        lookup = {f.name for f in dataclasses.fields(pd.PlanLookup)}
        frozen = {"decision_key", "value", "provenance", "status"}
        assert frozen <= ruling, sorted(ruling)
        assert frozen <= lookup, sorted(lookup)

    def test_every_status_this_returns_is_one_the_ledger_accepts(self, tmp_path: Path) -> None:
        """A status outside the ledger's closed set cannot be recorded, so it cannot be
        returned either — the two vocabularies are one vocabulary or the contract is not."""
        from studio.utils import decision_log as dl  # noqa: PLC0415

        seen = {
            pd.resolve("runtime.base-image", _plan(tmp_path, DIRECT)).status,
            pd.resolve("nope", _plan(tmp_path, DIRECT)).status,
            pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY), case="x").status,
        }
        assert seen == {"resolved", "absent", "ambiguous"}, seen
        assert seen <= set(dl.GATE_STATUSES), (seen, dl.GATE_STATUSES)

    def test_every_provenance_this_returns_is_one_the_ledger_accepts(
            self, tmp_path: Path) -> None:
        from studio.utils import decision_log as dl  # noqa: PLC0415

        seen = {
            pd.resolve("runtime.base-image", _plan(tmp_path, DIRECT)).provenance,
            pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY),
                       case="serious").provenance,
        }
        assert seen == {"plan", "policy"}, seen
        assert seen <= set(dl.GATE_PROVENANCE), (seen, dl.GATE_PROVENANCE)

    def test_an_unresolved_lookup_carries_the_ledgers_own_unspecified_literal(self) -> None:
        from studio.utils import decision_log as dl  # noqa: PLC0415

        assert pd.UNSPECIFIED == dl.UNSPECIFIED, (pd.UNSPECIFIED, dl.UNSPECIFIED)


class TestTheEvidenceIsBoundedLikeEverythingElseAuthorControlled:
    """`why` is a third sink for text from the plan and from the gate's own arguments."""

    def test_a_hostile_field_cannot_produce_an_unbounded_explanation(
            self, tmp_path: Path) -> None:
        """Found by walking the checklist, not by review.

        A 200,000-character dimension name produced a 200,097-character `why`. The record
        this lands in caps what it stores, but a caller logging the explanation directly
        had nothing between it and the plan file.
        """
        body = ('[[gate_decisions]]\nkey = "k"\ndimension = "' + "D" * 200_000
                + '"\n[gate_decisions.policy]\nrow = "v"\n')
        found = pd.resolve("k", _plan(tmp_path, body), case="missing")
        assert found.status == "ambiguous", found
        assert len(found.why) < 2_000, len(found.why)

    @pytest.mark.parametrize("supplier", ["key", "case"])
    def test_every_author_controlled_side_is_bounded_not_just_the_plans(
            self, tmp_path: Path, supplier: str) -> None:
        """The gate supplies two of these values and the plan supplies the rest.

        Capping the plan's side alone would leave the caller's, which is the shape of
        fix-the-reported-field-not-the-class.
        """
        huge = "x" * 200_000
        if supplier == "key":
            found = pd.resolve(huge, _plan(tmp_path, DIRECT))
        else:
            found = pd.resolve("review.follow-up-depth", _plan(tmp_path, POLICY), case=huge)
        assert found.status != "resolved", found
        assert len(found.why) < 2_000, (supplier, len(found.why))

    def test_every_outcome_is_built_through_the_one_bounded_constructor(self) -> None:
        """Bounding the finished string, not each value on its way in.

        The first guard here matched `{name!r}` and nothing else, so an exception's own
        text — `{exc}` — walked straight past it. Watching one spelling of one syntax only
        holds until someone writes the next interpolation. Asserting that every outcome is
        constructed in one place makes the property hold for the ones nobody has written.
        """
        tree = ast.parse(Path(pd.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name == "_lookup":
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "PlanLookup":
                    offenders.append(f"{node.name}:{call.lineno}")
        assert not offenders, (
            f"these build an outcome outside the bounded constructor, so their `why` is "
            f"whatever the plan said: {offenders}"
        )

    @pytest.mark.parametrize("field", ["why", "decision_key"])
    def test_the_constructor_bounds_its_fields_whatever_reached_it(self, field: str) -> None:
        """Asserted on the constructor, because no current caller can reach it unbounded.

        Every interpolation site caps its own values, so removing the cap here changes no
        observable behaviour today and a test driven through `resolve` cannot see it. That
        makes this the redundant half of a defence in depth — and the half that starts
        mattering the moment someone writes a `why` that does not go through `_said`,
        which is precisely how the last gap here appeared. Tested where the property is.
        """
        huge = "x" * 200_000
        found = pd._ambiguous(huge if field == "decision_key" else "k",
                              huge if field == "why" else "reason")
        assert len(getattr(found, field)) < 2_000, (field, len(getattr(found, field)))

    def test_an_exception_message_is_bounded_like_everything_else(
            self, tmp_path: Path) -> None:
        """The interpolation the first guard could not see."""
        plan_dir = _plan(tmp_path, "[[gate_decisions]\nkey = \"" + "L" * 200_000 + "\n")
        found = pd.resolve("k", plan_dir)
        assert found.status == "ambiguous", found
        assert len(found.why) < 2_000, len(found.why)


class TestAByteTheAuthorDidNotWriteNeverResolves:
    """Raised in review: `replace` turns an undecodable byte into a resolved value."""

    def test_a_plan_in_another_encoding_does_not_resolve_a_mangled_value(
            self, tmp_path: Path) -> None:
        """A latin-1 plan decoded with `replace` parsed cleanly and resolved `caf\ufffd-image`.

        That is this module proceeding on a value nobody wrote — the one thing it exists to
        refuse — reached through the decoder rather than through the matcher.
        """
        body = '[[gate_decisions]]\nkey = "runtime.base-image"\nvalue = "caf\xe9-image"\n'
        (tmp_path / pd.PLAN_FILE).write_bytes(body.encode("latin-1"))
        found = pd.resolve("runtime.base-image", tmp_path)
        assert found.status != "resolved", found
        assert "\ufffd" not in found.value, found.value
        assert "not valid UTF-8" in found.why, found.why

    def test_a_valid_utf8_plan_with_non_ascii_still_resolves(self, tmp_path: Path) -> None:
        """The other side of the boundary: strict decoding must not refuse legitimate text."""
        body = '[[gate_decisions]]\nkey = "runtime.base-image"\nvalue = "café-image"\n'
        (tmp_path / pd.PLAN_FILE).write_text(body, encoding="utf-8")
        found = pd.resolve("runtime.base-image", tmp_path)
        assert found.status == "resolved", found
        assert found.value == "café-image", found.value


class TestThisSectionDoesNotCollideWithTheOneAlreadyInThePlanFile:
    """A rename nothing guards is a rename someone undoes."""

    def test_the_section_is_not_the_key_ralphex_export_already_reads(self) -> None:
        """`plan.toml` already carries a `decisions` key, read as a table.

        `ralphex_export._resolve_lifecycle_action` does `decisions.get("lifecycle_action")`.
        An array of tables arrives there as a list, so naming this section `decisions` would
        raise `AttributeError` inside a shipped export command for any plan whose lifecycle
        is `manual`. Their name was there first; this one moved.
        """
        assert pd.DECISIONS_TABLE != "decisions", (
            "this section has taken the name of the table ralphex_export reads, which it "
            "will reach into with .get() and find a list"
        )

    def test_a_plan_carrying_both_sections_still_exports(self, tmp_path: Path) -> None:
        """The two coexist, asserted by running their reader over a plan that has both.

        Pinned against their code rather than against my memory of it: if the export
        reader changes shape, this fails here rather than in someone's plan.
        """
        from studio import ralphex_export as rx  # noqa: PLC0415
        import tomllib  # noqa: PLC0415

        body = f'''
[plan]
lifecycle = "manual"

[decisions]
lifecycle_action = "archive"

[[{pd.DECISIONS_TABLE}]]
key = "runtime.base-image"
value = "ubuntu-24.04"
'''
        manifest = tomllib.loads(body)
        assert rx._resolve_lifecycle_action(manifest) == "archive", "their reader broke"
        assert pd.resolve("runtime.base-image", _plan(tmp_path, body)).value == "ubuntu-24.04"


class TestWhatTheOutcomeTellsTheCallerAboutTheirOwnQuestion:
    """Raised in review: nothing asserted the returned key is the one that was asked."""

    @pytest.mark.parametrize("status", ["resolved", "absent", "ambiguous"])
    def test_the_returned_key_echoes_the_question_for_every_outcome(
            self, tmp_path: Path, status: str) -> None:
        """A caller matches an outcome to its question by this field.

        Asserted across all three outcomes rather than the happy one, since a caller reads
        it most when the answer did not come back.
        """
        body = {"resolved": DIRECT, "absent": '[plan]\ntask = "d"\n',
                "ambiguous": DIRECT + '[[gate_decisions]]\nkey = "runtime.base-image"\n'
                                      'value = "other"\n'}[status]
        found = pd.resolve("runtime.base-image", _plan(tmp_path, body))
        assert found.status == status, found
        assert found.decision_key == "runtime.base-image", found

    def test_a_key_past_the_text_cap_comes_back_truncated_and_that_is_stated(
            self, tmp_path: Path) -> None:
        """The exception to the echo, which a caller has to know about.

        Every field of an outcome is bounded; an unbounded key would be a sink for author
        text like any other. A key this size is hostile input rather than a real one.
        """
        found = pd.resolve("K" * 200_000, _plan(tmp_path, DIRECT))
        assert len(found.decision_key) < 2_000, len(found.decision_key)
        doc = pd.PlanLookup.__doc__ or ""
        fields = Path(pd.__file__).read_text(encoding="utf-8")
        assert "comes back truncated" in fields, \
            "the echo's one exception is no longer documented where the field is declared"


class TestTheGapsReviewFoundInTheseTests:
    """Each of these existed because a test asserted a claim it did not exercise."""

    def test_a_plan_of_exactly_the_size_bound_is_read(self, tmp_path: Path) -> None:
        """Only past-the-cap was covered, so `>` could become `>=` unnoticed.

        The same one-sided boundary review caught on the log's segment bound, in the file
        written after it.
        """
        body = '[[gate_decisions]]\nkey = "k"\nvalue = "v"\n'
        pad = pd._MAX_PLAN_BYTES - len(body.encode("utf-8")) - len("\n# ")
        plan_dir = _plan(tmp_path, body + "\n# " + "x" * pad)
        assert (tmp_path / pd.PLAN_FILE).stat().st_size == pd._MAX_PLAN_BYTES
        assert pd.resolve("k", plan_dir).resolved, "a plan exactly at the bound was refused"

    def test_an_oversized_plan_warns_as_well_as_refusing(
            self, tmp_path: Path, caplog) -> None:
        """It stops every gate that consults it, so it cannot be refused quietly."""
        plan_dir = _plan(tmp_path, "# " + "x" * (pd._MAX_PLAN_BYTES + 1))
        with caplog.at_level(logging.WARNING, logger=pd.logger.name):
            assert pd.resolve("k", plan_dir).status == "ambiguous"
        assert any("larger than any plan" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

    def test_a_case_is_ignored_by_a_direct_declaration(self, tmp_path: Path) -> None:
        """A direct answer does not depend on the dimension, so supplying one changes nothing.

        Untested, and the kind of thing that quietly starts mattering if the two resolution
        paths are ever merged.
        """
        plain = pd.resolve("runtime.base-image", _plan(tmp_path, DIRECT))
        with_case = pd.resolve("runtime.base-image", _plan(tmp_path, DIRECT), case="anything")
        assert plain == with_case, (plain, with_case)

    @pytest.mark.parametrize("declared", ["value = 42", "value = true", "value = 1.5",
                                          "value = [1, 2]", "value = 1979-05-27"])
    def test_a_non_string_declaration_does_not_resolve(
            self, tmp_path: Path, declared: str) -> None:
        """TOML carries integers, booleans, floats, arrays and dates; only text resolves.

        A gate consumes the value as text, so anything else is a declaration the plan made
        and this cannot honour — the plan spoke without deciding.
        """
        found = pd.resolve("k", _plan(tmp_path, f'[[gate_decisions]]\nkey = "k"\n{declared}\n'))
        assert found.status == "ambiguous", (declared, found)

    @pytest.mark.parametrize("row", ["serious = 42", "serious = true", "serious = [1]"])
    def test_a_non_string_policy_row_names_the_type_it_found(
            self, tmp_path: Path, row: str) -> None:
        """A generic 'not a value' left the author guessing which row and what was wrong."""
        body = f'[[gate_decisions]]\nkey = "k"\ndimension = "d"\n[gate_decisions.policy]\n{row}\n'
        found = pd.resolve("k", _plan(tmp_path, body), case="serious")
        assert found.status == "ambiguous", found
        assert "is a " in found.why, found.why

    def test_a_declaration_with_neither_a_value_nor_a_policy_is_ambiguous(
            self, tmp_path: Path) -> None:
        """A key on its own: the plan named the decision and then said nothing about it.

        Entirely untested, and it is the shape a half-written declaration takes.
        """
        found = pd.resolve("k", _plan(tmp_path, '[[gate_decisions]]\nkey = "k"\n'))
        assert found.status == "ambiguous", found

    def test_a_dimension_with_no_policy_table_says_so_specifically(
            self, tmp_path: Path) -> None:
        """Reported as 'declared with no rows' when there was no table at all."""
        body = '[[gate_decisions]]\nkey = "k"\ndimension = "d"\n'
        found = pd.resolve("k", _plan(tmp_path, body), case="x")
        assert found.status == "ambiguous", found
        assert "no policy table at all" in found.why, found.why

    def test_a_failed_read_carries_what_an_operator_diagnoses_from(
            self, tmp_path: Path) -> None:
        """`OSError` alone says neither which errno nor what the system reported."""
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            pytest.skip("needs a non-root uid for mode bits to gate the read")
        plan_dir = _plan(tmp_path, DIRECT)
        (tmp_path / pd.PLAN_FILE).chmod(0o000)
        try:
            found = pd.resolve("k", plan_dir)
        finally:
            (tmp_path / pd.PLAN_FILE).chmod(0o644)
        assert found.status == "ambiguous", found
        assert "errno" in found.why, found.why

    def test_malformed_entries_are_warned_about_not_only_mentioned(
            self, tmp_path: Path, caplog) -> None:
        """They appeared in one lookup's explanation and nowhere an operator watches."""
        body = '[[gate_decisions]]\nnotakey = "x"\n'
        with caplog.at_level(logging.WARNING, logger=pd.logger.name):
            pd.resolve("k", _plan(tmp_path, body))
        assert any("malformed" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]


class TestAPathThatIsNotAPlanCannotStopAGate:
    """The Critical, and the two Majors that misreport a broken plan as a silent one."""

    def test_a_fifo_named_plan_toml_does_not_hang_the_lookup(self, tmp_path: Path) -> None:
        """A FIFO reports `st_size == 0`, passing any size guard, and blocks on open.

        No exception, no timeout, no return — the gate simply never comes back. The
        module's own claim, that a file in the task directory which is not a plan would
        otherwise stall every gate, was not upheld for this one.

        Run on a thread with a bounded join, because a test for "this does not hang" that
        hangs stops the suite instead of failing it — a worse signal than a red one, and
        indistinguishable from CI being broken.
        """
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX-only: no FIFOs here")
        os.mkfifo(tmp_path / pd.PLAN_FILE)
        out: list = []
        worker = threading.Thread(target=lambda: out.append(pd.resolve("k", tmp_path)),
                                  daemon=True)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive(), "resolve() blocked on a FIFO — the gate cannot return"
        assert out[0].status == "ambiguous", out[0]
        assert "not a regular file" in out[0].why, out[0].why

    def test_a_directory_named_plan_toml_is_refused_not_parsed(self, tmp_path: Path) -> None:
        """The same check, reached by the case someone is far likelier to create by hand."""
        (tmp_path / pd.PLAN_FILE).mkdir()
        found = pd.resolve("k", tmp_path)
        assert found.status == "ambiguous", found

    def test_a_dangling_symlink_is_a_broken_plan_not_a_missing_one(
            self, tmp_path: Path) -> None:
        """Something is sitting at that path, so the plan is not silent — it is unreadable.

        `Path.stat` follows the link and raises the same error as nothing-at-all, so the
        two were indistinguishable and both read as silence.
        """
        os.symlink(tmp_path / "nowhere-at-all", tmp_path / pd.PLAN_FILE)
        found = pd.resolve("k", tmp_path)
        assert found.status == "ambiguous", found
        assert "symlink" in found.why, found.why

    def test_a_genuinely_missing_plan_is_still_silence(self, tmp_path: Path) -> None:
        """The other side of that boundary, so the fix cannot swallow the ordinary case."""
        assert pd.resolve("k", tmp_path).status == "absent"

    @pytest.mark.parametrize("section", ['gate_decisions = "oops"', "gate_decisions = 42",
                                         "gate_decisions = {}",
                                         "[gate_decisions]\nkey = \"k\""])
    def test_a_section_that_is_not_an_array_is_a_plan_that_spoke(
            self, tmp_path: Path, section: str) -> None:
        """It mentions decisions and declares none, which is not the plan being silent.

        Reporting it as `absent` tells an author their plan says nothing about a key they
        can see written in it.

        The section is written **before** `[plan]`, not after. A bare key following a table
        header belongs to that table, so `[plan]` then `gate_decisions = "oops"` nests it
        inside `[plan]` and never reaches the top level at all — the first version of this
        test asserted against a plan that did not contain the case, and the report it came
        from has the same slip.
        """
        found = pd.resolve("k", _plan(tmp_path, f'{section}\n\n[plan]\ntask = "d"\n'))
        assert found.status == "ambiguous", (section, found)

    def test_the_section_nested_under_plan_is_not_the_top_level_one(
            self, tmp_path: Path) -> None:
        """Guards the fixture above: `[plan].gate_decisions` is a different key entirely.

        Without this, rewriting the fixture back to the nested form would make the
        parametrized cases pass for the wrong reason — the plan having no top-level section
        rather than the section being unusable.
        """
        body = '[plan]\ntask = "d"\ngate_decisions = "oops"\n'
        found = pd.resolve("k", _plan(tmp_path, body))
        assert found.status == "absent", (
            "a key nested under [plan] is not the top-level section, so this plan really "
            f"is silent about decisions: {found}")

    def test_the_silence_verdict_is_carried_not_inferred_from_the_wording(self) -> None:
        """The contract's most important distinction must not rest on a prose prefix.

        A rephrase of the not-found message used to reclassify every task without a plan.
        One test did catch that exact rewording — but a test catching one rephrase is not
        the same as routing that cannot drift, which is what review was pointing at.
        """
        src = Path(pd.__file__).read_text(encoding="utf-8")
        assert 'startswith("the task has no' not in src, \
            "the absent/ambiguous routing is reading the reason's wording again"
        assert "verdict == SILENCE" in src, "the typed verdict is no longer what routes"


class TestThePreflightSaysWhatWillStopBeforeAnythingStarts:
    """The reason a phase declares its decisions rather than discovering them."""

    PLAN = '''
[[phases]]
number = 1
needs = ["runtime.base-image"]

[[phases]]
number = 3
needs = ["db.engine"]

[[phases]]
number = 4
needs = ["db.engine", "runtime.base-image"]

[[phases]]
number = 5

[[gate_decisions]]
key = "runtime.base-image"
value = "ubuntu-24.04"
'''

    def test_one_missing_answer_names_every_phase_it_blocks(self, tmp_path: Path) -> None:
        """The whole point: the blast radius stated once, not discovered phase by phase.

        Without this, the author supplies `db.engine` when phase 3 stops, and phase 4 stops
        on the same key — the same interruption served once per phase.
        """
        outlooks = {o.phase: o for o in pd.preflight(_plan(tmp_path, self.PLAN))}
        blocked = sorted(p for p, o in outlooks.items() if not o.will_run)
        assert blocked == ["3", "4"], {p: o.blocked_on for p, o in outlooks.items()}
        assert outlooks["3"].blocked_on == (("db.engine", "absent"),), outlooks["3"]

    def test_a_phase_whose_decisions_are_answered_is_reported_as_running(
            self, tmp_path: Path) -> None:
        outlooks = {o.phase: o for o in pd.preflight(_plan(tmp_path, self.PLAN))}
        assert outlooks["1"].will_run, outlooks["1"]

    def test_a_phase_declaring_nothing_is_reported_as_running(self, tmp_path: Path) -> None:
        """What makes the declaration safe to adopt one phase at a time.

        An undeclared phase behaves exactly as it would without this feature — it stops when
        it reaches the question rather than before. Reporting it as blocked would punish
        every plan written before the field existed.
        """
        outlooks = {o.phase: o for o in pd.preflight(_plan(tmp_path, self.PLAN))}
        assert outlooks["5"].will_run, outlooks["5"]

    def test_the_status_that_stops_a_phase_is_carried_not_just_the_fact(
            self, tmp_path: Path) -> None:
        """A key the plan never mentions and one it half-answers are different problems."""
        body = '''
[[phases]]
number = 1
needs = ["silent", "half-answered"]

[[gate_decisions]]
key = "half-answered"
'''
        blocked = dict(pd.preflight(_plan(tmp_path, body))[0].blocked_on)
        assert blocked["silent"] == "absent", blocked
        assert blocked["half-answered"] == "ambiguous", blocked

    def test_a_key_the_plan_answers_by_rule_is_not_forecast_as_blocking(
            self, tmp_path: Path) -> None:
        """The forecast runs before any gate, so it holds no value for the dimension.

        Asking without one is `ambiguous` — correctly, for a gate that really did ask that
        way. But a gate *will* supply it, so reporting the phase as blocked sends an author
        to answer a key their plan already answers, in the one field whose whole job is to
        be believed. Raised in review.
        """
        body = '''
[[phases]]
number = 1
needs = ["follow-up.depth"]

[[gate_decisions]]
key = "follow-up.depth"
dimension = "classification"
[gate_decisions.policy]
minor = "none"
'''
        outlook = pd.preflight(_plan(tmp_path, body))[0]
        assert outlook.blocked_on == (), outlook
        assert outlook.will_run, outlook
        # And the lookup itself is unchanged: the frozen contract still has three
        # statuses, and a gate that asks with no case still fails to resolve.
        found = pd.resolve("follow-up.depth", _plan(tmp_path, body))
        assert (found.status, found.awaits_case) == ("ambiguous", True), found
        answered = pd.resolve("follow-up.depth", _plan(tmp_path, body), case="minor")
        assert (answered.value, answered.awaits_case) == ("none", False), answered

    def test_a_plan_that_is_genuinely_broken_still_forecasts_as_blocking(
            self, tmp_path: Path) -> None:
        """The other side of that exclusion, or it would hide every policy fault.

        A policy declared without naming the dimension it is keyed on cannot be answered
        by any case, so no gate will resolve it and the forecast must say so.
        """
        body = '''
[[phases]]
number = 1
needs = ["follow-up.depth"]

[[gate_decisions]]
key = "follow-up.depth"
[gate_decisions.policy]
minor = "none"
'''
        outlook = pd.preflight(_plan(tmp_path, body))[0]
        assert outlook.blocked_on == (("follow-up.depth", "ambiguous"),), outlook

    def test_it_warns_and_never_decides(self, tmp_path: Path) -> None:
        """`preflight` reports; it does not gate — asserted as behaviour, not as prose.

        A reader could take `will_run` for permission. It is not: nothing here consults it
        before dispatch, and a phase reported as running can still stop the moment a gate
        inside it asks something no phase declared.

        The first version of this matched a docstring substring through
        `inspect.getsource`, which review correctly called out: adding enforcement while
        leaving the sentence in place would have passed. So this exercises the call and
        checks what it did — every phase is reported including the blocked ones, the plan
        on disk is untouched, and nothing raises.
        """
        plan_dir = _plan(tmp_path, self.PLAN)
        before = (plan_dir / pd.PLAN_FILE).read_bytes()
        outlooks = pd.preflight(plan_dir)
        # Reported, not withheld: a blocked phase still appears, because this describes
        # what every phase will find rather than deciding which may run.
        assert sorted(o.phase for o in outlooks) == ["1", "3", "4", "5"], outlooks
        assert any(not o.will_run for o in outlooks), "nothing was reported as blocked"
        assert (plan_dir / pd.PLAN_FILE).read_bytes() == before, \
            "preflight wrote to the plan; it is a forecast and must not"

    def test_a_plan_that_cannot_be_read_is_not_reported_as_nothing_to_stop(
            self, tmp_path: Path, caplog) -> None:
        """An empty forecast for a broken plan is this module's own failure, one level up.

        "No phase will stop" and "this plan could not be read" were the same answer —
        an empty list — which is exactly the silence-versus-defect distinction the rest of
        the module implements deliberately. Raised in review.

        A task with no plan.toml is silence and stays quiet: there is legitimately nothing
        to forecast. A plan that exists and will not parse is a defect and says so.
        """
        import logging  # noqa: PLC0415

        broken = tmp_path / "broken"
        broken.mkdir()
        (broken / pd.PLAN_FILE).write_text("[[phases]\nnumber = ", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger=pd.logger.name):
            assert pd.preflight(broken) == []
        assert any("unreadable rather than" in r.getMessage() for r in caplog.records), \
            [r.getMessage() for r in caplog.records]

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=pd.logger.name):
            assert pd.preflight(tmp_path / "no-plan-here") == []
        assert not caplog.records, [r.getMessage() for r in caplog.records]

    @pytest.mark.parametrize("malformed", [
        'needs = "runtime.base-image"',     # a string where a list belongs
        'needs = [1, 2]',                   # non-string members
        'needs = []',                       # declared empty
    ])
    def test_a_malformed_declaration_costs_the_warning_never_the_safety(
            self, tmp_path: Path, malformed: str) -> None:
        """The worst case is the warning nobody got, not work proceeding on an unknown answer.

        Whatever a phase declares, the gate inside it still asks when it reaches a question
        the plan does not answer. So a malformed `needs` degrades to the behaviour of not
        declaring one at all.
        """
        body = f"[[phases]]\nnumber = 1\n{malformed}\n"
        outlooks = pd.preflight(_plan(tmp_path, body))
        assert len(outlooks) == 1, outlooks
        assert outlooks[0].will_run, outlooks[0]

    def test_a_plan_with_no_phases_reports_nothing_rather_than_raising(
            self, tmp_path: Path) -> None:
        assert pd.preflight(_plan(tmp_path, DIRECT)) == []

    def test_a_missing_plan_reports_nothing_rather_than_raising(self, tmp_path: Path) -> None:
        assert pd.preflight(tmp_path) == []

    def test_the_phase_label_is_bounded_like_every_other_field(self, tmp_path: Path) -> None:
        """A phase number is author-controlled text like any other."""
        body = f'[[phases]]\nnumber = "{"9" * 200_000}"\nneeds = ["k"]\n'
        assert len(pd.preflight(_plan(tmp_path, body))[0].phase) < 2_000

    def test_an_outlook_cannot_be_edited_after_it_is_handed_over(
            self, tmp_path: Path) -> None:
        """`frozen=True` stops reassignment and nothing else.

        `blocked_on` held a plain list, so a caller could append to a forecast it was
        handed and the next reader would see keys the plan never blocked on. Raised in
        review; it is a tuple now.
        """
        outlook = pd.preflight(_plan(tmp_path, self.PLAN))[0]
        # The *value*, not the annotation: reverting the type hint alone changes nothing
        # at runtime, so a test that only read the hint would pass on a mutable list.
        assert isinstance(outlook.blocked_on, tuple), type(outlook.blocked_on)
        assert not isinstance(outlook.blocked_on, list), type(outlook.blocked_on)
        with pytest.raises(AttributeError):
            outlook.blocked_on = ()          # type: ignore[misc]
        with pytest.raises(AttributeError):
            outlook.blocked_on.append(("x", "absent"))   # type: ignore[attr-defined]

    def test_a_plan_cannot_forge_a_line_in_the_held_phase_notice(
            self, tmp_path: Path) -> None:
        """A bound is not a sanitiser, and both fields land in a notice a person reads.

        A phase numbered `"1\\nARMED: yes — every phase dispatched"` rendered a second
        line saying the opposite of the truth, and a decision key carrying an ANSI escape
        recoloured the terminal around it. Raised in review; fourth appearance of this
        forgery across three modules, so it is fixed at the helper every stored field
        passes through rather than at the field that was noticed.
        """
        body = ('[[phases]]\n'
                'number = "1\\nARMED: yes — every phase dispatched"\n'
                'needs = ["k\\u001b[31m.evil"]\n')
        outlook = pd.preflight(_plan(tmp_path, body))[0]
        assert "\n" not in outlook.phase, repr(outlook.phase)
        assert len(outlook.phase.splitlines()) == 1, repr(outlook.phase)
        key = outlook.blocked_on[0][0]
        assert "\x1b" not in key, repr(key)
        assert all(ch.isprintable() or ch == " " for ch in key), repr(key)

    def test_the_bound_fires_at_the_length_it_says(self, tmp_path: Path) -> None:
        """Where the cap fires, not merely that one exists.

        The tests around this use 200,000-character values and assert a ceiling, which
        passes for any cap at or below the real one — an off-by-one in the shared helper,
        or the constant moved by one, leaves them green. Raised in review on the sibling
        module the same day, so it is the class rather than the instance: the three
        lengths that matter are named here against literals.
        """
        cap = 500
        assert pd._bounded("k" * (cap - 1)) == "k" * (cap - 1)
        # The last length that survives whole, and the first that does not.
        assert pd._bounded("k" * cap) == "k" * cap
        over = pd._bounded("k" * (cap + 1))
        assert over != "k" * (cap + 1), "one character over the cap was not truncated"
        assert len(over) <= cap, len(over)

    def test_the_declaration_keys_are_the_names_the_checklist_documents(self) -> None:
        """Pinned to literals, because every fixture above is written in the plan's own syntax.

        The TOML in these tests spells `needs` and `[[phases]]` directly, so renaming the
        constants would fail them — for the right reason but with a confusing message. This
        says which name changed. It is the same guard the `gate_decisions` rename earned,
        applied to the two fields this increment reads rather than only the one it added.
        """
        assert pd.PHASE_NEEDS == "needs", pd.PHASE_NEEDS
        assert pd.PHASES_TABLE == "phases", pd.PHASES_TABLE

    @pytest.mark.parametrize("field", ["phase label", "blocked key"])
    def test_every_field_of_an_outlook_is_bounded_not_just_the_label(
            self, tmp_path: Path, field: str) -> None:
        """Both sides, because bounding one of two adjacent fields is the recurring miss.

        The phase label was bounded and the keys beside it were not, so a 200,000-character
        `needs` entry landed in the outlook whole. Same shape as the marker that kept three
        caller-supplied fields uncapped, found in review one change earlier.
        """
        huge = "K" * 200_000
        if field == "phase label":
            body = f'[[phases]]\nnumber = "{huge}"\nneeds = ["k"]\n'
            measured = pd.preflight(_plan(tmp_path, body))[0].phase
        else:
            body = f'[[phases]]\nnumber = 1\nneeds = ["{huge}"]\n'
            measured = pd.preflight(_plan(tmp_path, body))[0].blocked_on[0][0]
        assert len(measured) < 2_000, (field, len(measured))
