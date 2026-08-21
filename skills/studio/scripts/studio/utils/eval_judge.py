"""Advisory LLM-judge for the workflow eval-harness.

The **advisory** half of the eval-harness, plugged into the same ``Scorer`` seam the scaffold
(:mod:`studio.utils.eval_harness`) defines. It reads a completed run and opines on the one
thing the deterministic structural scorer cannot measure: **did the run follow its workflow's
rules?** Its verdict is ``ADVISORY`` — the runner forbids it from touching the exit code — and
its trustworthiness is **measured against a human-authored gold set**, never asserted.

Design commitments:

* **Seam, not transport.** Studio is stdlib-only, and the engine makes no model calls. So the
  harness owns the *prompt* and the *parsing* (both pure and unit-testable), and the model
  call is supplied by the host/agent through a pluggable ``JudgeFn``. With no ``judge_fn``
  wired, the judge returns ``UNKNOWN`` and ``cfs eval`` still runs and gates deterministically
  — a model can never sit inside a gate.
* **Measured, not asserted.** :func:`calibrate` runs the judge repeatedly over gold-backed
  scenarios and reports **accuracy** (agreement with the human label) and **consistency**
  (run-to-run variance). These are judge-quality metrics, never folded into structural
  compliance.
* **Coverage is derived.** Judge coverage is the set of scenarios that actually carry a gold
  set; a verdict on a scenario without gold is labelled *unvalidated advisory*. No figure ever
  reads as system-wide.

This module contains no model client. The real model call is provided out-of-tree.

@cpt-algo:cpt-studio-algo-eval-judge:p1
"""
# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-imports
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple, runtime_checkable

from .eval_harness import (RunArtifacts, Scenario, ScorerKind, ScorerResult,
                           VERDICT_FAIL, VERDICT_PASS, VERDICT_UNKNOWN)

logger = logging.getLogger(__name__)

#: The two human labels a gold entry may carry, and the judge verdicts they map to.
GOLD_COMPLIANT = "compliant"
GOLD_NON_COMPLIANT = "non_compliant"
_VERDICT_BY_LABEL = {GOLD_COMPLIANT: VERDICT_PASS, GOLD_NON_COMPLIANT: VERDICT_FAIL}

#: Cap on the run-evidence handed to the judge — bounded so the prompt stays deterministic
#: and small; the judge assesses compliance from this, not from the rule declarations.
_EVIDENCE_CAP = 4000
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-imports


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-datamodel
@dataclass
class Gold:
    """A human-authored label for one run — the ground truth calibration compares against."""

    verdict: str                                 # compliant | non_compliant
    rationale: str = ""
    rules_assessed: List[int] = field(default_factory=list)


@dataclass
class JudgeRequest:
    """The deterministic input handed to a ``JudgeFn`` — the harness builds this, no model call."""

    workflow: str
    rules: List[str]              # the `## Rules` prose extracted from the run, in phase order
    evidence: str                 # bounded phase-body content (rules removed) — what was *done*
    prompt: str                   # the full assembled prompt (deterministic), incl. a run summary


@dataclass
class JudgeReply:
    """A model's structured answer, parsed back by the harness."""

    verdict: str                  # compliant | non_compliant | unknown
    rationale: str = ""


@runtime_checkable
class JudgeFn(Protocol):  # pylint: disable=too-few-public-methods
    """The seam the host/agent supplies: turn a ``JudgeRequest`` into a ``JudgeReply``.

    The harness never implements this with a real model — that is provided out-of-tree. In
    tests and calibration it is a deterministic stub.
    """

    def __call__(self, request: JudgeRequest) -> JudgeReply:
        """Return the model's verdict on ``request``."""  # pragma: no cover
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-datamodel


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-prompt
def _split_sections(text: str) -> "Tuple[List[str], List[str]]":
    """Partition a phase body into ``(rules_lines, other_lines)`` by ``## Rules`` heading.

    Line-based on purpose — no lazy/lookahead regex (which SonarCloud flagged as super-linear /
    ambiguous). This keeps rule *declarations* apart from the rest of the body so the judge (and
    the reference stub) never mistake a rule's own wording for evidence of a violation.
    """
    rules: List[str] = []
    other: List[str] = []
    in_rules = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_rules = stripped[3:].strip().lower().startswith("rules")
            if in_rules:
                continue          # drop the heading line itself; keep other headings as context
        (rules if in_rules else other).append(line)
    return rules, other


def _extract_rules(run: RunArtifacts) -> List[str]:
    """The non-empty ``## Rules`` prose of each phase body, in filename order. Deterministic."""
    out: List[str] = []
    for name in sorted(run.phase_texts):
        body = "\n".join(_split_sections(run.phase_texts[name])[0]).strip()
        if body:
            out.append(body)
    return out


def _run_evidence(run: RunArtifacts) -> str:
    """Bounded, deterministic evidence of what the run actually contains — each phase body with
    its ``## Rules`` declaration removed — so compliance is judged from the work, not the rules.

    The ``_EVIDENCE_CAP`` budget is split **per phase**, not applied to the concatenation, so a
    long first phase can never swallow the whole budget and hide a later phase's violation.
    A phase trimmed to fit is marked ``[…truncated]`` so the judge sees that evidence was cut.
    """
    names = sorted(run.phase_texts)
    if not names:
        return ""
    per_phase = max(400, _EVIDENCE_CAP // len(names))
    chunks: List[str] = []
    for name in names:
        other = "\n".join(_split_sections(run.phase_texts[name])[1]).strip()
        if not other:
            continue
        if len(other) > per_phase:
            other = other[:per_phase].rstrip() + "\n[…truncated]"
        chunks.append(f"### {name}\n{other}")
    return "\n\n".join(chunks)


def _run_summary(run: RunArtifacts) -> str:
    """A stable one-line-per-phase digest of the run — no model call, order-deterministic."""
    task = str(run.plan_meta.get("task", "")) if isinstance(run.plan_meta, dict) else ""
    lines = [f"task: {task}", f"phases: {len(run.phases)}"]
    for phase in run.phases:
        if isinstance(phase, dict):
            lines.append(f"  - phase {phase.get('number')}: {phase.get('file')}")
    return "\n".join(lines)
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-prompt


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-request
def build_judge_request(run: RunArtifacts, scenario: Scenario) -> JudgeRequest:
    """Assemble the deterministic judge prompt for ``run`` — a pure function, no model call."""
    rules = _extract_rules(run)
    summary = _run_summary(run)
    evidence = _run_evidence(run)
    rules_block = "\n".join(f"- {rule}" for rule in rules) or "(no rules declared)"
    prompt = (
        f"You are judging whether a completed '{scenario.workflow}' workflow run followed its "
        "own rules. This is an advisory judgement; it never gates a build.\n\n"
        f"RULES the run was expected to follow:\n{rules_block}\n\n"
        f"THE RUN (summary):\n{summary}\n\n"
        f"EVIDENCE — what the run actually contains (judge compliance from this, not the "
        f"rules):\n{evidence or '(no evidence beyond the plan)'}\n\n"
        "Answer with a verdict of 'compliant' or 'non_compliant' and a one-line rationale.")
    return JudgeRequest(workflow=scenario.workflow, rules=rules, evidence=evidence, prompt=prompt)


def _reply_to_verdict(reply: object) -> str:
    """Map a reply to a scaffold verdict; anything unrecognised — including ``None`` or a
    non-``JudgeReply`` object a host might return — is UNKNOWN, never an AttributeError."""
    verdict = (getattr(reply, "verdict", "") or "").strip().lower()
    return _VERDICT_BY_LABEL.get(verdict, VERDICT_UNKNOWN)
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-request


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-gold
def load_gold(gold_path: Optional[Path]) -> Optional[Gold]:
    """Read a scenario's ``gold.toml`` ``[gold]`` label, or ``None`` when absent/malformed.

    Never raises: a missing or unreadable gold file simply means the scenario is not
    gold-backed, so its judge verdict is unvalidated rather than a crash.
    """
    if gold_path is None:
        return None
    try:
        with open(gold_path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("eval: gold file not usable (%s): %s", gold_path, exc)
        return None
    section = data.get("gold")
    if not isinstance(section, dict):
        logger.warning("eval: gold file missing a [gold] table: %s", gold_path)
        return None
    verdict = section.get("verdict")
    if verdict not in (GOLD_COMPLIANT, GOLD_NON_COMPLIANT):
        logger.warning("eval: gold [gold].verdict must be compliant|non_compliant: %s", gold_path)
        return None
    rules = section.get("rules_assessed")
    rules = [n for n in rules if isinstance(n, int)] if isinstance(rules, list) else []
    return Gold(verdict=verdict, rationale=str(section.get("rationale", "")), rules_assessed=rules)
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-gold


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-scorer
class AdvisoryJudge:  # pylint: disable=too-few-public-methods
    """Score a run's rule-compliance via an injected model. ADVISORY: it can never gate.

    ``judge_fn`` is supplied by the host/agent (the model call lives out-of-tree). With no
    ``judge_fn`` the judge returns UNKNOWN, so the harness runs without a model.
    """

    name = "rules-judge"
    kind = ScorerKind.ADVISORY

    def __init__(self, judge_fn: Optional[JudgeFn] = None) -> None:
        self._judge_fn = judge_fn

    def score(self, run: Optional[RunArtifacts], scenario: Scenario) -> ScorerResult:
        """Advisory PASS/FAIL/UNKNOWN on rule-compliance; never contributes to the exit code."""
        if run is None:
            return self._result(VERDICT_UNKNOWN, ["run artifacts could not be loaded"],
                                "unscoreable: no readable run", scenario)
        if self._judge_fn is None:
            return self._result(VERDICT_UNKNOWN, ["no judge model wired (advisory)"],
                                "no judge_fn: model supplied out-of-tree", scenario)
        request = build_judge_request(run, scenario)
        try:
            reply = self._judge_fn(request)
        # A misbehaving injected judge must degrade to UNKNOWN, never sink the run.
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("eval: judge_fn raised on scenario %s: %s", scenario.id, exc)
            return self._result(VERDICT_UNKNOWN, [f"judge_fn raised: {exc}"], "judge error", scenario)
        # Parse defensively: a host may return None or a non-JudgeReply — that is UNKNOWN, not
        # an AttributeError (calibrate() calls score() directly, so a raise would abort it).
        verdict = _reply_to_verdict(reply)
        rationale = getattr(reply, "rationale", "") or ""
        findings = [rationale] if rationale else []
        return self._result(verdict, findings, f"{len(request.rules)} rule(s) assessed", scenario)

    def _result(self, verdict: str, findings: List[str], coverage: str,
                scenario: Scenario) -> ScorerResult:
        """Wrap a verdict as an ADVISORY result, labelling validated vs unvalidated coverage.

        "Validated" means the scenario carries a gold set that actually *loads* — a missing or
        malformed ``gold.toml`` is unvalidated, not silently "gold-backed".
        """
        validated = scenario.gold_path is not None and load_gold(scenario.gold_path) is not None
        note = "gold-backed (validated)" if validated else "no valid gold (unvalidated advisory)"
        return ScorerResult(self.name, self.kind, verdict, None, findings, f"{coverage}; {note}")
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-scorer


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-stub
#: Phrases that make the reference stub call a run non-compliant. Deliberately shallow — the
#: stub is a wiring aid, not a judgement.
_STUB_NEGATIVE_MARKERS = ("violat", "forbidden", "must not", "broke", "ignored")


def reference_stub_judge(request: JudgeRequest) -> JudgeReply:
    """A deterministic keyword ``JudgeFn`` — **not a real model.**

    Ships so tests and ``cfs eval --calibrate`` can exercise the calibration machinery with no
    model wired. It scans only the **evidence** (what the run did) for a negative marker — never
    the rule declarations, so a rule that merely *says* "must not …" is not read as a violation.
    A real judge_fn is supplied out-of-tree and replaces it.
    """
    haystack = request.evidence.lower()
    if any(marker in haystack for marker in _STUB_NEGATIVE_MARKERS):
        return JudgeReply(GOLD_NON_COMPLIANT, "reference stub: negative marker in evidence")
    return JudgeReply(GOLD_COMPLIANT, "reference stub: no negative marker in evidence")
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-stub


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-calibrate
@dataclass
class Calibration:
    """The judge's measured quality over the gold-backed scenarios."""

    accuracy: Optional[float]           # fraction whose majority verdict matches the human label
    consistency: Optional[float]        # mean run-to-run agreement across K runs
    covered: List[str]                  # scenario ids that carry a gold set
    runs_per_scenario: int
    per_scenario: List[Dict[str, object]] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)   # gold-backed but unscoreable (run None)
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-calibrate


# @cpt-begin:cpt-studio-algo-eval-judge:p1:inst-judge-calibrate-run
def _majority(verdicts: List[str]) -> Tuple[str, int]:
    """The most common verdict and its count (ties resolve to the first-seen, deterministic)."""
    counts: Dict[str, int] = {}
    for verdict in verdicts:
        counts[verdict] = counts.get(verdict, 0) + 1
    best = max(verdicts, key=lambda v: counts[v]) if verdicts else VERDICT_UNKNOWN
    return best, counts.get(best, 0)


def _score_case(judge: AdvisoryJudge, scenario: Scenario, run: Optional[RunArtifacts],
                gold: Gold, runs: int) -> Tuple[bool, float, Dict[str, object]]:
    """Judge one gold-backed case ``runs`` times → ``(matched, consistency, report_row)``."""
    verdicts = [judge.score(run, scenario).verdict for _ in range(runs)]
    majority, count = _majority(verdicts)
    expected = _VERDICT_BY_LABEL.get(gold.verdict, VERDICT_UNKNOWN)
    matched = majority == expected
    row = {"scenario": scenario.id, "expected": expected, "majority": majority,
           "matched": matched, "consistency": round(count / runs, 4)}
    return matched, count / runs, row


def calibrate(cases: List[Tuple[Scenario, Optional[RunArtifacts], Gold]],
              judge_fn: JudgeFn, runs: int = 3) -> Calibration:
    """Run the judge ``runs`` times over each gold-backed case; report accuracy + consistency.

    ``accuracy`` is agreement of the majority verdict with the human label; ``consistency`` is
    the mean fraction of runs that landed on that majority (run-to-run stability). Both are
    ``None`` when there is nothing scoreable to measure — never a false 0. A case whose run
    could not be loaded (``run is None``) is a *run-loading* failure, not a judge failure, so it
    is **excluded** from accuracy/consistency (and reported in ``excluded``) — it never counts
    as a judge mismatch. ``covered`` still lists every gold-backed scenario.
    """
    runs = max(1, runs)
    judge = AdvisoryJudge(judge_fn)
    scoreable = [(scenario, run, gold) for scenario, run, gold in cases if run is not None]
    excluded = [scenario.id for scenario, run, _ in cases if run is None]
    rows = [_score_case(judge, scenario, run, gold, runs) for scenario, run, gold in scoreable]
    total = len(scoreable)
    return Calibration(
        accuracy=round(sum(1 for matched, _, _ in rows if matched) / total, 4) if total else None,
        consistency=round(sum(c for _, c, _ in rows) / total, 4) if total else None,
        covered=[scenario.id for scenario, _, _ in cases],
        runs_per_scenario=runs, per_scenario=[row for _, _, row in rows], excluded=excluded)
# @cpt-end:cpt-studio-algo-eval-judge:p1:inst-judge-calibrate-run
