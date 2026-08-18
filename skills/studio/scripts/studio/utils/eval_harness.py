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
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

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


@dataclass
class ScenarioResult:
    """All scorers' results for one scenario."""

    scenario_id: str
    workflow: str
    results: List[ScorerResult]
    expect: str = ""     # the scenario's declared oracle, surfaced for declared-vs-actual


@dataclass
class EvalReport:
    """The outcome of running a suite: per-scenario results."""

    scenarios: List[ScenarioResult]


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
        """PASS if every declared phase is present, FAIL if any missing, UNKNOWN if unloadable."""
        if run is None:
            return ScorerResult(
                self.name, self.kind, VERDICT_UNKNOWN, None,
                ["run artifacts could not be loaded"], "unscoreable: no readable plan.toml")
        if not run.phases:
            return ScorerResult(
                self.name, self.kind, VERDICT_UNKNOWN, None,
                ["run declares no phases"], "unscoreable: nothing to assess")
        # phases are normalised to dicts by load_run; a phase with no file is a benign
        # skip (matching load_run), not a missing file.
        missing = [
            phase["file"]
            for phase in run.phases
            if isinstance(phase.get("file"), str) and phase["file"]
            and phase["file"] not in run.phase_texts
        ]
        if missing:
            return ScorerResult(
                self.name, self.kind, VERDICT_FAIL, 0.0,
                [f"declared phase file missing: {name}" for name in missing],
                f"{len(run.phases)} declared phases")
        return ScorerResult(
            self.name, self.kind, VERDICT_PASS, 100.0, [],
            f"{len(run.phases)} declared phases, all present")
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-reference-scorer


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-load-scenarios
def load_scenarios(root: Path) -> List[Scenario]:
    """Discover scenarios under ``root`` by globbing ``*/scenario.toml``.

    A malformed or id-less descriptor is skipped with a warning, never raised, and a
    ``run_dir``/gold path that escapes the scenario directory (absolute or ``..``) is
    rejected — one bad or unsafe scenario must not sink the whole suite.
    """
    scenarios: List[Scenario] = []
    for descriptor in sorted(root.glob("*/scenario.toml")):
        try:
            with open(descriptor, "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            logger.warning("eval: skipping unreadable scenario descriptor %s: %s", descriptor, exc)
            continue
        section = data.get("scenario", {})
        scenario_id = section.get("id")
        if not scenario_id:
            logger.warning("eval: scenario descriptor missing [scenario].id: %s", descriptor)
            continue
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
            expect=str(section.get("expect", "unknown")),
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
        target = run_dir / name
        if not target.resolve().is_relative_to(run_dir.resolve()):
            # A phase file that escapes the run dir (absolute or ../) is never read.
            logger.warning("eval: phase file escapes the run dir, skipping: %s", name)
            continue
        try:
            phase_texts[name] = target.read_text(encoding="utf-8")
        except OSError as exc:
            # Absent/unreadable phase → left out of phase_texts so a scorer flags it.
            logger.debug("eval: declared phase file unreadable (%s): %s", name, exc)
            continue
    return RunArtifacts(plan_meta=plan_meta, phases=phases, phase_texts=phase_texts)
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-load-run


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-run-scenario
def run_scenario(scenario: Scenario, scorers: List[Scorer]) -> ScenarioResult:
    """Load one scenario's run and apply every scorer to it.

    A scorer that raises degrades to UNKNOWN for that scenario (with a warning) rather
    than sinking the whole suite — the seam must tolerate a misbehaving future scorer.
    """
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


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-run-suite
def run_suite(root: Path, scorers: List[Scorer]) -> EvalReport:
    """Run every scenario under ``root`` through ``scorers`` and aggregate."""
    return EvalReport([run_scenario(scenario, scorers) for scenario in load_scenarios(root)])
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


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-gate
def gate_exit_code(compliance: Optional[float], check: bool, min_compliance: float) -> int:
    """Opt-in gating: exit 2 only under ``check`` when compliance is below the floor.

    Gating is off by default (running eval reports, it does not fail a build unless
    asked). Nothing-scoreable (``compliance is None``) never fails. Advisory verdicts
    never reach here because they are excluded from ``compliance``.
    """
    if check and compliance is not None and compliance < min_compliance:
        return 2
    return 0
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-gate


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-report-json
def report_to_dict(report: EvalReport) -> Dict[str, object]:
    """Serialise a report: per-scenario compliance, a failing-check histogram, and an
    UNKNOWN-aware, coverage-stating summary."""
    scored = 0
    unknown = 0
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
            "structural_compliance": structural_compliance(report),
            "coverage": coverage,
        },
        "failing_checks": dict(sorted(failing.items(), key=lambda item: item[1], reverse=True)),
        "per_scenario": per_scenario,
    }
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-report-json


# @cpt-begin:cpt-studio-algo-eval-harness-run:p1:inst-diff-reports
def diff_reports(report: EvalReport, baseline: Dict[str, object]) -> Dict[str, object]:
    """Per-scenario compliance change vs a baseline report, bucketed.

    Distinguishes improvements from regressions (unlike a flat verdict diff): a scenario
    dropping out of scoring, or its compliance falling, is a regression; a scenario
    scoring for the first time or rising is not. ``has_regression`` is the gate-worthy bit.
    """
    prev = {row.get("scenario"): row.get("compliance")
            for row in baseline.get("per_scenario", [])}
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
        if scenario_id not in prev or before is None:
            if now is not None:
                newly_scoreable.append({"scenario": scenario_id, "to": now})
        elif now is None:
            no_longer_scoreable.append({"scenario": scenario_id, "from": before})
        elif now < before:
            regressed.append({"scenario": scenario_id, "from": before, "to": now})
        elif now > before:
            improved.append({"scenario": scenario_id, "from": before, "to": now})
    for scenario_id, before in prev.items():
        if scenario_id not in seen and before is not None:
            no_longer_scoreable.append({"scenario": scenario_id, "from": before})
    return {
        "regressed": regressed,
        "improved": improved,
        "newly_scoreable": newly_scoreable,
        "no_longer_scoreable": no_longer_scoreable,
        "aggregate_before": baseline.get("summary", {}).get("structural_compliance"),
        "aggregate_after": structural_compliance(report),
        "has_regression": bool(regressed or no_longer_scoreable),
    }
# @cpt-end:cpt-studio-algo-eval-harness-run:p1:inst-diff-reports
