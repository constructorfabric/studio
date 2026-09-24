"""Declarative section order: the rescue pass, `order`, and the relaxable rules.

The matcher enforced an order no kit could state and no kit could relax: a
section written earlier than the kit declares it simply failed to match and was
reported as absent. These tests pin the two halves of the fix separately —
that a present-but-displaced section is *found* (the rescue pass, which runs
for every kit), and that it is *reported* only where a kit declared an order —
because a single end-to-end assertion cannot tell one from the other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils import constraints as C  # noqa: E402
from studio.utils import error_codes as EC  # noqa: E402
from studio.utils import severity as S  # noqa: E402
from studio.utils import toml_utils  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(tmp_path: Path, body: str, name: str = "artifact.md") -> Path:
    path = tmp_path / name
    path.write_text(body.lstrip(), encoding="utf-8")
    return path


def _heading(pattern: str, heading_id: str, **kwargs) -> C.HeadingConstraint:
    return C.HeadingConstraint(
        level=kwargs.pop("level", 2),
        pattern=pattern,
        id=heading_id,
        **kwargs,
    )


def _kind(headings, order=None, **kwargs) -> C.ArtifactKindConstraints:
    return C.ArtifactKindConstraints(
        name=None,
        description=None,
        defined_id=[],
        headings=list(headings),
        order=order,
        **kwargs,
    )


def _report(path: Path, constraints: C.ArtifactKindConstraints, kind: str = "PRD"):
    return C.validate_headings_contract(
        path=path,
        constraints=constraints,
        registered_systems=None,
        artifact_kind=kind,
    )


def _codes(report, bucket: str = "errors"):
    return [str(f.get("code")) for f in (report.get(bucket) or [])]


def _finding(report, code: str):
    for finding in (report.get("errors") or []) + (report.get("warnings") or []):
        if finding.get("code") == code:
            return finding
    return None


#: Three sections, written in the order A, B, C.
_IN_ORDER = """
# Doc

## Alpha

text

## Beta

text

## Gamma

text
"""

#: The same three sections, with Beta written before Alpha.
_SWAPPED = """
# Doc

## Beta

text

## Alpha

text

## Gamma

text
"""

_ABC = [_heading("Alpha", "sec-alpha"), _heading("Beta", "sec-beta"), _heading("Gamma", "sec-gamma")]


# ---------------------------------------------------------------------------
# AC1 — a declared order names both sections
# ---------------------------------------------------------------------------

def test_a_section_written_before_the_one_it_must_follow_names_both(tmp_path):
    path = _doc(tmp_path, _SWAPPED)
    report = _report(path, _kind(_ABC, order=C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta"))))

    assert _codes(report) == [EC.HEADING_ORDER_VIOLATION]
    finding = _finding(report, EC.HEADING_ORDER_VIOLATION)
    assert finding["heading_id"] == "sec-beta"
    assert finding["expected_after"]["id"] == "sec-alpha"
    # Dropped rather than null, the way every other absent extra is.
    assert "expected_before" not in finding
    assert "`sec-beta`" in finding["message"] and "`sec-alpha`" in finding["message"]


def test_the_finding_carries_the_line_of_both_sections(tmp_path):
    """A line number for the displaced section alone is not a diagnosis."""
    path = _doc(tmp_path, _SWAPPED)
    report = _report(path, _kind(_ABC, order=C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta"))))

    finding = _finding(report, EC.HEADING_ORDER_VIOLATION)
    assert finding["heading_line"] == 3          # `## Beta`
    assert finding["line"] == 3
    assert finding["expected_after"]["line"] == 7  # `## Alpha`
    assert "(line 3)" in finding["message"] and "(line 7)" in finding["message"]


def test_the_finding_names_the_nearest_section_that_has_to_be_cleared(tmp_path):
    """Gamma has to clear both Alpha and Beta; only the nearer one is named.

    Listing every section the move has to get past would turn one move into a
    list to reconcile.
    """
    path = _doc(tmp_path, """
# Doc

## Gamma

## Alpha

## Beta
""")
    report = _report(path, _kind(
        _ABC, order=C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta", "sec-gamma"))))

    assert _codes(report) == [EC.HEADING_ORDER_VIOLATION]
    finding = _finding(report, EC.HEADING_ORDER_VIOLATION)
    assert finding["heading_id"] == "sec-gamma"
    assert finding["expected_after"]["id"] == "sec-alpha"
    assert finding["expected_after"]["line"] == 5


# ---------------------------------------------------------------------------
# AC2 — no order, no ordering findings
# ---------------------------------------------------------------------------

def test_a_kit_that_declares_no_order_reports_nothing_about_order(tmp_path):
    path = _doc(tmp_path, _SWAPPED)
    report = _report(path, _kind(_ABC))
    assert _codes(report) == []


def test_and_no_longer_calls_the_displaced_section_missing(tmp_path):
    """The old `heading-missing` for a present section *was* an ordering rule.

    Suppressing only the new code while leaving that in place would satisfy the
    letter of "no ordering findings" and none of its point.
    """
    path = _doc(tmp_path, _SWAPPED)
    report = _report(path, _kind(_ABC))
    assert EC.HEADING_MISSING not in _codes(report)


def test_an_in_order_document_is_untouched_by_any_of_this(tmp_path):
    path = _doc(tmp_path, _IN_ORDER)
    for order in (None, C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta", "sec-gamma"))):
        assert _codes(_report(path, _kind(_ABC, order=order))) == []


# ---------------------------------------------------------------------------
# AC4 — a partial order leaves the rest free
# ---------------------------------------------------------------------------

def test_sections_outside_the_order_may_appear_anywhere(tmp_path):
    """Gamma is displaced too, but no order names it, so it is nobody's problem."""
    path = _doc(tmp_path, """
# Doc

## Gamma

## Beta

## Alpha
""")
    report = _report(path, _kind(_ABC, order=C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta"))))

    assert _codes(report) == [EC.HEADING_ORDER_VIOLATION]
    assert _finding(report, EC.HEADING_ORDER_VIOLATION)["heading_id"] == "sec-beta"


def test_declared_expands_to_every_section_in_declaration_order(tmp_path):
    """The one-line way back to the strictness that used to be unavoidable."""
    path = _doc(tmp_path, _SWAPPED)
    kit, errors = _load(tmp_path, {
        "artifacts": {
            "PRD": {
                "identifiers": {"fr": {"required": True}},
                "order": "declared",
                "headings": [
                    {"level": 2, "pattern": "Alpha", "id": "sec-alpha"},
                    {"level": 2, "pattern": "Beta", "id": "sec-beta"},
                    {"level": 2, "pattern": "Gamma", "id": "sec-gamma"},
                ],
            },
        },
    })
    assert errors == []
    assert kit.by_kind["PRD"].order == C.HeadingOrder.from_sequence(
        ("sec-alpha", "sec-beta", "sec-gamma"))
    assert _codes(_report(path, kit.by_kind["PRD"])) == [EC.HEADING_ORDER_VIOLATION]


# ---------------------------------------------------------------------------
# The rescue pass itself
# ---------------------------------------------------------------------------

def test_a_genuinely_absent_required_section_is_still_missing(tmp_path):
    path = _doc(tmp_path, "# Doc\n\n## Alpha\n")
    report = _report(path, _kind([_heading("Alpha", "sec-alpha"), _heading("Beta", "sec-beta")]))
    assert _codes(report) == [EC.HEADING_MISSING]


def test_a_genuinely_absent_optional_section_is_still_silent(tmp_path):
    path = _doc(tmp_path, "# Doc\n\n## Alpha\n")
    report = _report(path, _kind([
        _heading("Alpha", "sec-alpha"),
        _heading("Beta", "sec-beta", required=False),
    ]))
    assert _codes(report) == []


def test_the_rescue_cannot_take_a_section_another_constraint_matched(tmp_path):
    """Two constraints must not both stand on the document's only Alpha.

    Without the claim, a constraint whose own section is absent would rescue a
    neighbour's and report the file as complete.
    """
    path = _doc(tmp_path, "# Doc\n\n## Alpha\n")
    report = _report(path, _kind([
        _heading("Alpha", "sec-alpha"),
        _heading("Alpha", "sec-alpha-again"),
    ]))
    assert _codes(report) == [EC.HEADING_MISSING]
    assert _finding(report, EC.HEADING_MISSING)["heading_id"] == "sec-alpha-again"


def test_a_rescued_section_is_measured_by_its_own_rules(tmp_path):
    """The accepted behaviour change: a displaced section is no longer unchecked.

    Before the rescue pass a section written out of order was reported absent
    and nothing else about it was ever looked at — its numbering and its
    repetition went unvalidated. Finding it means checking it.
    """
    path = _doc(tmp_path, """
# Doc

## 2. Beta

## Alpha
""")
    report = _report(path, _kind([
        _heading("Alpha", "sec-alpha"),
        _heading("Beta", "sec-beta", numbered=False),
    ]))
    assert _codes(report) == [EC.HEADING_NUMBERING_MISMATCH]


def test_children_of_a_rescued_section_are_scoped_under_it(tmp_path):
    path = _doc(tmp_path, """
# Doc

## Beta

### Detail

## Alpha
""")
    report = _report(path, _kind([
        _heading("Alpha", "sec-alpha"),
        _heading("Beta", "sec-beta"),
        _heading("Detail", "sec-detail", level=3),
    ]))
    assert _codes(report) == []


def test_a_subsection_travels_with_its_parent_through_unconstrained_headings(tmp_path):
    """The chain is every ancestor, not the nearest one.

    A displaced section usually has a plain subheading over its constrained
    detail. Checking only the immediate parent broke the chain at the first
    heading no constraint names, so the detail was reported for a move its
    ancestor already accounts for.
    """
    path = _doc(tmp_path, """
# Doc

## Beta

### Plain

#### Detail

## Alpha
""")
    report = _report(path, _kind(
        [
            _heading("Alpha", "sec-alpha"),
            _heading("Beta", "sec-beta"),
            _heading("Detail", "sec-detail", level=4),
        ],
        order=C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta", "sec-detail")),
    ))
    assert _codes(report) == [EC.HEADING_ORDER_VIOLATION]
    assert _finding(report, EC.HEADING_ORDER_VIOLATION)["heading_id"] == "sec-beta"


def test_only_the_displaced_parent_is_reported_not_its_subsections(tmp_path):
    """One move fixes the document, so the report names one move."""
    path = _doc(tmp_path, """
# Doc

## Beta

### Detail

## Alpha
""")
    report = _report(path, _kind(
        [
            _heading("Alpha", "sec-alpha"),
            _heading("Beta", "sec-beta"),
            _heading("Detail", "sec-detail", level=3),
        ],
        order=C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta", "sec-detail")),
    ))
    assert _codes(report) == [EC.HEADING_ORDER_VIOLATION]
    assert _finding(report, EC.HEADING_ORDER_VIOLATION)["heading_id"] == "sec-beta"


def test_the_cursor_never_rewinds_onto_an_already_measured_section(tmp_path):
    """A rescue looks backwards; it must not offer the past to what comes next.

    Delta sits before the rescued Alpha. If the rescue moved the cursor back to
    Alpha's position, the later Gamma constraint would search from there and
    match the earlier Gamma, changing which section every subsequent rule is
    measured against.
    """
    path = _doc(tmp_path, """
# Doc

## Gamma

## Beta

## Alpha

## Gamma
""")
    report = _report(path, _kind([
        _heading("Alpha", "sec-alpha"),
        _heading("Beta", "sec-beta"),
        _heading("Gamma", "sec-gamma"),
    ]))
    # Gamma matches the copy after Alpha, not the one at the top of the file.
    assert _codes(report) == []


# ---------------------------------------------------------------------------
# AC3 — numbering and depth become ordinary, relaxable rules
# ---------------------------------------------------------------------------

_MISNUMBERED = """
# Doc

## 1. Alpha

## 3. Beta
"""


def _policy(per_kind: dict) -> S.SeverityPolicy:
    return S.SeverityPolicy(kit=S.SeverityTables(by_kind=per_kind))


def test_a_kit_can_switch_off_consecutive_numbering_for_one_kind(tmp_path):
    path = _doc(tmp_path, _MISNUMBERED)
    constraints = _kind(_ABC[:2])
    policy = _policy({"PRD": {EC.HEADING_NUMBER_NOT_CONSECUTIVE: S.OFF}})

    without = C.validate_artifact_file(
        artifact_path=path, artifact_kind="PRD", constraints=constraints)
    assert EC.HEADING_NUMBER_NOT_CONSECUTIVE in _codes(without)

    with_policy = C.validate_artifact_file(
        artifact_path=path, artifact_kind="PRD", constraints=constraints, policy=policy)
    assert EC.HEADING_NUMBER_NOT_CONSECUTIVE not in _codes(with_policy)


def test_switching_it_off_for_one_kind_leaves_the_others_alone(tmp_path):
    path = _doc(tmp_path, _MISNUMBERED)
    policy = _policy({"PRD": {EC.HEADING_NUMBER_NOT_CONSECUTIVE: S.OFF}})

    report = C.validate_artifact_file(
        artifact_path=path,
        artifact_kind="DESIGN",
        constraints=_kind(_ABC[:2]),
        policy=policy,
    )
    assert EC.HEADING_NUMBER_NOT_CONSECUTIVE in _codes(report)


def test_a_kit_can_lower_the_toc_depth_jump_rule_for_one_kind(tmp_path):
    path = _doc(tmp_path, """
# Doc

## Alpha

#### Too deep
""")
    constraints = _kind([_heading("Alpha", "sec-alpha")])
    policy = _policy({"PRD": {EC.TOC_HEADING_DEPTH_JUMP: S.OFF}})

    without = C.validate_artifact_file(
        artifact_path=path, artifact_kind="PRD", constraints=constraints)
    assert EC.TOC_HEADING_DEPTH_JUMP in _codes(without, "warnings")

    with_policy = C.validate_artifact_file(
        artifact_path=path, artifact_kind="PRD", constraints=constraints, policy=policy)
    assert EC.TOC_HEADING_DEPTH_JUMP not in _codes(with_policy, "warnings")


# ---------------------------------------------------------------------------
# `heading-requires-multiple`
# ---------------------------------------------------------------------------

_ONE_FLOW = """
# Doc

## Alpha
"""


def test_a_single_occurrence_of_a_repeated_section_is_off_by_default(tmp_path):
    path = _doc(tmp_path, _ONE_FLOW)
    report = C.validate_artifact_file(
        artifact_path=path,
        artifact_kind="PRD",
        constraints=_kind([_heading("Alpha", "sec-alpha", multiple=True)], toc=False),
    )
    assert _codes(report) == [] and _codes(report, "warnings") == []
    assert report["suppressed"] == 1


def test_but_the_rule_runs_and_reports_once_a_kit_asks_for_it(tmp_path):
    path = _doc(tmp_path, _ONE_FLOW)
    report = C.validate_artifact_file(
        artifact_path=path,
        artifact_kind="PRD",
        constraints=_kind([_heading("Alpha", "sec-alpha", multiple=True)], toc=False),
        policy=_policy({"PRD": {EC.HEADING_REQUIRES_MULTIPLE: S.ERROR}}),
    )
    assert _codes(report) == [EC.HEADING_REQUIRES_MULTIPLE]
    assert "at least 2" in _finding(report, EC.HEADING_REQUIRES_MULTIPLE)["message"]


def test_two_occurrences_satisfy_it(tmp_path):
    path = _doc(tmp_path, "# Doc\n\n## Alpha\n\n## Alpha\n")
    report = C.validate_artifact_file(
        artifact_path=path,
        artifact_kind="PRD",
        constraints=_kind([_heading("Alpha", "sec-alpha", multiple=True)], toc=False),
        policy=_policy({"PRD": {EC.HEADING_REQUIRES_MULTIPLE: S.ERROR}}),
    )
    assert _codes(report) == []


# ---------------------------------------------------------------------------
# Parsing `order`
# ---------------------------------------------------------------------------

def _load(tmp_path: Path, data: dict):
    path = tmp_path / "constraints.toml"
    path.write_text(toml_utils.dumps(data), encoding="utf-8")
    return C.load_constraints_file(path)


def _kind_toml(order=None, heading_ids=("sec-alpha", "sec-beta")) -> dict:
    kind: dict = {
        "identifiers": {"fr": {"required": True}},
        "headings": [
            {"level": 2, "pattern": hid.replace("sec-", "").title(), "id": hid}
            for hid in heading_ids
        ],
    }
    if order is not None:
        kind["order"] = order
    return kind


def test_a_kind_without_order_declares_none(tmp_path):
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": _kind_toml()}})
    assert errors == []
    assert kit.by_kind["PRD"].order is None


def test_an_order_list_selects_the_sections_it_names(tmp_path):
    kit, errors = _load(tmp_path, {
        "artifacts": {"PRD": _kind_toml(
            order=["sec-alpha", "sec-gamma"],
            heading_ids=("sec-alpha", "sec-beta", "sec-gamma"),
        )}})
    assert errors == []
    assert kit.by_kind["PRD"].order == C.HeadingOrder.from_sequence(("sec-alpha", "sec-gamma"))


def test_an_order_may_not_re_sequence_the_declared_headings(tmp_path):
    """`order` chooses what is enforced; the headings list says in what sequence.

    An order running against the declarations would describe a document the
    matcher never looks for, so it is refused at the point it is written rather
    than silently unenforced at the point it would matter.
    """
    kit, errors = _load(tmp_path, {
        "artifacts": {"PRD": _kind_toml(order=["sec-beta", "sec-alpha"])}})
    assert kit is None
    assert any("does not re-sequence them" in message for message in errors), errors
    assert any("'sec-alpha'" in message and "'sec-beta'" in message for message in errors)


@pytest.mark.parametrize(
    ("order", "expected"),
    [
        (["sec-alpha", "sec-nope"], "unknown heading id 'sec-nope'"),
        (["sec-alpha", "sec-alpha"], "more than once"),
        (["sec-alpha", ""], "non-empty heading ids"),
        (["sec-alpha", " "], "non-empty heading ids"),
        (["sec-alpha", 7], "non-empty heading ids"),
        ("first", 'must be a list of heading ids or "declared"'),
        (" declared ", 'must be a list of heading ids or "declared"'),
        (7, 'must be a list of heading ids or "declared"'),
    ],
)
def test_an_order_that_cannot_be_honoured_fails_the_load(tmp_path, order, expected):
    """A typo in `order` is a section its author believes is being ordered."""
    kit, errors = _load(tmp_path, {"artifacts": {"PRD": _kind_toml(order=order)}})
    assert kit is None
    assert any(expected in message for message in errors), errors


def test_nothing_the_published_schema_refuses_is_allowed_to_load(tmp_path):
    """The one direction of schema/loader disagreement that misleads anybody.

    `kit-constraints.schema.json` pins the string form with `const`, so a
    padded `" declared "` is invalid there. If it loaded anyway, the schema —
    which is what teams point their editors and preflight checks at — would be
    calling a working file broken. The reverse (schema accepts, loader refuses)
    is unavoidable: only the loader knows which ids the kind declares.
    """
    schema = json.loads(
        (Path(__file__).parent.parent / "schemas" / "kit-constraints.schema.json").read_text())
    order = schema["$defs"]["artifact_kind_constraints"]["properties"]["order"]
    string_form = [branch for branch in order["oneOf"] if "const" in branch][0]
    list_form = [branch for branch in order["oneOf"] if branch.get("type") == "array"][0]

    assert string_form["const"] == "declared"
    assert list_form["items"]["pattern"] == r"\S"
    assert list_form["uniqueItems"] is True

    kit, errors = _load(tmp_path, {
        "artifacts": {"PRD": _kind_toml(order=string_form["const"])}})
    assert errors == [] and kit is not None


def test_order_entries_are_matched_case_insensitively_like_every_heading_id(tmp_path):
    kit, errors = _load(tmp_path, {
        "artifacts": {"PRD": _kind_toml(order=["SEC-ALPHA", "sec-beta"])}})
    assert errors == []
    assert kit.by_kind["PRD"].order == C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta"))


# ---------------------------------------------------------------------------
# Merging two kits' orders
# ---------------------------------------------------------------------------

def _two_kits(tmp_path: Path, first: dict, second: dict):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for folder, data in (("a", first), ("b", second)):
        (tmp_path / folder / "constraints.toml").write_text(
            toml_utils.dumps({"artifacts": {"PRD": data}}), encoding="utf-8")
    return C.load_constraints_files(
        [tmp_path / "a" / "constraints.toml", tmp_path / "b" / "constraints.toml"])


def test_two_kits_orders_add_up(tmp_path):
    kit, errors = _two_kits(
        tmp_path,
        _kind_toml(order=["sec-alpha", "sec-beta"]),
        _kind_toml(order=["sec-beta", "sec-gamma"], heading_ids=("sec-beta", "sec-gamma")),
    )
    assert errors == []
    assert kit.by_kind["PRD"].order == C.HeadingOrder.from_sequence(
        ("sec-alpha", "sec-beta", "sec-gamma"))


def test_two_kits_that_contradict_each_other_fail_the_load(tmp_path):
    """Each kit is coherent on its own; only the pair is impossible.

    Keeping either kit's word would enforce an order the other kit's author
    would read as already satisfied.
    """
    kit, errors = _two_kits(
        tmp_path,
        _kind_toml(order=["sec-alpha", "sec-beta"], heading_ids=("sec-alpha", "sec-beta")),
        _kind_toml(order=["sec-beta", "sec-alpha"], heading_ids=("sec-beta", "sec-alpha")),
    )
    assert kit is None
    assert any("contradicts another kit's order" in message for message in errors), errors
    assert any("'sec-beta'" in message and "'sec-alpha'" in message for message in errors)


def test_a_cycle_that_only_closes_across_three_kits_is_caught(tmp_path):
    """The fold makes the third order meet both of the first two at once."""
    paths = []
    for name, order in (
        ("a", ("sec-alpha", "sec-beta")),
        ("b", ("sec-beta", "sec-gamma")),
        ("c", ("sec-gamma", "sec-alpha")),
    ):
        (tmp_path / name).mkdir()
        path = tmp_path / name / "constraints.toml"
        path.write_text(
            toml_utils.dumps({"artifacts": {
                "PRD": _kind_toml(order=list(order), heading_ids=order)}}),
            encoding="utf-8",
        )
        paths.append(path)

    kit, errors = C.load_constraints_files(paths)
    assert kit is None
    assert any("contradicts another kit's order" in message for message in errors), errors


def test_a_contradicted_merge_returns_nothing_even_when_nobody_asked_for_errors(tmp_path):
    """Fail-closed without being asked to be.

    `merge_kit_constraints_all_of` is exported. A caller that does not pass an
    `errors` list would otherwise receive a fully-formed model holding one
    arbitrary reading of the contradiction, indistinguishable from a merge that
    worked — the silence would be the caller's problem rather than this
    function's.
    """
    def _kit(ids):
        return C.KitConstraints(by_kind={"PRD": C.ArtifactKindConstraints(
            name=None, description=None, defined_id=[],
            order=C.HeadingOrder.from_sequence(ids))})

    assert C.merge_kit_constraints_all_of([_kit(("x", "y")), _kit(("y", "x"))]) is None

    errors: list[str] = []
    assert C.merge_kit_constraints_all_of(
        [_kit(("x", "y")), _kit(("y", "x"))], errors) is None
    assert any("contradicts another kit's order" in message for message in errors)

    # A merge that can be performed still is.
    merged = C.merge_kit_constraints_all_of([_kit(("x", "y")), _kit(("y", "z"))])
    assert merged is not None and merged.by_kind["PRD"].order.relates("x", "z")


def test_one_kit_with_an_order_and_one_without_keeps_the_order(tmp_path):
    kit, errors = _two_kits(
        tmp_path, _kind_toml(order=["sec-alpha", "sec-beta"]), _kind_toml())
    assert errors == []
    assert kit.by_kind["PRD"].order == C.HeadingOrder.from_sequence(("sec-alpha", "sec-beta"))


# ---------------------------------------------------------------------------
# The order model
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("a", "b", True),
        ("b", "a", False),
        ("a", "a", False),
        ("a", "unlisted", False),
        ("unlisted", "b", False),
        (None, "b", False),
        ("a", None, False),
    ],
)
def test_relates_answers_only_for_pairs_it_was_given(first, second, expected):
    assert C.HeadingOrder.from_sequence(("a", "b")).relates(first, second) is expected


def test_an_empty_order_relates_nothing():
    assert C.HeadingOrder().relates("a", "b") is False


def test_merging_never_reverses_what_either_kit_wrote():
    """The failure a spliced sequence cannot avoid.

    `("a", "c")` spliced onto `("b", "c")` is `("a", "c", "b")`, which states c
    before b — the opposite of the second kit's list — and a before b, which
    neither kit wrote. Held as pairs, the sum says exactly what they said.
    """
    merged = C._merge_heading_order(
        C.HeadingOrder.from_sequence(("a", "c")),
        C.HeadingOrder.from_sequence(("b", "c")),
        "PRD",
        [],
    )
    assert merged.relates("b", "c") is True
    assert merged.relates("c", "b") is False
    assert merged.relates("a", "b") is False
    assert merged.relates("b", "a") is False


def test_a_relation_neither_kit_wrote_but_both_imply_is_enforced():
    """a before c and c before b is a before b, whoever said which half."""
    merged = C._merge_heading_order(
        C.HeadingOrder.from_sequence(("a", "c")),
        C.HeadingOrder.from_sequence(("c", "b")),
        "PRD",
        [],
    )
    assert merged.relates("a", "b") is True


# ---------------------------------------------------------------------------
# What the rescue pass does not promise
# ---------------------------------------------------------------------------

def test_a_repeated_section_is_repeated_even_with_subsections_between(tmp_path):
    """"At least two" counts the scope, not the run.

    The matcher collects only the first consecutive run, because
    `multiple = false` has always meant "not twice in a row". A section that
    genuinely repeats almost always has its own subsections between the
    copies, so counting the run would report every one of them as appearing
    once.
    """
    path = _doc(tmp_path, """
# Doc

## Flow

### Step

## Flow

### Step
""")
    constraints = _kind([_heading("Flow", "sec-flow", multiple=True)], toc=False)
    policy = _policy({"PRD": {EC.HEADING_REQUIRES_MULTIPLE: S.ERROR}})

    report = C.validate_artifact_file(
        artifact_path=path, artifact_kind="PRD", constraints=constraints, policy=policy)
    assert _codes(report) == []


def test_every_copy_of_a_repeated_section_has_its_numbering_checked(tmp_path):
    """`numbered` is "each matching heading", and a second copy is one of them.

    The consecutive run and the scope are the same list until something sits
    between the copies. Checking numbering on the run alone meant a repeated
    section's later copies were unvalidated exactly when the section was long
    enough to have subsections — which is when it repeats at all.
    """
    path = _doc(tmp_path, """
# Doc

## Flow

### Step

## 2. Flow
""")
    report = _report(path, _kind(
        [_heading("Flow", "sec-flow", numbered=False)], toc=False))
    assert _codes(report) == [EC.HEADING_NUMBERING_MISMATCH]
    assert _finding(report, EC.HEADING_NUMBERING_MISMATCH)["line"] == 7


def test_but_a_duplicate_separated_by_a_subsection_is_still_not_a_duplicate(tmp_path):
    """The other rule keeps the run, and that asymmetry is the point.

    `multiple = false` has meant "not twice in a row" since before this branch.
    Widening it to the scope would report duplicates in documents that pass
    today, so only the rules that ask about the section — not the run — read
    the wider list.
    """
    path = _doc(tmp_path, """
# Doc

## Flow

### Step

## Flow
""")
    report = _report(path, _kind(
        [_heading("Flow", "sec-flow", multiple=False)], toc=False))
    assert EC.HEADING_PROHIBITS_MULTIPLE not in _codes(report)


def test_a_heading_two_constraints_can_both_see_is_judged_once(tmp_path):
    """The cost of reading the scope instead of the run, and its bound.

    Only one constraint *claims* a heading, but every constraint whose pattern
    matches it *sees* it while counting its scope. Without a record of what has
    been ruled on, one numbering defect is reported once per constraint that
    could have matched it — the document has one problem, so it gets one
    finding, from whichever constraint reaches it first.
    """
    path = _doc(tmp_path, """
# Doc

## Flow

### Step

## 2. Flow
""")
    report = _report(path, _kind([
        _heading("Flow", "sec-flow-a", numbered=False),
        _heading("Flow", "sec-flow-b", numbered=False),
    ], toc=False))
    assert _codes(report) == [EC.HEADING_NUMBERING_MISMATCH]
    assert _finding(report, EC.HEADING_NUMBERING_MISMATCH)["heading_id"] == "sec-flow-a"


def test_the_leftover_match_is_still_claimable_by_the_next_constraint(tmp_path):
    """Seeing a heading is not taking it — the second constraint still matches.

    The pair above would also produce one finding if the scope inspection had
    quietly claimed everything it looked at, so this pins the other half: the
    unclaimed copy is what the second constraint matches on.
    """
    path = _doc(tmp_path, """
# Doc

## Flow

### Step

## Flow
""")
    report = _report(path, _kind([
        _heading("Flow", "sec-flow-a"),
        _heading("Flow", "sec-flow-b"),
    ], toc=False))
    assert _codes(report) == []


def test_a_section_that_appears_once_is_still_reported_when_it_has_subsections(tmp_path):
    """The other half of the same count — widening it must not silence the rule."""
    path = _doc(tmp_path, "# Doc\n\n## Flow\n\n### Step\n")
    report = C.validate_artifact_file(
        artifact_path=path,
        artifact_kind="PRD",
        constraints=_kind([_heading("Flow", "sec-flow", multiple=True)], toc=False),
        policy=_policy({"PRD": {EC.HEADING_REQUIRES_MULTIPLE: S.ERROR}}),
    )
    assert _codes(report) == [EC.HEADING_REQUIRES_MULTIPLE]


def test_a_subsection_left_behind_by_its_displaced_parent_is_reported_missing(tmp_path):
    """A rescued parent takes its own scope with it, and the child is judged there.

    Deliberate, and the reason the per-level anchor is *not* guarded the way
    the cursor is: guarding it would point a rescued section's children at
    whichever sibling happened to match last, which is the case
    `test_children_of_a_rescued_section_are_scoped_under_it` covers.

    Before the rescue pass this document reported `sec-c` missing — a section
    plainly present on line 3. It now reports the section that really is not
    where the kit puts it. Either way the document fails; only the sentence
    changed, and the new one is true.
    """
    path = _doc(tmp_path, """
# A

## C

## B

### D
""")
    report = _report(path, _kind([
        _heading("A", "sec-a", level=1),
        _heading("B", "sec-b"),
        _heading("C", "sec-c"),
        _heading("D", "sec-d", level=3),
    ]))
    assert _codes(report) == [EC.HEADING_MISSING]
    assert _finding(report, EC.HEADING_MISSING)["heading_id"] == "sec-d"
