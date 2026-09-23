"""Workflow eval-harness scaffold — scenario format + runner.

The scaffold both halves of the eval-harness plug into: it loads *scenarios*
(a completed workflow run + metadata), feeds each run to a set of *scorers*, and
aggregates the results into a report. It deliberately contains no real scoring
logic — a deterministic structural scorer and an advisory LLM-judge land later and
plug into the ``Scorer`` seam defined here.

Design principles:

* **The gate contract.** Only ``DETERMINISTIC`` results contribute to structural
  compliance, and gating is **opt-in** (``--check`` in the CLI) against a tunable
  floor. ``ADVISORY`` results are reported but can never move the exit code.
* **"Unscoreable != zero".** A run that cannot be loaded, or a scorer that raises,
  yields ``UNKNOWN`` with a ``None`` score — excluded from compliance, never a 0.
* **Honest reporting.** Compliance is reported per scenario and in aggregate, with a
  failing-check histogram and a coverage string derived from the scorers that ran.

@cpt-algo:cpt-studio-algo-eval-harness-run:p1
"""
# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-harness-imports
from __future__ import annotations

import logging
import math
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Iterable, Dict, List, Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-harness-imports


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-eval-datamodel
class ScorerKind(str, Enum):
    """Whether a scorer's verdict is allowed to influence the exit code."""

    DETERMINISTIC = "deterministic"   # contributes to structural compliance / gating
    ADVISORY = "advisory"             # reported only, never gates


#: Verdicts a scorer may return. ``UNKNOWN`` is distinct from ``FAIL`` on purpose:
#: "could not assess" is never "failed" and never scores 0.
VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_UNKNOWN = "UNKNOWN"


@dataclass
class ScorerResult:
    """One scorer's verdict on one scenario."""

    scorer: str
    kind: ScorerKind
    verdict: str
    score_pct: Optional[float]
    findings: List[str] = field(default_factory=list)
    coverage: str = ""


@dataclass
class Scenario:
    """A test case: a completed run to score, plus metadata."""

    id: str
    workflow: str
    run_dir: Path
    expect: str                      # compliant | non_compliant | unknown (oracle)
    gold_path: Optional[Path] = None  # consumed by the advisory judge only


@dataclass
class RunArtifacts:
    """The loaded artifacts of one completed workflow run."""

    plan_meta: Dict[str, object]
    phases: List[Dict[str, object]]
    phase_texts: Dict[str, str]
    #: Phase-shaped files sitting in the run directory that the manifest does not declare.
    #: Collected at load time because only the loader knows the directory; a scorer that had
    #: to go back to disk for this would be reading a tree that may have moved underneath it.
    undeclared_phase_files: List[str] = field(default_factory=list)




def _lost_run_coverage(run: "RunArtifacts") -> str:
    """The coverage line for a lost-run FAIL, describing the failure it accompanies.

    A manifest naming only out-of-bounds files was reported as `0 undeclared phase file(s)` —
    a number with no bearing on why it failed. Found in review.
    """
    # Branches in the **same order** as `lost_run_finding`. They were inverted: the finding
    # led with the out-of-bounds case and the coverage line led with orphans, so when both were
    # true the coverage counted something the finding never mentioned — the exact mismatch this
    # helper exists to prevent. Found in review.
    named = sum(1 for phase in run.phases
                if isinstance(phase.get("file"), str) and phase["file"])
    if named:
        return f"{named} declared phase file(s), none usable inside the run directory"
    return f"{len(run.undeclared_phase_files)} undeclared phase file(s)"


def lost_run_finding(run: "RunArtifacts") -> Optional[str]:
    """The finding for a manifest that names no phase file while phase files exist — or None.

    **Deliberately one shape.** Earlier rounds also failed a manifest whose every entry was
    rejected as out-of-bounds, and whose entries named files that were missing or unreadable.
    Each widening needed another fact about the loader's internals, and each one broke a
    neighbouring case: a path normalised in one place and not another, an entry counted as
    declared before the read that proved it was not there, a relative-path computation that
    could raise and abort the whole suite. Six rounds, all in machinery added past the original
    scope.

    So this fires only where the evidence is unambiguous and needs nothing but the manifest and
    the directory listing: the plan names no phase file at all, and phase files are sitting
    there unclaimed. Every other shape keeps the verdict it had before this change.
    """
    named = [phase for phase in run.phases
             if isinstance(phase.get("file"), str) and phase["file"]]
    if named or not run.undeclared_phase_files:
        return None
    present = ", ".join(run.undeclared_phase_files[:3])
    more = "" if len(run.undeclared_phase_files) <= 3 else f" (+{len(run.undeclared_phase_files) - 3} more)"
    return (f"manifest-matches-files: the plan names no phase file while {present}{more} "
            f"{'is' if len(run.undeclared_phase_files) == 1 else 'are'} present")


def _lost_run_coverage(run: "RunArtifacts") -> str:
    """The coverage line for a lost-run FAIL — one shape, so one sentence."""
    return f"{len(run.undeclared_phase_files)} undeclared phase file(s)"


@dataclass
class EvalReport:
    """The outcome of running a suite: per-scenario results."""

    scenarios: List[ScenarioResult]


@dataclass
class ScenarioResult:
    """All scorers' results for one scenario."""

    scenario_id: str
    workflow: str
    results: List[ScorerResult]
    expect: str = ""     # the scenario's declared oracle, surfaced for declared-vs-actual


@runtime_checkable
class Scorer(Protocol):  # pylint: disable=too-few-public-methods
    """The seam the structural scorer and the advisory judge plug into.

    A scorer inspects a loaded run and returns a ``ScorerResult``. Its ``kind``
    decides whether its verdict can reach the exit code — the runner enforces that,
    the scorer only declares it.
    """

    name: str
    kind: ScorerKind

    def score(self, run: Optional[RunArtifacts], scenario: Scenario) -> ScorerResult:
        """Return this scorer's verdict on ``run`` for ``scenario``."""  # pragma: no cover
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-eval-datamodel


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-reference-scorer
class ReferencePresenceScorer:  # pylint: disable=too-few-public-methods
    """A deliberately trivial deterministic scorer used only to exercise the seam.

    **This is not the real structural scorer** (a follow-up). It checks one thing —
    that the run loaded and every declared phase file is present — so the scaffold,
    its fixtures, and the gate-contract test have something concrete to run.
    """

    name = "reference-presence"
    kind = ScorerKind.DETERMINISTIC

    def score(self, run: Optional[RunArtifacts],
              scenario: Scenario) -> ScorerResult:  # pylint: disable=unused-argument
        """PASS if every checkable phase file is present, FAIL if any missing, else UNKNOWN."""
        if run is None:
            return ScorerResult(
                self.name, self.kind, VERDICT_UNKNOWN, None,
                ["run artifacts could not be loaded"], "unscoreable: no readable plan.toml")
        if not run.phases:
            return ScorerResult(
                self.name, self.kind, VERDICT_UNKNOWN, None,
                ["run declares no phases"], "unscoreable: nothing to assess")
        # Only phases that declare a file are checkable. A run whose phases declare no
        # verifiable file is unscoreable by this scorer, not a vacuous 100% pass.
        checkable = [phase["file"] for phase in run.phases
                     if isinstance(phase.get("file"), str) and phase["file"]]
        if not checkable:
            return ScorerResult(
                self.name, self.kind, VERDICT_UNKNOWN, None,
                ["no phase declares a checkable file"], "unscoreable: nothing to verify")
        missing = [name for name in checkable if name not in run.phase_texts]
        if missing:
            return ScorerResult(
                self.name, self.kind, VERDICT_FAIL, 0.0,
                [f"declared phase file missing: {name}" for name in missing],
                f"{len(checkable)} checkable phase file(s)")
        return ScorerResult(
            self.name, self.kind, VERDICT_PASS, 100.0, [],
            f"{len(checkable)} checkable phase file(s), all present")
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-reference-scorer


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-load-scenarios
def _declared_expect(value: object, descriptor: Path) -> str:
    """A scenario's oracle, or `"unknown"` with a warning when it is not one of the three.

    `expect` decides whether a scenario's result is compared against its own claim at all, so a
    value the comparison does not recognise opts that scenario out silently. A single typo --
    `non-compliant` for `non_compliant` -- was enough to do it, and nothing anywhere said so.
    Found in review. Still `"unknown"` rather than a hard error, because one malformed
    descriptor must not sink a suite; the warning is what makes the opt-out visible.
    """
    if not isinstance(value, str):
        # A TOML `true` or number reached the report as "True"/"1" once `str()` was applied
        # unconditionally. Not a claim in any spelling, so it is reported as the absent claim
        # it is rather than as a string nobody wrote. Found in review.
        logger.warning("eval: scenario [scenario].expect is %r, which is not a string — "
                       "treating it as unknown: %s", value, descriptor)
        return "unknown"
    text = value
    if text not in ("compliant", "non_compliant", "unknown"):
        logger.warning(
            "eval: scenario [scenario].expect is %r, which is not one of compliant, "
            "non_compliant, unknown — this scenario's result is not checked against its own "
            "claim: %s", text, descriptor)
    # Returned **as written**, not normalised to "unknown". Rewriting it made a typo
    # indistinguishable downstream from a deliberate no-claim: the report showed `unknown`
    # for both, so the only trace of the mistake was a log line nobody reads back. Left as-is,
    # the report shows `non-compliant` and a reader can see the hyphen. The comparison treats
    # anything it does not recognise as claiming nothing, which is unchanged. Found in review.
    return text


def load_scenarios(root: Path) -> List[Scenario]:
    """Discover scenarios under ``root`` by globbing ``*/scenario.toml``.

    A malformed, id-less, or **duplicate-id** descriptor is skipped with a warning, never
    raised, and a ``run_dir``/gold path that escapes the scenario directory (absolute or
    ``..``) is rejected — one bad or unsafe scenario must not sink the whole suite. IDs are
    kept unique because calibration identities (``covered``/``excluded``/rows) key on them.
    """
    scenarios: List[Scenario] = []
    seen_ids = set()
    for descriptor in sorted(root.glob("*/scenario.toml")):
        try:
            with open(descriptor, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            logger.warning("eval: skipping unreadable scenario descriptor %s: %s", descriptor, exc)
            continue
        section = data.get("scenario", {})
        if not isinstance(section, dict):
            logger.warning("eval: [scenario] is not a table, skipping: %s", descriptor)
            continue
        scenario_id = section.get("id")
        if not scenario_id:
            logger.warning("eval: scenario descriptor missing [scenario].id: %s", descriptor)
            continue
        if str(scenario_id) in seen_ids:
            # Reserve the id on the FIRST descriptor to declare it — before path validation — so a
            # duplicate is deterministically skipped regardless of either descriptor's validity, and
            # the id can never resolve to a different run_dir/gold pair. (A duplicate would make
            # calibration identities — covered/excluded/rows — ambiguous and hide duplicate counting.)
            logger.warning("eval: duplicate [scenario].id %r, skipping later descriptor: %s",
                           scenario_id, descriptor)
            continue
        seen_ids.add(str(scenario_id))
        base = descriptor.parent
        run_dir = base / str(section.get("run_dir", "run"))
        if not run_dir.resolve().is_relative_to(base.resolve()):
            # Keep scenarios self-contained: reject absolute or ../ paths that escape the base.
            logger.warning("eval: scenario %s run_dir escapes its directory, skipping: %s",
                           scenario_id, section.get("run_dir"))
            continue
        gold = section.get("gold", {})
        gold_rel = gold.get("path") if isinstance(gold, dict) else None
        gold_path = None
        if gold_rel:
            candidate = base / str(gold_rel)
            if candidate.resolve().is_relative_to(base.resolve()):
                gold_path = candidate
            else:
                logger.warning("eval: scenario %s gold path escapes its directory, ignoring: %s",
                               scenario_id, gold_rel)
        scenarios.append(Scenario(
            id=str(scenario_id),
            workflow=str(section.get("workflow", "unknown")),
            run_dir=run_dir,
            expect=_declared_expect(section.get("expect", "unknown"), descriptor),
            gold_path=gold_path,
        ))
    return scenarios
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-load-scenarios


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-load-run
def load_run(run_dir: Path) -> Optional[RunArtifacts]:
    """Load a completed run's ``plan.toml`` + ``phase-*.md``.

    Returns ``None`` (→ UNKNOWN) for a missing or malformed plan rather than raising:
    "unscoreable != zero". A declared phase file that cannot be read is simply absent
    from ``phase_texts`` so a scorer can report it, not a crash.
    """
    plan_path = run_dir / "plan.toml"
    try:
        with open(plan_path, "rb") as handle:
            manifest = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("eval: run has no readable plan.toml at %s: %s", plan_path, exc)
        return None
    plan_meta = manifest.get("plan")
    if not isinstance(plan_meta, dict) or not plan_meta:
        logger.warning("eval: plan.toml missing a [plan] section: %s", plan_path)
        return None
    phases = manifest.get("phases", [])
    if not isinstance(phases, list):
        logger.warning("eval: plan.toml [[phases]] is not a list: %s", plan_path)
        return None
    phases = [phase for phase in phases if isinstance(phase, dict)]  # drop malformed entries
    phase_texts: Dict[str, str] = {}
    for phase in phases:
        name = phase.get("file")
        if not isinstance(name, str) or not name:   # non-string file must not crash the run
            continue
        # Normalised **once**, and used for both the read and the record. Two earlier attempts
        # normalised only one of the two: the accepted path was rewritten while the read still
        # used the raw manifest string, so a POSIX run declaring `steps\\phase-1.md` recorded a
        # file it never opened, dropped the real one off the orphan list, and left the scorers
        # disagreeing — the very fault this whole change exists to end. Found in review, twice.
        #
        # `PurePosixPath` also collapses a leading `./` correctly, where the `lstrip("./")` it
        # replaces was a character-set strip that turned `.steps/phase-1.md` into
        # `steps/phase-1.md` and swapped one real file for another.
        target = run_dir / PurePosixPath(name.replace("\\", "/"))
        if not target.resolve().is_relative_to(run_dir.resolve()):
            # A phase file that escapes the run dir (absolute or ../) is never read, and is
            # not recorded as declared either: it names nothing this run can contain.
            logger.warning("eval: phase file escapes the run dir, skipping: %s", name)
            continue
        try:
            phase_texts[name] = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # Absent/unreadable phase → left out of phase_texts so a scorer flags it.
            # UnicodeDecodeError belongs here with OSError, not in the caller: it is a
            # ValueError, so leaving it out let one phase file of non-UTF-8 bytes
            # propagate through load_cases into run_suite and abort the whole suite,
            # discarding every other scenario's result. Undecodable is just one more
            # way a declared file cannot be read.
            logger.warning("eval: declared phase file unreadable (%s): %s", name, exc)
            continue
    # What is on disk but unclaimed. A manifest declaring nothing while phase files sit beside
    # it is not "a different workflow shape" -- it is a manifest that has lost its own run, and
    # the distinction is what lets a scorer fail it instead of shrugging.
    # Compared as base names on both sides. Differencing `Path.name` against the raw manifest
    # string reported a declared `./phase-1.md` as undeclared, and a scorer acting on that
    # produced FAIL 0.0 where the honest answer was UNKNOWN -- the false 0% this scorer
    # promises never to produce, reintroduced by a string comparison. Found in review.
    # Relative paths on both sides, and nothing resolved. A manifest entry that is absolute
    # or climbs out simply will not match — which is harmless here, because a plan that names
    # any file at all is not the shape this finding fires on.
    declared = {PurePosixPath(phase["file"].replace("\\", "/")).as_posix()
                for phase in phases
                if isinstance(phase.get("file"), str) and phase["file"]}
    # Deliberately unbounded, after a capped version was tried and reverted. Truncating the
    # list corrupted every count derived from it — the finding said "(+97 more)" and the
    # coverage line "100" for 105 orphans, with the real total only in a log nobody reads back
    # — and it did not bound the walk either, since `sorted` materialises the whole result
    # before any slice. Determinism is worth more here than a bound that buys nothing: this is
    # a directory the caller pointed `--scenarios-dir` at, the same shape as every other corpus
    # scan in this repository. Raised in review, and the cure was worse than the complaint.
    undeclared = sorted(
        path.relative_to(run_dir).as_posix() for path in sorted(run_dir.rglob("phase-*.md"))
        if path.is_file() and path.relative_to(run_dir).as_posix() not in declared)
    return RunArtifacts(plan_meta=plan_meta, phases=phases, phase_texts=phase_texts,
                        undeclared_phase_files=undeclared)
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-load-run


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-run-scenario
#: Sentinel for run_scenario's optional pre-loaded run — ``None`` is a valid "unreadable run",
#: so it cannot double as "not supplied".
_NO_PRELOAD = object()


def run_scenario(scenario: Scenario, scorers: List[Scorer],
                 run: "object" = _NO_PRELOAD) -> ScenarioResult:
    """Load one scenario's run and apply every scorer to it.

    A scorer that raises degrades to UNKNOWN for that scenario (with a warning) rather
    than sinking the whole suite — the seam must tolerate a misbehaving future scorer.
    A caller may pass an already-loaded ``run`` (``_NO_PRELOAD`` means "load it here") so the
    report and calibration can share one disk snapshot instead of reading twice.
    """
    if run is _NO_PRELOAD:
        run = load_run(scenario.run_dir)
    results: List[ScorerResult] = []
    for scorer in scorers:
        try:
            results.append(scorer.score(run, scenario))
        # A plugged-in scorer must not crash the whole run — degrade it to UNKNOWN.
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("eval: scorer %s raised on scenario %s: %s",
                           getattr(scorer, "name", "?"), scenario.id, exc)
            results.append(ScorerResult(
                getattr(scorer, "name", "unknown-scorer"),
                getattr(scorer, "kind", ScorerKind.ADVISORY),
                VERDICT_UNKNOWN, None, [f"scorer raised: {exc}"], "scorer error"))
    return ScenarioResult(scenario.id, scenario.workflow, results, scenario.expect)
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-run-scenario


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-load-cases
def load_cases(root: Path) -> List[Tuple[Scenario, Optional[RunArtifacts]]]:
    """Load every ``(scenario, run)`` once — the single disk snapshot the report and calibration
    share, so the two can never measure different versions of the same files."""
    return [(scenario, load_run(scenario.run_dir)) for scenario in load_scenarios(root)]
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-load-cases


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-run-suite
def run_suite_over(cases: List[Tuple[Scenario, Optional[RunArtifacts]]],
                   scorers: List[Scorer]) -> EvalReport:
    """Run pre-loaded ``(scenario, run)`` pairs through ``scorers`` — no disk read here."""
    return EvalReport([run_scenario(scenario, scorers, run) for scenario, run in cases])


def run_suite(root: Path, scorers: List[Scorer]) -> EvalReport:
    """Run every scenario under ``root`` through ``scorers`` and aggregate (loads from disk)."""
    return run_suite_over(load_cases(root), scorers)
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-run-suite


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-compliance
def _scenario_compliance(scenario_result: ScenarioResult) -> Tuple[int, int, Optional[float]]:
    """Deterministic (passed, total, fraction|None) for one scenario. UNKNOWN excluded."""
    passed = 0
    failed = 0
    for result in scenario_result.results:
        if result.kind is ScorerKind.DETERMINISTIC:
            if result.verdict == VERDICT_PASS:
                passed += 1
            elif result.verdict == VERDICT_FAIL:
                failed += 1
    total = passed + failed
    return passed, total, (round(passed / total, 4) if total else None)


def structural_compliance(report: EvalReport) -> Optional[float]:
    """Aggregate deterministic pass ratio across the suite. ``None`` when nothing scored.

    Only deterministic verdicts count — this is the number gating reads, so an advisory
    scorer can never affect it.
    """
    passed = 0
    total = 0
    for scenario_result in report.scenarios:
        scenario_passed, scenario_total, _ = _scenario_compliance(scenario_result)
        passed += scenario_passed
        total += scenario_total
    return round(passed / total, 4) if total else None
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-compliance


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-oracle
#: What a scenario's declared `expect` claims the deterministic verdict will be. `unknown`
#: makes no claim and is never a mismatch.
_ORACLE_EXPECTS = {"compliant": VERDICT_PASS, "non_compliant": VERDICT_FAIL}


def _deterministic_verdict(verdicts: Iterable[str]) -> str:
    """The one verdict a scenario's deterministic scorers amount to.

    FAIL wins over PASS, and anything else — including no deterministic result at all — is
    UNKNOWN. Named rather than written inline in both comparison functions: it was a nested
    conditional duplicated in two places, which is how the two came to treat the empty case
    differently in the first place.
    """
    seen = set(verdicts)
    if VERDICT_FAIL in seen:
        return VERDICT_FAIL
    if VERDICT_PASS in seen:
        return VERDICT_PASS
    return VERDICT_UNKNOWN


def oracle_mismatches(scenario_results: List[ScenarioResult]) -> List[str]:
    """Scenarios whose declared oracle disagrees with what the deterministic scorers said.

    Every scenario declares `expect` in its descriptor, and that value travelled all the way
    into the JSON report under a comment reading "surfaced for declared-vs-actual" -- while
    nothing anywhere performed the comparison. A fixture asserting it is non-compliant could
    therefore come back `UNKNOWN`, be dropped from the denominator, and leave no trace: the
    suite's own statement of what should happen never met the result.

    `UNKNOWN` counts as a mismatch against either claim, deliberately. A scenario written to
    demonstrate a failure, which the scorer then cannot assess, is exactly the case that
    hides -- the suite looks smaller rather than worse. `expect = "unknown"` claims nothing
    and so can never mismatch.
    """
    mismatches: List[str] = []
    for scenario_result in scenario_results:
        wanted = _ORACLE_EXPECTS.get(scenario_result.expect)
        if wanted is None:
            continue
        verdicts = [r.verdict for r in scenario_result.results
                    if r.kind is ScorerKind.DETERMINISTIC]
        # No deterministic result at all resolves to UNKNOWN rather than being skipped. The
        # first version `continue`d here, which contradicted this docstring's own policy that
        # UNKNOWN counts against either claim — and skipped exactly the scenario that
        # produced nothing to judge. Found in review.
        got = _deterministic_verdict(verdicts)
        if got != wanted:
            mismatches.append(
                f"{scenario_result.scenario_id}: declared {scenario_result.expect!r} "
                f"(expects {wanted}) but scored {got}")
    return sorted(mismatches)


def gating_oracle_mismatches(scenario_results: List[ScenarioResult]) -> List[str]:
    """The subset of `oracle_mismatches` that may fail a build: **definite disagreements only**.

    A scenario that scored `UNKNOWN` against a claim is reported, because it is the shape that
    hides — but it must not gate. This module's contract is that *unscoreable is never a
    failure*: a run nobody could assess is not evidence of a defect, and `run_scenario`
    deliberately degrades a raising scorer to `UNKNOWN` so that one broken plug-in cannot sink
    a whole suite.

    The first version of this gated on every mismatch, `UNKNOWN` included. A suite of one
    healthy scenario and one unreadable `plan.toml` then printed "structural compliance: 100%"
    and exited 2 — the contract inverted, by a change whose whole subject was how unscoreable
    runs are treated. Found in review; the reporting and the gating are now separate questions.
    """
    definite = {VERDICT_PASS, VERDICT_FAIL}
    gating: List[str] = []
    for scenario_result in scenario_results:
        wanted = _ORACLE_EXPECTS.get(scenario_result.expect)
        if wanted is None:
            continue
        verdicts = {r.verdict for r in scenario_result.results
                    if r.kind is ScorerKind.DETERMINISTIC}
        got = _deterministic_verdict(verdicts)
        if got in definite and got != wanted:
            gating.append(f"{scenario_result.scenario_id}: declared "
                          f"{scenario_result.expect!r} (expects {wanted}) but scored {got}")
    return sorted(gating)
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-oracle


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-gate
def gate_exit_code(compliance: Optional[float], check: bool, min_compliance: float) -> int:
    """Opt-in gating: exit 2 only under ``check`` when compliance is below the floor.

    Gating is off by default (running eval reports, it does not fail a build unless
    asked). Advisory verdicts never reach here because they are excluded from ``compliance``.

    Nothing-scoreable (``compliance is None`` — an empty suite, or one whose every scenario
    was unscoreable) fails a ``check`` that demanded a positive floor: a gate asked to enforce
    a minimum and given nothing to measure has failed to assess, not passed — the rule
    ``spec-coverage`` already applies, and the "cannot assess is not PASS" principle (HYP-2925,
    and the empty-codebase ruling). A non-positive floor demands nothing, so a suite that
    scored nothing still clears it.
    """
    if not check:
        return 0
    if compliance is None:
        return 2 if min_compliance > 0 else 0
    return 2 if compliance < min_compliance else 0
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-gate


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-report-json
def report_to_dict(report: EvalReport) -> Dict[str, object]:
    """Serialise a report: per-scenario compliance, a failing-check histogram, and an
    UNKNOWN-aware, coverage-stating summary."""
    scored = 0
    unknown = 0
    agg_passed = 0                             # accumulate the aggregate here to avoid a 2nd pass
    agg_total = 0
    scorers_seen: Dict[str, str] = {}          # name -> kind, so coverage reflects what ran
    failing: Dict[str, int] = {}               # deterministic FAILs per scorer (histogram)
    per_scenario: List[Dict[str, object]] = []
    for scenario_result in report.scenarios:
        results_json: List[Dict[str, object]] = []
        for result in scenario_result.results:
            scorers_seen[result.scorer] = result.kind.value
            if result.verdict == VERDICT_UNKNOWN:
                unknown += 1
            else:
                scored += 1
            if result.kind is ScorerKind.DETERMINISTIC and result.verdict == VERDICT_FAIL:
                failing[result.scorer] = failing.get(result.scorer, 0) + 1
            results_json.append({
                "scorer": result.scorer,
                "kind": result.kind.value,
                "verdict": result.verdict,
                "score_pct": result.score_pct,
                "findings": result.findings,
                "coverage": result.coverage,
            })
        scenario_passed, scenario_total, scenario_compliance = _scenario_compliance(scenario_result)
        agg_passed += scenario_passed
        agg_total += scenario_total
        per_scenario.append({
            "scenario": scenario_result.scenario_id,
            "workflow": scenario_result.workflow,
            "expect": scenario_result.expect,
            "compliance": scenario_compliance,
            "passed": scenario_passed,
            "total": scenario_total,
            "results": results_json,
        })
    coverage = "; ".join(f"{name} ({kind})" for name, kind in sorted(scorers_seen.items())) \
        or "no scorers ran"
    return {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "scenarios": len(report.scenarios),
            "results": scored + unknown,   # scored/unknown count scorer-results, not scenarios
            "scored": scored,
            "unknown": unknown,
            "structural_compliance": round(agg_passed / agg_total, 4) if agg_total else None,
            "coverage": coverage,
        },
        "failing_checks": dict(sorted(failing.items(), key=lambda item: item[1], reverse=True)),
        "per_scenario": per_scenario,
    }
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-report-json


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-diff-reports
def _aggregate_baseline(baseline_summary: object) -> Optional[float]:
    """The baseline's overall compliance, or ``None`` when it is not a usable number."""
    if not isinstance(baseline_summary, dict):
        return None
    value = baseline_summary.get("structural_compliance")
    return value if _usable_baseline(value) else None


def _usable_baseline(value: object) -> bool:
    """Whether a baseline number can be compared against at all.

    Excludes bool (an int subclass) and the non-finite floats, which survive an
    ``isinstance`` check and then fail every comparison silently. Shared by the
    per-scenario values and the aggregate, which were hardened separately and so
    disagreed about what counted as a number (#234 review).
    """
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-fence-delim
def fence_delim(stripped: str) -> Optional[Tuple[str, int]]:
    """A Markdown fenced-code delimiter -- three or more backticks or tildes -- as
    ``(char, run_length)``, else ``None``.

    Here, in the module both scorers already import, rather than in either of them: the
    CommonMark closer rule (same character, run at least as long as the opener, nothing
    but whitespace after) was implemented twice, independently, once in
    ``eval_judge._split_sections`` and once in ``eval_structural._prose_headings``. Two
    copies of one rule drift, and the second copy was written without noticing the first
    (constructorfabric/studio#234 review).
    """
    for char in ("`", "~"):
        if stripped.startswith(char * 3):
            return char, len(stripped) - len(stripped.lstrip(char))
    return None


def fence_closes(delim: Tuple[str, int], opener: Tuple[str, int], stripped: str) -> bool:
    """Whether ``delim`` closes ``opener``: same character, at least as long, and nothing
    but whitespace after the run."""
    return (delim[0] == opener[0] and delim[1] >= opener[1]
            and not stripped[delim[1]:].strip())
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-fence-delim


def diff_reports(report: EvalReport, baseline: Dict[str, object]) -> Dict[str, object]:
    """Per-scenario compliance change vs a baseline report, bucketed.

    A scenario whose compliance falls, **or which was scoreable in the baseline and is now
    unscoreable while still in the suite (its run broke)**, is a regression and gates
    ``--check``. One that scores for the first time or rises is not. A scenario that is
    gone from the suite entirely is surfaced in ``no_longer_scoreable`` but is **not** a
    regression — removing an obsolete scenario should not fail a build. A baseline whose
    per-scenario compliance is missing or non-numeric is treated as "no prior value" (no
    comparison), never a crash. ``has_regression`` reflects only ``regressed``.
    """
    rows = baseline.get("per_scenario", [])
    # Only string scenario ids: a non-string/unhashable id (e.g. a list) would raise when
    # used as a dict key and never matches a real scenario anyway.
    prev = ({row["scenario"]: row.get("compliance")
             for row in rows
             if isinstance(row, dict) and isinstance(row.get("scenario"), str)}
            if isinstance(rows, list) else {})
    regressed: List[Dict[str, object]] = []
    improved: List[Dict[str, object]] = []
    newly_scoreable: List[Dict[str, object]] = []
    no_longer_scoreable: List[Dict[str, object]] = []
    seen = set()
    for scenario_result in report.scenarios:
        scenario_id = scenario_result.scenario_id
        seen.add(scenario_id)
        _, _, now = _scenario_compliance(scenario_result)
        before = prev.get(scenario_id)
        # missing / non-numeric baseline → no comparison; exclude bool (a subclass of int),
        # and NaN/inf, which are floats and so survive the isinstance check. NaN then
        # disappears a second time: every comparison against it is False, so the scenario
        # joined neither `regressed` nor `improved` and `has_regression` stayed False even
        # for a drop to zero. A corrupt or hand-edited baseline switched the gate off and
        # said nothing.
        if not _usable_baseline(before):
            before = None
        if before is None:
            if now is not None:
                newly_scoreable.append({"scenario": scenario_id, "to": now})
        elif now is None:
            # still in the suite but no longer scoreable (its run broke) — a regression.
            regressed.append({"scenario": scenario_id, "from": before, "to": None})
        elif now < before:
            regressed.append({"scenario": scenario_id, "from": before, "to": now})
        elif now > before:
            improved.append({"scenario": scenario_id, "from": before, "to": now})
    for scenario_id, before in prev.items():
        if scenario_id not in seen and _usable_baseline(before):
            # gone from the suite entirely — surfaced, but not a gate-worthy regression.
            no_longer_scoreable.append({"scenario": scenario_id, "from": before})
    baseline_summary = baseline.get("summary", {})
    return {
        "regressed": regressed,
        "improved": improved,
        "newly_scoreable": newly_scoreable,
        "no_longer_scoreable": no_longer_scoreable,
        # Guarded like the per-scenario values above: a corrupt baseline's aggregate is
        # a number the report *shows a reader*, and NaN rendered beside a real
        # `aggregate_after` reads as a measurement rather than as missing data.
        "aggregate_before": _aggregate_baseline(baseline_summary),
        "aggregate_after": structural_compliance(report),
        "has_regression": bool(regressed),   # removals are surfaced, not gated
    }
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-diff-reports
