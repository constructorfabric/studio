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
from typing import Dict, Optional

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
    # Four of them come from ``_validate_cdsl_step`` (utils/constraints.py) and
    # are a deliberate, tracked backlog concession rather than a judgement that
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
    EC.HEADING_REQUIRES_MULTIPLE:               ERROR,
    EC.HEADING_NUMBERING_MISMATCH:              ERROR,
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
    registry = {
        value for name, value in vars(EC).items()
        if name.isupper() and isinstance(value, str)
    }
    missing = sorted(registry - set(DEFAULT_SEVERITY))
    orphaned = sorted(set(DEFAULT_SEVERITY) - registry)
    if missing or orphaned:
        raise RuntimeError(
            "DEFAULT_SEVERITY is out of step with error_codes: "
            f"missing={missing} orphaned={orphaned}"
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
