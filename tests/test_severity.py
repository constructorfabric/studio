"""Tests for studio.utils.severity — severity as a property of a finding.

Covers:
- DEFAULT_SEVERITY pinned as a whole-table golden, compared by value
- every error_codes constant has an entry, and no entry is orphaned
- default_severity: known code, unknown code, absent code
- both finding builders stamp severity from the table
- the required/optional code pairs carry different defaults
- the repo-wide invariant: the list a finding lands in equals its severity

The golden below is the point of this file. Asserting only that every code
*has* a default would let a rule ship as ``warning`` when it should be
``error``: every "fails on bad input" test would stay green, because those
tests assert exit codes and message text rather than the label itself. The
table is therefore compared by value, entry by entry.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

import pytest

from studio.utils import error_codes as EC
from studio.utils import severity as sev
from studio.utils.codebase import error as code_error
from studio.utils.constraints import error as constraints_error


# ---------------------------------------------------------------------------
# The golden table
# ---------------------------------------------------------------------------

EXPECTED_DEFAULT_SEVERITY: Dict[str, str] = {
    "LANG001": "error",
    "cdsl-code-syntax": "error",
    "cdsl-duplicate-inst-id": "error",
    "cdsl-incomplete-step-line": "warning",
    "cdsl-language-operator": "error",
    "cdsl-missing-checkbox": "warning",
    "cdsl-missing-inst-id": "warning",
    "cdsl-missing-phase-token": "warning",
    "cdsl-not-plain-english": "error",
    "cdsl-placeholder": "error",
    "cdsl-step-unchecked": "error",
    "cdsl-type-annotation": "error",
    "code-docs-only": "error",
    "code-inst-missing": "error",
    "code-inst-orphan": "error",
    "code-no-marker": "error",
    "code-orphan-ref": "error",
    "code-task-unchecked": "error",
    "codebase-entry-empty": "warning",
    "constraints-invalid": "error",
    "constraints-unknown-key": "warning",
    "def-done-ref-not-done": "error",
    "def-link-form-not-allowed": "error",
    "def-missing-priority": "error",
    "def-missing-task": "error",
    "def-prohibited-priority": "error",
    "def-prohibited-task": "error",
    "def-wrong-headings": "error",
    "duplicate-definition": "error",
    "file-load-error": "error",
    "file-read-error": "error",
    "file-too-large": "error",
    "heading-missing": "error",
    "heading-number-not-consecutive": "error",
    "heading-numbering-mismatch": "error",
    "heading-order-violation": "error",
    "heading-prohibits-multiple": "error",
    "heading-requires-multiple": "off",
    "id-kind-not-allowed": "error",
    "id-not-referenced": "error",
    "id-not-referenced-no-scope": "warning",
    "id-system-unrecognized": "error",
    "kit-binding-error": "error",
    "kit-model-invalid": "error",
    "kit-path-not-accessible": "error",
    "kit-resource-path-not-found": "error",
    "kit-template-binding-missing": "warning",
    "marker-begin-no-end": "error",
    "marker-dup-begin": "error",
    "marker-dup-scope": "error",
    "marker-empty-block": "error",
    "marker-end-no-begin": "error",
    "missing-constraints": "error",
    "parent-checked-nested-unchecked": "error",
    "parent-unchecked-all-done": "error",
    "ref-done-def-not-done": "error",
    "ref-from-prohibited-kind": "error",
    "ref-missing-from-kind": "error",
    "ref-missing-priority": "error",
    "ref-missing-task": "error",
    "ref-missing-task-for-tracked": "error",
    "ref-no-definition": "error",
    "ref-prohibited-priority": "error",
    "ref-prohibited-task": "error",
    "ref-target-not-in-scope": "warning",
    "ref-task-def-no-task": "error",
    "ref-wrong-headings": "error",
    "registry-autodetect-failed": "error",
    "registry-autodetect-invalid": "error",
    "required-id-kind-missing": "error",
    "template-def-kind-not-in-constraints": "error",
    "template-def-placeholder-missing": "error",
    "template-def-placeholder-missing-optional": "warning",
    "template-def-placeholder-wrong-headings": "error",
    "template-id-kind-no-template": "error",
    "template-read-error": "error",
    "template-ref-kind-not-in-constraints": "error",
    "template-ref-placeholder-missing": "error",
    "template-ref-placeholder-missing-optional": "warning",
    "template-ref-placeholder-wrong-headings": "error",
    "toc-anchor-broken": "error",
    "toc-heading-depth-jump": "warning",
    "toc-heading-duplicate": "warning",
    "toc-heading-not-in-toc": "error",
    "toc-missing": "error",
    "toc-missing-description": "warning",
    "toc-section-too-long": "warning",
    "toc-stale": "warning",
}


def _all_code_constants() -> Dict[str, str]:
    return {
        name: value
        for name, value in vars(EC).items()
        if name.isupper() and isinstance(value, str)
    }


# ---------------------------------------------------------------------------
# The table itself
# ---------------------------------------------------------------------------

def test_default_severity_matches_the_golden_table_by_value():
    """Every default is pinned. Changing one must fail here, by name."""
    assert sev.DEFAULT_SEVERITY == EXPECTED_DEFAULT_SEVERITY


def test_every_error_code_constant_has_a_default_severity():
    codes = set(_all_code_constants().values())
    assert codes - set(sev.DEFAULT_SEVERITY) == set()


def test_table_has_no_entry_for_a_code_that_does_not_exist():
    codes = set(_all_code_constants().values())
    assert set(sev.DEFAULT_SEVERITY) - codes == set()


def test_every_default_is_a_member_of_the_vocabulary():
    assert set(sev.DEFAULT_SEVERITY.values()) <= set(sev.VALIDATION_SEVERITIES)


def test_only_the_reviewed_codes_default_to_off():
    """Which rules ship non-blocking is a reviewed list, not a side effect.

    A default of ``off`` means the rule runs and nobody hears it, so the set is
    pinned by name here. It is the negative form of the golden table: adding a
    code to it takes an edit to this test and the argument that goes with it.

    ``heading-requires-multiple`` is the only member. "At least two of this
    section" is true of a kit's repeated-block constraints and false of every
    document with a single flow, a single state or a single acceptance
    criterion, so the kits that want it declare ``multiple = true`` and raise
    it per kind.
    """
    off_codes = {code for code, value in sev.DEFAULT_SEVERITY.items() if value == sev.OFF}
    assert off_codes == {EC.HEADING_REQUIRES_MULTIPLE}


def test_the_module_refuses_to_import_when_the_registry_gains_an_unlisted_code(monkeypatch):
    """Exhaustiveness is enforced at import, not only by this test file.

    A test-only check is a promise production never hears. This executes the
    module under a drifted registry and expects it to refuse — and it is the
    execution, not a direct call, that is asserted, so removing the
    module-level guard invocation fails here even if the function survives.

    The module is executed into a throwaway namespace rather than reloaded in
    place. ``importlib.reload`` rebinds the real module's classes to fresh
    objects while every module that did ``from .severity import ...`` keeps the
    originals, so a reload here leaves ``isinstance`` checks elsewhere in the
    codebase quietly false for the rest of the session — a failure that lands
    in whichever unrelated test happens to run next.
    """
    import importlib.util

    monkeypatch.setattr(EC, "PROBE_CODE_WITHOUT_A_DEFAULT", "probe-code-without-a-default", raising=False)
    spec = importlib.util.spec_from_file_location("studio.utils._severity_import_probe", sev.__file__)
    probe = importlib.util.module_from_spec(spec)
    # The attribute name must appear, not only the value: a bare
    # `missing=['1.0']` would leave a reader unable to tell a non-rule-code
    # constant from a rule code whose default was forgotten.
    with pytest.raises(
        RuntimeError,
        match=(
            "missing=\\[\"PROBE_CODE_WITHOUT_A_DEFAULT = 'probe-code-without-a-default'\"\\]"
            ".*does not belong in that module"
        ),
    ):
        spec.loader.exec_module(probe)

    assert "studio.utils._severity_import_probe" not in sys.modules
    assert sev.default_severity(EC.TOC_STALE) == "warning"


def test_the_guard_also_refuses_an_entry_no_code_backs(monkeypatch):
    """The other direction, called directly.

    It cannot be reached by reloading: the table names its keys as ``EC.X``
    attribute references, so removing a constant from the registry raises
    ``AttributeError`` while the dict is still being built, before the guard
    ever runs. An orphaned entry can only arise as a stray literal, which is
    what is planted here.
    """
    monkeypatch.setitem(sev.DEFAULT_SEVERITY, "orphaned-probe-code", "error")
    with pytest.raises(RuntimeError, match="orphaned=\\['orphaned-probe-code'\\]"):
        sev._assert_table_covers_registry()


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code,expected", [
    (EC.TOC_STALE, "warning"),
    (EC.CDSL_MISSING_INST_ID, "warning"),
    (EC.HEADING_MISSING, "error"),
    (EC.MARKER_DUP_BEGIN, "error"),
])
def test_default_severity_resolves_a_known_code(code: str, expected: str):
    assert sev.default_severity(code) == expected


@pytest.mark.parametrize("code", [None, "", "no-such-code-exists"])
def test_an_absent_or_unknown_code_resolves_to_error(code):
    """Fail closed: an unrecognised rule must not become silently non-blocking."""
    assert sev.default_severity(code) == "error"


# ---------------------------------------------------------------------------
# The two-code split
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("required_code,optional_code", [
    (EC.TEMPLATE_DEF_PLACEHOLDER_MISSING, EC.TEMPLATE_DEF_PLACEHOLDER_MISSING_OPTIONAL),
    (EC.TEMPLATE_REF_PLACEHOLDER_MISSING, EC.TEMPLATE_REF_PLACEHOLDER_MISSING_OPTIONAL),
])
def test_required_and_optional_placeholders_are_two_codes_at_two_defaults(
    required_code: str, optional_code: str
):
    """One code must mean one default severity.

    These sites previously emitted a single codeless finding routed to either
    list by a ``required`` flag. A single code would make severity depend on
    call-site control flow again, which is exactly what this model removes.
    """
    assert required_code != optional_code
    assert sev.default_severity(required_code) == "error"
    assert sev.default_severity(optional_code) == "warning"


# ---------------------------------------------------------------------------
# Both builders stamp
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("builder", [constraints_error, code_error], ids=["constraints", "codebase"])
def test_builder_stamps_severity_from_the_table(builder):
    warn = builder("toc", "m", path=Path("a.md"), line=1, code=EC.TOC_STALE)
    err = builder("structure", "m", path=Path("a.md"), line=1, code=EC.HEADING_MISSING)
    assert warn["severity"] == "warning"
    assert err["severity"] == "error"


@pytest.mark.parametrize("builder", [constraints_error, code_error], ids=["constraints", "codebase"])
def test_builder_stamps_error_when_no_code_is_supplied(builder):
    finding = builder("structure", "m", path=Path("a.md"), line=1)
    assert finding["severity"] == "error"


def test_severity_is_stamped_not_defaulted_by_keyword():
    """A keyword default would silently agree with whatever the call site did.

    Stamping from the table is what makes the equivalence testable, so a
    warning-by-default code must come out as ``warning`` even though the
    builder was given no severity argument at all.
    """
    finding = constraints_error("toc", "m", path=Path("a.md"), code=EC.TOC_HEADING_DUPLICATE)
    assert finding["severity"] == "warning"


# ---------------------------------------------------------------------------
# The table is the only source of severity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("builder", [constraints_error, code_error], ids=["constraints", "codebase"])
@pytest.mark.parametrize("supplied", ["off", "warning", "error"])
def test_a_caller_cannot_override_the_stamped_severity(builder, supplied):
    """`**extra` is splatted over the finding after the stamp, so a call site
    passing `severity=` would silently beat the table. No call site does; this
    makes sure none can start to without being told."""
    with pytest.raises(TypeError, match="derived from the finding's code"):
        builder("toc", "m", path=Path("a.md"), code=EC.TOC_STALE, severity=supplied)


def test_other_extras_still_pass_through():
    """The guard must reject exactly one key, not harden the builder generally."""
    finding = constraints_error(
        "template", "m", path=Path("a.md"), code=EC.TEMPLATE_READ_ERROR,
        kit_id="sdlc", artifact_kind="PRD",
    )
    assert finding["kit_id"] == "sdlc"
    assert finding["artifact_kind"] == "PRD"
    assert finding["severity"] == "error"


# ---------------------------------------------------------------------------
# Each newly coded branch emits its code, at its declared severity
#
# Deterministic and self-contained: these call the emitting helpers directly
# with synthetic inputs, so they neither depend on this repository's own
# content nor shell out. Each fails if its call site loses the `code=` kwarg or
# names the wrong constant.
# ---------------------------------------------------------------------------

def test_missing_kit_resource_path_is_coded_and_an_error(tmp_path):
    from studio.commands.validate_kits import _missing_resource_binding_errors

    errors = _missing_resource_binding_errors("sdlc", {"prd-template": str(tmp_path / "nope.md")})
    assert [(e["code"], e["severity"]) for e in errors] == [
        (EC.KIT_RESOURCE_PATH_NOT_FOUND, "error")
    ]


def test_unbindable_artifact_kind_is_coded_and_advisory():
    """The one advisory member of the newly coded set.

    validate-kits reports this with status PASS and warning_count 1, so an
    `error` default here would turn a passing kit check into a failing one.
    """
    from studio.commands.validate_kits import _missing_bound_artifact_warnings

    results = _missing_bound_artifact_warnings(kit_id="sdlc", known_kinds={"PRD"}, artifacts={})
    warning = results[0]["warnings"][0]
    assert (warning["code"], warning["severity"]) == (EC.KIT_TEMPLATE_BINDING_MISSING, "warning")
    assert results[0]["status"] == "PASS"


def test_unloadable_constraints_is_coded_and_an_error(tmp_path):
    from studio.commands.self_check import _append_constraints_load_failure

    results: List[dict] = []
    _append_constraints_load_failure(
        results, kit_id="sdlc", kit_base=tmp_path,
        constraints_path=None, constraint_errors=["bad table"],
    )
    finding = results[0]["errors"][0]
    assert (finding["code"], finding["severity"]) == (EC.CONSTRAINTS_INVALID, "error")


def test_id_kind_without_a_template_is_coded_and_an_error(tmp_path):
    from studio.commands.self_check import _append_missing_template_id_issue

    issues: Dict[str, List[dict]] = {"errors": [], "warnings": []}
    _append_missing_template_id_issue(
        issues, template_path=tmp_path / "t.md", kit_id="sdlc", kind_u="PRD", id_kind="fr",
    )
    finding = issues["errors"][0]
    assert (finding["code"], finding["severity"]) == (EC.TEMPLATE_ID_KIND_NO_TEMPLATE, "error")


@pytest.mark.parametrize("required,expected_code,expected_severity,expected_list", [
    (True, EC.TEMPLATE_DEF_PLACEHOLDER_MISSING, "error", "errors"),
    (False, EC.TEMPLATE_DEF_PLACEHOLDER_MISSING_OPTIONAL, "warning", "warnings"),
])
def test_missing_definition_placeholder_splits_by_required(
    tmp_path, required, expected_code, expected_severity, expected_list
):
    """The two-code split, exercised at its real call site.

    This is the branch that previously emitted one codeless finding routed by
    `required`; the code must track the flag, or severity silently depends on
    call-site control flow again.
    """
    from studio.commands.self_check import _append_missing_definition_placeholder

    issues: Dict[str, List[dict]] = {"errors": [], "warnings": []}
    _append_missing_definition_placeholder(
        issues, required=required, template_path=tmp_path / "t.md",
        kit_id="sdlc", kind_u="PRD", id_kind="fr", template_id="cpt-{system}-fr-{slug}",
    )
    finding = issues[expected_list][0]
    assert (finding["code"], finding["severity"]) == (expected_code, expected_severity)


@pytest.mark.parametrize("required,expected_code,expected_severity", [
    (True, EC.TEMPLATE_REF_PLACEHOLDER_MISSING, "error"),
    (False, EC.TEMPLATE_REF_PLACEHOLDER_MISSING_OPTIONAL, "warning"),
])
def test_missing_reference_placeholder_splits_by_required(
    tmp_path, required, expected_code, expected_severity
):
    from studio.commands.self_check import _append_missing_reference_issue

    target = "errors" if required else "warnings"
    issues: Dict[str, List[dict]] = {"errors": [], "warnings": []}
    _append_missing_reference_issue(
        issues, target, required=required, template_path=tmp_path / "t.md",
        kit_id="sdlc", kind_u="PRD", id_kind="fr", template_id="cpt-{system}-fr-{slug}",
    )
    finding = issues[target][0]
    assert (finding["code"], finding["severity"]) == (expected_code, expected_severity)


# --- the remaining branches: same direct-call pattern, each asserting code and
# --- severity together so the call site cannot drop one without failing.

def test_unreadable_template_is_coded_and_an_error(tmp_path, monkeypatch):
    """TEMPLATE_READ_ERROR sits behind the heading-contract phase, so that phase
    is stubbed to pass and the template path simply does not exist."""
    import studio.commands.self_check as sc
    from types import SimpleNamespace

    monkeypatch.setattr(sc, "validate_headings_contract", lambda **_: {"errors": [], "warnings": []})
    for_kind = SimpleNamespace(headings=None, defined_id=[])
    issues = sc._check_template_constraints_consistency(
        template_path=tmp_path / "does-not-exist.md", kind="PRD", kit_id="sdlc",
        kit_base=tmp_path, kit_constraints=SimpleNamespace(by_kind={"PRD": for_kind}),
        artifacts_meta=SimpleNamespace(get_all_system_prefixes=lambda: set()),
    )
    finding = issues["errors"][0]
    assert (finding["code"], finding["severity"]) == (EC.TEMPLATE_READ_ERROR, "error")


def test_definition_placeholder_outside_its_headings_is_coded_and_an_error(tmp_path):
    from studio.commands.self_check import _check_defined_id_placeholders
    from types import SimpleNamespace

    constraint = SimpleNamespace(
        kind="fr", template="cpt-{system}-fr-{slug}", required=True, headings=["Requirements"],
    )
    issues = _check_defined_id_placeholders(
        template_path=tmp_path / "t.md", kit_id="sdlc", kind_u="PRD",
        constraints_for_kind=SimpleNamespace(defined_id=[constraint]),
        lines=["**ID**: `cpt-{system}-fr-{slug}`"],
        headings_at=[[], ["Overview"]],  # line 1 sits under Overview, not Requirements
    )
    finding = issues["errors"][0]
    assert (finding["code"], finding["severity"]) == (
        EC.TEMPLATE_DEF_PLACEHOLDER_WRONG_HEADINGS, "error",
    )


def test_reference_placeholder_outside_its_headings_is_coded_and_an_error(tmp_path):
    from studio.commands.self_check import _required_reference_heading_issue

    finding = _required_reference_heading_issue(
        headings_at=[[], ["Overview"]], occurrences=[1], allowed_norm={"requirements"},
        required=True, template_path=tmp_path / "t.md", kit_id="sdlc", kind_u="PRD",
        id_kind="fr", template_id="cpt-{system}-fr-{slug}",
    )
    assert finding is not None
    assert (finding["code"], finding["severity"]) == (
        EC.TEMPLATE_REF_PLACEHOLDER_WRONG_HEADINGS, "error",
    )


def test_unloadable_kit_model_is_coded_and_an_error(tmp_path):
    from studio.commands.validate_kits import _apply_path_model_info

    all_errors: List[dict] = []
    report: Dict[str, object] = {"status": "PASS", "error_count": 0}
    _apply_path_model_info(
        model=None, model_error=ValueError("manifest is missing [[kits]]"), has_model_input=True,
        kit_dir=tmp_path, slug="k", verbose=False, kit_report=report, all_errors=all_errors,
    )
    assert report["status"] == "FAIL"
    assert (all_errors[0]["code"], all_errors[0]["severity"]) == (EC.KIT_MODEL_INVALID, "error")


def test_inaccessible_kit_path_is_coded_and_an_error(tmp_path):
    from studio.utils.context import _build_inaccessible_kit_path_error

    finding = _build_inaccessible_kit_path_error(tmp_path, "sdlc", r"C:\kits\sdlc")
    assert (finding["code"], finding["severity"]) == (EC.KIT_PATH_NOT_ACCESSIBLE, "error")


@pytest.mark.parametrize("failure", ["reported", "raised"], ids=["binding-list", "value-error"])
def test_kit_binding_failure_is_coded_and_an_error_on_both_paths(tmp_path, monkeypatch, failure):
    """Two emitting sites share one code: bindings the resolver reports, and a
    resolver that raises. Both must land in `errors` with the same code."""
    import studio.utils.manifest as manifest
    from studio.utils.context import load_resource_bindings

    if failure == "reported":
        monkeypatch.setattr(
            manifest, "resolve_resource_bindings_with_errors",
            lambda *_: ({}, ["resource 'prd-template' has no source"]),
        )
    else:
        def _raise(*_):
            raise ValueError("core.toml: [kits.sdlc] is not a table")
        monkeypatch.setattr(manifest, "resolve_resource_bindings_with_errors", _raise)

    _, _, errors = load_resource_bindings(tmp_path, "sdlc")
    assert [(e["code"], e["severity"]) for e in errors] == [(EC.KIT_BINDING_ERROR, "error")]


@pytest.mark.parametrize("behaviour,expected_code", [
    ("returns-messages", EC.REGISTRY_AUTODETECT_INVALID),
    ("raises", EC.REGISTRY_AUTODETECT_FAILED),
])
def test_autodetect_failures_are_coded_and_errors(tmp_path, behaviour, expected_code):
    from studio.utils.context import _expand_autodetect_errors
    from types import SimpleNamespace

    if behaviour == "returns-messages":
        meta = SimpleNamespace(expand_autodetect=lambda **_: ["pattern '**' is not anchored"])
    else:
        def _boom(**_):
            raise ValueError("autodetect root does not exist")
        meta = SimpleNamespace(expand_autodetect=_boom)

    errors = _expand_autodetect_errors(meta, tmp_path, tmp_path, kits={})
    assert [(e["code"], e["severity"]) for e in errors] == [(expected_code, "error")]


# ---------------------------------------------------------------------------
# Per-code reasons reach the kit-validation surfaces, not only `validate`
# ---------------------------------------------------------------------------

def test_validate_kits_findings_carry_their_reasons(tmp_path):
    """The `_REASONS` entries for kit codes were unreachable from `validate-kits`
    and `self-check`, which never enriched their own reports. Both entry points
    now converge on `_build_validate_kits_result`; this pins that a kit-level
    finding and a binding warning both come out with `reasons`, and that `path`
    survives enrichment because the renderer and duplicate filter read it."""
    from studio.commands.validate_kits import _build_validate_kits_result

    kit_error = constraints_error(
        "resources", "Resource 'x' path not found: /nope", path=tmp_path / "nope",
        line=1, code=EC.KIT_RESOURCE_PATH_NOT_FOUND, kit="sdlc",
    )
    binding_warning = constraints_error(
        "template", "no binding", path=None, line=1,
        code=EC.KIT_TEMPLATE_BINDING_MISSING, kit_id="sdlc", artifact_kind="PRD",
    )
    _, result = _build_validate_kits_result(
        verbose=True, kit_reports=[], all_errors=[kit_error],
        self_check_report={"results": [{"status": "PASS", "warnings": [binding_warning]}]},
        project_root=tmp_path,
    )
    assert result["errors"][0]["reasons"], "kit-level finding lost its reasons"
    assert "path" in result["errors"][0], "path must survive enrichment"
    assert result["self_check_results"][0]["warnings"][0]["reasons"], "binding warning lost its reasons"


def test_enrichment_is_idempotent_across_the_self_check_then_kits_double_pass(tmp_path):
    """Self-check enriches its findings once; `_build_validate_kits_result` enriches
    the same dicts again. The code relies on the second pass being a no-op. This
    pins that reliance: a change that appended to `reasons`, or wrote a
    relativised value back into `location`, would corrupt the agent-facing fixing
    text on exactly the findings that flow through both commands."""
    import copy
    from studio.utils.fixing import enrich_issues

    finding = constraints_error(
        "template", "ID kind has no template in constraints.toml",
        path=tmp_path / "kits" / "sdlc" / "artifacts" / "PRD" / "template.md", line=1,
        code=EC.TEMPLATE_ID_KIND_NO_TEMPLATE, kit_id="sdlc", artifact_kind="PRD", id_kind="fr",
    )
    enrich_issues([finding], project_root=tmp_path, strip_path=False)
    after_first_pass = copy.deepcopy(finding)
    assert after_first_pass["reasons"], "first pass must have produced reasons for this to test anything"

    enrich_issues([finding], project_root=tmp_path, strip_path=False)

    assert finding == after_first_pass, "second enrichment pass changed the finding"
    for key in ("reasons", "fixing_prompt", "path", "location"):
        assert finding.get(key) == after_first_pass.get(key), f"{key} drifted on the second pass"


@pytest.mark.integration
def test_list_membership_equals_stamped_severity_in_validate_kits(repo_validate_kits_report):
    """The same invariant `validate` is held to, on the report that is built on a
    separate path: top-level errors, per-kit errors, and every self-check result's
    errors and warnings."""
    report = repo_validate_kits_report
    checks: List[tuple] = []
    for finding in report.get("errors") or []:
        checks.append(("errors", "error", finding))
    for kit in report.get("kits") or []:
        for finding in kit.get("errors") or []:
            checks.append((f"kits[{kit.get('kit')}].errors", "error", finding))
    for item in report.get("self_check_results") or []:
        where = f"self_check_results[{item.get('kit')}/{item.get('kind')}]"
        for finding in item.get("errors") or []:
            checks.append((f"{where}.errors", "error", finding))
        for finding in item.get("warnings") or []:
            checks.append((f"{where}.warnings", "warning", finding))

    assert checks, "validate-kits produced no findings — the invariant would be vacuous"
    mismatches = [
        f"{where}: {f.get('code')} stamped {f.get('severity')}"
        for where, want, f in checks if f.get("severity") != want
    ]
    assert not mismatches, mismatches


# ---------------------------------------------------------------------------
# The stamped severity reaches the human report
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_error,code,expected", [
    (True, EC.HEADING_MISSING, "error"),
    (False, EC.TOC_STALE, "warning"),
])
def test_human_output_renders_the_stamped_severity(capsys, is_error, code, expected):
    """A stamped severity that never reaches the reader is not reported.

    ``severity`` was briefly listed in the human formatter's ``handled_keys``
    without anything rendering it, which suppressed it from validate output
    entirely — the worst of both, since the key looked handled. Pin it.
    """
    from studio.commands.validate import _format_issue
    from studio.utils.ui import set_json_mode

    set_json_mode(False)
    try:
        _format_issue(
            constraints_error("toc", "m", path=Path("a.md"), line=3, code=code),
            is_error=is_error,
        )
    finally:
        set_json_mode(True)

    assert f"severity: {expected}" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The repo-wide invariant
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


#: Generous enough that only a genuine hang trips it — a full validate of this
#: repository runs in well under a second. Without it a deadlocked child would
#: block the run forever, and CI would report a timeout on the whole job rather
#: than on the test that caused it.
_VALIDATE_TIMEOUT_SECONDS = 300


def _run_studio_json(command: str) -> Dict[str, object]:
    """Run one CLI command over this repository and return its JSON report.

    Uses ``sys.executable`` rather than a bare ``python3``: the interpreter
    first on PATH is commonly older than this project supports, and a run that
    silently measured the wrong thing is precisely the failure this module
    exists to make impossible.
    """
    import subprocess  # local: only the integration fixtures shell out
    import sys

    try:
        proc = subprocess.run(
            [sys.executable, "skills/studio/scripts/studio.py", command, "--json", "--verbose"],
            cwd=_repo_root(), capture_output=True, text=True, check=False,
            timeout=_VALIDATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"{command} did not finish within {_VALIDATE_TIMEOUT_SECONDS}s — treat as a hang, "
            f"not a slow machine; it normally completes in under a second. "
            f"stderr tail: {(exc.stderr or b'')[-400:]!r}"
        ) from exc
    assert proc.stdout.strip(), f"{command} produced no stdout (exit {proc.returncode}): {proc.stderr[:400]}"
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def repo_validate_report() -> Dict[str, object]:
    """This repository's own ``validate`` report, run once per module."""
    return _run_studio_json("validate")


@pytest.fixture(scope="module")
def repo_validate_kits_report() -> Dict[str, object]:
    """This repository's own ``validate-kits`` report, run once per module.

    ``self-check`` is a CLI alias for the same command, so one run covers both
    surfaces that build their findings outside ``validate``'s pipeline.
    """
    return _run_studio_json("validate-kits")


@pytest.mark.integration
def test_list_membership_equals_stamped_severity_over_this_repo(repo_validate_report):
    """The invariant the whole model rests on, measured on real output."""
    report = repo_validate_report

    mismatches: List[str] = []
    for list_name, expected in (("errors", "error"), ("warnings", "warning")):
        for finding in report.get(list_name) or []:
            if finding.get("severity") != expected:
                mismatches.append(
                    f"{finding.get('code')} in {list_name} stamped {finding.get('severity')}"
                )
    assert not mismatches, mismatches


@pytest.mark.integration
def test_every_finding_this_repo_emits_carries_a_code(repo_validate_report):
    report = repo_validate_report
    findings = (report.get("errors") or []) + (report.get("warnings") or [])
    assert findings, "validate produced no findings — the invariant would be vacuous"
    assert [f for f in findings if not f.get("code")] == []
