"""Severity as a property of a validation finding.

Before this module, a finding's severity was not data: it was decided by *which
list the call site appended to*, in about fourteen places across
``utils/constraints.py``, ``utils/toc.py``, ``commands/validate.py`` and
``commands/self_check.py``. That made severity impossible to configure, because
there was nothing to configure — only control flow.

Every finding is now stamped from ``DEFAULT_SEVERITY`` at build time. The table
reproduces today's routing exactly: the twelve codes currently sent to
``warnings`` default to ``warning``, every other code defaults to ``error``.
Stamping from a table rather than from a keyword default is what makes that
equivalence testable — a keyword default would silently agree with whatever the
call site already did.

The table is exhaustive over ``error_codes`` on purpose. A shorter table plus a
fallback would give every code *a* default while pinning only a handful, and a
rule shipped as ``warning`` when it should be ``error`` keeps every "fails on
bad input" test green, because those tests assert exit codes and message text
rather than the label itself.

@cpt-algo:cpt-studio-algo-traceability-validation-severity-policy:p1
"""

# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-imports
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import error_codes as EC
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-imports

# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-vocabulary
# ---------------------------------------------------------------------------
# The severity vocabulary
# ---------------------------------------------------------------------------
# ``off`` is declared here but no code defaults to it yet: suppression arrives
# with the configuration layer. Declaring the full vocabulary now keeps the
# stamped field and the configured field one type rather than two.
#
# Named ``VALIDATION_SEVERITIES`` rather than ``SEVERITIES`` because
# ``utils/artifact_quality.py`` already exports a ``SEVERITIES`` for advisory
# findings (``info`` / ``warn``) — a different vocabulary for a different model,
# and one name for both would invite the wrong import.
ERROR = "error"
WARNING = "warning"
OFF = "off"

VALIDATION_SEVERITIES = (ERROR, WARNING, OFF)
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-vocabulary

# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-default-table
# ---------------------------------------------------------------------------
# Default severity per rule code — exhaustive over ``error_codes``
# ---------------------------------------------------------------------------
DEFAULT_SEVERITY: Dict[str, str] = {
    # --- warning by default: reproduces today's routing exactly -------------
    # Each entry below corresponds to a call site that appends to ``warnings``.
    #
    # Four of them come from ``_validate_cdsl_step_candidate``
    # (utils/constraints.py:1340) and are a deliberate, tracked backlog
    # concession rather than a judgement that
    # the rules are advisory in principle. They are two distinct groups, both
    # intentional here:
    #   - the missing-token trio, CDSL.md S.3 / S.4 / S.5, one per absent token;
    #   - CDSL_INCOMPLETE_STEP_LINE, CDSL.md CO.4, emitted once *alongside* the
    #     trio when any token is missing — not a member of it.
    EC.CDSL_MISSING_CHECKBOX:                   WARNING,
    EC.CDSL_MISSING_PHASE_TOKEN:                WARNING,
    EC.CDSL_MISSING_INST_ID:                    WARNING,
    EC.CDSL_INCOMPLETE_STEP_LINE:               WARNING,
    EC.TOC_HEADING_DUPLICATE:                   WARNING,
    EC.TOC_HEADING_DEPTH_JUMP:                  WARNING,
    EC.TOC_SECTION_TOO_LONG:                    WARNING,
    EC.TOC_MISSING_DESCRIPTION:                 WARNING,
    EC.TOC_STALE:                               WARNING,
    EC.REF_TARGET_NOT_IN_SCOPE:                 WARNING,
    EC.ID_NOT_REFERENCED_NO_SCOPE:              WARNING,
    EC.CODEBASE_ENTRY_EMPTY:                    WARNING,
    # The optional half of each template-placeholder pair; the required half is
    # an error below. Two codes rather than one code at two severities.
    EC.TEMPLATE_DEF_PLACEHOLDER_MISSING_OPTIONAL: WARNING,
    EC.TEMPLATE_REF_PLACEHOLDER_MISSING_OPTIONAL: WARNING,
    # Advisory today: a kind whose template/examples cannot be bound is reported
    # with status PASS and warning_count 1 by validate-kits.
    EC.KIT_TEMPLATE_BINDING_MISSING:            WARNING,
    # A `[validation]` key this engine does not know. Warning, so that a kit
    # written for a newer engine stays installable on an older one — but never
    # silence, or the kit author keeps believing a policy is in force.
    EC.CONSTRAINTS_UNKNOWN_KEY:                 WARNING,

    # --- error by default ---------------------------------------------------
    EC.TEMPLATE_DEF_PLACEHOLDER_MISSING:        ERROR,
    EC.TEMPLATE_REF_PLACEHOLDER_MISSING:        ERROR,
    EC.TEMPLATE_ID_KIND_NO_TEMPLATE:            ERROR,
    EC.TEMPLATE_DEF_PLACEHOLDER_WRONG_HEADINGS: ERROR,
    EC.TEMPLATE_REF_PLACEHOLDER_WRONG_HEADINGS: ERROR,
    EC.TEMPLATE_READ_ERROR:                     ERROR,
    EC.CONSTRAINTS_INVALID:                     ERROR,
    EC.KIT_RESOURCE_PATH_NOT_FOUND:             ERROR,
    EC.KIT_MODEL_INVALID:                       ERROR,
    EC.KIT_PATH_NOT_ACCESSIBLE:                 ERROR,
    EC.KIT_BINDING_ERROR:                       ERROR,
    EC.REGISTRY_AUTODETECT_INVALID:             ERROR,
    EC.REGISTRY_AUTODETECT_FAILED:              ERROR,
    EC.CDSL_STEP_UNCHECKED:                     ERROR,
    EC.PARENT_UNCHECKED_ALL_DONE:               ERROR,
    EC.PARENT_CHECKED_NESTED_UNCHECKED:         ERROR,
    EC.REF_NO_DEFINITION:                       ERROR,
    EC.REF_DONE_DEF_NOT_DONE:                   ERROR,
    EC.DEF_DONE_REF_NOT_DONE:                   ERROR,
    EC.REF_TASK_DEF_NO_TASK:                    ERROR,
    EC.DUPLICATE_DEFINITION:                    ERROR,
    EC.HEADING_NUMBER_NOT_CONSECUTIVE:          ERROR,
    EC.ID_NOT_REFERENCED:                       ERROR,
    EC.MISSING_CONSTRAINTS:                     ERROR,
    EC.ID_SYSTEM_UNRECOGNIZED:                  ERROR,
    EC.ID_KIND_NOT_ALLOWED:                     ERROR,
    EC.REQUIRED_ID_KIND_MISSING:                ERROR,
    EC.TEMPLATE_DEF_KIND_NOT_IN_CONSTRAINTS:    ERROR,
    EC.TEMPLATE_REF_KIND_NOT_IN_CONSTRAINTS:    ERROR,
    EC.DEF_MISSING_TASK:                        ERROR,
    EC.DEF_PROHIBITED_TASK:                     ERROR,
    EC.DEF_MISSING_PRIORITY:                    ERROR,
    EC.DEF_PROHIBITED_PRIORITY:                 ERROR,
    EC.DEF_WRONG_HEADINGS:                      ERROR,
    EC.HEADING_MISSING:                         ERROR,
    EC.HEADING_PROHIBITS_MULTIPLE:              ERROR,
    # Off by default: "at least two" enforced everywhere would fail every
    # document with a single flow, state or definition of done. A kit that
    # means it turns the rule on for the kinds where it holds.
    EC.HEADING_REQUIRES_MULTIPLE:               OFF,
    EC.HEADING_NUMBERING_MISMATCH:              ERROR,
    EC.HEADING_ORDER_VIOLATION:                 ERROR,
    EC.REF_MISSING_FROM_KIND:                   ERROR,
    EC.REF_WRONG_HEADINGS:                      ERROR,
    EC.REF_MISSING_TASK_FOR_TRACKED:            ERROR,
    EC.REF_FROM_PROHIBITED_KIND:                ERROR,
    EC.REF_MISSING_TASK:                        ERROR,
    EC.REF_PROHIBITED_TASK:                     ERROR,
    EC.REF_MISSING_PRIORITY:                    ERROR,
    EC.REF_PROHIBITED_PRIORITY:                 ERROR,
    EC.MARKER_DUP_BEGIN:                        ERROR,
    EC.MARKER_END_NO_BEGIN:                     ERROR,
    EC.MARKER_EMPTY_BLOCK:                      ERROR,
    EC.MARKER_BEGIN_NO_END:                     ERROR,
    EC.MARKER_DUP_SCOPE:                        ERROR,
    EC.CODE_DOCS_ONLY:                          ERROR,
    EC.CODE_ORPHAN_REF:                         ERROR,
    EC.CODE_TASK_UNCHECKED:                     ERROR,
    EC.CODE_NO_MARKER:                          ERROR,
    EC.CODE_INST_MISSING:                       ERROR,
    EC.CODE_INST_ORPHAN:                        ERROR,
    EC.TOC_MISSING:                             ERROR,
    EC.TOC_ANCHOR_BROKEN:                       ERROR,
    EC.TOC_HEADING_NOT_IN_TOC:                  ERROR,
    EC.FILE_READ_ERROR:                         ERROR,
    EC.FILE_LOAD_ERROR:                         ERROR,
    EC.FILE_TOO_LARGE:                          ERROR,
    EC.CONTENT_LANGUAGE_VIOLATION:              ERROR,
    EC.CDSL_CODE_SYNTAX:                        ERROR,
    EC.CDSL_TYPE_ANNOTATION:                    ERROR,
    EC.CDSL_LANGUAGE_OPERATOR:                  ERROR,
    EC.CDSL_NOT_PLAIN_ENGLISH:                  ERROR,
    EC.CDSL_DUPLICATE_INST_ID:                  ERROR,
    EC.CDSL_PLACEHOLDER:                        ERROR,
}
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-default-table


def _assert_table_covers_registry() -> None:
    """Fail at import if the table and ``error_codes`` have drifted apart.

    The docstring above promises exhaustiveness; a test alone cannot keep that
    promise, because production never runs the tests. A code added to the
    registry without a default would otherwise fall back to ``error`` silently
    — correct in direction, but unreviewed — and an entry left behind after a
    code was removed would pin a default nothing can ever emit.
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-exhaustive-guard
    # Carry the attribute name, not just the value: `missing=['1.0']` gives a
    # reader nothing, while `SCHEMA_VERSION = '1.0'` says at a glance that the
    # constant is not a rule code and belongs elsewhere — which is the whole
    # difference between diagnosing this and "fixing" it with a bogus default.
    # Pairs rather than a dict, so two constants sharing a value both appear.
    registry_pairs = [
        (name, value) for name, value in vars(EC).items()
        if name.isupper() and isinstance(value, str)
    ]
    missing = sorted(
        f"{name} = {value!r}"
        for name, value in registry_pairs
        if value not in DEFAULT_SEVERITY
    )
    # Orphans have no attribute name by definition — that is what makes them
    # orphans — so the value is the whole identity and is listed bare.
    orphaned = sorted(set(DEFAULT_SEVERITY) - {value for _, value in registry_pairs})
    if missing or orphaned:
        raise RuntimeError(
            "DEFAULT_SEVERITY is out of step with error_codes: "
            f"missing={missing} orphaned={orphaned}. "
            "Every uppercase string constant in error_codes.py is a rule code and "
            "needs a default here; a constant that is not a rule code does not "
            "belong in that module."
        )
    # @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-exhaustive-guard


_assert_table_covers_registry()


def reject_caller_severity(extra: Dict[str, object]) -> None:
    """Refuse a caller-supplied ``severity``; the table is the only source.

    Both finding builders stamp severity and then splat ``**extra`` over the
    result, so a call site passing ``severity=`` would silently win over the
    declared default. No call site does today — this raises so none can start
    without being told, which is the whole guarantee this module exists to make.
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-reject-override
    if "severity" in extra:
        raise TypeError(
            "severity is derived from the finding's code, not passed by the caller: "
            f"remove severity={extra['severity']!r} and rely on DEFAULT_SEVERITY"
        )
    # @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-reject-override


def default_severity(code: Optional[str]) -> str:
    """Return the declared default severity for ``code``.

    An absent or unrecognised code resolves to ``error``. That direction is
    deliberate: an unknown rule must not become silently non-blocking, which is
    the failure mode this whole model exists to make impossible.
    """
    # @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-resolve-default
    if code:
        declared = DEFAULT_SEVERITY.get(code)
        if declared is not None:
            return declared
    # @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-resolve-default
    # @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-unknown-is-error
    return ERROR
    # @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-unknown-is-error


# ---------------------------------------------------------------------------
# Configured policy: the layers above the built-in default
# ---------------------------------------------------------------------------

# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-strictness
#: Severity ordered by how much it blocks. Comparing on this is what lets a
#: raise be told from a lowering, which is the whole basis of the locking rule.
_STRICTNESS: Dict[str, int] = {OFF: 0, WARNING: 1, ERROR: 2}

#: Where a resolved severity came from, most specific first. Reported verbatim
#: by ``--explain-severity``, so these are part of the CLI contract.
SOURCE_ENTRY = "entry"
SOURCE_PROJECT_KIND = "project-kind"
SOURCE_PROJECT = "project"
SOURCE_KIT_KIND = "kit-kind"
SOURCE_KIT = "kit"
SOURCE_DEFAULT = "default"


def is_stricter(candidate: str, than: str) -> bool:
    """Return whether ``candidate`` blocks more than ``than``."""
    return _STRICTNESS.get(candidate, 2) > _STRICTNESS.get(than, 2)
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-strictness


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-parse-value
def parse_severity_value(value: object, where: str, errors: List[str]) -> Optional[str]:
    """Parse one configured severity, recording a message when it is not one.

    An unrecognised value fails the load rather than falling back. The
    opposite reflex — treat the unfamiliar as "no opinion" and carry on — is
    right when the unknown merely *describes* an outcome, and wrong here,
    because this value *disables checking*: a typo would silently switch a rule
    off and the run would still report success.
    """
    if not isinstance(value, str):
        errors.append(f"{where} must be a string, one of {', '.join(VALIDATION_SEVERITIES)}")
        return None
    normalized = value.strip().lower()
    if normalized not in VALIDATION_SEVERITIES:
        errors.append(
            f"{where} is {value!r}, which is not a severity; "
            f"expected one of {', '.join(VALIDATION_SEVERITIES)}"
        )
        return None
    return normalized
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-parse-value


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-policy-model
@dataclass(frozen=True)
class SeverityTables:
    """One layer of configured severity: whole-scope, and per artifact kind.

    ``unknown_keys`` records keys found under ``[validation]`` that this
    version does not understand. They are carried rather than dropped so
    ``validate-kits`` can report them: the kind parser's habit of silently
    ignoring what it does not recognise is how a misspelled rule name turns
    into a rule nobody is enforcing and nobody is told about.
    """

    by_code: Dict[str, str] = field(default_factory=dict)
    by_kind: Dict[str, Dict[str, str]] = field(default_factory=dict)
    fail_on_warnings: bool = False
    unknown_keys: Tuple[str, ...] = ()

    def is_empty(self) -> bool:
        """Return whether this layer configures nothing at all."""
        return not self.by_code and not self.by_kind and not self.fail_on_warnings


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-entry-key
#: The two kinds of constraint entry that can declare a severity. They share a
#: namespace per artifact kind but not a key: a heading whose id is
#: ``requirement`` and an ID kind named ``requirement`` are different entries,
#: and merging them would let one silently inherit the other's lock.
ENTRY_HEADING = "heading"
ENTRY_IDENTIFIER = "identifier"

#: An entry key: (entry type, normalised entry id).
EntryKey = Tuple[str, str]


def entry_key(entry_type: str, entry_id: object) -> Optional[EntryKey]:
    """Build the lookup key for one constraint entry, or None if it has no id.

    Ids are case-folded on both sides. Heading ids are already normalised by
    the constraint loader, but an ID kind is stored as the author typed it in
    ``[artifacts.PRD.identifiers.FR]`` while every emission site lowercases it
    before attaching it to a finding — so without folding here, an entry
    declared in capitals would configure a rule nothing ever matches.
    """
    normalized = str(entry_id or "").strip().lower()
    if not normalized:
        return None
    return (entry_type, normalized)
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-entry-key


@dataclass(frozen=True)
class EntrySeverity:
    """A severity declared on one constraint entry, and whether it is locked."""

    severity: Optional[str] = None
    locked: bool = False


@dataclass(frozen=True)
class SeverityDecision:
    """The effective severity for one rule, and the account of how it got there."""

    severity: str
    source: str
    #: Set when a project layer lowered the kit-side value, to what it lowered from.
    lowered_from: Optional[str] = None
    #: Set when a project layer tried to lower a locked entry and was refused.
    refused_from: Optional[str] = None
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-policy-model


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-policy-resolve
@dataclass(frozen=True)
class SeverityPolicy:
    """Resolved severity for any (code, kind, entry), across every layer.

    Two layers, not six: everything the *kit* declares (entry, per-kind, whole
    kit, built-in default) settles first into one kit-side value, and then the
    *project* layer is admitted against it under the raise/lower rule. Reading
    it as six layers of plain specificity cannot be right — the entry is the
    most specific declaration of all, so a project could never override one,
    and ``locked`` would have nothing to mean.
    """

    kit: SeverityTables = field(default_factory=SeverityTables)
    project: SeverityTables = field(default_factory=SeverityTables)
    #: kind -> entry id (heading id or ID kind) -> declared severity and lock.
    entries: Dict[str, Dict[str, EntrySeverity]] = field(default_factory=dict)

    @property
    def fail_on_warnings(self) -> bool:
        """Return whether warnings alone should fail the run."""
        return bool(self.project.fail_on_warnings)

    def is_configured(self) -> bool:
        """Return whether any layer configures a severity."""
        return bool(
            not self.kit.is_empty()
            or not self.project.is_empty()
            or any(self.entries.values())
        )

    def _entry(self, kind: Optional[str], key: Optional[EntryKey]) -> EntrySeverity:
        if not kind or not key:
            return EntrySeverity()
        return self.entries.get(str(kind).strip().upper(), {}).get(key, EntrySeverity())

    def entry_keys_for(self, kind: Optional[str]) -> List[EntryKey]:
        """List the entries that declare anything for ``kind``, in a stable order."""
        if not kind:
            return []
        return sorted(self.entries.get(str(kind).strip().upper(), {}))

    def _kit_side(
        self,
        code: Optional[str],
        kind: Optional[str],
        entry: EntrySeverity,
    ) -> Tuple[str, str]:
        """Settle the kit's own opinion: entry, then per-kind, then kit, then default."""
        if entry.severity:
            return entry.severity, SOURCE_ENTRY
        normalized_kind = str(kind).strip().upper() if kind else ""
        if code and normalized_kind:
            per_kind = self.kit.by_kind.get(normalized_kind, {}).get(code)
            if per_kind:
                return per_kind, SOURCE_KIT_KIND
        if code:
            whole_kit = self.kit.by_code.get(code)
            if whole_kit:
                return whole_kit, SOURCE_KIT
        return default_severity(code), SOURCE_DEFAULT

    def _project_side(self, code: Optional[str], kind: Optional[str]) -> Tuple[Optional[str], str]:
        normalized_kind = str(kind).strip().upper() if kind else ""
        if code and normalized_kind:
            per_kind = self.project.by_kind.get(normalized_kind, {}).get(code)
            if per_kind:
                return per_kind, SOURCE_PROJECT_KIND
        if code:
            whole_project = self.project.by_code.get(code)
            if whole_project:
                return whole_project, SOURCE_PROJECT
        return None, SOURCE_PROJECT

    def resolve(
        self,
        code: Optional[str],
        kind: Optional[str] = None,
        key: Optional[EntryKey] = None,
    ) -> SeverityDecision:
        """Return the effective severity for one rule and the layer that set it."""
        entry = self._entry(kind, key)
        kit_value, kit_source = self._kit_side(code, kind, entry)
        project_value, project_source = self._project_side(code, kind)
        if project_value is None or project_value == kit_value:
            return SeverityDecision(severity=kit_value, source=kit_source)
        # @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-raise-lower
        if is_stricter(project_value, kit_value):
            # Raising is always allowed: a project may hold itself to more than
            # the kit asks for without the kit's permission.
            return SeverityDecision(severity=project_value, source=project_source)
        if entry.locked:
            return SeverityDecision(
                severity=kit_value,
                source=kit_source,
                refused_from=project_value,
            )
        return SeverityDecision(
            severity=project_value,
            source=project_source,
            lowered_from=kit_value,
        )
        # @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-raise-lower
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-policy-resolve


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-declared-overrides
def declared_overrides(policy: SeverityPolicy) -> List[Dict[str, object]]:
    """List every project setting that lowers a rule, or was refused for trying.

    Derived from the *configuration*, not from what happened to be emitted. A
    rule lowered to ``off`` produces no finding at all, and that is precisely
    the case a reader most needs to see named; an occurrence-based list would
    be silent about exactly the setting that silenced everything else.
    """
    rows: List[Dict[str, object]] = []
    seen: Set[Tuple[object, ...]] = set()
    for scope_kind, code in _configured_project_pairs(policy):
        rows.extend(_overrides_for_setting(policy, scope_kind, code, seen))
    # Sorted by what a reader scans for, not by dict order: goldens hide an
    # ordering bug behind whatever insertion order the config happened to have.
    rows.sort(key=lambda row: (str(row["kind"] or ""), str(row["code"]), str(row["entry"] or "")))
    return rows


def _overrides_for_setting(
    policy: SeverityPolicy,
    scope_kind: Optional[str],
    code: str,
    seen: Set[Tuple[object, ...]],
) -> List[Dict[str, object]]:
    """Rows for one configured (kind, code) setting: unscoped, then per entry.

    An entry that declares a stricter severity than its kind's table is lowered
    by a project setting that leaves the kind-level value untouched, so
    resolving only without an entry would report no lowering at all while the
    entry's own rules were quietly relaxed.
    """
    rows: List[Dict[str, object]] = []
    unscoped = policy.resolve(code, scope_kind)
    baseline: Optional[Tuple[object, object, object]] = None
    if unscoped.lowered_from is not None or unscoped.refused_from is not None:
        row = override_row(code, scope_kind, None, unscoped)
        baseline = (row["from"], row["to"], row["applied"])
        rows.append(row)
        seen.add((scope_kind, code, None))
    for entry_kind, key in _override_entry_keys(policy, scope_kind):
        row = _entry_override_row(policy, entry_kind, code, key, baseline, seen)
        if row is not None:
            rows.append(row)
    return rows


def _entry_override_row(
    policy: SeverityPolicy,
    entry_kind: str,
    code: str,
    key: EntryKey,
    baseline: Optional[Tuple[object, object, object]],
    seen: Set[Tuple[object, ...]],
) -> Optional[Dict[str, object]]:
    """One entry's row, or None when it adds nothing the reader needs.

    Resolved against the entry's *own* artifact kind. A whole-project setting
    has no kind of its own, and passing None here is what made the entry
    invisible: ``_entry`` needs the kind to find it, so every entry-specific
    override under an unscoped setting — including a locked entry's refusal —
    resolved as though no entry existed.
    """
    decision = policy.resolve(code, entry_kind, key)
    if decision.lowered_from is None and decision.refused_from is None:
        return None
    identity = (entry_kind, code, key)
    if identity in seen:
        return None
    row = override_row(code, entry_kind, key, decision)
    if baseline == (row["from"], row["to"], row["applied"]):
        # Says exactly what the unscoped row already said: an entry that merely
        # inherits the setting would otherwise turn one decision into as many
        # lines as the kit has entries, burying the entries that differ.
        return None
    seen.add(identity)
    return row


def _override_entry_keys(
    policy: SeverityPolicy,
    kind: Optional[str],
) -> List[Tuple[str, EntryKey]]:
    """Entries a setting for ``kind`` could reach, each with its own kind.

    The artifact kind travels with the key because resolution needs it: an
    unscoped project setting reaches entries in every kind, and each must be
    resolved against the kind that owns it rather than against no kind at all.
    """
    kinds = [str(kind).strip().upper()] if kind else sorted(policy.entries)
    return [
        (entry_kind, key)
        for entry_kind in kinds
        for key in policy.entry_keys_for(entry_kind)
    ]


def _configured_project_pairs(policy: SeverityPolicy) -> List[Tuple[Optional[str], str]]:
    pairs: List[Tuple[Optional[str], str]] = [(None, code) for code in sorted(policy.project.by_code)]
    for kind in sorted(policy.project.by_kind):
        pairs.extend((kind, code) for code in sorted(policy.project.by_kind[kind]))
    return pairs


def override_row(
    code: Optional[str],
    kind: Optional[str],
    key: Optional[EntryKey],
    decision: SeverityDecision,
) -> Dict[str, object]:
    """Render one lowering or refusal for the report and for ``--explain-severity``."""
    return {
        "code": code,
        "kind": kind,
        "entry": f"{key[0]}:{key[1]}" if key else None,
        "from": decision.lowered_from or decision.severity,
        "to": decision.refused_from or decision.severity,
        "applied": decision.refused_from is None,
        "source": decision.source,
    }
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-declared-overrides


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-apply
@dataclass
class PolicyOutcome:
    """Findings after policy, partitioned by the severity they now carry."""

    errors: List[Dict[str, object]] = field(default_factory=list)
    warnings: List[Dict[str, object]] = field(default_factory=list)
    suppressed: int = 0
    #: Lowerings the kit refused, as they were met. Refusals are reported from
    #: what actually happened rather than from the configuration, because a
    #: locked entry only refuses the rules that entry owns, and which rules
    #: those are is not something the tables can be asked ahead of time.
    refusals: List[Dict[str, object]] = field(default_factory=list)


def _finding_entry_key(finding: Dict[str, object]) -> Optional[EntryKey]:
    """Return the constraint entry a finding belongs to, if it names one.

    The two fields are checked separately rather than as one namespace: a
    heading whose id is ``requirement`` and an ID kind named ``requirement``
    are different entries, and one must not inherit the other's severity.
    """
    for field_name, entry_type in (("heading_id", ENTRY_HEADING), ("id_kind", ENTRY_IDENTIFIER)):
        value = finding.get(field_name)
        if isinstance(value, str) and value.strip():
            return entry_key(entry_type, value)
    return None


def apply_policy(
    policy: Optional[SeverityPolicy],
    findings: Iterable[Dict[str, object]],
    *,
    kind: Optional[str] = None,
) -> PolicyOutcome:
    """Restamp findings from ``policy``, drop the suppressed, repartition the rest.

    Re-running this over an already-applied list is a no-op: resolution is a
    function of the finding's own code, kind and entry, and a suppressed
    finding is gone rather than marked, so nothing can be counted twice. That
    is what lets the artifact pass apply the kind it knows and the command
    level sweep up everything else without either having to know about the
    other.
    """
    outcome = PolicyOutcome()
    seen_refusals: Set[Tuple[object, ...]] = set()
    for finding in findings:
        severity = _settle_finding(policy, finding, kind, outcome, seen_refusals)
        if severity == OFF:
            outcome.suppressed += 1
            continue
        finding["severity"] = severity
        bucket = outcome.warnings if severity == WARNING else outcome.errors
        bucket.append(finding)
    return outcome


def _settle_finding(
    policy: Optional[SeverityPolicy],
    finding: Dict[str, object],
    kind: Optional[str],
    outcome: PolicyOutcome,
    seen_refusals: Set[Tuple[object, ...]],
) -> str:
    """Return one finding's effective severity, recording any refusal it met."""
    code = finding.get("code")
    normalized_code = code if isinstance(code, str) else None
    if policy is None:
        return str(finding.get("severity") or default_severity(normalized_code))
    finding_kind = finding.get("artifact_kind") or kind
    normalized_kind = str(finding_kind) if finding_kind else None
    key = _finding_entry_key(finding)
    decision = policy.resolve(normalized_code, normalized_kind, key)
    _record_refusal(outcome, seen_refusals, normalized_code, normalized_kind, key, decision)
    return decision.severity


def _record_refusal(
    outcome: PolicyOutcome,
    seen_refusals: Set[Tuple[object, ...]],
    code: Optional[str],
    kind: Optional[str],
    key: Optional[EntryKey],
    decision: SeverityDecision,
) -> None:
    """Record a refused lowering once per rule, however many findings met it."""
    if decision.refused_from is None:
        return
    identity = (code, kind, key)
    if identity in seen_refusals:
        return
    seen_refusals.add(identity)
    outcome.refusals.append(override_row(code, kind, key, decision))
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-apply


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-exit-code
@dataclass(frozen=True)
class RunVerdict:
    """The one verdict shared by ``validate``, ``validate-kits`` and ``validate-toc``."""

    status: str
    exit_code: int
    #: Present only when warnings alone decided the outcome, so a reader can
    #: tell a genuine failure from a `--fail-on-warnings` run at a glance.
    failed_on: Optional[str] = None


def run_verdict(
    error_count: int,
    warning_count: int,
    *,
    fail_on_warnings: bool = False,
    pass_status: str = "PASS",
    fail_status: str = "FAIL",
    warn_status: Optional[str] = None,
) -> RunVerdict:
    """Decide status and exit code from the counts alone.

    Without ``fail_on_warnings`` the exit code is a function of the error count
    and nothing else — that is the invariant the whole severity model rests on,
    and the reason it is decided in one place rather than three.
    """
    if error_count:
        return RunVerdict(status=fail_status, exit_code=2)
    if warning_count and fail_on_warnings:
        return RunVerdict(status=fail_status, exit_code=2, failed_on="warnings")
    if warning_count and warn_status:
        return RunVerdict(status=warn_status, exit_code=0)
    return RunVerdict(status=pass_status, exit_code=0)
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-exit-code


# @cpt-begin:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-parse-tables
#: Keys understood under a ``[validation]`` table. Anything else is reported.
_KIT_VALIDATION_KEYS = frozenset({"severity"})
#: What a kit's `[artifacts.<KIND>.validation]` may carry. `toc` is read by the
#: constraints loader rather than here — TOC depth is not a severity — but it
#: is named in this set so it is not reported as a key this engine does not
#: understand. Per-kind only: how deep a document's outline goes is a property
#: of the kind, like the `toc` switch it configures, and a whole-kit default
#: would be a second answer to that question with no rule for which one wins.
_KIT_KIND_VALIDATION_KEYS = frozenset({"severity", "toc"})
_PROJECT_VALIDATION_KEYS = frozenset({"severity", "fail_on_warnings"})


def is_known_rule_code(code: str) -> bool:
    """Return whether ``code`` is a rule this engine actually has.

    ``DEFAULT_SEVERITY`` is exhaustive over the registry by construction and
    guarded at import, so it doubles as the list of every code that exists.
    """
    return code in DEFAULT_SEVERITY


def _parse_severity_table(
    raw: object,
    where: str,
    errors: List[str],
    unknown: List[str],
    *,
    allow_kinds: bool = True,
) -> Tuple[Dict[str, str], Dict[str, Dict[str, str]]]:
    """Split one ``[...severity]`` table into per-code and per-kind entries.

    A string value names a rule code; a table value names an artifact kind.

    A key naming no rule this engine has is collected into ``unknown`` rather
    than accepted in silence. The registry is closed and guarded at import, so
    a misspelled code is knowable here — and a misspelling accepted quietly is
    a policy its author believes is in force and the engine has never seen,
    which is the same failure the unknown-key check above exists to prevent,
    one level down.
    """
    by_code: Dict[str, str] = {}
    by_kind: Dict[str, Dict[str, str]] = {}
    if raw is None:
        return by_code, by_kind
    if not isinstance(raw, dict):
        errors.append(f"{where} must be a table of rule codes")
        return by_code, by_kind
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            # Fail closed, like an unreadable value: a blank key configures
            # nothing and cannot be reported back to its author by name.
            errors.append(f"{where} has a blank key; a rule code or artifact kind is required")
            continue
        if isinstance(value, dict):
            _parse_nested_kind_table(
                name, value, where, errors, unknown, by_kind, allow_kinds=allow_kinds)
            continue
        parsed = parse_severity_value(value, f"{where}.{name}", errors)
        if parsed is None:
            continue
        if not is_known_rule_code(name):
            unknown.append(f"{where}.{name}")
            continue
        by_code[name] = parsed
    return by_code, by_kind


def _parse_nested_kind_table(
    name: str,
    value: Dict[str, object],
    where: str,
    errors: List[str],
    unknown: List[str],
    by_kind: Dict[str, Dict[str, str]],
    *,
    allow_kinds: bool,
) -> None:
    if not allow_kinds:
        # This table is already scoped to one kind; a kind inside it would be
        # two answers to the same question with no rule for which one wins.
        errors.append(f"{where}.{name} takes rule codes, not artifact kinds")
        return
    nested_code, nested_kind = _parse_severity_table(
        value, f"{where}.{name}", errors, unknown, allow_kinds=False)
    if nested_kind:
        errors.append(f"{where}.{name} may not nest another artifact kind")
        return
    if nested_code:
        by_kind.setdefault(name.upper(), {}).update(nested_code)


def _parse_validation_table(
    raw: object,
    where: str,
    known_keys: Set[str],
    errors: List[str],
    *,
    allow_kinds: bool = True,
) -> SeverityTables:
    if raw is None:
        return SeverityTables()
    if not isinstance(raw, dict):
        errors.append(f"{where} must be a table")
        return SeverityTables()
    unknown = [f"{where}.{key}" for key in sorted(raw) if str(key) not in known_keys]
    by_code, by_kind = _parse_severity_table(
        raw.get("severity"), f"{where}.severity", errors, unknown, allow_kinds=allow_kinds)
    fail_on_warnings = False
    if "fail_on_warnings" in known_keys and "fail_on_warnings" in raw:
        value = raw.get("fail_on_warnings")
        if isinstance(value, bool):
            fail_on_warnings = value
        else:
            errors.append(f"{where}.fail_on_warnings must be boolean")
    return SeverityTables(
        by_code=by_code,
        by_kind=by_kind,
        fail_on_warnings=fail_on_warnings,
        unknown_keys=tuple(sorted(unknown)),
    )


def parse_kit_validation(
    raw: object,
    errors: List[str],
    *,
    where: str = "[validation]",
    allow_kinds: bool = True,
) -> SeverityTables:
    """Parse a kit's ``[validation]`` table from ``constraints.toml``.

    ``allow_kinds`` is false for a table already scoped to one artifact kind —
    the same condition under which `toc` is a key, so it selects the key set
    too rather than being asked twice in two ways.
    """
    known = _KIT_VALIDATION_KEYS if allow_kinds else _KIT_KIND_VALIDATION_KEYS
    return _parse_validation_table(
        raw, where, set(known), errors, allow_kinds=allow_kinds)


def parse_project_validation(raw: object, errors: List[str]) -> SeverityTables:
    """Parse a project's ``[validation]`` table from ``core.toml``."""
    return _parse_validation_table(raw, "[validation]", set(_PROJECT_VALIDATION_KEYS), errors)


def merge_severity_tables(layers: Sequence[SeverityTables]) -> SeverityTables:
    """Merge one layer per kit, strictest-wins, matching how ``required`` merges.

    Each layer is one kit's complete opinion — its whole-kit table and its
    kind-scoped tables together. Two kits bound into one project are both
    authorities, and taking the stricter of their opinions is the only merge
    that cannot quietly relax a rule one of them meant to enforce.

    Within a layer, specificity decides and strictness does not: a kit that
    says ``warning`` generally and ``off`` for PRD means ``off`` for PRD. That
    is the whole point of a per-kind table, and it is what the resolver's own
    precedence does. Strictness only arbitrates *between* kits, where nobody
    has agreed to be overruled.
    """
    by_code: Dict[str, str] = {}
    for layer in layers:
        for code, severity in layer.by_code.items():
            _keep_stricter(by_code, code, severity)
    by_kind: Dict[str, Dict[str, str]] = {}
    for kind in {kind for layer in layers for kind in layer.by_kind}:
        by_kind[kind] = _merge_kind_across_layers(layers, kind)
    return SeverityTables(
        by_code=by_code,
        by_kind=by_kind,
        unknown_keys=tuple(sorted({key for layer in layers for key in layer.unknown_keys})),
    )


def _merge_kind_across_layers(layers: Sequence[SeverityTables], kind: str) -> Dict[str, str]:
    """Strictest of each layer's *effective* value for one artifact kind.

    A layer's effective value is its kind-scoped entry if it has one, else its
    whole-kit entry, else no opinion at all. Comparing effective values is what
    stops kit A's whole-kit ``error`` losing to kit B's PRD-scoped ``off``
    purely because the two landed in different tables — while still letting a
    single kit's own per-kind entry override its own whole-kit one.
    """
    merged: Dict[str, str] = {}
    for code in {code for layer in layers for code in layer.by_kind.get(kind, {})}:
        for layer in layers:
            effective = layer.by_kind.get(kind, {}).get(code) or layer.by_code.get(code)
            if effective:
                _keep_stricter(merged, code, effective)
    return merged


def _keep_stricter(table: Dict[str, str], code: str, severity: str) -> None:
    existing = table.get(code)
    if existing is None or is_stricter(severity, existing):
        table[code] = severity
# @cpt-end:cpt-studio-algo-traceability-validation-severity-policy:p1:inst-severity-parse-tables
