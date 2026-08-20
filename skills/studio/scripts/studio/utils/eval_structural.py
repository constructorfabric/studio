"""Deterministic structural scorer for the workflow eval-harness.

The real ``DETERMINISTIC`` scorer that plugs into the ``Scorer`` seam the scaffold
(:mod:`studio.utils.eval_harness`) defines. It reads a completed run's ``plan.toml``
manifest and the ``[phase]`` frontmatter carried by each ``phase-*.md`` file, runs a
**registry** of independent structural checks (numbering, manifest agreement, dependency
order, declared outputs, required sections), and returns a ``ScorerResult`` with a
compliance %, per-check findings, and the scaffold's UNKNOWN discipline.

Design commitments, inherited from the scaffold's gate contract: **unscoreable is not
zero** (a run that will not load, or whose phases carry no parseable ``[phase]``
frontmatter, scores ``UNKNOWN`` with a ``None`` score, never a false 0%); and **the
registry is the unit of extension** — each check is a small tagged callable, skippable by
name or tag and testable in isolation, rather than one hardcoded function. The scorer is a
pure function of the in-memory run artifacts: no filesystem, no model call, no way to add
either to a score.

@cpt-algo:cpt-studio-algo-eval-structural:p1
"""
# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-imports
from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from .eval_harness import (RunArtifacts, Scenario, ScorerKind, ScorerResult,
                           VERDICT_FAIL, VERDICT_PASS, VERDICT_UNKNOWN)

logger = logging.getLogger(__name__)
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-imports


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-config
#: The fenced TOML block at the head of a phase file, carrying its ``[phase]`` table.
#: Only *horizontal* whitespace is allowed after the opening fence (``[ \t]`` not ``\s``):
#: letting ``\s`` swallow newlines makes an unterminated fence backtrack quadratically.
_FRONTMATTER_RE = re.compile(r"^```toml[ \t]*\r?\n(?P<body>.*?)\r?\n```", re.DOTALL)

#: Body sections a self-contained phase file is expected to carry, by default. Measured
#: against the real plans, not invented: the common shape is ``## Preamble`` / ``## What`` /
#: ``## Rules``. A workflow whose phases legitimately differ overrides this below.
DEFAULT_SECTIONS: Tuple[str, ...] = ("Preamble", "What", "Rules")

#: Per-workflow required-section overrides. A verification-style workflow legitimately
#: carries no ``## Rules`` block, so scoring it against the universal set would be a
#: false-fail; a workflow absent from this map uses ``DEFAULT_SECTIONS``.
WORKFLOW_SECTIONS: Dict[str, Tuple[str, ...]] = {
    "verify": ("Preamble", "What"),
    "verification": ("Preamble", "What"),
}
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-config


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-datamodel
@dataclass
class StructuralInput:
    """Everything the checks read: the manifest plus the parsed phase frontmatter."""

    plan_meta: Dict[str, object]                    # plan.toml [plan] table
    manifest_phases: List[Dict[str, object]]        # plan.toml [[phases]] entries
    phases: Dict[int, Dict[str, object]]            # phase number -> parsed [phase] frontmatter
    bodies: Dict[int, str]                          # phase number -> raw phase-file body
    by_file: Dict[str, int]                         # phase filename -> the number it declares
    duplicates: List[str]                           # files that re-declare an already-seen number
    invalid: List[str]                              # files WITH a [phase] block that is broken
    no_frontmatter: List[str]                       # files with no [phase] block at all
    required_sections: Tuple[str, ...]              # sections this workflow's phases must carry
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-datamodel


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-parse
def _as_phase_int(value: object) -> Optional[int]:
    """A phase number/total as a plain ``int``, or ``None`` when it is not one.

    TOML already types its scalars, so this is a *type check*, not a parse — there is no
    exception path to swallow. ``bool`` is excluded on purpose (it is an ``int`` subclass,
    but a flag is never a phase number).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


#: Leading bytes tolerated before the fence: a UTF-8 BOM and any blank lines / indentation.
#: Editors and templating commonly prepend these, and rejecting them would look like a
#: "missing frontmatter" false-negative rather than the near-miss it is.
_LEADING_NOISE = "﻿ \t\r\n"


def _match_frontmatter(text: str):
    """Match the ``[phase]`` fence, tolerating a leading BOM / blank lines. Returns the match
    and the normalised text it was matched against (so callers can slice by ``.end()``)."""
    normalised = text.lstrip(_LEADING_NOISE)
    return _FRONTMATTER_RE.match(normalised), normalised


def _parse_phase_table(body: str) -> Optional[Dict[str, object]]:
    """Parse an already-extracted fenced ``[phase]`` TOML *body* into its table, or ``None``
    when the TOML is malformed (surfaced as a warning, not swallowed) or carries no ``[phase]``.
    """
    try:
        data = tomllib.loads(body)
    except tomllib.TOMLDecodeError as exc:
        logger.warning("eval: phase file has a malformed [phase] frontmatter block: %s", exc)
        return None
    phase = data.get("phase")
    return phase if isinstance(phase, dict) else None


def _collect_phases(phase_texts: Dict[str, str]) -> Tuple[Dict[int, Dict[str, object]],
                                                          Dict[int, str], Dict[str, int],
                                                          List[str], List[str], List[str]]:
    """Parse phase bodies into ``(by_number, bodies, by_file, duplicates, invalid, no_block)``.

    Keying phases by their declared ``number`` (not by filename) is deliberate: it lets the
    checks reason about ordering and dependencies. ``by_file`` retains the filename→number
    pairing so a check can verify the manifest maps each number to the right file. A file that
    cannot contribute a phase is *retained as a finding*, never silently dropped, and the two
    failure modes are kept apart: a file that **has** a ``[phase]`` block but is broken
    (unparseable TOML, or a bad number) goes to ``invalid`` — that is a *failing* run; a file
    with **no** fenced block at all goes to ``no_block`` — that may just be a different workflow
    shape. A second file re-declaring a number is recorded in ``duplicates``.
    """
    phases: Dict[int, Dict[str, object]] = {}
    bodies: Dict[int, str] = {}
    by_file: Dict[str, int] = {}
    duplicates: List[str] = []
    invalid: List[str] = []
    no_block: List[str] = []
    for name in sorted(phase_texts):
        text = phase_texts[name]
        match, _ = _match_frontmatter(text)
        if match is None:
            no_block.append(f"{name}: no [phase] frontmatter block")
            continue
        front = _parse_phase_table(match.group("body"))
        if front is None:
            invalid.append(f"{name}: [phase] frontmatter present but unparseable")
            continue
        number = _as_phase_int(front.get("number"))
        if not number or number <= 0:
            invalid.append(f"{name}: missing or non-positive phase number")
            continue
        by_file[name] = number
        if number in phases:
            duplicates.append(f"{name} re-declares phase {number}")
            continue
        phases[number] = front
        bodies[number] = text
    return phases, bodies, by_file, duplicates, invalid, no_block
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-parse


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-check-helpers
def _capped(items: List[str], cap: int = 3) -> str:
    """Join the first ``cap`` items, appending ``(+N more)`` so a truncated detail never hides
    the true count from a reader."""
    shown = "; ".join(items[:cap])
    extra = len(items) - cap
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def _manifest_numbers(inp: StructuralInput) -> List[int]:
    """Every positive phase number the manifest lists, **duplicates preserved** (order kept)."""
    numbers: List[int] = []
    for entry in inp.manifest_phases:
        number = _as_phase_int(entry.get("number"))
        if number and number > 0:
            numbers.append(number)
    return numbers


def _manifest_declared(inp: StructuralInput) -> Set[int]:
    """The set of positive phase numbers the ``plan.toml`` manifest declares."""
    return set(_manifest_numbers(inp))


def _phase_totals(inp: StructuralInput) -> Set[int]:
    """The distinct ``total`` values the phase frontmatter declares.

    A missing or non-integer ``total`` counts as ``0`` (not dropped), so an absent total
    lands in the set and trips ``phase-total-consistent`` rather than vanishing.
    """
    totals: Set[int] = set()
    for front in inp.phases.values():
        total = _as_phase_int(front.get("total"))
        totals.add(total if total is not None else 0)
    return totals
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-check-helpers


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-deps
#: Keys that normalise to a plausible misspelling of ``depends_on`` — flagged so a typo
#: (e.g. ``dependsOn``) is reported, not silently read as "no dependencies".
_DEP_KEY_ALIASES = frozenset({"dependson", "dependencies", "depends", "dependency",
                              "dependsupon", "dependon", "dependenton", "dependings"})


def _misspelled_dep_key(front: Dict[str, object]) -> Optional[str]:
    """A frontmatter key that looks like a misspelled ``depends_on`` (when the real key is
    absent), or ``None``. Normalises case/underscores/hyphens before comparing."""
    if "depends_on" in front:
        return None
    for key in front:
        if isinstance(key, str) and key.lower().replace("_", "").replace("-", "") in _DEP_KEY_ALIASES:
            return key
    return None


def _dependency_problems(inp: StructuralInput) -> Tuple[List[str], List[str]]:
    """Return ``(unresolved, forward)`` dependency problems across all phases."""
    unresolved: List[str] = []
    forward: List[str] = []
    for number, front in sorted(inp.phases.items()):
        misspelled = _misspelled_dep_key(front)
        if misspelled is not None:
            unresolved.append(f"phase {number}: '{misspelled}' looks like a misspelled depends_on")
        deps = front.get("depends_on")
        if deps is None:
            deps = []
        elif not isinstance(deps, list):
            # A present-but-non-list depends_on is a malformed declaration, not "no deps" —
            # flag it rather than silently treating it as empty (which would vacuously pass).
            unresolved.append(f"phase {number}: depends_on must be an array")
            continue
        for dep in deps:
            dep_no = _as_phase_int(dep)
            if dep_no is None:
                unresolved.append(f"phase {number} -> {dep!r}")
            elif dep_no not in inp.phases:
                unresolved.append(f"phase {number} -> {dep_no} (missing)")
            elif dep_no >= number:
                forward.append(f"phase {number} -> {dep_no}")
    return unresolved, forward
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-deps


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-checks
def _check_phase_frontmatter_valid(inp: StructuralInput) -> Tuple[bool, str]:
    # Once a run is scoreable (some phase parsed), every other declared phase file must too —
    # whether it has a broken block (``invalid``) or none at all (``no_frontmatter``), it is a
    # broken phase and fails here, so it can never be silently dropped into a vacuous pass.
    problems = inp.invalid + inp.no_frontmatter
    return not problems, _capped(problems)


def _check_phase_numbers_unique(inp: StructuralInput) -> Tuple[bool, str]:
    return not inp.duplicates, _capped(inp.duplicates)
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-checks


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-checks-manifest
def _check_manifest_numbers_unique(inp: StructuralInput) -> Tuple[bool, str]:
    numbers = _manifest_numbers(inp)
    dupes = sorted({n for n in numbers if numbers.count(n) > 1})
    return not dupes, f"manifest re-declares phase(s): {dupes}" if dupes else ""


def _check_manifest_entries_valid(inp: StructuralInput) -> Tuple[bool, str]:
    # A [[phases]] entry with a missing or non-positive number is malformed. Other manifest
    # checks quietly drop such entries (they reduce to the set of *valid* numbers), so without
    # this a broken manifest entry would never surface — flag each one explicitly.
    bad = []
    for index, entry in enumerate(inp.manifest_phases):
        number = _as_phase_int(entry.get("number"))
        if number is None or number <= 0:
            bad.append(f"entry {index}: number={entry.get('number')!r}")
    return not bad, _capped(bad)


def _check_manifest_present(inp: StructuralInput) -> Tuple[bool, str]:
    # The scaffold already turns an unreadable/`[plan]`-less plan.toml into UNKNOWN before a
    # scorer runs, so this checks the *other* half — that the [[phases]] manifest actually
    # lists the phases the files carry. It fails when a plan.toml has a [plan] table but no
    # numbered [[phases]] entries, a real and distinct defect (not a vacuous always-pass).
    ok = bool(_manifest_declared(inp))
    return ok, "" if ok else "plan.toml [[phases]] declares no numbered phase"


def _check_manifest_total_matches_entries(inp: StructuralInput) -> Tuple[bool, str]:
    declared = _manifest_declared(inp)
    total_declared = _as_phase_int(inp.plan_meta.get("total_phases")) or 0
    ok = total_declared == len(declared)
    return ok, f"total_phases={total_declared}, entries={len(declared)}"


def _check_manifest_matches_files(inp: StructuralInput) -> Tuple[bool, str]:
    # Two things must agree, not just the number *set*: (1) the declared and found number sets
    # match, and (2) each manifest entry's number->file pairing matches the file's own declared
    # number — a manifest that maps phase 1 to phase-2.md must not pass on set equality alone.
    problems: List[str] = []
    declared = _manifest_declared(inp)
    found = set(inp.phases)
    if declared != found:
        problems.append(f"declared={sorted(declared)}, found={sorted(found)}")
    for entry in inp.manifest_phases:
        number = _as_phase_int(entry.get("number"))
        file = entry.get("file")
        if not isinstance(file, str) or number is None:
            continue
        actual = inp.by_file.get(file)
        if actual is None:
            problems.append(f"{file} (manifest phase {number}) has no valid phase")
        elif actual != number:
            problems.append(f"manifest pairs {file}->{number} but the file declares {actual}")
    return not problems, _capped(problems, 3)


def _check_numbering_contiguous(inp: StructuralInput) -> Tuple[bool, str]:
    numbers = sorted(inp.phases)
    ok = numbers == list(range(1, len(numbers) + 1))
    return ok, f"numbers={numbers}"
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-checks-manifest


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-checks-phase
def _check_phase_total_consistent(inp: StructuralInput) -> Tuple[bool, str]:
    totals = _phase_totals(inp)
    ok = len(totals) == 1 and totals != {0}
    return ok, f"declared totals={sorted(totals)}"


def _check_phase_total_matches_count(inp: StructuralInput) -> Tuple[bool, str]:
    totals = _phase_totals(inp)
    count = len(inp.phases)
    ok = totals == {count}
    return ok, f"total={sorted(totals)}, count={count}"


def _check_dependencies_resolve(inp: StructuralInput) -> Tuple[bool, str]:
    unresolved, _ = _dependency_problems(inp)
    return not unresolved, _capped(unresolved)


def _check_dependencies_not_forward(inp: StructuralInput) -> Tuple[bool, str]:
    _, forward = _dependency_problems(inp)
    return not forward, _capped(forward)


def _check_every_phase_declares_output(inp: StructuralInput) -> Tuple[bool, str]:
    missing = [str(n) for n, front in sorted(inp.phases.items())
               if not (front.get("outputs") or front.get("output_files"))]
    return not missing, (f"phases without outputs: {_capped(missing, 5)}" if missing else "")
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-checks-phase


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-prose
def _prose_headings(raw_body: str) -> str:
    """The phase body reduced to its real Markdown prose — the leading ``[phase]`` frontmatter
    and every fenced code block removed — so a ``## Section``-looking line inside TOML or a
    code sample is not mistaken for a real heading (which would inflate compliance).

    A simple line-based fence toggle, not a Markdown parser: no regex over the whole body, so
    no backtracking, and it covers the fenced ` ``` ` blocks phase files actually use.
    """
    front, normalised = _match_frontmatter(raw_body)
    body = normalised[front.end():] if front else normalised
    visible: List[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            visible.append(line)
    return "\n".join(visible)
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-prose


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-checks-sections
def _check_required_sections(inp: StructuralInput) -> Tuple[bool, str]:
    missing: List[str] = []
    for number in sorted(inp.phases):
        body = _prose_headings(inp.bodies.get(number, ""))
        for section in inp.required_sections:
            if not re.search(rf"^##\s+{re.escape(section)}\b", body, re.MULTILINE):
                missing.append(f"phase {number}: {section}")
    return not missing, _capped(missing)
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-checks-sections


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-registry
@dataclass(frozen=True)
class Check:
    """One structural check: a name, tags (for grouped skipping), and a pure predicate."""

    name: str
    tags: Tuple[str, ...]
    run: Callable[[StructuralInput], Tuple[bool, str]]   # -> (passed, detail)


#: The registry. Each check is independent — order affects only the findings list, not any
#: verdict. Extending the scorer means appending a ``Check`` here, not editing a function.
#: Two invariants the tests enforce: check names are **unique** (pass/total aggregation and
#: skip-by-name rely on it) and contain **no colon** (findings serialise as ``name: detail``,
#: which consumers split on the first colon).
CHECKS: List[Check] = [
    Check("phase-frontmatter-valid", ("phase",), _check_phase_frontmatter_valid),
    Check("phase-numbers-unique", ("phase",), _check_phase_numbers_unique),
    Check("manifest-present", ("manifest",), _check_manifest_present),
    Check("manifest-entries-valid", ("manifest",), _check_manifest_entries_valid),
    Check("manifest-numbers-unique", ("manifest",), _check_manifest_numbers_unique),
    Check("manifest-total-matches-entries", ("manifest",), _check_manifest_total_matches_entries),
    Check("manifest-matches-files", ("manifest",), _check_manifest_matches_files),
    Check("numbering-contiguous-from-1", ("numbering",), _check_numbering_contiguous),
    Check("phase-total-consistent", ("phase",), _check_phase_total_consistent),
    Check("phase-total-matches-count", ("phase",), _check_phase_total_matches_count),
    Check("dependencies-resolve", ("deps",), _check_dependencies_resolve),
    Check("dependencies-not-forward", ("deps",), _check_dependencies_not_forward),
    Check("every-phase-declares-an-output", ("outputs",), _check_every_phase_declares_output),
    Check("required-sections-present", ("sections",), _check_required_sections),
]
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-registry


# @cpt-begin:cpt-studio-algo-eval-structural:p1:inst-structural-scorer
class StructuralScorer:  # pylint: disable=too-few-public-methods
    """Score a run's structural compliance against the check registry.

    Deterministic: its verdict may reach the exit code (the runner enforces that; this
    class only declares ``kind``). ``skip`` disables checks by name *or* tag, so a suite can
    turn off a family of checks (e.g. all ``manifest`` checks) without editing the registry.
    The scorer touches no filesystem — it is a pure function of the in-memory run artifacts.
    """

    name = "structural"
    kind = ScorerKind.DETERMINISTIC

    def __init__(self, skip: Tuple[str, ...] = ()) -> None:
        self._skip = frozenset(skip)
        # A skip token matching no check name or tag is almost always a typo — warn rather
        # than silently no-op (which would leave the caller thinking a check was disabled).
        known = {check.name for check in CHECKS} | {tag for check in CHECKS for tag in check.tags}
        unknown = self._skip - known
        if unknown:
            logger.warning("eval: StructuralScorer(skip=...) has unrecognized name(s)/tag(s): %s",
                           sorted(unknown))

    def _active_checks(self) -> List[Check]:
        """The registry minus any check whose name or tag is in the skip-set."""
        return [check for check in CHECKS
                if check.name not in self._skip and not set(check.tags) & self._skip]

    def _evaluate(self, inp: StructuralInput,
                  active: List[Check]) -> Tuple[int, List[str]]:
        """Run every active check; return ``(passed, findings)`` for the failed ones."""
        findings: List[str] = []
        passed = 0
        for check in active:
            ok, detail = check.run(inp)
            if ok:
                passed += 1
            else:
                findings.append(f"{check.name}: {detail}" if detail else check.name)
        return passed, findings

    def _unknown(self, finding: str, coverage: str) -> ScorerResult:
        """A UNKNOWN result — unscoreable, never a 0."""
        return ScorerResult(self.name, self.kind, VERDICT_UNKNOWN, None, [finding], coverage)

    def score(self, run: Optional[RunArtifacts], scenario: Scenario) -> ScorerResult:
        """PASS if every active check passes, FAIL if any fails, UNKNOWN if unscoreable."""
        if run is None:
            return self._unknown("run artifacts could not be loaded",
                                 "unscoreable: no readable plan.toml")

        phases, bodies, by_file, duplicates, invalid, no_block = _collect_phases(run.phase_texts)
        if not phases:
            if invalid:
                # Phase files carry a [phase] block that is broken — a *failing* run, not a
                # different shape: score FAIL, don't hide it as UNKNOWN.
                return ScorerResult(
                    self.name, self.kind, VERDICT_FAIL, 0.0,
                    [f"phase-frontmatter-valid: {_capped(invalid)}"],
                    f"{len(invalid)} phase file(s) with broken [phase] frontmatter")
            return self._unknown(
                "no phase file carries a parseable [phase] frontmatter block",
                "unscoreable: a different workflow shape, not a failing one")

        active = self._active_checks()
        if not active:
            # Every check was skipped — nothing was assessed, which is UNKNOWN, not a pass.
            return self._unknown("all structural checks were skipped",
                                 "unscoreable: no checks ran")

        inp = StructuralInput(
            plan_meta=run.plan_meta,
            manifest_phases=run.phases,
            phases=phases,
            bodies=bodies,
            by_file=by_file,
            duplicates=duplicates,
            invalid=invalid,
            no_frontmatter=no_block,
            required_sections=WORKFLOW_SECTIONS.get(scenario.workflow, DEFAULT_SECTIONS),
        )
        passed, findings = self._evaluate(inp, active)
        return ScorerResult(
            self.name, self.kind,
            VERDICT_PASS if passed == len(active) else VERDICT_FAIL,
            round(passed / len(active) * 100, 2), findings,
            f"{len(active)} structural check(s) over {len(phases)} phase(s)")
# @cpt-end:cpt-studio-algo-eval-structural:p1:inst-structural-scorer
