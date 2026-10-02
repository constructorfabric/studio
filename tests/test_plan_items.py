"""Tests for enumerating a plan's deliverable items from phase-file acceptance criteria.

The reader's contract: items come out in phase-then-authoring order; a `[x]` is the author's
claim and never a verdict; every item is `explicit` in v1; and a plan or phase file that will
not read is a reported gap, never a silent empty list or a crash.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/studio/scripts"))

from studio.utils import plan_items as pi  # noqa: E402


def _plan(tmp_path: Path, manifest: str, phase_files: dict[str, str]) -> Path:
    """Write a plan.toml plus its phase files and return the plan directory."""
    (tmp_path / pi.PLAN_FILE).write_text(manifest, encoding="utf-8")
    for name, body in phase_files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


_TWO_PHASE_MANIFEST = """\
[plan]
task = "demo"
total_phases = 2
[[phases]]
number = 1
file = "phase-1.md"
[[phases]]
number = 2
file = "phase-2.md"
"""

_PHASE_1 = """\
# Phase 1

## What
Produce the first artifact.

## Acceptance Criteria
- [ ] PRD file exists
- [x] User reviewed actor list
- [ ] No unresolved `{...}` variables outside code fences

## Output Format
Use the required completion report.
"""

_PHASE_2 = """\
# Phase 2

## Acceptance Criteria
* [X] Second artifact exists
* [ ] Line count within budget
"""


def test_reads_items_in_phase_then_authoring_order(tmp_path: Path) -> None:
    result = pi.read_plan_items(
        _plan(tmp_path, _TWO_PHASE_MANIFEST, {"phase-1.md": _PHASE_1, "phase-2.md": _PHASE_2})
    )
    assert result.error is None
    assert result.read_problems == []
    assert [(i.phase, i.ordinal, i.text, i.authored_done) for i in result.items] == [
        (1, 0, "PRD file exists", False),
        (1, 1, "User reviewed actor list", True),
        (1, 2, "No unresolved `{...}` variables outside code fences", False),
        (2, 0, "Second artifact exists", True),
        (2, 1, "Line count within budget", False),
    ]
    assert all(i.verify_kind == pi.VERIFY_EXPLICIT for i in result.items)


def test_authored_checkbox_is_a_claim_not_a_verdict(tmp_path: Path) -> None:
    # A `[x]` sets authored_done but never promotes the item past `explicit` -- the reader
    # records the claim; verification (a later increment) decides if it is true.
    result = pi.read_plan_items(
        _plan(tmp_path, _TWO_PHASE_MANIFEST, {"phase-1.md": _PHASE_1, "phase-2.md": _PHASE_2})
    )
    done = [i for i in result.items if i.authored_done]
    assert done
    assert all(i.verify_kind == pi.VERIFY_EXPLICIT for i in done)


@pytest.mark.parametrize(
    "line, expected_done",
    [
        ("- [ ] open", False),
        ("- [x] lower", True),
        ("- [X] upper", True),
        ("* [ ] star bullet", False),
        ("  - [x] indented", True),
    ],
)
def test_checkbox_variants_are_recognised(tmp_path: Path, line: str, expected_done: bool) -> None:
    body = f"## Acceptance Criteria\n{line}\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert len(result.items) == 1
    assert result.items[0].authored_done is expected_done


def test_checkboxes_outside_the_criteria_section_are_ignored(tmp_path: Path) -> None:
    # A checkbox under a different `##` heading is not a deliverable item; the section both
    # opens on the right heading and CLOSES on the next one. Reverting either breaks this.
    body = (
        "## Acceptance Criteria\n"
        "- [ ] real criterion\n"
        "## Rules\n"
        "- [x] not a criterion\n"
    )
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert [i.text for i in result.items] == ["real criterion"]


def test_a_phase_with_no_criteria_is_surfaced_not_invented(tmp_path: Path) -> None:
    body = "# Phase 1\n## What\nNothing to check here.\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert result.items == []
    assert result.phases_without_criteria == [1]
    assert result.error is None


def test_missing_plan_is_an_error_not_a_crash(tmp_path: Path) -> None:
    result = pi.read_plan_items(tmp_path)  # no plan.toml written
    assert result.items == []
    assert result.error  # a non-empty reason, never a silent empty list


def test_a_malformed_phases_table_is_an_error(tmp_path: Path) -> None:
    # `phases` must be top-level, not nested under `[plan]`, to be the array the reader walks;
    # a top-level `phases = "oops"` is the author declaring the table and getting it wrong.
    (tmp_path / pi.PLAN_FILE).write_text('phases = "oops"\n[plan]\ntask = "t"\n', encoding="utf-8")
    result = pi.read_plan_items(tmp_path)
    assert result.items == []
    assert result.error is not None
    assert "phases" in result.error


def test_an_unreadable_phase_file_is_a_problem_but_other_phases_still_read(tmp_path: Path) -> None:
    # phase-1 points at a file that does not exist; phase-2 is fine and still contributes.
    result = pi.read_plan_items(
        _plan(tmp_path, _TWO_PHASE_MANIFEST, {"phase-2.md": _PHASE_2})  # no phase-1.md
    )
    assert [i.text for i in result.items] == ["Second artifact exists", "Line count within budget"]
    assert any("phase 1" in p for p in result.read_problems)
    assert result.error is None


def test_a_phase_path_escaping_the_plan_dir_is_refused(tmp_path: Path) -> None:
    secret = tmp_path / "secret.md"
    secret.write_text("## Acceptance Criteria\n- [ ] LEAKED\n", encoding="utf-8")
    plan_dir = tmp_path / "plan"
    plan_dir.mkdir()
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="../secret.md"\n'
    (plan_dir / pi.PLAN_FILE).write_text(manifest, encoding="utf-8")
    result = pi.read_plan_items(plan_dir)
    assert result.items == []  # the escaping file is NOT read
    assert "LEAKED" not in " ".join(i.text for i in result.items)
    assert any("escapes" in p for p in result.read_problems)


def test_long_criterion_text_is_bounded(tmp_path: Path) -> None:
    body = "## Acceptance Criteria\n- [ ] " + ("A" * 5000) + "\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert len(result.items) == 1
    assert 0 < len(result.items[0].text) <= 500  # the shared _bounded cap


def test_a_non_utf8_phase_file_is_a_problem_not_a_crash(tmp_path: Path) -> None:
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    (tmp_path / pi.PLAN_FILE).write_text(manifest, encoding="utf-8")
    (tmp_path / "p.md").write_bytes(b"## Acceptance Criteria\n- [ ] \xff\xfe not utf8\n")
    result = pi.read_plan_items(tmp_path)
    assert result.items == []
    assert any("UTF-8" in p for p in result.read_problems)


def test_more_than_the_cap_criteria_truncates_with_a_note(tmp_path: Path) -> None:
    lines = "\n".join(f"- [ ] item {n}" for n in range(pi.MAX_ITEMS_PER_PHASE + 25))
    body = f"## Acceptance Criteria\n{lines}\n"
    manifest = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {"p.md": body}))
    assert len(result.items) == pi.MAX_ITEMS_PER_PHASE
    assert any("more than" in p for p in result.read_problems)


def test_exactly_the_cap_is_not_truncated(tmp_path: Path) -> None:
    # The exact boundary: cap items is not truncation (no off-by-one note).
    lines = "\n".join(f"- [ ] item {n}" for n in range(pi.MAX_ITEMS_PER_PHASE))
    result = _one_phase(tmp_path, lines)
    assert len(result.items) == pi.MAX_ITEMS_PER_PHASE
    assert not any("more than" in p for p in result.read_problems)


def test_one_over_the_cap_truncates_exactly_one(tmp_path: Path) -> None:
    # The other side of the boundary: cap+1 drops exactly the one over, with the note.
    lines = "\n".join(f"- [ ] item {n}" for n in range(pi.MAX_ITEMS_PER_PHASE + 1))
    result = _one_phase(tmp_path, lines)
    assert len(result.items) == pi.MAX_ITEMS_PER_PHASE
    assert any("more than" in p for p in result.read_problems)


_ONE_PHASE_MANIFEST = '[plan]\ntask="t"\n[[phases]]\nnumber=1\nfile="p.md"\n'


def _one_phase(tmp_path: Path, criteria: str) -> pi.PlanItems:
    body = f"## Acceptance Criteria\n{criteria}\n"
    return pi.read_plan_items(_plan(tmp_path, _ONE_PHASE_MANIFEST, {"p.md": body}))


def test_a_needs_marker_declares_the_dependency_keeping_the_full_text(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs: pricing_model)")
    assert result.read_problems == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.depends_on_question == "pricing_model"
    # the marker is NOT stripped: the text is the full criterion, so two criteria differing
    # only by their marker keep distinct identities
    assert item.text == "PRD approved (needs: pricing_model)"


def test_two_criteria_differing_only_by_marker_stay_distinct(tmp_path: Path) -> None:
    # The feature's own differentiator must not collapse two deliverables to one verdict
    # identity: same base wording, different dependency, must remain two distinct items.
    result = _one_phase(
        tmp_path,
        "- [ ] Deploy (needs: staging_ok)\n- [ ] Deploy (needs: prod_ok)")
    assert [i.text for i in result.items] == [
        "Deploy (needs: staging_ok)", "Deploy (needs: prod_ok)"]
    assert [i.depends_on_question for i in result.items] == ["staging_ok", "prod_ok"]
    assert len({i.text for i in result.items}) == 2  # distinct verdict identities


def test_no_marker_means_no_dependency(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] PRD approved")
    assert result.items[0].depends_on_question is None


def test_a_checked_criterion_with_a_marker_keeps_both(tmp_path: Path) -> None:
    # Checkbox parsing and marker parsing are independent: a `[x]` criterion still carries its
    # dependency (guards against a regression that couples the two).
    result = _one_phase(tmp_path, "- [x] PRD approved (needs: pricing_model)")
    item = result.items[0]
    assert item.authored_done is True
    assert item.depends_on_question == "pricing_model"


def test_a_malformed_needs_key_is_reported_and_not_applied(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs: Pricing-Model)")
    item = result.items[0]
    assert item.depends_on_question is None          # the bad key is not applied
    assert any("needs" in p and "criterion 1" in p for p in result.read_problems)


def test_the_reserved_unspecified_key_is_rejected(tmp_path: Path) -> None:
    # `(needs: unspecified)` is syntactically valid but the register treats "unspecified" as
    # "no key", so it could never block: reject it loudly rather than apply it silently.
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs: unspecified)")
    assert result.items[0].depends_on_question is None
    assert any("reserved" in p for p in result.read_problems)


def test_a_key_the_log_cannot_store_unchanged_is_rejected(tmp_path: Path) -> None:
    # The grammar has no length limit but the decision log caps `decision_key` at 500 chars. A
    # longer valid key would be recorded truncated, so an answering event could never match it and
    # the item would stay blocked with no further diagnostic. Reject-and-report, like the other
    # unusable keys — not a silent partial application.
    long_key = "a" * 501  # grammar-valid, but one over the log's field cap
    result = _one_phase(tmp_path, f"- [ ] Ship it (needs: {long_key})")
    assert result.items[0].depends_on_question is None
    assert any("longer than the decision log" in p for p in result.read_problems)


def test_a_marker_with_trailing_punctuation_is_still_honoured(tmp_path: Path) -> None:
    # A marker that ends a sentence ("...(needs: k).") must still be read — not silently ignored,
    # which would let the item complete with its declared dependency unchecked.
    for text in ("- [ ] PRD approved (needs: pricing_model).",
                 "- [ ] PRD approved (needs: pricing_model)!",
                 "- [ ] PRD approved (needs: pricing_model) ;"):
        result = _one_phase(tmp_path, text)
        assert result.read_problems == []
        assert result.items[0].depends_on_question == "pricing_model", text


def test_a_needs_like_group_mid_sentence_is_still_left_alone(tmp_path: Path) -> None:
    # Allowing trailing punctuation must not start matching a marker that is not trailing.
    result = _one_phase(tmp_path, "- [ ] Document what the API (needs: auth) exposes and ships")
    assert result.items[0].depends_on_question is None
    # A closed group followed by real words is prose, not a broken marker: no diagnostic.
    assert result.read_problems == []


def test_a_trailing_marker_missing_its_colon_is_reported(tmp_path: Path) -> None:
    # A typo'd marker (missing colon) must NOT silently collapse to "no dependency" — the author
    # meant to gate the item, so the broken shape is reported, not read as "waits on nothing".
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs pricing_model)")
    assert result.items[0].depends_on_question is None
    assert any("malformed" in p for p in result.read_problems)


def test_a_trailing_marker_missing_its_closing_paren_is_reported(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs: pricing_model")
    assert result.items[0].depends_on_question is None
    assert any("malformed" in p for p in result.read_problems)


def test_a_trailing_marker_with_an_extra_paren_is_reported(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs: pricing_model))")
    assert result.items[0].depends_on_question is None
    assert any("malformed" in p for p in result.read_problems)


def test_a_needs_like_word_is_not_treated_as_a_broken_marker(tmp_path: Path) -> None:
    # "(needsfoo)" is a different word, not a typo'd marker — no false diagnostic.
    result = _one_phase(tmp_path, "- [ ] Ship the (needsfoo) module")
    assert result.items[0].depends_on_question is None
    assert result.read_problems == []


def test_a_long_criterion_keeps_its_dependency_past_the_text_bound(tmp_path: Path) -> None:
    # `_extract_needs` runs on the FULL text, but `PlanItem.text` is capped at 500 chars. A
    # criterion longer than the cap whose marker sits past it must still yield the right
    # dependency key (the part that actually blocks), even though the stored text is truncated.
    pad = "x" * 520  # the base text alone exceeds the 500-char store cap
    result = _one_phase(tmp_path, f"- [ ] {pad} (needs: pricing_model)")
    item = result.items[0]
    assert result.read_problems == []
    assert item.depends_on_question == "pricing_model"   # key survives the bound
    assert len(item.text) <= 500                          # stored text is capped
    assert item.text.endswith("…[truncated]")             # and marked as truncated
    assert "(needs: pricing_model)" not in item.text      # the marker fell outside the cap


def test_two_long_criteria_collide_in_text_but_keep_distinct_keys(tmp_path: Path) -> None:
    # The disclosed boundary consequence (/047): two criteria identical up to the cap but
    # differing only in a trailing marker store the SAME truncated text, so `(phase, text)`
    # collapses — yet their dependency keys stay distinct, which is the identity that blocks.
    # Pin it so a future refactor at the 500-char boundary cannot change it unnoticed.
    pad = "x" * 520
    result = _one_phase(
        tmp_path, f"- [ ] {pad} (needs: staging_ok)\n- [ ] {pad} (needs: prod_ok)")
    assert len({i.text for i in result.items}) == 1                       # texts collide past the cap
    assert [i.depends_on_question for i in result.items] == ["staging_ok", "prod_ok"]  # keys do not


def test_a_second_earlier_marker_is_reported(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] Ship it (needs: a) (needs: b)")
    assert result.items[0].depends_on_question is None  # not a silent partial application
    assert any("more than one" in p for p in result.read_problems)


def test_an_empty_needs_key_is_reported(tmp_path: Path) -> None:
    result = _one_phase(tmp_path, "- [ ] PRD approved (needs: )")
    assert result.items[0].depends_on_question is None
    assert any("needs" in p for p in result.read_problems)


def test_needs_like_text_mid_criterion_is_left_alone(tmp_path: Path) -> None:
    # Only a *trailing* marker is a dependency; `(needs: …)` mid-sentence is plain prose.
    result = _one_phase(tmp_path, "- [ ] Document what the API (needs: auth) exposes")
    item = result.items[0]
    assert item.depends_on_question is None
    assert item.text == "Document what the API (needs: auth) exposes"
    assert result.read_problems == []


def test_a_non_table_phase_entry_is_skipped_with_a_note(tmp_path: Path) -> None:
    manifest = 'phases = ["not-a-table"]\n[plan]\ntask = "t"\n'  # top-level phases, non-table entry
    result = pi.read_plan_items(_plan(tmp_path, manifest, {}))
    assert result.items == []
    assert any("not a table" in p for p in result.read_problems)


def test_a_phase_declaring_no_file_is_a_note(tmp_path: Path) -> None:
    manifest = '[plan]\ntask = "t"\n[[phases]]\nnumber = 1\n'
    result = pi.read_plan_items(_plan(tmp_path, manifest, {}))
    assert result.items == []
    assert any("no `file`" in p for p in result.read_problems)
