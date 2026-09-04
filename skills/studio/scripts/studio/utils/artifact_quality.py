"""Artifact-quality finding model — the shared, advisory unit every detector emits.

Studio's deterministic layer assures *code*; this feature surfaces semantic-quality **findings** on
Project Markdown artifacts (duplication, purpose-mismatch, gap, traceability-meaning, contradiction).
This module is the contract they all speak: one :class:`ArtifactFinding` shape and the JSON schema a
presentation layer consumes. It carries **no detection logic** — detectors (later tasks) import it.

The model mirrors the two shipped ones — ``PdslFinding`` (deterministic, ``to_dict``, location) and
``SemanticFinding`` (advisory verdict + evidence guard) — and holds their invariants:

* **Advisory — never gates.** ``severity`` is only ``info`` / ``warn``; there is no ``error`` and no
  exit-code authority. A finding is a suggestion a human acts on.
* **Read-only.** A finding carries evidence and a *suggested* action — never an edit payload.
* **No combined score.** Findings are individual signals; the model refuses a single quality number.
* **Detector-namespaced verdict.** Judged detectors carry their own verdict vocabulary (traceability:
  ``covered|partial|drifted|contradictory|uncovered``; contradiction: ``contradictory|consistent``;
  purpose: ``mismatch|ok``), and every judged detector also admits ``unjudgeable``. Structural
  detectors carry ``verdict=None`` — the finding itself is the signal.
* **Honest-unjudgeable.** A judged detector with no judge wired emits ``unjudgeable`` — never a
  silent "clean", never a dropped finding.

@cpt-algo:cpt-studio-algo-artifact-quality-finding-model:p1
"""
# @cpt-begin:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-imports
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, Optional

#: Bumped on any breaking change to the finding shape, so a presentation-layer consumer can detect
#: a contract change rather than mis-reading fields.
SCHEMA_VERSION = 1

#: The detectors this model serves (a finding names exactly one).
DETECTORS = ("duplication", "purpose", "gap", "traceability", "contradiction")

#: Advisory severities only — there is deliberately no ``error``: a finding can never gate.
SEVERITIES = ("info", "warn")

#: The two kinds of detector. ``structural`` findings carry ``verdict=None``; ``judged`` findings
#: carry a detector-namespaced verdict (or ``unjudgeable``).
KINDS = ("structural", "judged")

#: The one verdict every judged detector shares — the honest "could not judge" outcome.
VERDICT_UNJUDGEABLE = "unjudgeable"
# @cpt-end:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-imports


# @cpt-begin:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-locus
@dataclass(frozen=True)
class Locus:
    """Where in an artifact a finding sits — enough for a UI to jump to it and quote it."""

    artifact_path: str            # project-relative POSIX path of the Markdown artifact
    anchor: Optional[str] = None  # a heading slug / section id, when the finding is section-scoped
    line: Optional[int] = None    # 1-based line, when the finding is line-scoped

    def __post_init__(self) -> None:
        # Types first, then a canonical project-relative POSIX path and a 1-based line, so a UI
        # never receives a locus it cannot resolve and no wrong type fails late in serialisation.
        self._validate_types()
        self._validate_path()
        if self.line is not None and self.line < 1:
            raise ValueError(f"line is 1-based; got {self.line}")
        self._validate_anchor()

    def _validate_types(self) -> None:
        if not isinstance(self.artifact_path, str):
            raise TypeError(f"artifact_path must be a str, got {type(self.artifact_path).__name__}")
        if self.anchor is not None and not isinstance(self.anchor, str):
            raise TypeError(f"anchor must be a str or None, got {type(self.anchor).__name__}")
        if self.line is not None and type(self.line) is not int:  # bool is an int subclass
            raise TypeError(f"line must be an int or None, got {type(self.line).__name__}")

    def _validate_path(self) -> None:
        if not self.artifact_path:
            raise ValueError("artifact_path must be a non-empty project-relative POSIX path")
        if self.artifact_path.startswith("/") or "\\" in self.artifact_path:
            raise ValueError(
                f"artifact_path must be project-relative POSIX (no leading '/', no '\\'): "
                f"{self.artifact_path!r}")
        head = self.artifact_path[:2]
        if len(head) == 2 and head[1] == ":" and head[0].isascii() and head[0].isalpha() \
                and self.artifact_path[2:3] in ("", "/"):  # Windows drive letter (C:/…, C:)
            raise ValueError(
                f"artifact_path must be project-relative (no drive letter): {self.artifact_path!r}")
        if {"", ".", ".."} & set(self.artifact_path.split("/")):
            raise ValueError(
                f"artifact_path must be canonical — no '.', '..', or empty '//' segments: "
                f"{self.artifact_path!r}")
        if any(ord(ch) < 0x20 for ch in self.artifact_path):
            raise ValueError(f"artifact_path must not contain control characters: {self.artifact_path!r}")

    def _validate_anchor(self) -> None:
        if self.anchor is not None and (not self.anchor.strip()
                                        or any(ord(ch) < 0x20 for ch in self.anchor)):
            raise ValueError(
                f"anchor must be a non-empty, control-char-free identifier (or None): {self.anchor!r}")

    def to_dict(self) -> Dict[str, object]:
        """Serialise, omitting the optional fields that were not set."""
        out: Dict[str, object] = {"artifact_path": self.artifact_path}
        if self.anchor is not None:
            out["anchor"] = self.anchor
        if self.line is not None:
            out["line"] = self.line
        return out
# @cpt-end:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-locus


# @cpt-begin:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-finding
@dataclass(frozen=True)
class ArtifactFinding:
    """One advisory semantic-quality finding on a Project artifact — the unit every detector emits.

    A finding names its ``detector`` and ``kind``, points at a ``primary`` locus (and a ``related``
    one for pair detectors — duplication, gap, contradiction, traceability), quotes grep-verifiable
    ``evidence``, and offers a ``suggested_action``. It never carries an edit payload or a score.

    ``verdict`` is **detector-namespaced** and ``None`` for structural detectors; ``confidence`` and
    ``evidence_ok`` are meaningful only for judged findings. Constructing an invalid finding raises,
    so a malformed finding never reaches the report.
    """

    detector: str
    severity: str
    kind: str
    message: str
    primary: Locus
    evidence: str = ""
    suggested_action: str = ""
    related: Optional[Locus] = None
    verdict: Optional[str] = None
    evidence_ok: bool = False
    confidence: Optional[str] = None
    schema_version: int = field(default=SCHEMA_VERSION)

    def __post_init__(self) -> None:
        # Reject wrong types before any value check or serialisation touches them (so a bad type
        # fails here, not late in a consumer), then enforce the advisory-contract values.
        self._validate_types()
        self._validate_values()

    def _validate_types(self) -> None:
        for name in ("detector", "severity", "kind", "message", "evidence", "suggested_action"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a str, got {type(getattr(self, name)).__name__}")
        if not isinstance(self.primary, Locus):
            raise TypeError(f"primary must be a Locus, got {type(self.primary).__name__}")
        if self.related is not None and not isinstance(self.related, Locus):
            raise TypeError(f"related must be a Locus or None, got {type(self.related).__name__}")
        for name in ("verdict", "confidence"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a str or None, got {type(value).__name__}")
        if type(self.evidence_ok) is not bool:  # bool is an int subclass, keep it exact
            raise TypeError(f"evidence_ok must be a bool, got {type(self.evidence_ok).__name__}")
        if type(self.schema_version) is not int:  # excludes bool (True == 1)
            raise TypeError(f"schema_version must be an int, got {type(self.schema_version).__name__}")

    def _validate_values(self) -> None:
        if self.detector not in DETECTORS:
            raise ValueError(f"unknown detector {self.detector!r}; expected one of {DETECTORS}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"advisory severity must be one of {SEVERITIES}, got {self.severity!r}")
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")
        if not self.message.strip():
            raise ValueError("message must be non-empty — a finding must explain itself")
        if self.kind == "structural":
            if self.verdict is not None:
                raise ValueError("a structural finding carries no verdict (verdict must be None)")
            if self.confidence is not None or self.evidence_ok:
                raise ValueError("a structural finding carries no judged metadata "
                                 "(confidence must be None, evidence_ok False)")
        if self.kind == "judged" and (self.verdict is None or not self.verdict.strip()):
            raise ValueError("a judged finding must carry a non-empty verdict (or 'unjudgeable')")
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {SCHEMA_VERSION} (the only supported contract), "
                f"got {self.schema_version}")
# @cpt-end:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-finding

    # @cpt-begin:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-finding-serialize
    def to_dict(self) -> Dict[str, object]:
        """Serialise to the wire shape the presentation layer consumes (see ``finding_json_schema``).

        Emits every required key plus ``schema_version``, and the optional ``related`` / ``verdict`` /
        ``confidence`` only when set — the exact shape ``finding_json_schema()`` describes.
        """
        out: Dict[str, object] = {
            "detector": self.detector,
            "severity": self.severity,
            "kind": self.kind,
            "message": self.message,
            "primary": self.primary.to_dict(),
            "evidence": self.evidence,
            "evidence_ok": self.evidence_ok,
            "suggested_action": self.suggested_action,
            "schema_version": self.schema_version,
        }
        if self.related is not None:
            out["related"] = self.related.to_dict()
        if self.verdict is not None:
            out["verdict"] = self.verdict
        if self.confidence is not None:
            out["confidence"] = self.confidence
        return out
    # @cpt-end:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-finding-serialize


# @cpt-begin:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-schema
#: The exact whitespace ``str.strip()`` removes (``str.isspace()``), as a regex character-class body.
#: Anchor/message blankness is decided by ``str.strip()``; enumerating it explicitly — not ECMA
#: ``\s``, which differs on U+0085/U+FEFF/U+001C–1F — lets the wire pattern mirror the constructor
#: exactly under a standards-compliant validator.
_PY_STRIP_WS = r"\t\n\x0b\x0c\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000"

#: The stable JSON contract a presentation/UI layer relies on — obtain a fresh, mutable copy via
#: :func:`finding_json_schema`. Versioned by ``schema_version``; the optional keys (``related`` /
#: ``verdict`` / ``confidence``) appear only when set. There is deliberately no combined-score field
#: and no edit payload — the model is advisory and read-only.
_FINDING_JSON_SCHEMA: Dict[str, object] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "ArtifactFinding",
    "type": "object",
    "additionalProperties": False,
    "required": ["detector", "severity", "kind", "message", "primary", "evidence",
                 "evidence_ok", "suggested_action", "schema_version"],
    "properties": {
        "detector": {"enum": list(DETECTORS)},
        "severity": {"enum": list(SEVERITIES)},
        "kind": {"enum": list(KINDS)},
        # Non-blank: at least one char str.strip() would NOT remove. Explicit class (not ECMA `\S`)
        # so the wire pattern mirrors str.strip() exactly, incl. U+0085/U+FEFF/U+001C-1F.
        "message": {"type": "string", "minLength": 1, "pattern": rf"[^{_PY_STRIP_WS}]"},
        "primary": {"$ref": "#/definitions/locus"},
        "related": {"$ref": "#/definitions/locus"},
        "evidence": {"type": "string"},
        "evidence_ok": {"type": "boolean"},
        "suggested_action": {"type": "string"},
        # Non-blank when present — same explicit str.strip() class as message (not ECMA `\S`, which
        # diverges on U+0085/U+FEFF), so a judged verdict mirrors the constructor exactly.
        "verdict": {"type": "string", "pattern": rf"[^{_PY_STRIP_WS}]"},
        "confidence": {"type": "string"},
        "schema_version": {"const": SCHEMA_VERSION},
    },
    # Mirror the constructor's invariants on the wire so a hand-authored payload (not built through
    # ArtifactFinding) can't smuggle a structural verdict, judged-only metadata on a structural
    # finding, or a verdict-less judged finding past a validator. Per-detector verdict vocabularies
    # are enforced by each detector, not this shared contract.
    "allOf": [
        {"if": {"properties": {"kind": {"const": "structural"}}},
         "then": {"allOf": [{"not": {"required": ["verdict"]}},
                            {"not": {"required": ["confidence"]}},
                            {"properties": {"evidence_ok": {"const": False}}}]}},
        {"if": {"properties": {"kind": {"const": "judged"}}},
         "then": {"required": ["verdict"]}},
    ],
    "definitions": {
        "locus": {
            "type": "object",
            "additionalProperties": False,
            "required": ["artifact_path"],
            "properties": {
                # Canonical project-relative POSIX path: one or more '/'-joined segments, each
                # non-empty, not '.'/'..', and free of '\' and control chars. This mirrors the
                # dataclass's per-segment check (leading, interior AND trailing) — the dataclass is
                # authoritative, but the wire pattern must reject the same set (incl. traversal).
                "artifact_path": {"type": "string",
                                  "pattern": r"^(?![A-Za-z]:(?:/|$))(?!\.\.?(?:/|$))[^/\\\x00-\x1f]+"
                                             r"(?:/(?!\.\.?(?:/|$))[^/\\\x00-\x1f]+)*$"},
                # Non-blank (not all str.strip() whitespace) and control-free. Explicit classes,
                # no ECMA `\s`/`.`, so the wire pattern mirrors the constructor exactly — NEL, BOM,
                # line/paragraph separators all agree with str.strip() / ord < 0x20.
                "anchor": {"type": "string", "minLength": 1,
                           "pattern": rf"^(?![{_PY_STRIP_WS}]*$)[^\x00-\x1f]+$"},
                "line": {"type": "integer", "minimum": 1},
            },
        },
    },
}


def finding_json_schema() -> Dict[str, object]:
    """Return a fresh, mutable deep copy of the wire contract (see ``_FINDING_JSON_SCHEMA``).

    The schema is a shared contract, so it is not exposed as a mutable module global: each caller
    gets its own copy and cannot alter the version other consumers validate against.
    """
    return copy.deepcopy(_FINDING_JSON_SCHEMA)
# @cpt-end:cpt-studio-algo-artifact-quality-finding-model:p1:inst-aq-schema
