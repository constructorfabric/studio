"""Tests for the artifact-quality finding model (utils.artifact_quality).

Pins the shared contract every detector emits: the model validates itself on construction, serialises
to a stable shape (optional fields omitted when unset), and carries the advisory / read-only /
no-score / honest-unjudgeable invariants. The JSON schema is checked to match what ``to_dict`` emits.
"""
import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "studio" / "scripts"))

from studio.utils.artifact_quality import (
    ArtifactFinding,
    Locus,
    DETECTORS,
    KINDS,
    SEVERITIES,
    finding_json_schema,
    SCHEMA_VERSION,
    VERDICT_UNJUDGEABLE,
)


SCHEMA = finding_json_schema()  # one snapshot; tests never mutate it

def _structural(**over):
    kw = dict(detector="duplication", severity="warn", kind="structural",
              message="repeated content", primary=Locus("docs/a.md"))
    kw.update(over)
    return ArtifactFinding(**kw)


def _judged(**over):
    kw = dict(detector="traceability", severity="info", kind="judged", verdict="drifted",
              message="link drifted", primary=Locus("docs/a.md", anchor="goals", line=12),
              evidence="the requirement text", evidence_ok=True, confidence="medium")
    kw.update(over)
    return ArtifactFinding(**kw)


def _ecma(pattern):
    """Compile a JSON-Schema (ECMA-262) pattern for faithful matching under Python's re.

    Python's ``$`` also matches just before a trailing newline; ECMA-262 ``$`` (no multiline, as a
    JSON-Schema validator uses) matches only at the true end. Translate ``$`` -> ``\\Z`` so the test
    reflects what a real validator does, not Python's newline quirk.

    Only faithful for patterns built from explicit character classes. Python's ``\\s``/``\\S`` track
    ``str.isspace()``, which differs from ECMA's whitespace set (U+0085/U+FEFF), so this helper would
    silently report false agreement on such a pattern — refuse them rather than mislead a parity test.
    """
    for whitespace_token in (r"\s", r"\S"):
        assert whitespace_token not in pattern, \
            "_ecma() is not faithful for whitespace-class patterns (Python vs ECMA differ)"
    return re.compile(pattern.replace("$", r"\Z"))


def test_schema_anchor_pattern_agrees_with_constructor():
    # Explicit-class pattern (no ECMA \\s / '.'), so _ecma() is faithful and the wire schema mirrors
    # str.strip()/control exactly -- including the exotic cases the earlier \\s-based pattern got
    # wrong: NEL (U+0085) is blank to both, BOM (U+FEFF) is kept by both, U+2028 is a valid char.
    rx = _ecma(SCHEMA["definitions"]["locus"]["properties"]["anchor"]["pattern"])
    good = ["goals", "a b", "a\u2028b", "sec-1", "\ufeff"]
    bad = ["", "   ", "\x85", "\t", "a\nb"]
    for anchor in good:
        assert rx.match(anchor), f"schema should accept anchor {anchor!r}"
        assert Locus("docs/a.md", anchor=anchor).anchor == anchor
    for anchor in bad:
        assert not rx.match(anchor), f"schema should reject anchor {anchor!r}"
        with pytest.raises(ValueError):
            Locus("docs/a.md", anchor=anchor)


# --- construction + validation --------------------------------------------

def test_valid_structural_and_judged_construct():
    assert _structural().verdict is None
    assert _judged().verdict == "drifted"


def test_unknown_detector_raises():
    with pytest.raises(ValueError, match="unknown detector"):
        _structural(detector="typos")


def test_severity_error_is_rejected():
    # advisory only — there is deliberately no "error" severity, so a finding can never gate
    with pytest.raises(ValueError, match="advisory severity"):
        _structural(severity="error")


def test_bad_kind_raises():
    with pytest.raises(ValueError, match="kind must be"):
        _structural(kind="fatal")


def test_structural_with_a_verdict_raises():
    with pytest.raises(ValueError, match="structural finding carries no verdict"):
        _structural(verdict="covered")


def test_judged_without_a_verdict_raises():
    primary = Locus("docs/a.md")
    with pytest.raises(ValueError, match="judged finding must carry a non-empty verdict"):
        ArtifactFinding(detector="contradiction", severity="warn", kind="judged",
                        message="x", primary=primary)


def test_unjudgeable_is_a_legal_judged_verdict():
    assert _judged(verdict=VERDICT_UNJUDGEABLE).verdict == VERDICT_UNJUDGEABLE
    assert VERDICT_UNJUDGEABLE == "unjudgeable"


def test_unsupported_schema_version_is_rejected():
    # the versioned contract admits exactly the one version it defines
    with pytest.raises(ValueError, match="schema_version must be"):
        _structural(schema_version=SCHEMA_VERSION + 1)


# --- serialisation ---------------------------------------------------------

def test_locus_to_dict_omits_unset():
    assert Locus("docs/a.md").to_dict() == {"artifact_path": "docs/a.md"}
    assert Locus("docs/a.md", anchor="g", line=3).to_dict() == {
        "artifact_path": "docs/a.md", "anchor": "g", "line": 3}


@pytest.mark.parametrize("bad_path", ["", "/abs/a.md", "docs\\a.md", "../a.md", "a/../b.md"])
def test_locus_rejects_non_relative_posix_paths(bad_path):
    # empty / absolute / backslash / traversal all violate the project-relative POSIX contract
    with pytest.raises(ValueError):
        Locus(bad_path)


def test_locus_rejects_non_positive_line():
    with pytest.raises(ValueError, match="1-based"):
        Locus("docs/a.md", line=0)


def test_structural_to_dict_omits_optional_fields():
    d = _structural().to_dict()
    assert d["detector"] == "duplication"
    assert d["kind"] == "structural"
    assert d["schema_version"] == SCHEMA_VERSION
    # unset optionals are absent, not null
    for k in ("related", "verdict", "confidence"):
        assert k not in d
    # required keys always present
    for k in ("detector", "severity", "kind", "message", "primary", "evidence",
              "evidence_ok", "suggested_action", "schema_version"):
        assert k in d


def test_judged_to_dict_includes_optionals_when_set():
    d = _judged(related=Locus("docs/b.md")).to_dict()
    assert d["verdict"] == "drifted"
    assert d["confidence"] == "medium"
    assert d["related"] == {"artifact_path": "docs/b.md"}


def test_no_combined_score_and_no_edit_payload():
    # the model refuses a single quality number and never carries an applyable edit
    d = _judged().to_dict()
    for banned in ("score", "quality_score", "edit", "patch", "fix"):
        assert banned not in d


# --- the JSON schema contract ---------------------------------------------

def test_schema_is_versioned_and_well_formed():
    assert SCHEMA["title"] == "ArtifactFinding"
    assert SCHEMA["additionalProperties"] is False
    # no score / edit field is even *allowed* by the schema
    props = SCHEMA["properties"]
    assert "score" not in props
    assert "edit" not in props
    assert "schema_version" in SCHEMA["required"]


def test_schema_pins_schema_version_and_encodes_kind_verdict_rule():
    # schema_version is pinned to the one supported contract, not "any integer"
    assert SCHEMA["properties"]["schema_version"] == {"const": SCHEMA_VERSION}
    # the locus line is 1-based on the wire, mirroring the model
    assert SCHEMA["definitions"]["locus"]["properties"]["line"]["minimum"] == 1
    # structural => no verdict; judged => verdict required (mirrors the constructor)
    conds = SCHEMA["allOf"]
    structural = next(c for c in conds if c["if"]["properties"]["kind"]["const"] == "structural")
    judged = next(c for c in conds if c["if"]["properties"]["kind"]["const"] == "judged")
    assert {"not": {"required": ["verdict"]}} in structural["then"]["allOf"]
    assert judged["then"] == {"required": ["verdict"]}


def test_serialised_finding_keys_are_all_allowed_properties():
    # NB: key-membership only — behavioural schema conformance is covered by the parity tests below
    props = set(SCHEMA["properties"])
    required = set(SCHEMA["required"])
    for finding in (_structural(), _judged(related=Locus("docs/b.md", line=1))):
        keys = set(finding.to_dict())
        assert keys <= props, f"emitted keys not in schema: {keys - props}"
        assert required <= keys, f"missing required keys: {required - keys}"


def test_finding_rejects_non_str_confidence():
    with pytest.raises(TypeError, match="confidence must be a str"):
        _judged(confidence=123)


def test_float_schema_version_is_rejected():
    with pytest.raises(TypeError, match="schema_version must be an int"):
        _structural(schema_version=4.5)


# --- schema<->constructor parity: the wire pattern must reject exactly what the dataclass rejects,
#     so a hand-authored payload can't smuggle a value past a validator the constructor would block.

def test_schema_artifact_path_pattern_agrees_with_constructor():
    rx = _ecma(SCHEMA["definitions"]["locus"]["properties"]["artifact_path"]["pattern"])
    good = ["docs/a.md", "a/b/c.md", "a..b/c.md"]
    bad = ["", "/abs.md", "docs\\a.md", "./x.md", "../x.md", "docs//a.md",
           "a/./b.md", "a/../b.md", "docs/..", "a/", "docs/a\n.md"]
    for path in good:
        assert rx.match(path), f"schema pattern should accept {path!r}"
        assert Locus(path).artifact_path == path  # constructor agrees
    for path in bad:
        assert not rx.match(path), f"schema pattern should reject {path!r} (traversal/malformed)"
        with pytest.raises((ValueError, TypeError)):
            Locus(path)  # constructor agrees


def test_schema_message_pattern_agrees_with_constructor():
    # Explicit-class pattern mirrors str.strip() exactly over the whole whitespace set, incl. the
    # exotic U+001C-1F / U+0085 (blank to both) and U+FEFF (kept by both).
    rx = re.compile(SCHEMA["properties"]["message"]["pattern"])

    def ctor_accepts(message):
        try:
            _structural(message=message)
            return True
        except ValueError:
            return False

    for message in ("a real message", "\ufeff", "x\x1c", "a\nb", "", "   ", "\t", "\x85", "\x1c"):
        assert bool(rx.search(message)) == ctor_accepts(message), \
            f"schema/constructor disagree on message {message!r}"


def test_finding_json_schema_returns_a_fresh_deep_copy():
    # The wire contract is not a shared mutable global: each call yields an isolated copy.
    first, second = finding_json_schema(), finding_json_schema()
    assert first is not second
    first["properties"]["severity"]["enum"].append("error")
    assert "error" not in second["properties"]["severity"]["enum"]
    assert "error" not in finding_json_schema()["properties"]["severity"]["enum"]


# --- maintainer review: runtime type validation (fail at construction, not late) ---

@pytest.mark.parametrize("bad", [123, None, 4.5, b"docs/a.md"])
def test_locus_rejects_non_str_path(bad):
    with pytest.raises(TypeError, match="artifact_path must be a str"):
        Locus(bad)


@pytest.mark.parametrize("bad_line", ["7", 4.5, True])
def test_locus_rejects_non_int_line(bad_line):
    with pytest.raises(TypeError, match="line must be an int"):
        Locus("docs/a.md", line=bad_line)


def test_locus_rejects_non_str_anchor():
    with pytest.raises(TypeError, match="anchor must be a str"):
        Locus("docs/a.md", anchor=3)


def test_finding_rejects_non_locus_primary():
    with pytest.raises(TypeError, match="primary must be a Locus"):
        ArtifactFinding(detector="gap", severity="warn", kind="structural",
                        message="x", primary="docs/a.md")


def test_finding_rejects_non_str_message():
    primary = Locus("docs/a.md")
    with pytest.raises(TypeError, match="message must be a str"):
        ArtifactFinding(detector="gap", severity="warn", kind="structural",
                        message=123, primary=primary)


def test_finding_rejects_non_locus_related():
    with pytest.raises(TypeError, match="related must be a Locus"):
        _judged(related="docs/b.md")


def test_finding_rejects_non_str_verdict():
    with pytest.raises(TypeError, match="verdict must be a str"):
        _judged(verdict=123)


def test_finding_rejects_non_bool_evidence_ok():
    with pytest.raises(TypeError, match="evidence_ok must be a bool"):
        _judged(evidence_ok="yes")


# --- maintainer review: malformed paths / anchors, blank & structural-metadata rules ---

@pytest.mark.parametrize("bad", ["./docs/a.md", "docs//a.md", "a/./b.md", "docs/a\n.md", "docs/a\tb.md"])
def test_locus_rejects_malformed_paths(bad):
    with pytest.raises(ValueError):
        Locus(bad)


@pytest.mark.parametrize("bad", ["", "   ", "head\nline"])
def test_locus_rejects_malformed_anchor(bad):
    with pytest.raises(ValueError, match="anchor"):
        Locus("docs/a.md", anchor=bad)


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_finding_rejects_blank_message(blank):
    primary = Locus("docs/a.md")
    with pytest.raises(ValueError, match="message must be non-empty"):
        ArtifactFinding(detector="gap", severity="warn", kind="structural",
                        message=blank, primary=primary)


def test_structural_rejects_judged_only_metadata():
    with pytest.raises(ValueError, match="no judged metadata"):
        _structural(confidence="high")
    with pytest.raises(ValueError, match="no judged metadata"):
        _structural(evidence_ok=True)


def test_bool_schema_version_is_rejected():
    # True == 1 == SCHEMA_VERSION, so a value-equality check alone would let it through
    with pytest.raises(TypeError, match="schema_version must be an int"):
        _structural(schema_version=True)


def test_schema_mirrors_the_tightened_invariants():
    props = SCHEMA["properties"]
    assert props["message"]["minLength"] == 1
    locus = SCHEMA["definitions"]["locus"]["properties"]
    assert "pattern" in locus["artifact_path"]
    assert locus["anchor"]["minLength"] == 1
    structural_then = next(c for c in SCHEMA["allOf"]
                           if c["if"]["properties"]["kind"]["const"] == "structural")["then"]["allOf"]
    assert {"not": {"required": ["confidence"]}} in structural_then
    assert {"properties": {"evidence_ok": {"const": False}}} in structural_then


# --- property-based / generated invariants (seed-deterministic; stdlib random, no Hypothesis dep) ---
# Assert the load-bearing invariants over inputs neither the author nor the reviewers hand-picked.

_PATH_ALPHABET = "abc/./../\\\t\n\x01 ."  # biased toward the tricky path characters


def _rand_str(rng, alphabet, max_len):
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_len)))


def test_property_locus_construction_is_total_and_safe():
    # For ANY generated input, Locus either rejects with ValueError/TypeError or constructs and
    # round-trips — it never raises an unexpected exception, and a constructed line is always >= 1.
    rng = random.Random(20260903)
    accepted = 0
    for _ in range(400):
        path = _rand_str(rng, _PATH_ALPHABET, 12)
        anchor = None if rng.random() < 0.5 else _rand_str(rng, _PATH_ALPHABET, 5)
        line = rng.choice([None, -2, 0, 1, 7, True, "3"])
        try:
            loc = Locus(path, anchor=anchor, line=line)
        except (ValueError, TypeError):
            continue  # rejection is a legal outcome
        accepted += 1
        assert loc.to_dict()["artifact_path"] == path
        assert loc.line is None or loc.line >= 1
    assert accepted > 0, "generator never produced a valid Locus — the accept-branch went vacuous"


def test_property_schema_path_pattern_agrees_with_constructor_on_generated_paths():
    # The wire regex must accept a generated path iff the constructor does — no smuggle gap either way.
    rng = random.Random(31415926)
    rx = _ecma(SCHEMA["definitions"]["locus"]["properties"]["artifact_path"]["pattern"])
    seen = {True: 0, False: 0}
    for _ in range(400):
        path = _rand_str(rng, _PATH_ALPHABET, 14)
        try:
            Locus(path)
            accepted_by_ctor = True
        except (ValueError, TypeError):
            accepted_by_ctor = False
        seen[accepted_by_ctor] += 1
        assert bool(rx.match(path)) == accepted_by_ctor, \
            f"schema/constructor disagree on {path!r}: ctor={accepted_by_ctor}"
    assert seen[True] > 0, "no path was accepted — the positive-agreement branch went vacuous"
    assert seen[False] > 0, "no path was rejected — the negative-agreement branch went vacuous"


def test_property_valid_finding_serialises_within_the_schema_shape():
    # Any validly-constructed finding serialises to allowed keys only, always includes the required
    # ones, and a structural finding never emits judged-only metadata.
    rng = random.Random(27182818)
    props = set(SCHEMA["properties"])
    required = set(SCHEMA["required"])
    for _ in range(300):
        kind = rng.choice(KINDS)
        judged = kind == "judged"
        finding = ArtifactFinding(
            detector=rng.choice(DETECTORS),
            severity=rng.choice(SEVERITIES),
            kind=kind,
            message="m" + str(rng.randint(0, 99)),
            primary=Locus("docs/a.md", line=rng.choice([None, 1, 5])),
            evidence=rng.choice(["", "quoted evidence"]),
            suggested_action=rng.choice(["", "do the thing"]),
            related=rng.choice([None, Locus("docs/b.md")]),
            verdict=("drifted" if judged else None),
            evidence_ok=(rng.random() < 0.5 if judged else False),
            confidence=(rng.choice([None, "high", "medium"]) if judged else None),
        )
        emitted = set(finding.to_dict())
        assert emitted <= props
        assert required <= emitted
        if kind == "structural":
            assert "verdict" not in emitted
            assert "confidence" not in emitted
            assert finding.to_dict()["evidence_ok"] is False


# --- maintainer review round 3 (all Minor) -------------------------------------------------

def test_locus_rejects_windows_drive_letter():
    for bad in ("C:/x.md", "c:/x.md", "C:", "Z:/a/b.md"):
        with pytest.raises(ValueError, match="drive letter"):
            Locus(bad)
    # a POSIX filename that merely contains a colon mid-name is still valid
    assert Locus("a:b.md").artifact_path == "a:b.md"


def test_schema_path_pattern_rejects_drive_letter():
    rx = _ecma(SCHEMA["definitions"]["locus"]["properties"]["artifact_path"]["pattern"])
    assert not rx.match("C:/x.md")
    assert not rx.match("C:")
    assert rx.match("a:b.md")  # colon mid-name allowed, matching the constructor


def test_related_property_refs_the_locus_definition():
    assert SCHEMA["properties"]["related"] == {"$ref": "#/definitions/locus"}


def test_locus_and_finding_are_value_equal_and_hashable():
    # frozen dataclasses -> structural equality + hashable (usable in sets / as dict keys).
    # Bind separate instances so the equality is value-based, not identity (and not a self-compare).
    loc, loc_copy = Locus("docs/a.md", line=3), Locus("docs/a.md", line=3)
    assert loc == loc_copy
    assert loc is not loc_copy
    assert Locus("docs/a.md") != Locus("docs/b.md")
    assert len({Locus("docs/a.md"), Locus("docs/a.md")}) == 1
    finding, finding_copy = _structural(), _structural()
    assert finding == finding_copy
    assert finding is not finding_copy
    assert len({finding, finding_copy}) == 1


def test_message_whitespace_class_equals_str_strip_over_all_unicode():
    # Codifies the exhaustive parity the review flagged: the message pattern's implicit whitespace
    # class matches exactly the code points str.strip() removes (str.isspace()), across all Unicode.
    rx = re.compile(SCHEMA["properties"]["message"]["pattern"])  # [^<whitespace class>]
    strip_ws = {cp for cp in range(0x110000) if chr(cp).isspace()}
    class_ws = {cp for cp in range(0x110000) if rx.search(chr(cp)) is None}
    assert class_ws == strip_ws


# tab / lf, a control, NEL (blank), U+2028 separator, BOM (kept) — the cases the anchor parity turns on
_ANCHOR_ALPHA = "ab .-/" + chr(0x09) + chr(0x0a) + chr(0x01) + chr(0x85) + chr(0x2028) + chr(0xfeff)


def test_property_schema_anchor_pattern_agrees_with_constructor_on_generated_anchors():
    rng = random.Random(16180339)
    rx = _ecma(SCHEMA["definitions"]["locus"]["properties"]["anchor"]["pattern"])
    seen = {True: 0, False: 0}
    for _ in range(400):
        anchor = "".join(rng.choice(_ANCHOR_ALPHA) for _ in range(rng.randint(0, 8)))
        try:
            Locus("docs/a.md", anchor=anchor)
            ok = True
        except (ValueError, TypeError):
            ok = False
        seen[ok] += 1
        assert bool(rx.match(anchor)) == ok, f"schema/constructor disagree on anchor {anchor!r}"
    assert seen[True] > 0
    assert seen[False] > 0


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_judged_finding_rejects_blank_verdict(blank):
    # a judged finding needs a real verdict, not an empty/whitespace string (mirrors message)
    with pytest.raises(ValueError, match="non-empty verdict"):
        _judged(verdict=blank)


def test_schema_verdict_is_non_blank_like_message():
    verdict = SCHEMA["properties"]["verdict"]
    assert verdict["type"] == "string"
    # non-blank via the same explicit str.strip() class as message -> exact constructor parity,
    # not ECMA \S (which diverges on U+0085 / U+FEFF)
    assert verdict["pattern"] == SCHEMA["properties"]["message"]["pattern"]
